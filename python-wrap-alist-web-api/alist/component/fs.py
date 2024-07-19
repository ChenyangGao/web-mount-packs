#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["AttrDict", "PathType", "AlistPath", "AlistFileSystem"]

import errno

from asyncio import get_running_loop, run, TaskGroup
from collections import deque
from collections.abc import (
    AsyncIterable, AsyncIterator, Awaitable, Callable, Coroutine, ItemsView, 
    Iterable, Iterator, KeysView, Mapping, ValuesView, 
)
from datetime import datetime
from functools import cached_property, partial, update_wrapper
from hashlib import sha256
from http.cookiejar import Cookie, CookieJar
from inspect import isawaitable
from io import BytesIO, TextIOWrapper, UnsupportedOperation
from itertools import chain, pairwise
from json import loads
from mimetypes import guess_type
from os import (
    fsdecode, fspath, fstat, lstat, makedirs, remove, scandir, stat_result, 
    path as ospath, DirEntry, PathLike, 
)
from pathlib import Path
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split as splitpath, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError, COPY_BUFSIZE # type: ignore
from stat import S_IFDIR, S_IFREG
from typing import cast, overload, Any, IO, Literal, Never, Optional, Self, TypeAlias
from types import MappingProxyType, MethodType
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4
from warnings import filterwarnings, warn

from dateutil.parser import parse as dt_parse
from download import AsyncDownloadTask, DownloadTask
from filewrap import bio_chunk_iter, bio_chunk_async_iter, Buffer, SupportsRead, SupportsWrite
from glob_pattern import translate_iter
from httpfile import HTTPFileReader
from http_request import complete_url, encode_multipart_data, encode_multipart_data_async, SupportsGeturl
from httpx_request import request
from iterutils import run_gen_step, run_gen_step_iter, Yield, YieldFrom
from multidict import CIMultiDict
from yarl import URL

from .client import check_response, AlistClient


AttrDict: TypeAlias = dict
PathType: TypeAlias = str | PathLike[str] | AttrDict


class method:

    def __init__(self, func: Callable, /):
        self.__func__ = func

    def __get__(self, instance, type=None, /):
        if instance is None:
            return self
        return MethodType(self.__func__, instance)

    def __set__(self, instance, value, /):
        raise TypeError("can't set value")


def parse_as_timestamp(s: None | str = None, /) -> float:
    if not s:
        return 0.0
    if s.startswith("0001-01-01"):
        return 0.0
    try:
        return dt_parse(s).timestamp()
    except:
        return 0.0


class AlistPath(Mapping, PathLike[str]):
    "AList path information."
    fs: AlistFileSystem
    path: str
    password: str = ""

    def __init__(
        self, 
        /, 
        fs: AlistFileSystem, 
        path: PathType = "", 
        password: str = "", 
        **attr, 
    ):
        attr.update(fs=fs, path=fs.abspath(path), password=password)
        super().__setattr__("__dict__", attr)

    def __and__(self, path: PathType, /) -> Self:
        return type(self)(
            self.fs, 
            commonpath((self.path, self.fs.abspath(path))), 
            password=self.password, 
        )

    @overload
    def __call__(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Self:
        ...
    @overload
    def __call__(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def __call__(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.get_attr(async_=async_, **kwargs)
            return self
        return run_gen_step(gen_step, async_=async_)

    def __contains__(self, key, /) -> bool:
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.__dict__.get("accessed"):
            self()
        return self.__dict__[key]

    def __ge__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __gt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __hash__(self, /) -> int:
        return hash((self.fs.client, self.path))

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __lt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}({', '.join(f'{k}={v!r}' for k, v in self.__dict__.items())})"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> Self:
        return self.joinpath(path)

    def set_password(self, value, /):
        self.__dict__["password"] = str(value)

    def get(self, /, key, default=None):
        return self.__dict__.get(key, default)

    def keys(self, /) -> KeysView:
        return self.__dict__.keys()

    def values(self, /) -> ValuesView:
        return self.__dict__.values()

    def items(self, /) -> ItemsView:
        return self.__dict__.items()

    @property
    def anchor(self, /) -> str:
        return "/"

    def as_uri(self, /) -> str:
        return self.url

    @property
    def attr(self, /) -> MappingProxyType:
        return MappingProxyType(self.__dict__)

    @overload
    def copy(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> None | Self:
        ...
    @overload
    def copy(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | Self]:
        ...
    def copy(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | Self | Coroutine[Any, Any, None | Self]:
        def gen_step():
            dst = yield self.fs.copy(
                self, 
                dst_path, 
                dst_password=dst_password or self.password, 
                overwrite=overwrite, 
                onerror=onerror, 
                recursive=True, 
                async_=async_, 
            )
            if not dst:
                return None
            return type(self)(self.fs, dst, dst_password or self.password)
        return run_gen_step(gen_step, async_=async_)

    @property
    def directory(self, /) -> Self:
        if self.is_dir():
            return self
        return self.parent

    @overload
    def download(
        self, 
        /, 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[AlistPath], bool] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[Self, str, DownloadTask]]:
        ...
    @overload
    def download(
        self, 
        /, 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[AlistPath], bool] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[Self, str, AsyncDownloadTask]]:
        ...
    def download(
        self, 
        /, 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[AlistPath], bool] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[Self, str, DownloadTask]] | AsyncIterator[tuple[Self, str, AsyncDownloadTask]]:
        return self.fs.download_tree(
            self, 
            to_dir=to_dir, 
            write_mode=write_mode, 
            submit=submit, 
            no_root=no_root, 
            onerror=onerror, 
            predicate=predicate, 
            refresh=refresh, 
            async_=async_, # type: ignore
        )

    @overload
    def enumdir(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[str]:
        ...
    @overload
    def enumdir(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[str]:
        ...
    def enumdir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[str] | AsyncIterator[str]:
        return self.fs.enumdir(
            self if self.is_dir() else self.parent, 
            async_=async_, 
            **kwargs, 
        )

    @overload
    def exists(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            try:
                yield self.get_attr(async_=async_)
                return True
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_=async_)

    @property
    def file_extension(self, /) -> None | str:
        if not self.is_file():
            return None
        return splitext(basename(self.path))[1]

    @overload
    def get_attr(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> AttrDict:
        ...
    @overload
    def get_attr(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def get_attr(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        def gen_step():
            attr = yield self.fs.attr(self.path, async_=async_, **kwargs)
            self.__dict__.update(attr)
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_raw_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def get_raw_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_raw_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.fs.get_raw_url(
            self, 
            headers=headers, 
            async_=async_, 
        )

    def get_url(
        self, 
        /, 
        ensure_ascii: bool = True, 
    ) -> str:
        return self.fs.get_url(
            self, 
            sign=self["sign"], 
            ensure_ascii=ensure_ascii, 
        )

    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[Self]:
        ...
    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[Self]:
        ...
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
            async_=async_, # type: ignore
        )

    def is_absolute(self, /) -> bool:
        return True

    @overload
    def is_empty(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def is_empty(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_empty(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.is_empty(self, async_=async_)

    @method
    def is_dir(self, /) -> bool:
        try:
            return self["is_dir"]
        except FileNotFoundError:
            return False

    @method
    def is_file(self, /) -> bool:
        try:
            return not self["is_dir"]
        except FileNotFoundError:
            return False

    # TODO: 如果 provider 是 alias，则为 True
    def is_symlink(self, /) -> bool:
        return False

    @overload
    def isdir(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def isdir(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isdir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.isdir(self, async_=async_)

    @overload
    def isfile(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def isfile(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isfile(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.isfile(self, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[Self]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[Self]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.fs.iter(
            self if self.is_dir() else self.parent,  
            async_=async_, # type: ignore
            **kwargs, 
        )

    @overload
    def iterdir(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Iterator[AttrDict]:
        ...
    @overload
    def iterdir(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> AsyncIterator[AttrDict]:
        ...
    def iterdir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[AttrDict] | AsyncIterator[AttrDict]:
        return self.fs.iterdir(
            self if self.is_dir() else self.parent, 
            async_=async_, 
            **kwargs, 
        )

    def joinpath(self, /, *paths: str | PathLike[str]) -> Self:
        if not paths:
            return self
        path = self["path"]
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new, self.password)

    @overload
    def listdir(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> list[str]:
        ...
    @overload
    def listdir(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def listdir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        return self.fs.listdir(
            self if self.is_dir() else self.parent, 
            async_=async_, 
            **kwargs, 
        )

    @overload
    def listdir_attr(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> list[AttrDict]:
        ...
    @overload
    def listdir_attr(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, list[AttrDict]]:
        ...
    def listdir_attr(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> list[AttrDict] | Coroutine[Any, Any, list[AttrDict]]:
        return self.fs.listdir_attr(
            self if self.is_dir() else self.parent, 
            async_=async_, 
            **kwargs, 
        )

    @overload
    def listdir_path(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> list[Self]:
        ...
    @overload
    def listdir_path(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, list[Self]]:
        ...
    def listdir_path(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> list[Self] | Coroutine[Any, Any, list[Self]]:
        return self.fs.listdir_path(
            self if self.is_dir() else self.parent, 
            async_=async_, # type: ignore
            **kwargs, 
        )

    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
    ) -> bool:
        pattern = "(?%s:%s)" % (
            "i"[:ignore_case], 
            "".join(
                "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                for pat, typ, _ in translate_iter(path_pattern)
            ), 
        )
        return re_compile(pattern).fullmatch(self["path"]) is not None

    @cached_property
    def media_type(self, /) -> None | str:
        if not self.is_file():
            return None
        return guess_type(self.path)[0] or "application/octet-stream"

    @overload
    def mkdir(
        self, 
        /, 
        exist_ok: bool = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def mkdir(
        self, 
        /, 
        exist_ok: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def mkdir(
        self, 
        /, 
        exist_ok: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.fs.makedirs(
                self, 
                exist_ok=exist_ok, 
                async_=async_, 
            )
            return self
        return run_gen_step(gen_step, async_=async_)

    @overload
    def move(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def move(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def move(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            dst = yield self.fs.move(
                self, 
                dst_path, 
                dst_password=dst_password or self.password, 
                async_=async_, 
            )
            if self["path"] == dst:
                return self
            return type(self)(self.fs, dst, dst_password or self.password)
        return run_gen_step(gen_step, async_=async_)

    @cached_property
    def name(self, /) -> str:
        return basename(self["path"])

    # TODO: 支持异步
    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
    ) -> HTTPFileReader | IO:
        return self.fs.open(
            self, 
            mode=mode, 
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
        )

    @property
    def parent(self, /) -> Self:
        path = self["path"]
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path), self.password)

    @cached_property
    def parents(self, /) -> tuple[Self, ...]:
        path = self["path"]
        if path == "/":
            return ()
        parents: list[Self] = []
        cls, fs, password = type(self), self.fs, self.password
        parent = dirname(path)
        while path != parent:
            parents.append(cls(fs, parent, password))
            path, parent = parent, dirname(parent)
        return tuple(parents)

    @cached_property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *self["path"][1:].split("/"))

    @property
    def raw_url(self, /) -> str:
        return self["raw_url"]

    @overload
    def read_bytes(
        self, 
        /, 
        start: int = 0, 
        stop: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_bytes(
        self, 
        /, 
        start: int = 0, 
        stop: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes(
        self, 
        /, 
        start: int = 0, 
        stop: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        return self.fs.read_bytes(self, start, stop, async_=async_)

    @overload
    def read_bytes_range(
        self, 
        /, 
        bytes_range: str = "0-", 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_bytes_range(
        self, 
        /, 
        bytes_range: str = "0-", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes_range(
        self, 
        /, 
        bytes_range: str = "0-", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        return self.fs.read_bytes_range(self, bytes_range, async_=async_)

    @overload
    def read_block(
        self, 
        /, 
        size: int = 0, 
        offset: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_block(
        self, 
        /, 
        size: int = 0, 
        offset: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_block(
        self, 
        /, 
        size: int = 0, 
        offset: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        return self.fs.read_block(self, size, offset, async_=async_)

    @overload
    def read_text(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def read_text(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def read_text(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.fs.read_text(
            self, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            async_=async_, 
        )

    def relative_to(self, other: None | PathType = None, /) -> str:
        if other is None:
            other = self.fs.path
        elif isinstance(other, (AttrDict, AlistPath)):
            other = cast(str, other["path"])
        else:
            other = fspath(other)
            if not other.startswith("/"):
                other = self.fs.abspath(other)
        path = self["path"]
        if other == "/":
            return path[1:]
        elif path == other:
            return ""
        elif path.startswith(other + "/"):
            return path[len(other)+1:]
        raise ValueError(f"{path!r} is not a subpath of {other!r}")

    @cached_property
    def relatives(self, /) -> tuple[str]:
        def it(path):
            stop = len(path)
            while stop:
                stop = path.rfind("/", 0, stop)
                yield path[stop+1:]
        return tuple(it(self["path"]))

    @overload
    def remove(
        self, 
        /, 
        recursive: bool = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def remove(
        self, 
        /, 
        recursive: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def remove(
        self, 
        /, 
        recursive: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.fs.remove(
            self, 
            recursive=recursive, 
            async_=async_, 
        )

    @overload
    def rename(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def rename(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def rename(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            dst = yield self.fs.rename(
                self, 
                dst_path, 
                dst_password=dst_password or self.password, 
                async_=async_, 
            )
            if self["path"] == dst:
                return self
            return type(self)(self.fs, dst, dst_password or self.password)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def renames(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def renames(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def renames(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            dst = yield self.fs.renames(
                self, 
                dst_path, 
                dst_password=dst_password or self.password, 
                async_=async_, 
            )
            if self["path"] == dst:
                return self
            return type(self)(self.fs, dst, dst_password or self.password)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def replace(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def replace(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def replace(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            dst = yield self.fs.replace(
                self, 
                dst_path, 
                dst_password=dst_password or self.password, 
                async_=async_, 
            )
            if self["path"] == dst:
                return self
            return type(self)(self.fs, dst, dst_password or self.password)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[Self]:
        ...
    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[Self]:
        ...
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
            async_=async_, # type: ignore
        )

    @overload
    def rmdir(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def rmdir(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def rmdir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.fs.rmdir(self, async_=async_)

    @property
    def root(self, /) -> Self:
        return type(self)(
            self.fs, 
            self.fs.storage_of(self), 
            self.password, 
        )

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if type(self) is type(path):
            return self == path
        return path in ("", ".") or self["path"] == self.fs.abspath(path)

    @overload
    def scandir(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[Self]:
        ...
    @overload
    def scandir(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        ...
    def scandir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.fs.scandir(
            self if self.is_dir() else self.parent, 
            async_=async_, # type: ignore
            **kwargs, 
        )

    @overload
    def stat(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> stat_result:
        ...
    @overload
    def stat(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, stat_result]:
        ...
    def stat(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> stat_result | Coroutine[Any, Any, stat_result]:
        return self.fs.stat(self, async_=async_)

    @cached_property
    def stem(self, /) -> str:
        return splitext(basename(self["path"]))[0]

    @cached_property
    def suffix(self, /) -> str:
        return splitext(basename(self["path"]))[1]

    @cached_property
    def suffixes(self, /) -> tuple[str, ...]:
        return tuple("." + part for part in basename(self["path"]).split(".")[1:])

    @overload
    def touch(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def touch(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def touch(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.fs.touch(self, async_=async_)
            return self
        return run_gen_step(gen_step, async_=async_)

    def tree(
        self, 
        /, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], Any] = False, 
        predicate: None | Callable[[AttrDict], Literal[None, 1, False, True]] = None, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        return self.fs.tree(
            self, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            predicate=predicate, 
            async_=async_, 
        )

    unlink = remove

    @cached_property
    def url(self, /) -> str:
        return self.fs.get_url(self)

    @overload
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        ...
    @overload
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[str], list[str]]]:
        ...
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[str], list[str]]] | AsyncIterator[tuple[str, list[str], list[str]]]:
        return self.fs.walk(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
            async_=async_, 
        )

    @overload
    def walk_attr(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    @overload
    def walk_attr(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        return self.fs.walk_attr(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
            async_=async_, # type: ignore
        )

    @overload
    def walk_path(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[str, list[Self], list[Self]]]:
        ...
    @overload
    def walk_path(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[Self], list[Self]]]:
        ...
    def walk_path(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[Self], list[Self]]] | AsyncIterator[tuple[str, list[Self], list[Self]]]:
        return self.fs.walk_path(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
            async_=async_, # type: ignore
        )

    def with_name(self, name: str, /) -> Self:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> Self:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> Self:
        return self.parent.joinpath(self.stem + suffix)

    @overload
    def write_bytes(
        self, 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def write_bytes(
        self, 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def write_bytes(
        self, 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.fs.write_bytes(self, data, async_=async_)
            return self
        return run_gen_step(gen_step, async_=async_)

    @overload
    def write_text(
        self, 
        /, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def write_text(
        self, 
        /, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def write_text(
        self, 
        /, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.fs.write_text(
                self, 
                text, 
                encoding=encoding, 
                errors=errors, 
                newline=newline, 
                async_=async_, 
            )
            return self
        return run_gen_step(gen_step, async_=async_)

    list = listdir_path


class AlistFileSystem:
    """Implemented some file system methods by utilizing AList's web api and 
    referencing modules such as `os`, `posixpath`, `pathlib.Path` and `shutil`."""
    client: AlistClient
    path: str
    refresh: bool
    request_kwargs: dict
    request: None | Callable
    async_request: None | Callable

    def __init__(
        self, 
        /, 
        client: AlistClient, 
        path: str | PathLike[str] = "/", 
        refresh: bool = False, 
        request_kwargs: Optional[dict] = None, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if path in ("", "/", ".", ".."):
            path = "/"
        else:
            path = "/" + normpath("/" + fspath(path)).lstrip("/")
        if request_kwargs is None:
            request_kwargs = {}
        self.__dict__.update(
            client=client, 
            path=path, 
            refresh=refresh, 
            request_kwargs=request_kwargs, 
            request=request, 
            async_request=async_request, 
        )

    def __contains__(self, path: PathType, /) -> bool:
        return self.exists(path)

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.client == other.client

    def __delitem__(self, path: PathType, /):
        self.rmtree(path)

    def __getitem__(self, path: PathType, /) -> AlistPath:
        return self.as_path(path)

    def __aiter__(self, /) -> AsyncIterator[AlistPath]:
        return self.iter(max_depth=-1, async_=True)

    def __iter__(self, /) -> Iterator[AlistPath]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, path: PathType, /) -> Self:
        self.chdir(path)
        return self

    def __len__(self, /) -> int:
        return self.dirlen(self.path)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self.client!r}, path={self.path!r}, refresh={self.refresh!r}, request_kwargs={self.request_kwargs!r})"

    def __setattr__(self, attr, val, /):
        if attr == "refresh":
            self.__dict__["refresh"] = bool(val)
        elif attr == "token":
            self.__dict__["token"] = str(val)
        else:
            raise TypeError(f"can't set attribute: {attr!r}")

    def __setitem__(
        self, 
        /, 
        path: PathType = "", 
        file: None | str | Buffer | PathLike | SupportsRead[Buffer] = None, 
    ):
        if file is None:
            return self.touch(path)
        elif isinstance(file, str):
            return self.write_text(path, file)
        elif isinstance(file, Buffer):
            return self.write_bytes(path, file)
        elif isinstance(file, PathLike):
            if ospath.isdir(file):
                return self.upload_tree(file, path, no_root=True, overwrite=True)
            else:
                return self.upload(file, path, overwrite=True)
        else:
            return self.upload(file, path, overwrite=True)

    @classmethod
    def login(
        cls, 
        /, 
        origin: str = "http://localhost:5244", 
        username: str = "", 
        password: str = "", 
    ) -> AlistFileSystem:
        return cls(AlistClient(origin, username, password))

    @classmethod
    def from_auth(
        cls, 
        /, 
        auth_token: str, 
        origin: str = "http://localhost:5244", 
    ):
        return cls(AlistClient.from_auth(auth_token, origin=origin))

    @cached_property
    def token(self, /) -> str:
        return self.get_token()

    @overload
    def get_token(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def get_token(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_token(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            resp = yield self.client.admin_setting_list(
                payload={"group": 0}, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **self.request_kwargs, 
            )
            token = next(item["value"] for item in check_response(resp)["data"] if item["key"] == "token")
            self.__dict__["token"] = token
            return token
        return run_gen_step(gen_step, async_=async_)

    @overload
    def reset_token(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def reset_token(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def reset_token(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            resp = yield self.client.admin_setting_reset_token( 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **self.request_kwargs, 
            )
            token = check_response(resp)["data"]
            self.__dict__["token"] = token
            return token
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_batch_rename(
        self, 
        /, 
        rename_pairs: Iterable[tuple[str, str]], 
        src_dir: PathType = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_batch_rename(
        self, 
        /, 
        rename_pairs: Iterable[tuple[str, str]], 
        src_dir: PathType = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_batch_rename(
        self, 
        /, 
        rename_pairs: Iterable[tuple[str, str]], 
        src_dir: PathType = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(src_dir, (AttrDict, AlistPath)):
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        payload = {
            "src_dir": src_dir, 
            "rename_objects": [{
                "src_name": src_name, 
                "new_name": new_name, 
            } for src_name, new_name in rename_pairs]
        }
        return check_response(self.client.fs_batch_rename( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_copy(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(src_dir, (AttrDict, AlistPath)):
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, (AttrDict, AlistPath)):
            dst_dir = cast(str, dst_dir["path"])
        else:
            dst_dir = self.abspath(dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return check_response(self.client.fs_copy( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_dirs(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_dirs(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_dirs(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "罗列出所有目录"
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        payload = {
            "path": path, 
            "password": password, 
            "refresh": refresh, 
        }
        return check_response(self.client.fs_dirs( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_form(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: PathType, 
        as_task: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_form(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: PathType, 
        as_task: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_form(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: PathType, 
        as_task: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(path, (AttrDict, AlistPath)):
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        return check_response(self.client.fs_form( # type: ignore
            file, 
            path, 
            as_task=as_task, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_get(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_get(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_get(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        payload = {"path": path, "password": password}
        request_kwargs = self.request_kwargs
        if headers:
            request_kwargs = dict(request_kwargs)
            if default_headers := self.request_kwargs.get("headers"):
                headers = {**default_headers, **headers}
            request_kwargs["headers"] = headers
        return check_response(self.client.fs_get( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def fs_list(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_list(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        payload = {
            "path": path, 
            "password": password, 
            "page": page, 
            "per_page": per_page, 
            "refresh": refresh, 
        }
        return check_response(self.client.fs_list( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_mkdir(
        self, 
        /, 
        path: PathType, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        /, 
        path: PathType, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir(
        self, 
        /, 
        path: PathType, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(path, (AttrDict, AlistPath)):
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if path == "/":
            return {"code": 200}
        return check_response(self.client.fs_mkdir( # type: ignore
            {"path": path}, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_move(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if not names:
            return {"code": 200}
        if isinstance(src_dir, (AttrDict, AlistPath)):
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, (AttrDict, AlistPath)):
            dst_dir = cast(str, dst_dir["path"])
        else:
            dst_dir = self.abspath(dst_dir)
        if src_dir == dst_dir:
            return {"code": 200}
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return check_response(self.client.fs_move( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_put(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: PathType, 
        as_task: bool = False, 
        filesize: int = -1, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_put(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: PathType, 
        as_task: bool = False, 
        filesize: int = -1, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_put(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: PathType, 
        as_task: bool = False, 
        filesize: int = -1, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(path, (AttrDict, AlistPath)):
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        return check_response(self.client.fs_put( # type: ignore
            file, 
            path, 
            as_task=as_task, 
            filesize=filesize, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_recursive_move(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_recursive_move(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_recursive_move(
        self, 
        /, 
        src_dir: PathType, 
        dst_dir: PathType, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(src_dir, (AttrDict, AlistPath)):
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, (AttrDict, AlistPath)):
            dst_dir = cast(str, dst_dir["path"])
        else:
            dst_dir = self.abspath(dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir}
        return check_response(self.client.fs_recursive_move( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_regex_rename(
        self, 
        /, 
        src_name_regex: str, 
        new_name_regex: str, 
        src_dir: PathType = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_regex_rename(
        self, 
        /, 
        src_name_regex: str, 
        new_name_regex: str, 
        src_dir: PathType = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_regex_rename(
        self, 
        /, 
        src_name_regex: str, 
        new_name_regex: str, 
        src_dir: PathType = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(src_dir, (AttrDict, AlistPath)):
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        payload = {
            "src_dir": src_dir, 
            "src_name_regex": src_name_regex, 
            "new_name_regex": new_name_regex, 
        }
        return check_response(self.client.fs_regex_rename( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_remove(
        self, 
        /, 
        src_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_remove(
        self, 
        /, 
        src_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_remove(
        self, 
        /, 
        src_dir: PathType, 
        names: list[str], 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if not names:
            return {"code": 200}
        if isinstance(src_dir, (AttrDict, AlistPath)):
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        payload = {"names": names, "dir": src_dir}
        return check_response(self.client.fs_remove( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_remove_empty_directory(
        self, 
        /, 
        src_dir: PathType = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_remove_empty_directory(
        self, 
        /, 
        src_dir: PathType = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_remove_empty_directory(
        self, 
        /, 
        src_dir: PathType = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(src_dir, (AttrDict, AlistPath)):
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        payload = {"src_dir": src_dir}
        return check_response(self.client.fs_remove_empty_directory( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_rename(
        self, 
        /, 
        path: PathType, 
        name: str, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        /, 
        path: PathType, 
        name: str, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        /, 
        path: PathType, 
        name: str, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(path, (AttrDict, AlistPath)):
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        payload = {"path": path, "name": name}
        return check_response(self.client.fs_rename( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_search(
        self, 
        /, 
        keywords: str, 
        src_dir: PathType = "", 
        scope: Literal[0, 1, 2] = 0, 
        page: int = 1, 
        per_page: int = 0, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_search(
        self, 
        /, 
        keywords: str, 
        src_dir: PathType = "", 
        scope: Literal[0, 1, 2] = 0, 
        page: int = 1, 
        per_page: int = 0, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search(
        self, 
        /, 
        keywords: str, 
        src_dir: PathType = "", 
        scope: Literal[0, 1, 2] = 0, 
        page: int = 1, 
        per_page: int = 0, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(src_dir, (AttrDict, AlistPath)):
            if not password:
                password = src_dir.get("password", "")
            src_dir = cast(str, src_dir["path"])
        else:
            src_dir = self.abspath(src_dir)
        payload = {
            "parent": src_dir, 
            "keywords": keywords, 
            "scope": scope, 
            "page": page, 
            "per_page": per_page, 
            "password": password, 
        }
        return check_response(self.client.fs_search( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_storage_delete(
        self, 
        id: int | str, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_storage_delete(
        self, 
        id: int | str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_storage_delete(
        self, 
        id: int | str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.admin_storage_delete( # type: ignore
            id, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_storage_disable(
        self, 
        /, 
        id: int | str, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_storage_disable(
        self, 
        /, 
        id: int | str, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_storage_disable(
        self, 
        /, 
        id: int | str, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.admin_storage_disable( # type: ignore
            {"id": id}, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_storage_enable(
        self, 
        /, 
        id: int | str, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_storage_enable(
        self, 
        /, 
        id: int | str, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_storage_enable(
        self, 
        /, 
        id: int | str, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.admin_storage_enable( # type: ignore
            {"id": id}, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_storage_list(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_storage_list(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_storage_list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.admin_storage_list( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    @overload
    def fs_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.admin_storage_update( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
        ))

    def abspath(
        self, 
        /, 
        path: PathType = "", 
    ) -> str:
        if path == "/":
            return "/"
        elif path in ("", "."):
            return self.path
        elif isinstance(path, (AttrDict, AlistPath)):
            return path["path"]
        path = fspath(path)
        if path.startswith("/"):
            return "/" + normpath(path).lstrip("/")
        return normpath(joinpath(self.path, path))

    def as_path(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
    ) -> AlistPath:
        if isinstance(path, AlistPath):
            if not password or password == path.get("password"):
                return path
            return AlistPath(**{**path, "password": password})
        elif isinstance(path, AttrDict):
            if not password or password == path.get("password"):
                return AlistPath(**{**path, "fs": self})
            return AlistPath(**{**path, "fs": self, "password": password})
        return AlistPath(fs=self, path=self.abspath(path), password=password)

    @overload
    def attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        headers: None | Mapping = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        headers: None | Mapping = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        headers: None | Mapping = None, 
        refresh: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        def gen_step():
            nonlocal path, password
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path if isinstance(path, AttrDict) else path.__dict__
                if not refresh:
                    return attr
                if not password:
                    password = attr.get("password", "")
                path = cast(str, attr["path"])
            else:
                path = self.abspath(path)
            attr = (yield self.fs_get(
                path, 
                password, 
                headers=headers, 
                async_=async_, 
            ))["data"]
            access_time = datetime.now()
            attr["accessed"] = access_time.astimezone().strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            attr["ctime"] = parse_as_timestamp(attr.get("created"))
            attr["mtime"] = parse_as_timestamp(attr.get("modified"))
            attr["atime"] = access_time.timestamp()
            attr["path"] = path
            attr["password"] = password
            return attr
        return run_gen_step(gen_step, async_=async_)

    def chdir(
        self, 
        /, 
        path: PathType = "/", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ):
        def gen_step():
            nonlocal path, password
            if isinstance(path, (AttrDict, AlistPath)):
                if not path["is_dir"]:
                    raise NotADirectoryError(errno.ENOTDIR, path)
                self.__dict__["path"] = path["path"]
                return
            path = self.abspath(path)
            if path == self.path:
                pass
            elif path == "/":
                self.__dict__["path"] = "/"
            else:
                attr = yield self.attr(
                    path, 
                    password, 
                    async_=async_, 
                )
                if attr["is_dir"]:
                    self.__dict__["path"] = path
                else:
                    raise NotADirectoryError(errno.ENOTDIR, attr)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def copy(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> None | str | dict:
        ...
    @overload
    def copy(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | str | dict]:
        ...
    def copy(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | str | dict | Coroutine[Any, Any, None | str | dict]:
        def gen_step():
            nonlocal src_path, dst_path, src_password, dst_password
            try:
                src_attr = yield self.attr(
                    src_path, 
                    src_password, 
                    async_=async_, 
                )
                src_path = cast(str, src_attr["path"])
                if src_attr["is_dir"]:
                    if recursive:
                        return (yield self.copytree(
                            src_attr, 
                            dst_path, 
                            src_password, 
                            dst_password, 
                            overwrite=overwrite, 
                            onerror=onerror, 
                            async_=async_, 
                        ))
                    raise IsADirectoryError(
                        errno.EISDIR, 
                        f"source path is a directory: {src_path!r} -> {dst_path!r}", 
                    )

                src_password = src_password or src_attr.get("password", "")
                src_dir, src_name = splitpath(src_path)

                dst_attr: None | AttrDict | AlistPath = None
                if isinstance(dst_path, (AttrDict, AlistPath)):
                    dst_attr = dst_path
                    dst_path = cast(str, dst_attr["path"])
                    dst_dir, dst_name = splitpath(dst_path)
                else:
                    dst_path = fspath(dst_path)
                    if dst_path.endswith("/"):
                        dst_dir, dst_name = dst_path, src_name
                        dst_path = joinpath(dst_dir, dst_name)
                    else:
                        dst_path = self.abspath(dst_path)
                        dst_dir, dst_name = splitpath(dst_path)

                if src_path == dst_path:
                    raise SameFileError(src_path)
                cmpath = commonpath((src_path, dst_path))
                if cmpath == dst_path:
                    raise PermissionError(
                        errno.EPERM, 
                        f"copy a file to its ancestor path is not allowed: {src_path!r} -> {dst_path!r}", 
                    )
                elif cmpath == src_path:
                    raise PermissionError(
                        errno.EPERM, 
                        f"copy a file to its descendant path is not allowed: {src_path!r} -> {dst_path!r}", 
                    )

                try:
                    if dst_attr is None:
                        dst_attr = yield self.attr(
                            dst_path, 
                            dst_password, 
                            async_=async_, 
                        )
                    dst_password = dst_password or dst_attr.get("password", "")
                except FileNotFoundError:
                    yield self.makedirs(
                        dst_dir, 
                        dst_password, 
                        exist_ok=True, 
                        async_=async_, 
                    )
                else:
                    if dst_attr["is_dir"]:
                        raise IsADirectoryError(
                            errno.EISDIR, 
                            f"destination path is a directory: {src_path!r} -> {dst_path!r}", 
                        )
                    elif overwrite:
                        yield self.remove(
                            dst_attr, 
                            async_=async_, 
                        )
                    else:
                        raise FileExistsError(
                            errno.EEXIST, 
                            f"destination path already exists: {src_path!r} -> {dst_path!r}", 
                        )

                if src_name == dst_name:
                    resp = yield self.fs_copy(
                        src_dir, 
                        dst_dir, 
                        [src_name], 
                        async_=async_, 
                    )
                    tasks = resp["data"]["tasks"]
                    if not tasks:
                        return dst_path
                    task = tasks[0]
                    task["dst_path"] = dst_path
                    return task
                else:
                    src_storage = yield self.storage_of(
                        src_dir, 
                        src_password, 
                        async_=async_, 
                    )
                    dst_storage = yield self.storage_of(
                        dst_dir, 
                        dst_password, 
                        async_=async_, 
                    )
                    if src_storage != dst_storage:
                        # NOTE: 跨 storage 复制为不同名字的文件，则转化为上传任务
                        resp = yield self.fs_put(
                            URL(self.get_url(src_path)), 
                            dst_path, 
                            as_task=True, 
                            filesize=src_attr["size"], 
                            async_=async_, 
                        )
                        task = resp["data"]["task"]
                        task["dst_path"] = dst_path
                        return task

                    if not (yield self.exists(
                        joinpath(dst_dir, src_name), 
                        async_=async_
                    )):
                        yield self.fs_copy(
                            src_dir, 
                            dst_dir, 
                            [src_name], 
                            async_=async_, 
                        )
                        yield self.fs_rename(
                            joinpath(dst_dir, src_name), 
                            dst_name, 
                            async_=async_, 
                        )
                    else:
                        tempdirname = str(uuid4())
                        tempdir = joinpath(dst_dir, tempdirname)
                        yield self.fs_mkdir(
                            tempdir, 
                            async_=async_, 
                        )
                        try:
                            yield self.fs_copy(
                                src_dir, 
                                tempdir, 
                                [src_name], 
                                async_=async_, 
                            )
                            yield self.fs_rename(
                                joinpath(tempdir, src_name), 
                                dst_name, 
                                async_=async_, 
                            )
                            yield self.fs_move(
                                tempdir, 
                                dst_dir, 
                                [dst_name], 
                                async_=async_, 
                            )
                        finally:
                            yield self.fs_remove(
                                dst_dir, 
                                [tempdirname], 
                                async_=async_, 
                            )
                    return dst_path
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
                return None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def copytree(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        as_task: bool = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> None | str | dict:
        ...
    @overload
    def copytree(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        as_task: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | str | dict]:
        ...
    def copytree(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        as_task: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | str | dict | Coroutine[Any, Any, None | str | dict]:
        def gen_step():
            nonlocal src_path, dst_path, src_password, dst_password
            try:
                src_attr = yield self.attr(
                    src_path, 
                    src_password, 
                    async_=async_, 
                )
                if not src_attr["is_dir"]:
                    return (yield self.copy(
                        src_attr, 
                        dst_path, 
                        src_password, 
                        dst_password, 
                        overwrite=overwrite, 
                        onerror=onerror, 
                        async_=async_, 
                    ))

                src_path = cast(str, src_attr["path"])
                src_password = src_password or src_attr.get("password", "")
                src_dir, src_name = splitpath(src_path)

                dst_attr: None | AttrDict | AlistPath = None
                if isinstance(dst_path, (AttrDict, AlistPath)):
                    dst_attr = dst_path
                    dst_path = cast(str, dst_attr["path"])
                    dst_dir, dst_name = splitpath(dst_path)
                else:
                    dst_path = fspath(dst_path)
                    if dst_path.endswith("/"):
                        dst_dir, dst_name = dst_path, src_name
                        dst_path = joinpath(dst_dir, dst_name)
                    else:
                        dst_path = self.abspath(dst_path)
                        dst_dir, dst_name = splitpath(dst_path)

                if src_path == dst_path:
                    raise SameFileError(src_path)
                cmpath = commonpath((src_path, dst_path))
                if cmpath == dst_path:
                    raise PermissionError(
                        errno.EPERM, 
                        f"copy a directory to its ancestor path is not allowed: {src_path!r} -> {dst_path!r}", 
                    )
                elif cmpath == src_path:
                    raise PermissionError(
                        errno.EPERM, 
                        f"copy a directory to its descendant path is not allowed: {src_path!r} -> {dst_path!r}", 
                    )

                try:
                    if dst_attr is None:
                        dst_attr = yield self.attr(
                            dst_path, 
                            dst_password, 
                            async_=async_, 
                        )
                    dst_password = dst_password or dst_attr.get("password", "")
                except FileNotFoundError:
                    yield self.makedirs(
                        dst_dir, 
                        dst_password, 
                        exist_ok=True, 
                        async_=async_, 
                    )
                    if src_name == dst_name:
                        if as_task:
                            yield self.fs_copy(
                                src_dir, 
                                dst_dir, 
                                [src_name], 
                                async_=async_, 
                            )
                            return dst_path
                    yield self.fs_mkdir(
                        dst_path, 
                        async_=async_, 
                    )
                else:
                    if not dst_attr["is_dir"]:
                        raise NotADirectoryError(
                            errno.ENOTDIR, 
                            f"destination path is not directory: {src_path!r} -> {dst_path!r}", 
                        )

                sub_srcattrs = yield self.listdir_attr(
                    src_attr, 
                    src_password, 
                    refresh=True, 
                    async_=async_, 
                )
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
                return None

            result = {}
            for sub_srcattr in sub_srcattrs:
                if sub_srcattr["is_dir"]:
                    result[sub_srcattr["path"]] = (yield self.copytree(
                        sub_srcattr, 
                        joinpath(dst_path, sub_srcattr["name"]), 
                        src_password, 
                        dst_password, 
                        overwrite=overwrite, 
                        onerror=onerror, 
                        as_task=as_task, 
                        async_=async_, 
                    ))
                else:
                    result[sub_srcattr["path"]] = (yield self.copy(
                        sub_srcattr, 
                        joinpath(dst_path, sub_srcattr["name"]), 
                        src_password, 
                        dst_password, 
                        overwrite=overwrite, 
                        onerror=onerror, 
                        async_=async_, 
                    ))
            return result
        return run_gen_step(gen_step, async_=async_)

    @overload
    def download(
        self, 
        /, 
        path: PathType, 
        file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = True, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> None | DownloadTask:
        ...
    @overload
    def download(
        self, 
        /, 
        path: PathType, 
        file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = True, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | AsyncDownloadTask]:
        ...
    def download(
        self, 
        /, 
        path: PathType, 
        file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = True, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | DownloadTask | Coroutine[Any, Any, None | AsyncDownloadTask]:
        """下载文件到路径或文件

        :param path: 文件在 alist 上的路径
        :param file: 本地路径或可写的文件
        :param write_mode: 写入模式
            - a: append，如果文件不存在则创建，存在则追加（断点续传），返回一个任务
            - w: write， 如果文件不存在则创建，存在则覆盖，返回一个任务
            - x: exists，如果文件不存在则创建，存在则报错 FileExistsError
            - i: ignore，如果文件不存在则创建，存在则忽略，返回 None
        :param submit: 提交执行
            - 如果为 True，则提交给默认的执行器
            - 如果为 False，不提交（稍后可执行 start() 方法手动提交，或运行 run() 方法阻塞执行）
            - 如果为 Callable，则立即调用以提交
        :param password: 密码，用来获取 alist 上文件的信息
        :param async_: 是否异步执行

        :return: 返回 None（表示跳过此任务）或任务对象
        """
        def gen_step():
            nonlocal path, file, password
            url: str = ""
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                path = cast(str, attr["path"])
                if attr["is_dir"]:
                    raise IsADirectoryError(errno.EISDIR, path)
                url = attr.get("raw_url", "")
                if not url and not password:
                    password = attr.get("password", "")
            else:
                path = self.abspath(path)

            if not url:
                attr = yield self.attr(
                    path, 
                    password, 
                    async_=async_, 
                )
                if attr["is_dir"]:
                    raise IsADirectoryError(errno.EISDIR, path)
                url = attr["raw_url"]

            if not isinstance(file, SupportsWrite):
                filepath = fspath(file)
                if not filepath:
                    filepath = attr["name"]
                if ospath.lexists(filepath):
                    if write_mode == "x":
                        raise FileExistsError(
                            errno.EEXIST, 
                            f"local path already exists: {filepath!r}", 
                        )
                    elif write_mode == "i":
                        return None
                file = filepath

            kwargs: dict = {
                "url": url, 
                "file": file, 
                "headers": dict(self.client.headers), 
                "resume": write_mode == "a", 
            }
            if callable(submit):
                kwargs["submit"] = submit
            task: AsyncDownloadTask | DownloadTask
            if async_:
                def async_response_generator_wrapper(func):
                    async def wrapper(*args, **kwds):
                        it = func(*args, **kwds)
                        resp = await anext(it)
                        def aclose():
                            async def none():
                                pass
                            resp.aclose = none
                            return it.aclose()
                        resp.aclose = aclose
                        resp.aiter  = it
                        return resp
                    return wrapper
                try:
                    from aiohttp import request as async_request
                except ImportError:
                    from httpx import AsyncClient

                    async def urlopen_for_iter_bytes(url, headers):
                        async with AsyncClient() as client:
                            async with client.stream("GET", url, headers=headers, follow_redirects=True) as resp:
                                yield resp
                                async for chunk in resp.aiter_bytes(COPY_BUFSIZE):
                                    yield chunk
                else:
                    async def urlopen_for_iter_bytes(url, headers):
                        async with async_request("GET", url, headers=headers) as resp:
                            yield resp
                            read = resp.content.read
                            while chunk := (await read(COPY_BUFSIZE)):
                                yield chunk
                kwargs["urlopen"] = async_response_generator_wrapper(urlopen_for_iter_bytes)
                kwargs["iter_bytes"] = lambda resp: resp.aiter
                task = AsyncDownloadTask.create_task(**kwargs)
            else:
                task = DownloadTask.create_task(**kwargs)
            if callable(submit) or submit:
                yield task.start
            return task
        return run_gen_step(gen_step, async_=async_)

    # TODO: 增加条件化重试机制
    # TODO: 后台开启一个下载管理器，可以管理各个下载任务，所有任务完成后，下载管理器关闭，下载任务可以排队
    # TODO: 下载管理器，多线程使用 ThreadPoolExecutor，异步使用 TaskGroup
    @overload
    def download_tree(
        self, 
        /, 
        path: PathType = "", 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[AlistPath], bool] = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[AlistPath, str, DownloadTask]]:
        ...
    @overload
    def download_tree(
        self, 
        /, 
        path: PathType = "", 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[AlistPath], bool] = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[AlistPath, str, AsyncDownloadTask]]:
        ...
    def download_tree(
        self, 
        /, 
        path: PathType = "", 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[AlistPath], bool] = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[AlistPath, str, DownloadTask]] | AsyncIterator[tuple[AlistPath, str, AsyncDownloadTask]]:
        def gen_step():
            nonlocal to_dir
            attr = yield self.attr(
                path, 
                password, 
                async_=async_, 
            )
            to_dir = fsdecode(to_dir)
            if to_dir:
                makedirs(to_dir, exist_ok=True)
            pathes: list[AlistPath]
            if attr["is_dir"]:
                if not no_root:
                    to_dir = ospath.join(to_dir, attr["name"])
                    if to_dir:
                        makedirs(to_dir, exist_ok=True)
                try:
                    pathes = yield self.listdir_attr(
                        attr, 
                        password=password, 
                        refresh=refresh, 
                        async_=async_, 
                    )
                except OSError as e:
                    if callable(onerror):
                        yield partial(onerror, e)
                    elif onerror:
                        raise
                    return
            else:
                pathes = [self.as_path(attr)]
            mode: Literal["i", "x", "w", "a"]
            for subpath in filter(predicate, pathes):
                if subpath["is_dir"]:
                    yield YieldFrom(self.download_tree(
                        subpath, 
                        ospath.join(to_dir, subpath["name"]), 
                        write_mode=write_mode, 
                        submit=submit, 
                        no_root=True, 
                        onerror=onerror, 
                        predicate=predicate, 
                        password=password, 
                        refresh=refresh, 
                        async_=async_, # type: ignore
                    ), identity=True)
                else:
                    mode = write_mode
                    try:
                        download_path = ospath.join(to_dir, subpath["name"])
                        remote_size = subpath["size"]
                        try:
                            size = lstat(download_path).st_size
                        except OSError:
                            pass
                        else:
                            if remote_size == size:
                                continue
                            elif remote_size < size:
                                mode = "w"
                        task = yield partial(
                            self.download, 
                            subpath, 
                            download_path, 
                            write_mode=mode, 
                            submit=submit, 
                            password=password, 
                            async_=async_, 
                        )
                        if task is not None:
                            yield Yield((subpath, download_path, task), identity=True)
                            if not submit and task.pending:
                                yield task.start
                    except (KeyboardInterrupt, GeneratorExit):
                        raise
                    except BaseException as e:
                        if callable(onerror):
                            yield partial(onerror, e)
                        elif onerror:
                            raise
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def ed2k(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def ed2k(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def ed2k(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            attr = yield self.attr(path, password, headers=headers, refresh=True, async_=async_)
            if attr["is_dir"]:
                raise IsADirectoryError(errno.EISDIR, attr["path"])
            return (yield self.client.ed2k(attr["raw_url"], headers, name=attr["name"], async_=async_))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def enumdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        full_path: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[str]:
        ...
    @overload
    def enumdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        full_path: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[str]:
        ...
    def enumdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        full_path: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[str] | AsyncIterator[str]:
        it = self.iterdir(
            path, 
            password=password, 
            page=page, 
            per_page=per_page, 
            refresh=refresh, 
            async_=async_, 
        )
        if async_:
            it = cast(AsyncIterator, it)
            if full_path:
                return (attr["path"] async for attr in it)
            else:
                return (attr["name"] async for attr in it)
        else:
            it = cast(Iterator, it)
            if full_path:
                return (attr["path"] for attr in it)
            else:
                return (attr["name"] for attr in it)

    @overload
    def exists(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            nonlocal path, password
            if isinstance(path, (AttrDict, AlistPath)):
                path = cast(str, path["path"])
            else:
                path = self.abspath(path)
            try:
                yield self.attr(
                    path, 
                    password, 
                    async_=async_, 
                )
                return True
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_=async_)

    def getcwd(self, /) -> str:
        return self.path

    @overload
    def dirlen(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def dirlen(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, int]:
        ...
    def dirlen(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            resp = yield self.fs_list(
                path, 
                password=password, 
                refresh=refresh, 
                per_page=1, 
                async_=async_, 
            )
            return resp["data"]["total"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_raw_url(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
     ) -> str:
        ...
    @overload
    def get_raw_url(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
     ) -> Coroutine[Any, Any, str]:
        ...
    def get_raw_url(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
     ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                path = cast(str, attr["path"])
                if attr["is_dir"]:
                    raise IsADirectoryError(errno.EISDIR, path)
                if "raw_url" in attr:
                    return attr["raw_url"]
                if not password:
                    password = attr.get("password", "")
            else:
                path = self.abspath(path)
            attr = yield self.attr(path, password, headers=headers, async_=async_)
            if attr["is_dir"]:
                raise IsADirectoryError(errno.EISDIR, path)
            return attr["raw_url"]
        return run_gen_step(gen_step, async_=async_)

    def get_url(
        self, 
        /, 
        path: PathType = "", 
        sign: str = "", 
        token: bool | str = "", 
        expire_timestamp: int = 0, 
        ensure_ascii: bool = True, 
    ) -> str:
        if isinstance(path, (AttrDict, AlistPath)):
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if sign:
            return self.client.get_url(path, sign=sign, ensure_ascii=ensure_ascii)
        if token:
            return self.client.get_url(
                path, 
                self.token if token is True else token, 
                expire_timestamp=expire_timestamp, 
                ensure_ascii=ensure_ascii, 
            )
        else:
            return self.client.get_url(path, ensure_ascii=ensure_ascii)

    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: PathType = "", 
        ignore_case: bool = False, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AlistPath]:
        ...
    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: PathType = "", 
        ignore_case: bool = False, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AlistPath]:
        ...
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: PathType = "", 
        ignore_case: bool = False, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AlistPath] | AsyncIterator[AlistPath]:
        if pattern == "*":
            return self.iter(
                dirname, 
                password=password, 
                async_=async_, 
            )
        elif len(pattern) >= 2 and not pattern.strip("*"):
            return self.iter(
                dirname, 
                password=password, 
                max_depth=-1, 
                async_=async_, 
            )
        def gen_step():
            nonlocal pattern, dirname, password
            if not pattern:
                try:
                    attr = yield self.attr(
                        dirname, 
                        password, 
                        async_=async_, 
                    )
                    yield Yield(self.as_path(attr), identity=True)
                except FileNotFoundError:
                    pass
                return
            elif not pattern.lstrip("/"):
                return Yield(AlistPath(self, "/", password), identity=True)
            splitted_pats = tuple(translate_iter(pattern))
            if pattern.startswith("/"):
                dirname = "/"
            elif isinstance(dirname, AlistPath):
                if not password:
                    password = dirname.get("password", "")
                dirname = cast(str, dirname["path"])
            else:
                dirname = self.abspath(dirname)
            i = 0
            if ignore_case:
                if any(typ == "dstar" for _, typ, _ in splitted_pats):
                    pattern = "".join(
                        "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                        for pat, typ, _ in splitted_pats
                    )
                    if dirname != "/":
                        pattern = re_escape(dirname) + pattern
                    match = re_compile("(?i:%s)" % pattern).fullmatch
                    return YieldFrom(self.iter(
                        dirname, 
                        password=password, 
                        max_depth=-1, 
                        predicate=lambda p: match(p["path"]) is not None, 
                        async_=async_, 
                    ), identity=True)
            else:
                typ = None
                for i, (pat, typ, orig) in enumerate(splitted_pats):
                    if typ != "orig":
                        break
                    dirname = joinpath(dirname, orig)
                if typ == "orig":
                    try:
                        attr = yield self.attr(
                            dirname, 
                            password, 
                            async_=async_, 
                        )
                        yield Yield(self.as_path(attr), identity=True)
                    except FileNotFoundError:
                        pass
                    return
                elif typ == "dstar" and i + 1 == len(splitted_pats):
                    return YieldFrom(self.iter(
                        dirname, 
                        password=password, 
                        max_depth=-1, 
                        async_=async_, 
                    ), identity=True)
                if any(typ == "dstar" for _, typ, _ in splitted_pats[i:]):
                    pattern = "".join(
                        "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                        for pat, typ, _ in splitted_pats[i:]
                    )
                    if dirname != "/":
                        pattern = re_escape(dirname) + pattern
                    match = re_compile(pattern).fullmatch
                    return YieldFrom(self.iter(
                        dirname, 
                        password=password, 
                        max_depth=-1, 
                        predicate=lambda p: match(p["path"]) is not None, 
                        async_=async_, 
                    ), identity=True)
            try:
                attr = yield self.attr(dirname, password, async_=async_)
            except FileNotFoundError:
                return
            path = AlistPath(self, **attr)
            if not path.is_dir():
                return
            cref_cache: dict[int, Callable] = {}
            def glob_step_match(path: AlistPath, i: int):
                j = i + 1
                at_end = j == len(splitted_pats)
                pat, typ, orig = splitted_pats[i]
                if typ == "orig":
                    subpath = path.joinpath(orig)
                    if at_end:
                        if (yield subpath.exists(async_=async_)):
                            yield Yield(subpath, identity=True)
                    elif subpath.is_dir():
                        yield from glob_step_match(subpath, j)
                else:
                    subpaths = yield path.listdir_path(async_=async_)
                    if typ == "star":
                        if at_end:
                            yield YieldFrom(subpaths, identity=True)
                        else:
                            for subpath in subpaths:
                                if subpath.is_dir():
                                    yield from glob_step_match(subpath, j)
                    else:
                        for subpath in subpaths:
                            try:
                                cref = cref_cache[i]
                            except KeyError:
                                if ignore_case:
                                    pat = "(?i:%s)" % pat
                                cref = cref_cache[i] = re_compile(pat).fullmatch
                            if cref(subpath.name):
                                if at_end:
                                    yield Yield(subpath, identity=True)
                                elif subpath.is_dir():
                                    yield from glob_step_match(subpath, j)
            yield from glob_step_match(path, i)
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def isdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def isdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            try:
                attr = yield self.attr(
                    path, 
                    password, 
                    async_=async_, 
                )
                return attr["is_dir"]
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_=async_)

    @overload
    def isfile(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def isfile(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isfile(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            try:
                attr = yield self.attr(
                    path, 
                    password, 
                    async_=async_, 
                )
                return not attr["is_dir"]
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_=async_)

    @overload
    def is_empty(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def is_empty(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_empty(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            nonlocal path, password
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                if not password:
                    password = attr.get("password", "")
            else:
                try:
                    attr = yield self.attr(path, password, async_=async_)
                except FileNotFoundError:
                    return True
            if attr["is_dir"]:
                return (yield self.dirlen(path, password, async_=async_)) == 0
            else:
                return attr["size"] == 0
        return run_gen_step(gen_step, async_=async_)

    @overload
    def is_storage(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def is_storage(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_storage(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            nonlocal path, password
            attr: None | AttrDict | AlistPath = None
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                path = cast(str, attr["path"])
                if not password:
                    password = attr.get("password", "")
            else:
                path = self.abspath(path)
            try:
                storages = yield self.list_storages(async_=async_)
                return any(path == s["mount_path"] for s in storages)
            except PermissionError:
                if path == "/":
                    return True
                if attr is None or "hash_info" not in attr:
                    try:
                        attr = cast(dict, (yield self.attr(path, password, async_=async_)))
                    except FileNotFoundError:
                        return False
                return attr["hash_info"] is None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter_bfs(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[AlistPath], None | bool] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AlistPath]:
        ...
    @overload
    def iter_bfs(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[AlistPath], None | bool] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AlistPath]:
        ...
    def iter_bfs(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[AlistPath], None | bool] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AlistPath] | AsyncIterator[AlistPath]:
        def gen_step():
            nonlocal min_depth, max_depth, password
            dq: deque[tuple[int, AlistPath]] = deque()
            push, pop = dq.append, dq.popleft
            try:
                attr = yield self.attr(top, password, async_=async_)
                if not password:
                    password = attr.get("password", "")
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
                return
            push((0, self.as_path(attr)))
            while dq:
                depth, path = pop()
                if min_depth <= 0:
                    if predicate is None:
                        pred = True
                    else:
                        pred = yield partial(predicate, path)
                    if pred is None:
                        return
                    elif pred:
                        yield Yield(path, identity=True)
                    min_depth = 1
                if depth == 0 and (not path.is_dir() or 0 <= max_depth <= depth):
                    return
                depth += 1
                try:
                    subpaths = yield self.listdir_path(path, password, refresh=refresh, async_=async_)
                    for path in subpaths:
                        if predicate is None:
                            pred = True
                        else:
                            pred = yield partial(predicate, path)
                        if pred is None:
                            continue
                        elif pred and depth >= min_depth:
                            yield Yield(path, identity=True)
                        if path.is_dir() and (max_depth < 0 or depth < max_depth):
                            push((depth, path))
                except OSError as e:
                    if callable(onerror):
                        yield partial(onerror, e)
                    elif onerror:
                        raise
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def iter_dfs(
        self, 
        /, 
        top: PathType = "", 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], None | bool]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AlistPath]:
        ...
    @overload
    def iter_dfs(
        self, 
        /, 
        top: PathType = "", 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], None | bool]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AlistPath]:
        ...
    def iter_dfs(
        self, 
        /, 
        top: PathType = "", 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], None | bool]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AlistPath] | AsyncIterator[AlistPath]:
        def gen_step():
            nonlocal min_depth, max_depth
            if not max_depth:
                return
            global_yield_me = True
            if min_depth > 1:
                global_yield_me = False
                min_depth -= 1
            elif min_depth <= 0:
                path = self.as_path(top, password)
                if "accessed" not in path:
                    yield path(async_=async_)
                if predicate is None:
                    pred = True
                else:
                    pred = yield partial(predicate, path)
                if pred is None:
                    return
                elif pred:
                    yield Yield(path, identity=True)
                if path.is_file():
                    return
                min_depth = 1
            if max_depth > 0:
                max_depth -= 1
            try:
                subpaths = yield self.listdir_path(top, password, refresh=refresh, async_=async_)
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
                return
            for path in subpaths:
                yield_me = global_yield_me
                if yield_me and predicate is not None:
                    pred = yield partial(predicate, path)
                    if pred is None:
                        continue
                    yield_me = pred
                if yield_me and topdown:
                    yield Yield(path, identity=True)
                if path.is_dir():
                    yield YieldFrom(self.iter(
                        path, 
                        topdown=topdown, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        predicate=predicate, 
                        onerror=onerror, 
                        refresh=refresh, 
                        password=password, 
                        async_=async_, 
                    ), identity=True)
                if yield_me and not topdown:
                    yield path
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], None | bool]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AlistPath]:
        ...
    @overload
    def iter(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], None | bool]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AlistPath]:
        ...
    def iter(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], None | bool]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AlistPath] | AsyncIterator[AlistPath]:
        if topdown is None:
            return self.iter_bfs(
                top, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                refresh=refresh, 
                password=password, 
                async_=async_, # type: ignore
            )
        else:
            return self.iter_dfs(
                top, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                refresh=refresh, 
                password=password, 
                async_=async_, # type: ignore
            )

    @overload
    def iterdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AttrDict]:
        ...
    @overload
    def iterdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AttrDict]:
        ...
    def iterdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AttrDict] | AsyncIterator[AttrDict]:
        def gen_step():
            if page > 0 or per_page <= 0:
                yield YieldFrom(self.listdir_attr(
                    path, 
                    password, 
                    refresh=refresh, 
                    page=page, 
                    per_page=per_page, 
                    async_=async_, 
                ))
            else:
                while True:
                    data = yield self.listdir_attr(
                        path, 
                        password, 
                        refresh=refresh, 
                        page=page, 
                        per_page=per_page, 
                        async_=async_, 
                    )
                    yield YieldFrom(data, identity=True)
                    if len(data) < per_page:
                        break
                    page += 1
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def list_storages(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def list_storages(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_storages(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        def gen_step():
            resp = yield self.fs_storage_list(async_=async_)
            return resp["data"]["content"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def listdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        full_path: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[str]:
        ...
    @overload
    def listdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        full_path: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def listdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        full_path: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        def gen_step():
            resp = yield self.fs_list(
                path, 
                password, 
                refresh=refresh, 
                page=page, 
                per_page=per_page, 
                async_=async_, 
            )
            data = resp["data"]["content"]
            if not data:
                return []
            if full_path:
                return [item["path"] for item in data]
            else:
                return [item["name"] for item in data]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def listdir_attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[AttrDict]:
        ...
    @overload
    def listdir_attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[AttrDict]]:
        ...
    def listdir_attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[AttrDict] | Coroutine[Any, Any, list[AttrDict]]:
        def gen_step():
            nonlocal path, password, page, per_page
            if page <= 0 or per_page < 0:
                page = 1
                per_page = 0
            resp = yield self.fs_list(
                path, 
                password, 
                refresh=refresh, 
                page=page, 
                per_page=per_page, 
                async_=async_, 
            )
            data = resp["data"]["content"]
            if not data:
                return []
            if isinstance(path, (AttrDict, AlistPath)):
                if not password:
                    password = path.get("password", "")
                path = cast(str, path["path"])
            else:
                path = self.abspath(path)
            for attr in data:
                attr["ctime"] = parse_as_timestamp(attr.get("created"))
                attr["mtime"] = parse_as_timestamp(attr.get("modified"))
                attr["path"] = joinpath(path, attr["name"])
                attr["password"] = password
            return data
        return run_gen_step(gen_step, async_=async_)

    @overload
    def listdir_path(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[AlistPath]:
        ...
    @overload
    def listdir_path(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[AlistPath]]:
        ...
    def listdir_path(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[AlistPath] | Coroutine[Any, Any, list[AlistPath]]:
        def gen_step():
            data = yield self.listdir_attr(
                path, 
                password, 
                refresh=refresh, 
                page=page, 
                per_page=per_page, 
                async_=async_, 
            )
            return [AlistPath(self, **attr) for attr in data]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def makedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        exist_ok: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def makedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        exist_ok: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def makedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        exist_ok: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            if isinstance(path, (AttrDict, AlistPath)):
                if not password:
                    password = path.get("password", "")
                path = cast(str, path["path"])
            else:
                path = self.abspath(path)
            if path == "/":
                return "/"
            try:
                attr = yield self.attr(path, password, async_=async_)
            except FileNotFoundError:
                yield self.fs_mkdir(path, async_=async_)
            else:
                if attr["is_dir"]:
                    if not exist_ok:
                        raise FileExistsError(errno.EEXIST, path)
                else:
                    raise NotADirectoryError(errno.ENOTDIR, path)
            return path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def mkdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def mkdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def mkdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            if isinstance(path, (AttrDict, AlistPath)):
                if not password:
                    password = path.get("password", "")
                path = cast(str, path["path"])
            else:
                path = self.abspath(path)
            if path == "/":
                raise PermissionError(
                    errno.EPERM, 
                    "create root directory is not allowed (because it has always existed)", 
                )
            try:
                attr = yield self.attr(path, password, async_=async_)
            except FileNotFoundError as e:
                dattr = yield self.attr(dirname(path), password, async_=async_)
                if not dattr["is_dir"]:
                    raise NotADirectoryError(errno.ENOTDIR, dattr["path"]) from e
                yield self.fs_mkdir(path, async_=async_)
                return path
            else:
                if attr["is_dir"]:
                    raise FileExistsError(errno.EEXIST, path)
                raise NotADirectoryError(errno.ENOTDIR, path) 
        return run_gen_step(gen_step, async_=async_)

    @overload
    def move(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def move(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def move(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal src_path, dst_path, src_password, dst_password
            src_attr: None | AttrDict | AlistPath = None
            dst_attr: None | AttrDict | AlistPath = None
            if isinstance(src_path, (AttrDict, AlistPath)):
                src_attr = src_path
                if not src_password:
                    src_password = src_attr.get("password", "")
                src_path = cast(str, src_attr["path"])
            else:
                src_path = self.abspath(src_path)
            if isinstance(dst_path, (AttrDict, AlistPath)):
                dst_attr = dst_path
                if not dst_password:
                    dst_password = dst_attr.get("password", "")
                dst_path = cast(str, dst_attr["path"])
            else:
                dst_path = self.abspath(dst_path)
            if src_path == dst_path or dirname(src_path) == dst_path:
                return src_path
            cmpath = commonpath((src_path, dst_path))
            if cmpath == dst_path:
                raise PermissionError(
                    errno.EPERM, 
                    f"rename a path as its ancestor is not allowed: {src_path!r} -> {dst_path!r}", 
                )
            elif cmpath == src_path:
                raise PermissionError(
                    errno.EPERM, 
                    f"rename a path as its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
                )
            # TODO: 还要考虑一种情况，就是 src_path 是个 storage
            if src_attr is None:
                src_attr = cast(dict, (yield self.attr(src_path, src_password, async_=async_)))
            try:
                if dst_attr is None:
                    dst_attr = cast(dict, (yield self.attr(dst_path, dst_password, async_=async_)))
            except FileNotFoundError:
                return (yield self.rename(
                    src_attr, 
                    dst_path, 
                    src_password, 
                    dst_password, 
                    async_=async_, # type: ignore
                ))
            else:
                if dst_attr["is_dir"]:
                    dst_filename = basename(src_path)
                    dst_filepath = joinpath(dst_path, dst_filename)
                    if (yield self.exists(dst_filepath, dst_password, async_=async_)):
                        raise FileExistsError(
                            errno.EEXIST, 
                            f"destination path {dst_filepath!r} already exists", 
                        )
                    yield self.fs_move(dirname(src_path), dst_path, [dst_filename], async_=async_)
                    return dst_filepath
                raise FileExistsError(errno.EEXIST, f"destination path {dst_path!r} already exists")
        return run_gen_step(gen_step, async_=async_)

    # TODO: 支持异步
    def open(
        self, 
        /, 
        path: PathType, 
        mode: str = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> HTTPFileReader | IO:
        if async_:
            raise NotImplementedError("asynchronous mode not implemented")
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        url = self.get_raw_url(path, password, headers=headers, async_=async_)
        request_kwargs = self.request_kwargs
        if headers:
            request_kwargs = dict(request_kwargs)
            if default_headers := self.request_kwargs.get("headers"):
                headers = {**default_headers, **headers}
            request_kwargs["headers"] = headers
        return self.client.open(
            url, 
            start=start, 
            seek_threshold=seek_threshold, 
            async_=async_, 
            **request_kwargs, 
        ).wrap(
            text_mode="b" not in mode, 
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    @overload
    def read_bytes(
        self, 
        /, 
        path: PathType, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_bytes(
        self, 
        /, 
        path: PathType, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes(
        self, 
        /, 
        path: PathType, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        def gen_step():
            nonlocal headers
            url = yield self.get_raw_url(path, password, headers=headers, async_=async_)
            request_kwargs = self.request_kwargs
            if headers:
                request_kwargs = dict(request_kwargs)
                if default_headers := self.request_kwargs.get("headers"):
                    headers = {**default_headers, **headers}
                request_kwargs["headers"] = headers
            return (yield self.client.read_bytes(
                url, 
                start, 
                stop, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_bytes_range(
        self, 
        /, 
        path: PathType, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_bytes_range(
        self, 
        /, 
        path: PathType, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes_range(
        self, 
        /, 
        path: PathType, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        def gen_step():
            nonlocal headers
            url = yield self.get_raw_url(path, password, headers=headers, async_=async_)
            request_kwargs = self.request_kwargs
            if headers:
                request_kwargs = dict(request_kwargs)
                if default_headers := self.request_kwargs.get("headers"):
                    headers = {**default_headers, **headers}
                request_kwargs["headers"] = headers
            return (yield self.client.read_bytes_range(
                url, 
                bytes_range, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_block(
        self, 
        /, 
        path: PathType, 
        size: int = 0, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_block(
        self, 
        /, 
        path: PathType, 
        size: int = 0, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_block(
        self, 
        /, 
        path: PathType, 
        size: int = 0, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        def gen_step():
            nonlocal headers
            if size <= 0:
                return b""
            url = yield self.get_raw_url(path, password, headers=headers, async_=async_)
            request_kwargs = self.request_kwargs
            if headers:
                request_kwargs = dict(request_kwargs)
                if default_headers := self.request_kwargs.get("headers"):
                    headers = {**default_headers, **headers}
                request_kwargs["headers"] = headers
            return (yield self.client.read_block(
                url, 
                size, 
                offset, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_text(
        self, 
        /, 
        path: PathType, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def read_text(
        self, 
        /, 
        path: PathType, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def read_text(
        self, 
        /, 
        path: PathType, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            data: bytes = yield self.read_bytes_range(
                path, 
                password=password, 
                headers=headers, 
                async_=async_, 
            )
            bio = BytesIO(data)
            tio = TextIOWrapper(
                bio, 
                encoding=encoding or "utf-8", 
                errors=errors, 
                newline=newline, 
            )
            return tio.read()
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        recursive: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def remove(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        recursive: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def remove(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        recursive: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            attr: None | AttrDict | AlistPath = None
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                if not password:
                    password = attr.get("password", "")
                path = cast(str, attr["path"])
            else:
                path = self.abspath(path)
            if path == "/":
                if recursive:
                    try:
                        storages = yield self.list_storages(async_=async_)
                    except PermissionError:
                        names = yield self.listdir("/", password, refresh=True, async_=async_)
                        yield self.fs_remove("/", names, async_=async_)
                    else:
                        for storage in storages:
                            yield self.fs_storage_delete(storage["id"], async_=async_)
                    return path
                raise PermissionError(
                    errno.EPERM, 
                    "remove the root directory is not allowed", 
                )
            if attr is None or "hash_info" not in attr:
                attr = cast(dict, (yield self.attr(path, password, async_=async_)))
            is_storage = attr.get("hash_info") is None
            if attr["is_dir"]:
                if not recursive:
                    if is_storage:
                        raise PermissionError(
                            errno.EPERM, 
                            f"remove a storage is not allowed: {path!r}", 
                        )
                    raise IsADirectoryError(errno.EISDIR, path)
                try:
                    storages = yield self.list_storages(async_=async_)
                except PermissionError:
                    if is_storage:
                        raise
                else:
                    for storage in storages:
                        if commonpath((storage["mount_path"], path)) == path:
                            yield self.fs_storage_delete(storage["id"], async_=async_)
            if not is_storage:
                dir_, name = splitpath(path)
                yield self.fs_remove(dir_, [name], async_=async_)
            return path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def removedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def removedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def removedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            attr: None | AttrDict | AlistPath = None
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                path = cast(str, attr["path"])
                if not attr["is_dir"]:
                    raise NotADirectoryError(errno.ENOTDIR, path)
                if not password:
                    password = attr.get("password", "")
            else:
                path = self.abspath(path)
            dirlen = self.dirlen
            remove = self.fs_remove
            remove_storage = self.fs_storage_delete
            if (yield dirlen(path, password, async_=async_)):
                raise OSError(errno.ENOTEMPTY, f"directory is not empty: {path!r}")
            if attr is None or "hash_info" not in attr:
                attr = cast(dict, (yield self.attr(path, password, async_=async_)))
            try:
                storages = yield self.list_storages(async_=async_)
                storage_path_to_id = {s["mount_path"]: s["id"] for s in storages}
            except PermissionError:
                if attr["hash_info"] is None:
                    raise
                storage_path_to_id = {}
            dir_, name = splitpath(path)
            if attr["hash_info"] is None:
                yield remove_storage(storage_path_to_id[path], async_=async_)
            else:
                yield remove(dir_, [name], async_=async_)
            try:
                del_dir = ""
                name = ""
                while True:
                    dir_length = yield dirlen(dir_, password, async_=async_)
                    if del_dir:
                        if dir_length > 1:
                            break
                    elif dir_length:
                        break
                    if dir_ in storage_path_to_id:
                        yield remove_storage(storage_path_to_id[dir_], async_=async_)
                        del_dir = ""
                    else:
                        del_dir = dir_
                    if dir_ == "/":
                        break
                    dir_, name = splitpath(dir_)
                if del_dir == "/":
                    if "/" in storage_path_to_id:
                        yield remove_storage(storage_path_to_id["/"], async_=async_)
                    elif name:
                        yield remove("/", [name], async_=async_)
                elif del_dir:
                    dir_, name = splitpath(del_dir)
                    yield remove(dir_, [name], async_=async_)
            except OSError:
                pass
            return path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def rename(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        replace: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def rename(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        replace: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def rename(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        replace: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal src_path, dst_path, src_password, dst_password
            src_attr: None | AttrDict | AlistPath = None
            dst_attr: AttrDict | AlistPath
            if isinstance(src_path, (AttrDict, AlistPath)):
                if not src_password:
                    src_password = src_path.get("password", "")
                src_path = cast(str, src_path["path"])
            else:
                src_path = self.abspath(src_path)
            if isinstance(dst_path, (AttrDict, AlistPath)):
                if not dst_password:
                    dst_password = dst_path.get("password", "")
                dst_path = cast(str, dst_path["path"])
            else:
                dst_path = self.abspath(dst_path)
            if src_path == dst_path:
                return dst_path
            if src_path == "/" or dst_path == "/":
                raise OSError(
                    errno.EINVAL, 
                    f"invalid argument: {src_path!r} -> {dst_path!r}", 
                )
            cmpath = commonpath((src_path, dst_path))
            if cmpath == dst_path:
                raise PermissionError(
                    errno.EPERM, 
                    f"rename a path as its ancestor is not allowed: {src_path!r} -> {dst_path!r}", 
                )
            elif cmpath == src_path:
                raise PermissionError(
                    errno.EPERM, 
                    f"rename a path as its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
                )
            src_dir, src_name = splitpath(src_path)
            dst_dir, dst_name = splitpath(dst_path)
            if src_attr is None or "hash_info" not in src_attr:
                src_attr = cast(dict, (yield self.attr(src_path, src_password, async_=async_)))
            try:
                dst_attr = cast(dict, (yield self.attr(dst_path, dst_password, async_=async_)))
            except FileNotFoundError:
                if src_attr["hash_info"] is None:
                    storages = yield self.list_storages(async_=async_)
                    for storage in storages:
                        if src_path == storage["mount_path"]:
                            storage["mount_path"] = dst_path
                            yield self.fs_storage_update(storage, async_=async_)
                            return dst_path
                    raise FileNotFoundError(errno.ENOENT, f"{src_path!r} is not an actual path")
                elif src_dir == dst_dir:
                    yield self.fs_rename(src_attr, dst_name, async_=async_)
                    return dst_path
                dstdir_attr = yield self.attr(dst_dir, dst_password, async_=async_)
                if not dstdir_attr["is_dir"]:
                    raise NotADirectoryError(
                        errno.ENOTDIR, 
                        f"{dst_dir!r} is not a directory: {src_path!r} -> {dst_path!r}", 
                    )
            else:
                if replace:
                    if dst_attr.get("hash_info") is None:
                        raise PermissionError(
                            errno.EPERM, 
                            f"replace a storage (or non-actual path) {dst_path!r} is not allowed: {src_path!r} -> {dst_path!r}", 
                        )
                    elif src_attr["is_dir"]:
                        if dst_attr["is_dir"]:
                            if (yield self.dirlen(dst_path, dst_password, async_=async_)):
                                raise OSError(
                                    errno.ENOTEMPTY, 
                                    f"directory {dst_path!r} is not empty: {src_path!r} -> {dst_path!r}", 
                                )
                        else:
                            raise NotADirectoryError(
                                errno.ENOTDIR, 
                                f"{dst_path!r} is not a directory: {src_path!r} -> {dst_path!r}", 
                            )
                    elif dst_attr["is_dir"]:
                        raise IsADirectoryError(
                            errno.EISDIR, 
                            f"{dst_path!r} is a directory: {src_path!r} -> {dst_path!r}", 
                        )
                    yield self.fs_remove(dst_dir, [dst_name], async_=async_)
                else:
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"{dst_path!r} already exists: {src_path!r} -> {dst_path!r}", 
                    )

            # TODO: 需要优化，后面再搞
            src_storage = self.storage_of(src_dir, src_password, async_=async_)
            dst_storage = self.storage_of(dst_dir, dst_password, async_=async_)
            if src_name == dst_name:
                if src_storage != dst_storage:
                    warn("cross storages movement will retain the original file: {src_path!r} |-> {dst_path!r}")
                self.fs_move(src_dir, dst_dir, [src_name], async_=async_)
            elif src_dir == dst_dir:
                self.fs_rename(src_path, dst_name, async_=async_)
            else:
                if src_storage != dst_storage:
                    raise PermissionError(
                        errno.EPERM, 
                        f"cross storages movement does not allow renaming: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}", 
                    )
                tempname = f"{uuid4()}{splitext(src_name)[1]}"
                self.fs_rename(src_path, tempname, async_=async_)
                try:
                    self.fs_move(src_dir, dst_dir, [tempname], async_=async_)
                    try:
                        self.fs_rename(joinpath(dst_dir, tempname), dst_name, async_=async_)
                    except:
                        self.fs_move(dst_dir, src_dir, [tempname], async_=async_)
                        raise
                except:
                    self.fs_rename(joinpath(src_dir, tempname), src_name, async_=async_)
                    raise
            return dst_path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def renames(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def renames(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def renames(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal src_path, dst_path, src_password
            dst_path = cast(str, (yield self.rename(src_path, dst_path, src_password, dst_password, async_=async_)))
            if isinstance(src_path, (AttrDict, AlistPath)):
                if not src_password:
                    src_password = src_path.get("password", "")
                src_path = cast(str, src_path["path"])
            else:
                src_path = self.abspath(src_path)
            if dirname(src_path) != dirname(dst_path):
                try:
                    yield self.removedirs(dirname(src_path), src_password, async_=async_)
                except OSError:
                    pass
            return dst_path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def replace(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def replace(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def replace(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.rename(src_path, dst_path, src_password, dst_password, replace=True, async_=async_)

    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: PathType = "", 
        ignore_case: bool = False, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AlistPath]:
        ...
    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: PathType = "", 
        ignore_case: bool = False, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AlistPath]:
        ...
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: PathType = "", 
        ignore_case: bool = False, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AlistPath] | AsyncIterator[AlistPath]:
        if not pattern:
            return self.iter(dirname, password=password, max_depth=-1, async_=async_)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, password=password, ignore_case=ignore_case, async_=async_)

    @overload
    def rmdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def rmdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def rmdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            attr: None | AttrDict | AlistPath = None
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                path = cast(str, attr["path"])
                if not attr["is_dir"]:
                    raise NotADirectoryError(errno.ENOTDIR, path)
                if not password:
                    password = attr.get("password", "")
            else:
                path = self.abspath(path)
            if path == "/":
                raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
            if attr is None or "hash_info" not in attr:
                attr = cast(dict, (yield self.attr(path, password, async_=async_)))
            if not attr["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, path)
            if attr["hash_info"] is None:
                raise PermissionError(errno.EPERM, f"remove a storage (or non-actual path) by `rmdir` is not allowed: {path!r}")
            elif not (yield self.dirlen(path, password, async_=async_)):
                raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
            dir_, name = splitpath(path)
            yield self.fs_remove(dir_, [name], async_=async_)
            return path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def rmtree(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def rmtree(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def rmtree(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.remove(path, password, recursive=True, async_=async_)

    @overload
    def scandir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AlistPath]:
        ...
    @overload
    def scandir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AlistPath]:
        ...
    def scandir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AlistPath] | AsyncIterator[AlistPath]:
        if async_:
            return (
                AlistPath(self, **attr) async for attr in 
                self.iterdir(
                    path, 
                    password, 
                    refresh=refresh, 
                    page=page, 
                    per_page=per_page, 
                    async_=True, 
                )
            )
        else:
            return (AlistPath(self, **attr) for attr in 
                self.iterdir(
                    path, 
                    password, 
                    refresh=refresh, 
                    page=page, 
                    per_page=per_page, 
                )
            )

    @overload
    def stat(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> stat_result:
        ...
    @overload
    def stat(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, stat_result]:
        ...
    def stat(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> stat_result | Coroutine[Any, Any, stat_result]:
        def gen_step():
            attr = yield self.attr(path, password, async_=async_)
            return stat_result((
                (S_IFDIR if attr["is_dir"] else S_IFREG) | 0o777, # mode
                0, # ino
                0, # dev
                1, # nlink
                0, # uid
                0, # gid
                attr.get("size") or 0, # size
                attr.get("atime") or attr["mtime"], # atime
                attr["mtime"], # mtime
                attr["ctime"], # ctime
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def storage_of(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def storage_of(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def storage_of(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            attr: None | AttrDict | AlistPath = None
            if isinstance(path, (AttrDict, AlistPath)):
                attr = path
                path = cast(str, attr["path"])
                if not password:
                    password = attr.get("password", "")
            else:
                path = self.abspath(path)
            try:
                storages = yield self.list_storages(async_=async_)
            except PermissionError:
                if path == "/":
                    return "/"
                if attr is None or "hash_info" not in attr:
                    attr = cast(dict, (yield self.attr(path, password, async_=async_)))
                while attr["hash_info"] is not None:
                    path = dirname(path)
                    if path == "/":
                        break
                    try:
                        attr = cast(dict, (yield self.attr(path, password, async_=async_)))
                    except FileNotFoundError:
                        pass
                return path
            else:
                storage = "/"
                for s in storages:
                    mount_path = s["mount_path"]
                    if path == mount_path:
                        return mount_path
                    elif commonpath((path, mount_path)) == mount_path and len(mount_path) > len(storage):
                        storage = mount_path
                return storage
        return run_gen_step(gen_step, async_=async_)

    def tree(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], Any] = False, 
        predicate: None | Callable[[AttrDict], Literal[None, 1, False, True]] = None, 
        password: str = "", 
        _depth: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        def gen_step():
            can_step_in: bool = max_depth < 0 or _depth < max_depth
            if _depth == 0 and min_depth <= 0:
                print(".")
            try:
                ls = yield self.listdir_attr(top, password, async_=async_)
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
            pred: Literal[None, 1, False, True] = True
            next_depth = _depth + 1
            for attr, nattr in pairwise(chain(ls, (None,))):
                attr = cast(AttrDict, attr)
                if predicate is not None:
                    pred = yield partial(predicate, attr)
                    if pred is None:
                        continue
                if next_depth >= min_depth and pred:
                    print('│   ' * _depth, end="")
                    if nattr is not None:
                        print('├── ' + attr["name"])
                    else:
                        print('└── ' + attr["name"])
                    if pred is 1:
                        continue
                if can_step_in and attr["is_dir"]:
                    yield self.tree(
                        attr, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        onerror=onerror, 
                        predicate=predicate, 
                        password=password, 
                        _depth=next_depth, 
                        async_=async_, 
                    )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def touch(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        is_dir: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def touch(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        is_dir: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def touch(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        is_dir: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            if not (yield self.exists(path, password, async_=async_)):
                if is_dir:
                    yield self.fs_mkdir(path, async_=async_)
                else:
                    yield self.upload(b"", path, password, async_=async_)
            return path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal path, password
            try:
                attr = yield self.attr(path, password, async_=async_)
                path = cast(str, attr["path"])
            except FileNotFoundError:
                pass
            else:
                if attr["is_dir"]:
                    name = ""
                    if isinstance(file, (str, PathLike)):
                        name = basename(fsdecode(file))
                    elif isinstance(file, (URL, SupportsGeturl)):
                        if isinstance(file, URL):
                            url = str(file)
                        else:
                            url = file.geturl()
                        name = basename(unquote(urlsplit(url).path))
                    elif isinstance(file, SupportsRead):
                        try:
                            name = basename(fsdecode(getattr(file, "name")))
                        except (AttributeError, TypeError):
                            pass
                    path = joinpath(cast(str, attr["path"]), name or uuid4().hex)
                    if name and (yield self.exists(path, password or attr["password"], async_=async_)):
                        raise FileExistsError(errno.EEXIST, path)
                if overwrite:
                    dir_, name = splitpath(path)
                    yield self.fs_remove(dir_, [name], async_=async_)
                else:
                    raise FileExistsError(errno.EEXIST, path)
            yield self.fs_form(file, path, as_task=as_task, async_=async_)
            if remove_done and isinstance(file, (str, PathLike)):
                try:
                    remove(file)
                except OSError:
                    pass
            return path
        return run_gen_step(gen_step, async_=async_)

    @overload
    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str] = ".", 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        no_root: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        predicate: None | Callable[[Path], bool] = None, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[str]:
        ...
    @overload
    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str] = ".", 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        no_root: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        predicate: None | Callable[[Path], bool] = None, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[str]:
        ...
    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str] = ".", 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        no_root: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        predicate: None | Callable[[Path], bool] = None, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[str] | AsyncIterator[str]:
        def gen_step():
            nonlocal path, password
            try:
                attr = yield self.attr(path, password, async_=async_)
                path = cast(str, attr["path"])
                if not password:
                    password = attr["password"]
                if not attr["is_dir"]:
                    raise NotADirectoryError(errno.ENOTDIR, path)
                try:
                    subpaths: Iterator[DirEntry] = scandir(local_path)
                    if predicate is not None:
                        subpaths = filter(lambda e: predicate(Path(e)), subpaths)
                except NotADirectoryError:
                    yield Yield(self.upload(
                        local_path, 
                        joinpath(path, ospath.basename(local_path)), 
                        password=password, 
                        as_task=as_task, 
                        overwrite=overwrite, 
                        remove_done=remove_done, 
                        async_=async_, 
                    ))
                else:
                    if not no_root:
                        path = joinpath(path, ospath.basename(local_path))
                    for entry in subpaths:
                        if entry.is_dir():
                            yield YieldFrom(self.upload_tree(
                                entry, 
                                joinpath(path, entry.name), 
                                password=password, 
                                as_task=as_task, 
                                no_root=True, 
                                overwrite=overwrite, 
                                remove_done=remove_done, 
                                async_=async_, 
                            ))
                        else:
                            yield Yield(self.upload(
                                entry, 
                                joinpath(path, entry.name), 
                                password=password, 
                                as_task=as_task, 
                                overwrite=overwrite, 
                                remove_done=remove_done, 
                                async_=async_, 
                            ))
                    return path
            except OSError as e:
                if callable(onerror):
                    onerror(e)
                elif onerror:
                    raise
        return run_gen_step_iter(gen_step, async_=async_)

    unlink = remove

    @overload
    def walk_attr_bfs(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    @overload
    def walk_attr_bfs(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr_bfs(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        def gen_step():
            nonlocal password
            attr = yield self.attr(top, password, async_=async_)
            password = attr["password"]
            dq: deque[tuple[int, AttrDict]] = deque([(0, attr)])
            push, pop = dq.append, dq.popleft
            while dq:
                depth, parent = pop()
                depth += 1
                try:
                    iter_me = min_depth <= 0 or depth >= min_depth
                    push_me = max_depth < 0 or depth < max_depth
                    if iter_me or push_me:
                        ls = yield self.listdir_attr(parent, password, refresh=refresh, async_=async_)
                        if iter_me:
                            dirs: list[AttrDict] = []
                            files: list[AttrDict] = []
                            for attr in ls:
                                if attr["is_dir"]:
                                    dirs.append(attr)
                                    if push_me:
                                        push((depth, attr))
                                else:
                                    files.append(attr)
                            yield Yield((parent["path"], dirs, files), identity=True)
                        else:
                            for attr in ls:
                                if attr["is_dir"]:
                                    push((depth, attr))
                except OSError as e:
                    if callable(onerror):
                        yield partial(onerror, e)
                    elif onerror:
                        raise
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def walk_attr_dfs(
        self, 
        /, 
        top: PathType = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    @overload
    def walk_attr_dfs(
        self, 
        /, 
        top: PathType = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr_dfs(
        self, 
        /, 
        top: PathType = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        def gen_step():
            nonlocal top, password
            if not max_depth:
                return
            if min_depth > 0:
                min_depth -= 1
            if max_depth > 0:
                max_depth -= 1
            yield_me = min_depth <= 0
            if isinstance(top, AlistPath):
                if not password:
                    password = top.get("password", "")
                top = cast(str, top["path"])
            else:
                top = self.abspath(top)
            try:
                ls = yield self.listdir_attr(top, password, refresh=refresh, async_=async_)
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
                return
            dirs: list[AttrDict] = []
            files: list[AttrDict] = []
            for attr in ls:
                if attr["is_dir"]:
                    dirs.append(attr)
                else:
                    files.append(attr)
            if yield_me and topdown:
                yield Yield((top, dirs, files), identity=True)
            for attr in dirs:
                yield YieldFrom(self.walk_attr_dfs(
                    attr, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    password=password, 
                    refresh=refresh, 
                    async_=async_, 
                ))
            if yield_me and not topdown:
                yield Yield((top, dirs, files), identity=True)
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def walk(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        ...
    @overload
    def walk(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[str], list[str]]]:
        ...
    def walk(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[str], list[str]]] | AsyncIterator[tuple[str, list[str], list[str]]]:
        if async_:
            return (
                (path, [a["name"] for a in dirs], [a["name"] for a in files])
                async for path, dirs, files in self.walk_attr(
                    top, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    password=password, 
                    refresh=refresh, 
                    async_=True, 
                )
            )
        else:
            return (
                (path, [a["name"] for a in dirs], [a["name"] for a in files])
                for path, dirs, files in self.walk_attr(
                    top, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    password=password, 
                    refresh=refresh, 
                )
            )

    @overload
    def walk_attr(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    @overload
    def walk_attr(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        if topdown is None:
            return self.walk_attr_bfs(
                top, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                async_=async_, # type: ignore
            )
        else:
            return self.walk_attr_dfs(
                top, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                async_=async_, # type: ignore
            )

    @overload
    def walk_path(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        ...
    @overload
    def walk_path(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        ...
    def walk_path(
        self, 
        /, 
        top: PathType = "", 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]] | AsyncIterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        if async_:
            return (
                (path, [AlistPath(self, **a) for a in dirs], [AlistPath(self, **a) for a in files])
                async for path, dirs, files in self.walk_attr(
                    top, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    password=password, 
                    refresh=refresh, 
                    async_=True, 
                )
            )
        else:
            return (
                (path, [AlistPath(self, **a) for a in dirs], [AlistPath(self, **a) for a in files])
                for path, dirs, files in self.walk_attr(
                    top, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    password=password, 
                    refresh=refresh, 
                )
            )

    @overload
    def write_bytes(
        self, 
        /, 
        path: PathType, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        password: str = "", 
        as_task: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def write_bytes(
        self, 
        /, 
        path: PathType, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        password: str = "", 
        as_task: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def write_bytes(
        self, 
        /, 
        path: PathType, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        password: str = "", 
        as_task: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.upload(
            data, 
            path, 
            password=password, 
            as_task=as_task, 
            overwrite=True, 
            async_=async_, 
        )

    @overload
    def write_text(
        self, 
        /, 
        path: PathType, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        password: str = "", 
        as_task: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def write_text(
        self, 
        /, 
        path: PathType, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        password: str = "", 
        as_task: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def write_text(
        self, 
        /, 
        path: PathType, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        password: str = "", 
        as_task: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        bio = BytesIO()
        if text:
            tio = TextIOWrapper(
                bio, 
                encoding=encoding or "utf-8", 
                errors=errors, 
                newline=newline, 
            )
            tio.write(text)
            tio.flush()
            bio.seek(0)
        return self.write_bytes(path, bio, password=password, as_task=as_task, async_=async_)

    list = listdir_path

    cd  = chdir
    cp  = copy
    pwd = getcwd
    ls  = listdir
    la  = listdir_attr
    ll  = listdir_path
    mv  = move
    rm  = remove

