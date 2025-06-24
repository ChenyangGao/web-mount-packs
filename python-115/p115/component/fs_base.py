#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "AttrDict", "P115PathBase", "P115FileSystemBase", "IDOrPathType", 
    "P115FSType", "P115PathType", 
]

import errno

from abc import ABC, abstractmethod
from collections import deque, UserString
from collections.abc import (
    AsyncIterator, Awaitable, Callable, Coroutine, Iterable, Iterator, 
    ItemsView, KeysView, Mapping, Sequence, ValuesView, 
)
from functools import cached_property, partial
from io import BytesIO, BufferedReader, TextIOWrapper, UnsupportedOperation
from inspect import isawaitable
from itertools import chain, pairwise
from mimetypes import guess_type
from os import fsdecode, fspath, lstat, makedirs, scandir, stat, stat_result, PathLike
from os import path as ospath
from posixpath import join as joinpath, splitext
from re import compile as re_compile, escape as re_escape
from shutil import COPY_BUFSIZE # type: ignore
from stat import S_IFDIR, S_IFREG # TODO: common stat method
from time import time
from typing import (
    cast, overload, Any, Generic, IO, Literal, Never, Self, TypeAlias, TypeVar, 
)
from types import MappingProxyType
from urllib.parse import parse_qsl, urlparse

from asynctools import async_map
from dictattr import AttrDict
from download import AsyncDownloadTask, DownloadTask
from filewrap import AsyncBufferedReader, AsyncTextIOWrapper, SupportsWrite
from glob_pattern import translate_iter
from hashtools import HashObj
from httpfile import AsyncHTTPFileReader, HTTPFileReader
from iterutils import run_gen_step, run_gen_step_iter, Yield, YieldFrom
from p115client import check_response, P115URL
from posixpatht import basename, commonpath, dirname, escape, joins, normpath, relpath, splits, unescape

from .client import P115Client


T = TypeVar("T")
IDOrPathType: TypeAlias = int | str | PathLike[str] | Sequence[str] | AttrDict
P115FSType = TypeVar("P115FSType", bound="P115FileSystemBase")
P115PathType = TypeVar("P115PathType", bound="P115PathBase")
CRE_115URL_EXPIRE_TS_search = re_compile(r"(?<=\?t=)[0-9]+").search


class P115PathBase(Generic[P115FSType], Mapping, PathLike[str]):

    def __init__(self, /, fs: P115FSType, attr: AttrDict):
        self.fs = fs
        self.attr = attr

    def __and__(self, path: str | PathLike[str], /) -> Self:
        attr = self.fs.attr(commonpath((self.path, self.fs.abspath(path))))
        return type(self)(self.fs, attr)

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
        return key in self.attr

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self.id == path.id

    def __fspath__(self, /) -> str:
        return self.path

    def __ge__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client: 
            return False
        return self.id >= self.id

    def __getattr__(self, attr, /):
        try:
            return self.attr[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __getitem__(self, key, /):
        return self.attr[key]

    def __gt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return self.id > path.id

    def __hash__(self, /) -> int:
        return hash((self.fs.client, self.id))

    def __index__(self, /) -> int:
        return self.id

    def __iter__(self, /) -> Iterator[str]:
        return iter(self.attr)

    def __le__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return self.id <= self.id

    def __len__(self, /) -> int:
        return len(self.attr)

    def __lt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return self.id < self.id

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(fs={self.fs!r}, attr={self.attr!r})"

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> Self:
        return self.joinpath(path)

    def get(self, /, key, default=None):
        return self.attr.get(key, default)

    def keys(self, /) -> KeysView:
        return self.attr.keys()

    def values(self, /) -> ValuesView:
        return self.attr.values()

    def items(self, /) -> ItemsView:
        return self.attr.items()

    @property
    def anchor(self, /) -> str:
        return "/"

    def as_uri(self, /) -> str:
        return self.url

    @overload
    def dictdir(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> dict[int, str]:
        ...
    @overload
    def dictdir(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, dict[int, str]]:
        ...
    def dictdir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> dict[int, str] | Coroutine[Any, Any, dict[int, str]]:
        return self.fs.dictdir(self, async_=async_, **kwargs)

    @overload
    def dictdir_attr(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> dict[int, AttrDict]:
        ...
    @overload
    def dictdir_attr(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, dict[int, AttrDict]]:
        ...
    def dictdir_attr(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> dict[int, AttrDict] | Coroutine[Any, Any, dict[int, AttrDict]]:
        return self.fs.dictdir_attr(self, async_=async_, **kwargs)

    @overload
    def dictdir_path(
        self, 
        /, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> dict[int, Self]:
        ...
    @overload
    def dictdir_path(
        self, 
        /, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, dict[int, Self]]:
        ...
    def dictdir_path(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> dict[int, Self] | Coroutine[Any, Any, dict[int, Self]]:
        return self.fs.dictdir_path(self, async_=async_, **kwargs)

    @cached_property
    def directory(self, /) -> Self:
        return self.get_directory()

    @overload
    def download(
        self, 
        /, 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[Self], bool] = None, 
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
        predicate: None | Callable[[Self], bool] = None, 
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
        predicate: None | Callable[[Self], bool] = None, 
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
            self if self.is_dir() else self["parent_id"], 
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

    @cached_property
    def file_extension(self, /) -> None | str:
        if not self.is_file():
            return None
        return splitext(basename(self.path))[1]

    @overload
    def get_attr(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def get_attr(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def get_attr(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        def gen_step():
            attr = yield self.fs.attr(self["id"], async_=async_)
            if attr is not self.attr:
                self.attr = attr
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_directory(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def get_directory(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def get_directory(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            if self.is_dir():
                return self
            return (yield partial(
                self.get_parent, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> P115URL:
        ...
    @overload
    def get_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def get_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        return self.fs.get_url(self, headers=headers, async_=async_)

    @overload
    def get_parent(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def get_parent(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def get_parent(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            if self.id == 0:
                return self
            attr = yield partial(self.fs.attr, self["parent_id"], async_=async_)
            return type(self)(self.fs, attr)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_parents(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterator[Self]:
        ...
    @overload
    def get_parents(
        self, 
        /, 
        async_: Literal[True], 
    ) -> AsyncIterator[Self]:
        ...
    def get_parents(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        cls = type(self)
        fs = self.fs
        get_attr = fs.attr
        if async_:
            async def wrap():
                for a in reversed(self["ancestors"][:-1]):
                    yield cls(fs, (await get_attr(a["id"], async_=True)))
            return wrap()
        else:
            return (cls(fs, get_attr(a["id"])) for a in reversed(self["ancestors"][:-1]))

    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
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
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[Self]:
        ...
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self["parent_id"], 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
            async_=async_, 
        )

    @overload
    def hash(
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> tuple[int, HashObj | T]:
        ...
    @overload
    def hash(
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, tuple[int, HashObj | T]]:
        ...
    def hash(
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> tuple[int, HashObj | T] | Coroutine[Any, Any, tuple[int, HashObj | T]]:
        return self.fs.hash(
            self.id, 
            digest=digest, # type: ignore
            start=start, 
            stop=stop, 
            headers=headers, 
            async_=async_, # type: ignore
        )

    @overload
    def hashes(
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        async_: Literal[False] = False, 
    ) -> tuple[int, list[HashObj | T]]:
        ...
    @overload
    def hashes(
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        ...
    def hashes(
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        async_: Literal[False, True] = False, 
    ) -> tuple[int, list[HashObj | T]] | Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        return self.fs.hashes(
            self.id, 
            digest, # type: ignore
            *digests, # type: ignore
            start=start, 
            stop=stop, 
            headers=headers, 
            async_=async_, # type: ignore
        )

    @cached_property
    def id(self, /) -> int:
        return self["id"]

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

    def is_dir(self, /) -> bool:
        try:
            return self["is_directory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def is_file(self, /) -> bool:
        try:
            return not self["is_directory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return True

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

    def inode(self, /) -> int:
        return self.id

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
            self if self.is_dir() else self["parent_id"], 
            async_=async_, 
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
            self if self.is_dir() else self["parent_id"], 
            async_=async_, 
            **kwargs, 
        )

    @overload
    def join(
        self, 
        /, 
        *names: str, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def join(
        self, 
        /, 
        *names: str, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def join(
        self, 
        /, 
        *names: str, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            if not names:
                return self
            attr = yield partial(self.fs.attr, names, pid=self.id, async_=async_)
            return type(self)(self.fs, attr)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def joinpath(
        self, 
        /, 
        *paths: str | PathLike[str], 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def joinpath(
        self, 
        /, 
        *paths: str | PathLike[str], 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def joinpath(
        self, 
        /, 
        *paths: str | PathLike[str], 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            if not paths:
                return self
            path = self.path
            path_new = normpath(joinpath(path, *paths))
            if path == path_new:
                return self
            if path != "/" and path_new.startswith(path + "/"):
                attr = yield partial(
                    self.fs.attr, 
                    path_new[len(path)+1:], 
                    pid=self.id, 
                    async_=async_, 
                )
            else:    
                attr = yield partial(self.fs.attr, path_new, async_=async_)
            return type(self)(self.fs, attr)
        return run_gen_step(gen_step, async_=async_)

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
            self if self.is_dir() else self["parent_id"], 
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
            self if self.is_dir() else self["parent_id"], 
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
            self if self.is_dir() else self["parent_id"], 
            async_=async_, 
            **kwargs, 
        )

    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> bool:
        pattern = "(?%s:%s)" % (
            "i"[:ignore_case], 
            "".join(
                "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                for pat, typ, _ in translate_iter(
                    path_pattern, 
                    allow_escaped_slash=allow_escaped_slash, 
                )
            ), 
        )
        return re_compile(pattern).fullmatch(self.path) is not None

    @cached_property
    def media_type(self, /) -> None | str:
        if not self.is_file():
            return None
        return guess_type(self.path)[0] or "application/octet-stream"

    @property
    def name(self, /) -> str:
        return basename(self.path)

    @overload
    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> HTTPFileReader | BufferedReader | TextIOWrapper:
        ...
    @overload
    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncHTTPFileReader | AsyncBufferedReader | AsyncTextIOWrapper:
        ...
    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] | type[AsyncHTTPFileReader] = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> HTTPFileReader | BufferedReader | TextIOWrapper | AsyncHTTPFileReader | AsyncBufferedReader | AsyncTextIOWrapper:
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
            http_file_reader_cls=http_file_reader_cls, 
            async_=async_, # type: ignore
        )

    @property
    def parent(self, /) -> Self:
        return self.get_parent()

    @property
    def parents(self, /) -> tuple[Self, ...]:
        return tuple(self.get_parents())

    @property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *splits(self.path, unescape=None)[0][1:])

    @property
    def path(self, /) -> str:
        return str(self["path"])

    @property
    def patht(self, /) -> tuple[str, ...]:
        return tuple(splits(self.path)[0])

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

    def relative_to(self, other: None | str | Self = None, /) -> str:
        dirname = str(self.fs.path)
        if other is None:
            other = dirname
        elif not isinstance(other, str):
            other = other.path
        return relpath(self.path, other, dirname)

    @cached_property
    def relatives(self, /) -> tuple[str]:
        patht, _ = splits(self.path)
        def it():
            path = patht[-1]
            if path:
                yield path
                for p in reversed(patht[1:-1]):
                    path = joinpath(unescape(p), path)
                    yield path
        return tuple(it())

    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
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
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[Self]:
        ...
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self["parent_id"], 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
            async_=async_, 
        )

    @cached_property
    def root(self, /) -> Self:
        return type(self)(self.fs, self.fs.attr(0))

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if type(self) is type(path):
            return self == path
        return path in ("", ".") or self.path == self.fs.abspath(str(path))

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
            self if self.is_dir() else self["parent_id"], 
            async_=async_, 
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
        return splitext(basename(self.path))[0]

    @cached_property
    def suffix(self, /) -> str:
        return splitext(basename(self.path))[1]

    @cached_property
    def suffixes(self, /) -> tuple[str, ...]:
        return tuple("." + part for part in basename(self.path).split(".")[1:])

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

    @property
    def url(self, /) -> P115URL:
        ns = self.__dict__
        try:
            url = ns["url"]
        except KeyError:
            pass
        else:
            match = CRE_115URL_EXPIRE_TS_search(url)[0] # type: ignore
            if time() < int(match):
                return url
        url = ns["url"] = self.fs.get_url(self)
        return url

    @overload
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
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
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[str], list[str]]]:
        ...
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[str], list[str]]] | AsyncIterator[tuple[str, list[str], list[str]]]:
        return self.fs.walk(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            async_=async_, 
            **kwargs, 
        )

    @overload
    def walk_attr(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
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
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        return self.fs.walk_attr(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            async_=async_, 
            **kwargs, 
        )

    @overload
    def walk_path(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
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
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[Self], list[Self]]]:
        ...
    def walk_path(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[Self], list[Self]]] | AsyncIterator[tuple[str, list[Self], list[Self]]]:
        return self.fs.walk_path(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            async_=async_, 
            **kwargs, 
        )

    @overload
    def with_name(
        self, 
        name: str, 
        /, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def with_name(
        self, 
        name: str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def with_name(
        self, 
        name: str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        return self.parent.joinpath(name, async_=async_)

    @overload
    def with_stem(
        self, 
        stem: str, 
        /, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def with_stem(
        self, 
        stem: str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def with_stem(
        self, 
        stem: str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        return self.parent.joinpath(stem + self.suffix, async_=async_)

    @overload
    def with_suffix(
        self, 
        suffix: str, 
        /, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def with_suffix(
        self, 
        suffix: str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def with_suffix(
        self, 
        suffix: str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        return self.parent.joinpath(self.stem + suffix, async_=async_)

    list = listdir_path
    dict = dictdir_path


class P115FileSystemBase(Generic[P115PathType]):
    client: P115Client
    id: int = 0
    path: str | UserString = "/"
    path_class: type[P115PathType]
    request: None | Callable = None
    async_request: None | Callable = None

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = P115Client(client)
        ns = self.__dict__
        ns["client"] = client
        if request is not None:
            ns["request"] = request
        if async_request is not None:
            ns["async_request"] = async_request

    def __contains__(self, id_or_path: IDOrPathType, /) -> bool:
        return self.exists(id_or_path)

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.client == other.client

    def __getitem__(self, id_or_path: IDOrPathType, /) -> P115PathType:
        return self.as_path(id_or_path)

    def __aiter__(self, /) -> AsyncIterator[P115PathType]:
        return self.iter(self.id, max_depth=-1, async_=True)

    def __iter__(self, /) -> Iterator[P115PathType]:
        return self.iter(self.id, max_depth=-1)

    def __itruediv__(self, id_or_path: IDOrPathType, /) -> Self:
        self.chdir(id_or_path)
        return self

    def __len__(self, /) -> int:
        return len(tuple(self.iterdir()))

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}, id={self.id!r}, path={self.path!r}) at {hex(id(self))}>"

    @overload
    @abstractmethod
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    @abstractmethod
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    @abstractmethod
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        ...

    @overload
    @abstractmethod
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> P115URL:
        ...
    @overload
    @abstractmethod
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    @abstractmethod
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        ...

    @overload
    @abstractmethod
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[AttrDict]:
        ...
    @overload
    @abstractmethod
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[AttrDict]:
        ...
    @abstractmethod
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[AttrDict] | AsyncIterator[AttrDict]:
        ...

    @overload
    def abspath(
        self, 
        path: str | PathLike[str] = "", 
        /, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def abspath(
        self, 
        path: str | PathLike[str] = "", 
        /, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def abspath(
        self, 
        path: str | PathLike[str] = "", 
        /, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.get_path(path, async_=async_)

    @overload
    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> P115PathType:
        ...
    @overload
    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, P115PathType]:
        ...
    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> P115PathType | Coroutine[Any, Any, P115PathType]:
        path_class = type(self).path_class
        def gen_step():
            attr: AttrDict
            if isinstance(id_or_path, path_class):
                return id_or_path
            elif isinstance(id_or_path, dict):
                attr = cast(AttrDict, id_or_path)
            else:
                attr = yield partial(
                    self.attr, 
                    id_or_path, 
                    pid=pid, 
                    ensure_dir=ensure_dir, 
                    async_=async_, 
                    **kwargs, 
                )
            return path_class(self, attr)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, int]:
        ...
    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int | Coroutine[Any, Any, int]:
        path_class = type(self).path_class
        def gen_step():
            nonlocal id_or_path
            if isinstance(id_or_path, (AttrDict, path_class)):
                id = id_or_path["id"]
                self.__dict__.update(id=id, path=id_or_path["path"])
                return id
            elif id_or_path in (0, "/"):
                self.__dict__.update(id=0, path="/")
                return 0
            if isinstance(id_or_path, PathLike):
                id_or_path = fspath(id_or_path)
            if not id_or_path or id_or_path == ".":
                return self.id
            attr = yield partial(
                self.attr, 
                id_or_path, 
                pid=pid, 
                ensure_dir=True, 
                async_=async_, 
            )
            if self.id == attr["id"]:
                return self.id
            elif attr["is_directory"]:
                self.__dict__.update(id=attr["id"], path=attr["path"])
                return attr["id"]
            else:
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{id_or_path!r} (in {pid!r}) is not a directory", 
                )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def dictdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> dict[int, str]:
        ...
    @overload
    def dictdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, dict[int, str]]:
        ...
    def dictdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> dict[int, str] | Coroutine[Any, Any, dict[int, str]]:
        if async_:
            async def request():
                if full_path:
                    return {attr["id"]: str(attr["path"]) async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)}
                else:
                    return {attr["id"]: attr["name"] async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)}
            return request()
        elif full_path:
            return {attr["id"]: str(attr["path"]) for attr in self.iterdir(id_or_path, pid=pid, **kwargs)}
        else:
            return {attr["id"]: attr["name"] for attr in self.iterdir(id_or_path, pid=pid, **kwargs)}

    @overload
    def dictdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> dict[int, AttrDict]:
        ...
    @overload
    def dictdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, dict[int, AttrDict]]:
        ...
    def dictdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> dict[int, AttrDict] | Coroutine[Any, Any, dict[int, AttrDict]]:
        if async_:
            async def request():
                return {attr["id"]: attr async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs)}
            return request()
        else:
            return {attr["id"]: attr for attr in self.iterdir(id_or_path, pid=pid, **kwargs)}

    @overload
    def dictdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> dict[int, P115PathType]:
        ...
    @overload
    def dictdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, dict[int, P115PathType]]:
        ...
    def dictdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> dict[int, P115PathType] | Coroutine[Any, Any, dict[int, P115PathType]]:
        path_class = type(self).path_class
        if async_:
            async def request():
                return {attr["id"]: path_class(self, attr) async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs)}
            return request()
        else:
            return {attr["id"]: path_class(self, attr) for attr in self.iterdir(id_or_path, pid=pid, **kwargs)}

    @overload
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, int]:
        ...
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            return len((yield self.listdir_attr(id_or_path, pid=pid, async_=async_)))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = True, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> None | DownloadTask:
        ...
    @overload
    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = True, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | AsyncDownloadTask]:
        ...
    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = True, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | DownloadTask | Coroutine[Any, Any, None | AsyncDownloadTask]:
        """下载文件到路径或文件

        :param id_or_path: 文件在 115 网盘上的 id 或路径
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
        :param pid: 待下载文件路径在 115 网盘上的上级 id（用于把相对路径转化为绝对路径）
        :param async_: 是否异步执行

        :return: 返回 None（表示跳过此任务）或任务对象
        """
        def gen_step():
            nonlocal file
            url = yield partial(
                self.get_url, 
                id_or_path, 
                pid=pid, 
                async_=async_, 
            )
            if not isinstance(file, SupportsWrite):
                filepath = fsdecode(file)
                if not filepath:
                    filepath = url.get("file_name") or ""
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
                "headers": {
                    **self.client.headers, 
                    "Cookie": "; ".join(f"{c.name}={c.value}" for c in self.client.cookiejar), 
                }, 
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
    @overload
    def download_tree(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[P115PathType], bool] = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[tuple[P115PathType, str, DownloadTask]]:
        ...
    @overload
    def download_tree(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[P115PathType], bool] = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[tuple[P115PathType, str, AsyncDownloadTask]]:
        ...
    def download_tree(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        to_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = False, 
        no_root: bool = False, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
        predicate: None | Callable[[P115PathType], bool] = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[tuple[P115PathType, str, DownloadTask]] | AsyncIterator[tuple[P115PathType, str, AsyncDownloadTask]]:
        def gen_step():
            nonlocal to_dir
            attr = yield partial(
                self.attr, 
                id_or_path, 
                pid=pid, 
                async_=async_, 
            )
            to_dir = fsdecode(to_dir)
            if to_dir:
                makedirs(to_dir, exist_ok=True)
            pathes: list[P115PathType]
            if attr["is_directory"]:
                if not no_root:
                    to_dir = ospath.join(to_dir, attr["name"])
                    if to_dir:
                        makedirs(to_dir, exist_ok=True)
                try:
                    pathes = yield partial(
                        self.listdir_path, 
                        attr, 
                        async_=async_, 
                    )
                except OSError as e:
                    if callable(onerror):
                        yield partial(onerror, e)
                    elif onerror:
                        raise
                    return
            else:
                pathes = [type(self).path_class(self, attr)]
            mode: Literal["i", "x", "w", "a"]
            for subpath in filter(predicate, pathes):
                if subpath["is_directory"]:
                    yield YieldFrom(self.download_tree(
                        subpath, 
                        ospath.join(to_dir, subpath["name"]), 
                        write_mode=write_mode, 
                        submit=submit, 
                        no_root=True, 
                        onerror=onerror, 
                        predicate=predicate, 
                        async_=async_, # type: ignore
                    ))
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
                            async_=async_, 
                        )
                        if task is not None:
                            yield Yield((subpath, download_path, task))
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
        id_or_path: IDOrPathType, 
        /, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def ed2k(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def ed2k(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            url = yield self.get_url(
                id_or_path, 
                pid=pid, 
                headers=headers, 
                async_=async_, 
            )
            return (yield self.client.ed2k(url, headers, name=url.get("file_name"), async_=async_))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def enumdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[str]:
        ...
    @overload
    def enumdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[str]:
        ...
    def enumdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[str] | AsyncIterator[str]:
        it = self.iterdir(id_or_path, pid=pid, async_=async_, **kwargs)
        if async_:
            it = cast(AsyncIterator, it)
            if full_path:
                return (str(attr["path"]) async for attr in it)
            else:
                return (attr["name"] async for attr in it)
        else:
            it = cast(Iterator, it)
            if full_path:
                return (str(attr["path"]) for attr in it)
            else:
                return (attr["name"] for attr in it)

    @overload
    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        path_class = type(self).path_class
        if isinstance(id_or_path, (AttrDict, path_class)):
            id_or_path = id_or_path["id"]
        def gen_step():
            try:
                yield partial(self.attr, id_or_path, pid=pid, async_=async_)
                return True
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_=async_)

    def getcid(self, /) -> int:
        return self.id

    def getcwd(self, /) -> str:
        return str(self.path)

    @overload
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> int:
        ...
    @overload
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, int):
                return id_or_path
            elif isinstance(id_or_path, (AttrDict, path_class)):
                return id_or_path["id"]
            if not id_or_path or id_or_path == ".":
                if pid is None:
                    return self.id
                return pid
            if id_or_path == "/":
                return 0
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_, **kwargs)
            return attr["id"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> str:
        ...
    @overload
    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, (AttrDict, path_class)):
                return str(id_or_path["path"])
            elif isinstance(id_or_path, int):
                id = id_or_path
                if id == 0:
                    return "/"
                attr = yield partial(self.attr, id, pid=pid, async_=async_, **kwargs)
                return str(attr["path"])
            if isinstance(id_or_path, (str, PathLike)):
                patht, parent = splits(fspath(id_or_path))
            else:
                if id_or_path:
                    patht = [id_or_path[0], *(p for p in id_or_path[1:] if p)]
                else:
                    patht = []
                parent = 0
            if patht and patht[0] == "":
                return joins(patht)
            if pid is None:
                ppath = str(self.path)
            else:
                attr = yield partial(self.attr, pid, async_=async_, **kwargs)
                ppath = str(attr["path"])
            if not (patht or parent):
                return ppath
            ppatht = splits(ppath)[0]
            if parent:
                ppatht = ppatht[1:-parent]
            return joins([*ppatht, *patht])
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> list[str]:
        ...
    @overload
    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, (AttrDict, path_class)):
                return splits(str(id_or_path["path"]))[0]
            elif isinstance(id_or_path, int):
                id = id_or_path
                if id == 0:
                    return [""]
                attr = yield partial(self.attr, id, pid=pid, async_=async_, **kwargs)
                return splits(str(attr["path"]))[0]
            if isinstance(id_or_path, (str, PathLike)):
                patht, parent = splits(fspath(id_or_path))
            else:
                if id_or_path:
                    patht = [id_or_path[0], *(p for p in id_or_path[1:] if p)]
                else:
                    patht = []
                parent = 0
            if patht and patht[0] == "":
                return patht
            if pid is None:
                ppatht = splits(str(self.path))[0]
            else:
                attr = yield partial(self.attr, pid, async_=async_, **kwargs)
                ppatht = splits(str(attr["path"]))[0]
            if not (patht or parent):
                return ppatht
            if parent:
                ppatht = ppatht[1:-parent]
            ppatht.extend(patht)
            return ppatht
        return run_gen_step(gen_step, async_=async_)

    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[P115PathType]:
        ...
    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[P115PathType]:
        ...
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[P115PathType] | AsyncIterator[P115PathType]:
        if pattern == "*":
            return self.iter(dirname, async_=async_)
        elif len(pattern) >= 2 and not pattern.strip("*"):
            return self.iter(dirname, max_depth=-1, async_=async_)
        def gen_step():
            nonlocal pattern, dirname
            if not pattern:
                try:
                    yield Yield(partial(self.as_path, dirname, async_=async_))
                except FileNotFoundError:
                    pass
                return
            elif not pattern.lstrip("/"):
                return Yield(self.as_path(0))
            splitted_pats = tuple(translate_iter(pattern, allow_escaped_slash=allow_escaped_slash))
            if pattern.startswith("/"):
                attr = self.attr(0)
                pid = 0
                dirname = "/"
            else:
                attr = yield self.attr(dirname, async_=async_)
                pid = cast(int, attr["id"])
                dirname = str(attr["path"])
            i = 0
            subpath = ""
            if ignore_case:
                if any(typ == "dstar" for _, typ, _ in splitted_pats):
                    pattern = "".join(
                        "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                        for pat, typ, _ in splitted_pats
                    )
                    if dirname != "/":
                        pattern = re_escape(dirname) + pattern
                    match = re_compile("(?i:%s)" % pattern).fullmatch
                    yield YieldFrom(self.iter(
                        attr, 
                        max_depth=-1, 
                        predicate=lambda p: match(str(p["path"])) is not None, 
                        async_=async_, 
                    ))
                    return
            else:
                typ = None
                for i, (pat, typ, orig) in enumerate(splitted_pats):
                    if typ != "orig":
                        break
                    subpath = joinpath(subpath, orig)
                if typ == "orig":
                    try:
                        yield Yield(partial(
                            self.as_path, 
                            subpath, 
                            pid=pid, 
                            async_=async_, 
                        ))
                    except FileNotFoundError:
                        pass
                    return
                elif typ == "dstar" and i + 1 == len(splitted_pats):
                    return YieldFrom(self.iter(
                        subpath, 
                        pid=pid, 
                        max_depth=-1, 
                        async_=async_, 
                    ))
                if any(typ == "dstar" for _, typ, _ in splitted_pats[i:]):
                    pattern = "".join(
                        "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                        for pat, typ, _ in splitted_pats[i:]
                    )
                    if dirname != "/":
                        pattern = re_escape(dirname) + pattern
                    match = re_compile(pattern).fullmatch
                    return YieldFrom(self.iter(
                        subpath, 
                        pid=pid, 
                        max_depth=-1, 
                        predicate=lambda p: match(p.path) is not None, 
                        async_=async_, 
                    ))
            cref_cache: dict[int, Callable] = {}
            if subpath:
                try:
                    path = yield partial(
                        self.as_path, 
                        subpath, 
                        pid=pid, 
                        async_=async_, 
                    )
                except FileNotFoundError:
                    return
            else:
                path = self.as_path(attr)
            if not path.is_dir():
                return
            def glob_step_match(path: P115PathType, i: int):
                j = i + 1
                at_end = j == len(splitted_pats)
                pat, typ, orig = splitted_pats[i]
                if typ == "orig":
                    try:
                        subpath = yield path.joinpath(orig, async_=async_)
                    except FileNotFoundError:
                        return
                    if at_end:
                        yield Yield(subpath)
                    elif subpath.is_dir():
                        yield from glob_step_match(subpath, j)
                elif typ == "star":
                    if at_end:
                        yield YieldFrom(path.iter(async_=async_))
                    else:
                        subpaths = yield path.listdir_path(async_=async_)
                        for subpath in subpaths:
                            if subpath.is_dir():
                                yield from glob_step_match(subpath, j)
                else:
                    subpaths = yield path.listdir_path(async_=async_)
                    for subpath in subpaths:
                        try:
                            cref = cref_cache[i]
                        except KeyError:
                            if ignore_case:
                                pat = "(?i:%s)" % pat
                            cref = cref_cache[i] = re_compile(pat).fullmatch
                        if cref(subpath.name):
                            if at_end:
                                yield Yield(subpath)
                            elif subpath.is_dir():
                                yield from glob_step_match(subpath, j)
            yield from glob_step_match(path, i)
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def hash(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> tuple[int, HashObj | T]:
        ...
    @overload
    def hash(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, tuple[int, HashObj | T]]:
        ...
    def hash(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> tuple[int, HashObj | T] | Coroutine[Any, Any, tuple[int, HashObj | T]]:
        def gen_step():
            url = yield self.get_url(
                id_or_path, 
                pid=pid, 
                headers=headers, 
                async_=async_, 
            )
            return (yield self.client.hash(
                url, 
                digest=digest, 
                start=start, 
                stop=stop, 
                headers=headers, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def hashes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        async_: Literal[False] = False, 
    ) -> tuple[int, list[HashObj | T]]:
        ...
    @overload
    def hashes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        ...
    def hashes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        pid: None | int = None, 
        async_: Literal[False, True] = False, 
    ) -> tuple[int, list[HashObj | T]] | Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        def gen_step():
            url = yield self.get_url(
                id_or_path, 
                pid=pid, 
                headers=headers, 
                async_=async_, 
            )
            return (yield self.client.hashes(
                url, 
                digest, 
                *digests, 
                start=start, 
                stop=stop, 
                headers=headers, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, path_class):
                return id_or_path["is_directory"]
            try:
                attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
                return attr["is_directory"]
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_=async_)

    @overload
    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, path_class):
                return not id_or_path["is_directory"]
            try:
                attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
                return not attr["is_directory"]
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_=async_)

    @overload
    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        "路径是否为空文件或空目录"
        def gen_step():
            try:
                attr = yield self.attr(id_or_path, pid=pid, async_=async_)
            except FileNotFoundError:
                return True
            if attr["is_directory"]:
                return (yield self.dirlen(id_or_path, pid=pid, async_=async_)) == 0
            else:
                return attr["size"] == 0
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        ...
    @overload
    def iter_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[P115PathType]:
        ...
    def iter_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType] | AsyncIterator[P115PathType]:
        def gen_step():
            nonlocal min_depth, max_depth
            dq: deque[tuple[int, P115PathType]] = deque()
            push, pop = dq.append, dq.popleft
            try:
                path = yield self.as_path(top, pid=pid, async_=async_)
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
                return
            push((0, path))
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
                        yield Yield(path)
                        if pred is 1:
                            return
                    min_depth = 1
                if depth == 0 and (not path.is_dir() or 0 <= max_depth <= depth):
                    return
                depth += 1
                try:
                    subpaths = yield self.listdir_path(path, async_=async_, **kwargs)
                    for path in subpaths:
                        if predicate is None:
                            pred = True
                        else:
                            pred = yield partial(predicate, path)
                        if pred is None:
                            continue
                        elif pred:
                            if depth >= min_depth:
                                yield Yield(path)
                            if pred is 1:
                                continue
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
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        ...
    @overload
    def iter_dfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[P115PathType]:
        ...
    def iter_dfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType] | AsyncIterator[P115PathType]:
        def gen_step():
            nonlocal top, min_depth, max_depth
            if not max_depth:
                return
            global_yield_me: Literal[1, False, True] = True
            if min_depth > 1:
                global_yield_me = False
                min_depth -= 1
            elif min_depth <= 0:
                path = yield self.as_path(top, pid=pid, async_=async_)
                if predicate is None:
                    pred = True
                else:
                    pred = yield partial(predicate, path)
                if pred is None:
                    return
                elif pred:
                    yield Yield(path)
                    if pred is 1:
                        return
                if path.is_file():
                    return
                min_depth = 1
                top = path.id
            if max_depth > 0:
                max_depth -= 1
            try:
                subpaths = yield self.listdir_path(top, pid=pid, async_=async_, **kwargs)
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
                    yield Yield(path)
                if yield_me is not 1 and path.is_dir():
                    yield YieldFrom(self.iter_dfs(
                        path, 
                        topdown=topdown, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        predicate=predicate, 
                        onerror=onerror, 
                        async_=async_, 
                        **kwargs, 
                    ))
                if yield_me and not topdown:
                    yield Yield(path)
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        ...
    @overload
    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[P115PathType]:
        ...
    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType] | AsyncIterator[P115PathType]:
        if topdown is None:
            return self.iter_bfs(
                top, 
                pid=pid, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                async_=async_, # type: ignore
                **kwargs, 
            )
        else:
            return self.iter_dfs(
                top, 
                pid=pid, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                async_=async_, # type: ignore
                **kwargs, 
            )

    @overload
    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> list[str]:
        ...
    @overload
    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        if async_:
            async def request():
                if full_path:
                    return [str(attr["path"]) async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)]
                else:
                    return [attr["name"] async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)]
            return request()
        elif full_path:
            return [str(attr["path"]) for attr in self.iterdir(id_or_path, pid=pid, **kwargs)]
        else:
            return [attr["name"] for attr in self.iterdir(id_or_path, pid=pid, **kwargs)]

    @overload
    def listdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> list[AttrDict]:
        ...
    @overload
    def listdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, list[AttrDict]]:
        ...
    def listdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> list[AttrDict] | Coroutine[Any, Any, list[AttrDict]]:
        if async_:
            async def request():
                return [attr async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs)]
            return request()
        else:
            return list(self.iterdir(id_or_path, pid=pid, **kwargs))

    @overload
    def listdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> list[P115PathType]:
        ...
    @overload
    def listdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> Coroutine[Any, Any, list[P115PathType]]:
        ...
    def listdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> list[P115PathType] | Coroutine[Any, Any, list[P115PathType]]:
        path_class = type(self).path_class
        if async_:
            async def request():
                return [path_class(self, attr) async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs)]
            return request()
        else:
            return [path_class(self, attr) for attr in self.iterdir(id_or_path, pid=pid, **kwargs)]

    @overload
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["r", "rt", "tr", "rb", "br"] = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> HTTPFileReader | BufferedReader | TextIOWrapper:
        ...
    @overload
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["r", "rt", "tr", "rb", "br"] = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncHTTPFileReader | AsyncBufferedReader | AsyncTextIOWrapper:
        ...
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["r", "rt", "tr", "rb", "br"] = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] | type[AsyncHTTPFileReader] = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> HTTPFileReader | BufferedReader | TextIOWrapper | AsyncHTTPFileReader | AsyncBufferedReader | AsyncTextIOWrapper:
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        url = self.get_url(id_or_path, pid=pid, headers=headers, async_=async_)
        return self.client.open(
            url, # type: ignore
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
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
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        stop: None | int = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        stop: None | int = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        stop: None | int = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        def gen_step():
            url = yield partial(self.get_url, id_or_path, pid=pid, async_=async_)
            return (yield partial(
                self.client.read_bytes, 
                url, 
                start=start, 
                stop=stop, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_bytes_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_bytes_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        def gen_step():
            url = yield partial(self.get_url, id_or_path, pid=pid, async_=async_)
            return (yield partial(
                self.client.read_bytes_range, 
                url, 
                bytes_range=bytes_range, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        size: int = 0, 
        offset: int = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bytes:
        ...
    @overload
    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        size: int = 0, 
        offset: int = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        size: int = 0, 
        offset: int = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        def gen_step():
            if size <= 0:
                return b""
            url = yield partial(self.get_url, id_or_path, pid=pid, async_=async_)
            return (yield partial(
                self.client.read_block, 
                url, 
                size=size, 
                start=offset, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            bio = BytesIO((yield partial(
                self.read_bytes_range, 
                id_or_path, 
                pid=pid, 
                async_=async_, 
            )))
            tio = TextIOWrapper(
                bio, 
                encoding=encoding or "utf-8", 
                errors=errors, 
                newline=newline, 
            )
            return tio.read()
        return run_gen_step(gen_step, async_=async_)

    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[P115PathType]:
        ...
    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[P115PathType]:
        ...
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[P115PathType] | AsyncIterator[P115PathType]:
        if not pattern:
            return self.iter(dirname, max_depth=-1, async_=async_)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(
            pattern, 
            dirname, 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
            async_=async_, 
        )

    @overload
    def scandir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        ...
    @overload
    def scandir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[P115PathType]:
        ...
    def scandir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType] | AsyncIterator[P115PathType]:
        path_class = type(self).path_class
        if async_:
            return async_map(
                path_class, 
                self.iterdir(id_or_path, pid=pid, async_=True, **kwargs), 
                threaded=False, 
            )
        else:
            return map(path_class, self.iterdir(id_or_path, pid=pid, **kwargs))

    @overload
    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> stat_result:
        ...
    @overload
    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, stat_result]:
        ...
    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> stat_result | Coroutine[Any, Any, stat_result]:
        raise UnsupportedOperation(
            errno.ENOSYS, 
            "`stat()` is currently not supported, use `attr()` instead."
        )

    def tree(
        self, 
        top: IDOrPathType = "", 
        /, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], Any] = False, 
        predicate: None | Callable[[AttrDict], Literal[None, 1, False, True]] = None, 
        pid: None | int = None, 
        _depth: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        def gen_step():
            can_step_in: bool = max_depth < 0 or _depth < max_depth
            if _depth == 0 and min_depth <= 0:
                print(".")
            try:
                subattrs = yield self.listdir_attr(top, pid=pid, async_=async_)
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
            pred: Literal[None, 1, False, True] = True
            next_depth = _depth + 1
            for attr, nattr in pairwise(chain(subattrs, (None,))):
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
                if can_step_in and attr["is_directory"]:
                    yield self.tree(
                        attr, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        onerror=onerror, 
                        predicate=predicate, 
                        pid=pid, 
                        _depth=next_depth, 
                        async_=async_, 
                    )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def walk_attr_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    @overload
    def walk_attr_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        def gen_step():
            attr = yield self.attr(top, pid=pid, async_=async_)
            dq: deque[tuple[int, AttrDict]] = deque([(0, attr)])
            push, pop = dq.append, dq.popleft
            while dq:
                depth, parent = pop()
                depth += 1
                try:
                    iter_me = min_depth <= 0 or depth >= min_depth
                    push_me = max_depth < 0 or depth < max_depth
                    if iter_me or push_me:
                        subattrs = yield self.listdir_attr(parent, async_=async_, **kwargs)
                        if iter_me:
                            dirs: list[AttrDict] = []
                            files: list[AttrDict] = []
                            for attr in subattrs:
                                if attr["is_directory"]:
                                    dirs.append(attr)
                                    if push_me:
                                        push((depth, attr))
                                else:
                                    files.append(attr)
                            yield Yield((str(parent["path"]), dirs, files))
                        else:
                            for attr in subattrs:
                                if attr["is_directory"]:
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
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    @overload
    def walk_attr_dfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr_dfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        def gen_step():
            nonlocal min_depth, max_depth
            if not max_depth:
                return
            if min_depth > 0:
                min_depth -= 1
            if max_depth > 0:
                max_depth -= 1
            yield_me = min_depth <= 0
            try:
                subattrs = yield self.listdir_attr(top, pid=pid, async_=async_, **kwargs)
            except OSError as e:
                if callable(onerror):
                    yield partial(onerror, e)
                elif onerror:
                    raise
                return
            dirs: list[AttrDict] = []
            files: list[AttrDict] = []
            for attr in subattrs:
                if attr["is_directory"]:
                    dirs.append(attr)
                else:
                    files.append(attr)
            parent_path = yield self.get_path(top, pid=pid, async_=async_)
            if yield_me and topdown:
                yield Yield((parent_path, dirs, files))
            for attr in dirs:
                yield YieldFrom(self.walk_attr_dfs(
                    attr, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    async_=async_, 
                ))
            if yield_me and not topdown:
                yield Yield((parent_path, dirs, files))
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        ...
    @overload
    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[str], list[str]]]:
        ...
    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[str], list[str]]] | AsyncIterator[tuple[str, list[str], list[str]]]:
        if async_:
            return (
                (path, [a["name"] for a in dirs], [a["name"] for a in files])
                async for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    async_=True, 
                    **kwargs, 
                )
            )
        else:
            return (
                (path, [a["name"] for a in dirs], [a["name"] for a in files])
                for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    **kwargs, 
                )
            )

    @overload
    def walk_attr(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    @overload
    def walk_attr(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        ...
    def walk_attr(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]] | AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        if topdown is None:
            return self.walk_attr_bfs(
                top, 
                pid=pid, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                async_=async_, # type: ignore
                **kwargs, 
            )
        else:
            return self.walk_attr_dfs(
                top, 
                pid=pid, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                async_=async_, # type: ignore
                **kwargs, 
            )

    @overload
    def walk_path(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[P115PathType], list[P115PathType]]]:
        ...
    @overload
    def walk_path(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[P115PathType], list[P115PathType]]]:
        ...
    def walk_path(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[P115PathType], list[P115PathType]]] | AsyncIterator[tuple[str, list[P115PathType], list[P115PathType]]]:
        path_class = type(self).path_class
        if async_:
            return (
                (path, [path_class(self, a) for a in dirs], [path_class(self, a) for a in files])
                async for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    async_=True, 
                    **kwargs, 
                )
            )
        else:
            return (
                (path, [path_class(self, a) for a in dirs], [path_class(self, a) for a in files])
                for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    **kwargs, 
                )
            )

    dict = dictdir_path
    list = listdir_path
    readdir = listdir

    cd = chdir
    pwd = getcwd
    ls = listdir
    la = listdir_attr
    ll = listdir_path

