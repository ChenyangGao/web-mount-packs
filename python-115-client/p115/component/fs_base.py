#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "P115PathBase", "P115FileSystemBase", 
    "AttrDict", "IDOrPathType", "P115FSType", "P115PathType", 
]

import errno

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import (
    AsyncIterator, Callable, Coroutine, Iterable, Iterator, ItemsView, KeysView, Mapping, 
    Sequence, ValuesView, 
)
from functools import cached_property, partial
from io import BytesIO, TextIOWrapper, UnsupportedOperation
from inspect import isawaitable
from itertools import chain, pairwise
from mimetypes import guess_type
from os import fsdecode, fspath, lstat, makedirs, scandir, stat, stat_result, PathLike
from os import path as ospath
from posixpath import join as joinpath, splitext
from re import compile as re_compile, escape as re_escape
from stat import S_IFDIR, S_IFREG # TODO: common stat method
from time import time
from typing import (
    overload, cast, Any, Generic, IO, Literal, Never, Self, TypeAlias, TypeVar, 
)
from types import MappingProxyType
from urllib.parse import parse_qsl, urlparse

from asynctools import async_map
from download import DownloadTask
from filewrap import SupportsWrite
from glob_pattern import translate_iter
from httpfile import HTTPFileReader
from iterutils import run_gen_step
from posixpatht import basename, commonpath, dirname, escape, joins, normpath, splits, unescape

from .client import check_response, P115Client, P115Url


AttrDict: TypeAlias = dict # TODO: TypedDict with extra keys
IDOrPathType: TypeAlias = int | str | PathLike[str] | Sequence[str] | AttrDict
P115FSType = TypeVar("P115FSType", bound="P115FileSystemBase")
P115PathType = TypeVar("P115PathType", bound="P115PathBase")
CRE_115URL_EXPIRE_TS_search = re_compile("(?<=\?t=)[0-9]+").search


class P115PathBase(Generic[P115FSType], Mapping, PathLike[str]):
    id: int
    path: str
    fs: P115FSType

    def __init__(self, /, attr: AttrDict):
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> Self:
        attr = self.fs.attr(commonpath((self.path, self.fs.abspath(path))))
        return type(self)(attr)

    def __call__(self, /) -> Self:
        super().__setattr__("__dict__", self.fs.attr(self.id))
        return self

    def __contains__(self, key, /) -> bool:
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self.id == path.id

    def __fspath__(self, /) -> str:
        return self.path

    def __ge__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client: 
            return False
        return self.id >= self.id

    def __getitem__(self, key, /):
        return self.__dict__[key]

    def __gt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return self.id > path.id

    def __hash__(self, /) -> int:
        return hash((self.fs.client, self.id))

    def __index__(self, /) -> int:
        return self.id

    def __iter__(self, /) -> Iterator[str]:
        return iter(self.__dict__)

    def __le__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return self.id <= self.id

    def __len__(self, /) -> int:
        return len(self.__dict__)

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
        return f"{name}({self.__dict__})"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attributes")

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> Self:
        return self.joinpath(path)

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

    # TODO: 支持异步
    def download(
        self, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: None | bool | Callable[[Callable], Any] = None, 
        no_root: bool = False, 
        predicate: None | Callable[[P115PathType], bool] = None, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
    ) -> Iterator[tuple[P115PathType, str, DownloadTask]]:
        return self.fs.download_tree(
            self, 
            local_dir, 
            write_mode=write_mode, 
            submit=submit, 
            no_root=no_root, 
            predicate=predicate, 
            onerror=onerror, 
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
        return self.fs.exists(self, async_=async_)

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
            attr = yield partial(self.fs.attr, self["id"], async_=async_)
            self.__dict__.clear()
            self.__dict__.update(attr)
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> P115Url:
        ...
    @overload
    def get_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, P115Url]:
        ...
    def get_url(
        self, 
        /, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> P115Url | Coroutine[Any, Any, P115Url]:
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
            return type(self)(attr)
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
        get_attr = self.fs.attr
        if async_:
            async def wrap():
                for a in reversed(self["ancestors"][:-1]):
                    yield cls(await get_attr(a["id"], async_=True))
            return wrap()
        else:
            return (cls(get_attr(a["id"])) for a in reversed(self["ancestors"][:-1]))

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

    def is_absolute(self, /) -> bool:
        return True

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
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Self], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[Self]:
        ...
    @overload
    def iter(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Self], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[Self]:
        ...
    def iter(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Self], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.fs.iter(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
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
        *names: str, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def join(
        self, 
        *names: str, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def join(
        self, 
        *names: str, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            if not names:
                return self
            attr = yield partial(self.fs.attr, names, pid=self.id, async_=async_)
            return type(self)(attr)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def joinpath(
        self, 
        *paths: str | PathLike[str], 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def joinpath(
        self, 
        *paths: str | PathLike[str], 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def joinpath(
        self, 
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
            return type(self)(attr)
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
        pattern = "/" + "/".join(
            t[0] for t in translate_iter(
                path_pattern, allow_escaped_slash=allow_escaped_slash))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

    @cached_property
    def media_type(self, /) -> None | str:
        if not self.is_file():
            return None
        return guess_type(self.path)[0] or "application/octet-stream"

    @cached_property
    def name(self, /) -> str:
        return basename(self.path)

    # TODO: 支持异步
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

    @cached_property
    def parent(self, /) -> Self:
        if self.id == 0:
            return self
        return type(self)(self.fs.attr(self["parent_id"]))

    @cached_property
    def parents(self, /) -> tuple[Self, ...]:
        cls = type(self)
        get_attr = self.fs.attr
        return tuple(cls(get_attr(a["id"])) for a in reversed(self["ancestors"][:-1]))

    @cached_property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *splits(self.path, do_unescape=False)[0][1:])

    @cached_property
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
        if size <= 0:
            return b""
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

    def relative_to(self, other: str | Self, /) -> str:
        if type(self) is type(other):
            other = cast(Self, other)
            other = other.path
        elif not cast(str, other).startswith("/"):
            other = self.fs.abspath(other)
        other = cast(str, other)
        path = self.path
        if path == other:
            return ""
        elif path.startswith(other+"/"):
            return path[len(other)+1:]
        raise ValueError(f"{path!r} is not in the subpath of {other!r}")

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
        return type(self)(self.fs.attr(0))

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if type(self) is type(path):
            return self == path
        return path in ("", ".") or self.path == self.fs.abspath(path)

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
    def url(self, /) -> P115Url:
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

    def with_name(self, name: str, /) -> Self:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> Self:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> Self:
        return self.parent.joinpath(self.stem + suffix)

    list = listdir_path
    dict = dictdir_path


class P115FileSystemBase(Generic[P115PathType]):
    client: P115Client
    id: int
    path: str
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

    def __eq__(self, other) -> bool:
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
    ) -> P115Url:
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
    ) -> Coroutine[Any, Any, P115Url]:
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
    ) -> P115Url | Coroutine[Any, Any, P115Url]:
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
        return self.get_path(path, pid=self.id, async_=async_)

    @overload
    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False] = False, 
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
                )
            attr["fs"] = self
            return path_class(attr)
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
                    return {attr["id"]: attr["path"] async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)}
                else:
                    return {attr["id"]: attr["name"] async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)}
            return request()
        elif full_path:
            return {attr["id"]: attr["path"] for attr in self.iterdir(id_or_path, pid=pid, **kwargs)}
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
                return {attr["id"]: path_class(attr) async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs)}
            return request()
        else:
            return {attr["id"]: path_class(attr) for attr in self.iterdir(id_or_path, pid=pid, **kwargs)}

    # TODO: 支持异步
    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        local_path_or_file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        pid: None | int = None, 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit: bool | Callable[[Callable], Any] = True, 
    ) -> None | DownloadTask:
        if not isinstance(local_path_or_file, SupportsWrite):
            path = cast(bytes | str | PathLike, local_path_or_file)
            if not path:
                path = self.attr(id_or_path, pid=pid)["name"]
            if ospath.lexists(path):
                if write_mode == "x":
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"local path already exists: {path!r}", 
                    )
                elif write_mode == "i":
                    return None
        kwargs: dict = {"resume": write_mode == "a"}
        if callable(submit):
            kwargs["submit"] = submit
        task = DownloadTask.create_task(
            lambda: self.get_url(id_or_path, pid=pid), 
            local_path_or_file, 
            headers=lambda: {
                **self.client.headers, 
                "Cookie": "; ".join(f"{c.name}={c.value}" for c in self.client.cookiejar), 
            }, 
            **kwargs, 
        )
        if callable(submit):
            task.run()
        elif submit:
            task.run_wait()
        return task

    # TODO: 支持异步
    def download_tree(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        local_dir: bytes | str | PathLike = "", 
        pid: None | int = None, 
        write_mode: Literal["i", "x", "w", "a"] = "a", 
        submit: None | bool | Callable[[Callable], Any] = None, 
        no_root: bool = False, 
        predicate: None | Callable[[P115PathType], bool] = None, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
    ) -> Iterator[tuple[P115PathType, str, DownloadTask]]:
        local_dir = fsdecode(local_dir)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        attr = self.attr(id_or_path, pid=pid)
        pathes: Iterable[P115PathType]
        if attr["is_directory"]:
            if not no_root:
                local_dir = ospath.join(local_dir, attr["name"])
                if local_dir:
                    makedirs(local_dir, exist_ok=True)
            pathes = self.scandir(attr["id"])
        else:
            path_class = type(self).path_class
            attr["fs"] = self
            pathes = (path_class(attr),)
        mode: Literal["i", "x", "w", "a"]
        for subpath in filter(predicate, pathes):
            if subpath["is_directory"]:
                yield from self.download_tree(
                    subpath["id"], 
                    ospath.join(local_dir, subpath["name"]), 
                    write_mode=write_mode, 
                    no_root=True, 
                    predicate=predicate, 
                    onerror=onerror, 
                )
            else:
                mode = write_mode
                try:
                    download_path = ospath.join(local_dir, subpath["name"])
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
                    task = self.download(
                        subpath["id"], 
                        download_path, 
                        write_mode=mode, 
                        submit=False if submit is None else submit, 
                    )
                except KeyboardInterrupt:
                    raise
                except BaseException as exc:
                    if onerror is None or onerror is True:
                        raise
                    elif callable(onerror):
                        onerror(exc)
                else:
                    if task is not None:
                        yield subpath, download_path, task
                        if submit is None:
                            task.run_wait()

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
        if async_:
            if full_path:
                return (attr["path"] async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs))
            else:
                return (attr["name"] async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs))
        elif full_path:
            return (attr["path"] for attr in self.iterdir(id_or_path, pid=pid, **kwargs))
        else:
            return (attr["name"] for attr in self.iterdir(id_or_path, pid=pid, **kwargs))

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
        return self.path

    @overload
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
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
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
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
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
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
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, (AttrDict, path_class)):
                return id_or_path["path"]
            elif isinstance(id_or_path, int):
                id = id_or_path
                if id == 0:
                    return "/"
                attr = yield partial(self.attr, id, pid=pid, async_=async_)
                return attr["path"]
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
                ppath = self.path
            else:
                attr = yield partial(self.attr, pid, async_=async_)
                ppath = attr["path"]
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
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, (AttrDict, path_class)):
                return splits(id_or_path["path"])[0]
            elif isinstance(id_or_path, int):
                id = id_or_path
                if id == 0:
                    return [""]
                attr = yield partial(self.attr, id, pid=pid, async_=async_)
                return splits(attr["path"])[0]
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
                ppatht = splits(self.path)[0]
            else:
                attr = yield partial(self.attr, pid, async_=async_)
                ppatht = splits(attr["path"])[0]
            if not (patht and parent):
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
        async def to_async_iter(it):
            for i in it:
                yield i
        def to_iter(it, async_: bool = False):
            if async_:
                return to_async_iter(it)
            else:
                return iter(it)
        def gen_step():
            nonlocal pattern
            if pattern == "*":
                return self.iter(dirname, async_=async_)
            elif pattern == "**":
                return self.iter(dirname, max_depth=-1, async_=async_)
            path_class = type(self).path_class
            if not pattern:
                try:
                    attr = yield partial(self.attr, dirname, async_=async_)
                except FileNotFoundError:
                    return to_iter((), async_=async_)
                else:
                    return to_iter((path_class(attr),), async_=async_)
            elif not pattern.lstrip("/"):
                return to_iter((path_class(self.attr(0)),), async_=async_)
            splitted_pats = tuple(translate_iter(
                pattern, 
                allow_escaped_slash=allow_escaped_slash, 
            ))
            dirname_as_id = isinstance(dirname, (int, AttrDict, path_class))
            dirid: int
            if dirname_as_id:
                if isinstance(dirname, int):
                    dirid = dirname
                else:
                    dirid = dirname["id"] # type: ignore
            if pattern.startswith("/"):
                dir_ = "/"
            else:
                dir_ = yield partial(self.get_path, dirname, async_=async_)
            i = 0
            dir2 = ""
            if ignore_case:
                if any(typ == "dstar" for _, typ, _ in splitted_pats):
                    pattern = joinpath(re_escape(dir_), "/".join(t[0] for t in splitted_pats))
                    match = re_compile("(?i:%s)" % pattern).fullmatch
                    return self.iter(
                        dirname, 
                        max_depth=-1, 
                        predicate=lambda p: match(p.path) is not None, 
                        async_=async_, 
                    )
            else:
                typ = None
                for i, (pat, typ, orig) in enumerate(splitted_pats):
                    if typ != "orig":
                        break
                    dir2 = joinpath(dir2, orig)
                dir_ = joinpath(dir_, dir2)
                if typ == "orig":
                    try:
                        if dirname_as_id:
                            attr = yield partial(self.attr, dir2, pid=dirid, async_=async_)
                        else:
                            attr = yield partial(self.attr, dir_, async_=async_)
                    except FileNotFoundError:
                        return to_iter((), async_=async_)
                    else:
                        return to_iter((path_class(attr),), async_=async_)
                elif typ == "dstar" and i + 1 == len(splitted_pats):
                    if dirname_as_id:
                        return self.iter(dir2, pid=dirid, max_depth=-1, async_=async_)
                    else:
                        return self.iter(dir_, max_depth=-1, async_=async_)
                if any(typ == "dstar" for _, typ, _ in splitted_pats):
                    pattern = joinpath(re_escape(dir_), "/".join(t[0] for t in splitted_pats[i:]))
                    match = re_compile(pattern).fullmatch
                    if dirname_as_id:
                        return self.iter(
                            dir2, 
                            pid=dirid, 
                            max_depth=-1, 
                            predicate=lambda p: match(p.path) is not None, 
                            async_=async_, 
                        )
                    else:
                        return self.iter(
                            dir_, 
                            max_depth=-1, 
                            predicate=lambda p: match(p.path) is not None, 
                            async_=async_, 
                        )
            cref_cache: dict[int, Callable] = {}
            if dirname_as_id:
                attr = yield partial(self.attr, dir2, pid=dirid, async_=async_)
            else:
                attr = yield partial(self.attr, dir_, async_=async_)
            if not attr["is_directory"]:
                return to_iter((), async_=async_)
            if async_:
                async def glob_step_match(path, i):
                    j = i + 1
                    at_end = j == len(splitted_pats)
                    pat, typ, orig = splitted_pats[i]
                    if typ == "orig":
                        subpath = path.joinpath(orig)
                        if at_end:
                            yield subpath
                        elif subpath["is_directory"]:
                            async for val in glob_step_match(subpath, j):
                                yield val
                    elif typ == "star":
                        if at_end:
                            async for val in path.iter(async_=True):
                                yield val
                        else:
                            async for subpath in path.iter(async_=True):
                                if subpath["is_directory"]:
                                    async for val in glob_step_match(subpath, j):
                                        yield val
                    else:
                        async for subpath in path.iter(async_=True):
                            try:
                                cref = cref_cache[i]
                            except KeyError:
                                if ignore_case:
                                    pat = "(?i:%s)" % pat
                                cref = cref_cache[i] = re_compile(pat).fullmatch
                            if cref(subpath["name"]):
                                if at_end:
                                    yield subpath
                                elif subpath["is_directory"]:
                                    async for val in glob_step_match(subpath, j):
                                        yield val
            else:
                def glob_step_match(path, i):
                    j = i + 1
                    at_end = j == len(splitted_pats)
                    pat, typ, orig = splitted_pats[i]
                    if typ == "orig":
                        subpath = path.joinpath(orig)
                        if at_end:
                            yield subpath
                        elif subpath["is_directory"]:
                            yield from glob_step_match(subpath, j)
                    elif typ == "star":
                        if at_end:
                            yield from path.iter()
                        else:
                            for subpath in path.iter():
                                if subpath["is_directory"]:
                                    yield from glob_step_match(subpath, j)
                    else:
                        for subpath in path.iter():
                            try:
                                cref = cref_cache[i]
                            except KeyError:
                                if ignore_case:
                                    pat = "(?i:%s)" % pat
                                cref = cref_cache[i] = re_compile(pat).fullmatch
                            if cref(subpath["name"]):
                                if at_end:
                                    yield subpath
                                elif subpath["is_directory"]:
                                    yield from glob_step_match(subpath, j)
            return glob_step_match(path_class(attr), i)
        if async_:
            async def wrap():
                async for attr in (await run_gen_step(gen_step, async_=True)):
                    yield attr
            return wrap()
        else:
            return run_gen_step(gen_step)

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

    def _iter_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        dq: deque[tuple[int, P115PathType]] = deque()
        push, pop = dq.append, dq.popleft
        path_class = type(self).path_class
        path = self.as_path(top, pid=pid)
        push((0, path))
        while dq:
            depth, path = pop()
            if min_depth <= 0:
                pred = predicate(path) if predicate else True
                if pred is None:
                    return
                elif pred:
                    yield path
                    if pred is 1:
                        return
                min_depth = 1
            if depth == 0 and (not path.is_dir() or 0 <= max_depth <= depth):
                return
            depth += 1
            try:
                for attr in self.iterdir(path, **kwargs):
                    path = path_class(attr)
                    pred = predicate(path) if predicate else True
                    if pred is None:
                        continue
                    elif pred:
                        if depth >= min_depth:
                            yield path
                        if pred is 1:
                            continue
                    if path.is_dir() and (max_depth < 0 or depth < max_depth):
                        push((depth, path))
            except OSError as e:
                if callable(onerror):
                    onerror(e)
                elif onerror:
                    raise

    async def _iter_bfs_async(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> AsyncIterator[P115PathType]:
        dq: deque[tuple[int, P115PathType]] = deque()
        push, pop = dq.append, dq.popleft
        path_class = type(self).path_class
        path = await self.as_path(top, pid=pid, async_=True)
        push((0, path))
        while dq:
            depth, path = pop()
            if min_depth <= 0:
                pred = predicate(path) if predicate else True
                if isawaitable(pred):
                    pred = await pred
                if pred is None:
                    return
                elif pred:
                    yield path
                    if pred is 1:
                        return
                min_depth = 1
            if depth == 0 and (not path.is_dir() or 0 <= max_depth <= depth):
                return
            depth += 1
            try:
                async for attr in self.iterdir(path, async_=True, **kwargs):
                    path = path_class(attr)
                    pred = predicate(path) if predicate else True
                    if isawaitable(pred):
                        pred = await pred
                    if pred is None:
                        continue
                    elif pred:
                        if depth >= min_depth:
                            yield path
                        if pred is 1:
                            continue
                    if path.is_dir() and (max_depth < 0 or depth < max_depth):
                        push((depth, path))
            except OSError as e:
                if callable(onerror):
                    ret = onerror(e)
                    if isawaitable(ret):
                        await ret
                elif onerror:
                    raise

    def _iter_dfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        if not max_depth:
            return
        global_yield_me: Literal[1, False, True] = True
        if min_depth > 1:
            global_yield_me = False
            min_depth -= 1
        elif min_depth <= 0:
            path = self.as_path(top, pid=pid)
            pred = predicate(path) if predicate else True
            if pred is None:
                return
            elif pred:
                yield path
                if pred is 1:
                    return
            if path.is_file():
                return
            min_depth = 1
            top = path.id
        if max_depth > 0:
            max_depth -= 1
        path_class = type(self).path_class
        try:
            for attr in self.iterdir(top, pid=pid, **kwargs):
                path = path_class(attr)
                yield_me = global_yield_me
                if yield_me and predicate:
                    pred = predicate(path)
                    if pred is None:
                        continue
                    yield_me = pred 
                if yield_me and topdown:
                    yield path
                if yield_me is not 1 and path.is_dir():
                    yield from self._iter_dfs(
                        path, 
                        topdown=topdown, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        predicate=predicate, 
                        onerror=onerror, 
                    )
                if yield_me and not topdown:
                    yield path
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise

    async def _iter_dfs_async(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> AsyncIterator[P115PathType]:
        if not max_depth:
            return
        global_yield_me: Literal[1, False, True] = True
        if min_depth > 1:
            global_yield_me = False
            min_depth -= 1
        elif min_depth <= 0:
            path = await self.as_path(top, pid=pid, async_=True)
            pred = predicate(path) if predicate else True
            if isawaitable(pred):
                pred = await pred
            if pred is None:
                return
            elif pred:
                yield path
                if pred is 1:
                    return
            if path.is_file():
                return
            min_depth = 1
            top = path.id
        if max_depth > 0:
            max_depth -= 1
        path_class = type(self).path_class
        try:
            async for attr in self.iterdir(top, pid=pid, async_=True, **kwargs):
                path = path_class(attr)
                yield_me = global_yield_me
                if yield_me and predicate:
                    pred = predicate(path)
                    if isawaitable(pred):
                        pred = await pred
                    if pred is None:
                        continue
                    yield_me = pred 
                if yield_me and topdown:
                    yield path
                if yield_me is not 1 and path.is_dir():
                    async for subpath in self._iter_dfs_async(
                        path, 
                        topdown=topdown, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        predicate=predicate, 
                        onerror=onerror, 
                    ):
                        yield subpath
                if yield_me and not topdown:
                    yield path
        except OSError as e:
            if callable(onerror):
                ret = onerror(e)
                if isawaitable(ret):
                    await ret
            elif onerror:
                raise

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
        if async_:
            if topdown is None:
                return self._iter_bfs_async(
                    top, 
                    pid=pid, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    **kwargs, 
                )
            else:
                return self._iter_dfs_async(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    **kwargs, 
                )
        elif topdown is None:
            return self._iter_bfs(
                top, 
                pid=pid, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                **kwargs, 
            )
        else:
            return self._iter_dfs(
                top, 
                pid=pid, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
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
                    return [attr["path"] async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)]
                else:
                    return [attr["name"] async for attr in self.iterdir(
                        id_or_path, pid=pid, async_=True, **kwargs)]
            return request()
        elif full_path:
            return [attr["path"] for attr in self.iterdir(id_or_path, pid=pid, **kwargs)]
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
                return [path_class(attr) async for attr in self.iterdir(
                    id_or_path, pid=pid, async_=True, **kwargs)]
            return request()
        else:
            return [path_class(attr) for attr in self.iterdir(id_or_path, pid=pid, **kwargs)]

    # TODO: 支持异步
    def open(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        mode: str = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        pid: None | int = None, 
    ) -> HTTPFileReader | IO:
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        url = self.get_url(id_or_path, pid=pid)
        return self.client.open(
            url, 
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
        _depth: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        def gen_step():
            can_step_in: bool = max_depth < 0 or _depth < max_depth
            if _depth == 0 and min_depth <= 0:
                print(".")
            try:
                ls = yield partial(
                    self.listdir_attr, 
                    top, 
                    async_=async_, 
                )
            except OSError as e:
                if callable(onerror):
                    onerror(e)
                elif onerror:
                    raise
            pred: Literal[None, 1, False, True] = True
            next_depth = _depth + 1
            for attr, nattr in pairwise(chain(ls, (None,))):
                attr = cast(AttrDict, attr)
                if predicate is not None:
                    pred = predicate(attr)
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
                    self.tree(
                        attr, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        onerror=onerror, 
                        predicate=predicate, 
                        _depth=next_depth, 
                    )
        return run_gen_step(gen_step, async_=async_)

    def _walk_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        dq: deque[tuple[int, AttrDict]] = deque()
        push, pop = dq.append, dq.popleft
        push((0, self.attr(top, pid=pid)))
        while dq:
            depth, parent = pop()
            depth += 1
            try:
                push_me = max_depth < 0 or depth < max_depth
                if min_depth <= 0 or depth >= min_depth:
                    dirs: list[AttrDict] = []
                    files: list[AttrDict] = []
                    for attr in self.iterdir(parent, **kwargs):
                        if attr["is_directory"]:
                            dirs.append(attr)
                            if push_me:
                                push((depth, attr))
                        else:
                            files.append(attr)
                    yield parent["path"], dirs, files
                elif push_me:
                    for attr in self.iterdir(parent, **kwargs):
                        if attr["is_directory"]:
                            push((depth, attr))
            except OSError as e:
                if callable(onerror):
                    onerror(e)
                elif onerror:
                    raise

    async def _walk_bfs_async(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        dq: deque[tuple[int, AttrDict]] = deque()
        push, pop = dq.append, dq.popleft
        attr = await self.attr(top, pid=pid, async_=True)
        push((0, attr))
        while dq:
            depth, parent = pop()
            depth += 1
            try:
                push_me = max_depth < 0 or depth < max_depth
                if min_depth <= 0 or depth >= min_depth:
                    dirs: list[AttrDict] = []
                    files: list[AttrDict] = []
                    async for attr in self.iterdir(parent, async_=True, **kwargs):
                        if attr["is_directory"]:
                            dirs.append(attr)
                            if push_me:
                                push((depth, attr))
                        else:
                            files.append(attr)
                    yield parent["path"], dirs, files
                elif push_me:
                    async for attr in self.iterdir(parent, async_=True, **kwargs):
                        if attr["is_directory"]:
                            push((depth, attr))
            except OSError as e:
                if callable(onerror):
                    ret = onerror(e)
                    if isawaitable(ret):
                        await ret
                elif onerror:
                    raise

    def _walk_dfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        if not max_depth:
            return
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        try:
            dirs: list[AttrDict] = []
            files: list[AttrDict] = []
            for attr in self.iterdir(top, pid=pid, **kwargs):
                if attr["is_directory"]:
                    dirs.append(attr)
                else:
                    files.append(attr)
            if yield_me and topdown:
                yield self.get_path(top, pid=pid), dirs, files
            for attr in dirs:
                yield from self._walk_dfs(
                    attr, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                )
            if yield_me and not topdown:
                yield self.get_path(top, pid=pid), dirs, files
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise

    async def _walk_dfs_async(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> AsyncIterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        if not max_depth:
            return
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        try:
            dirs: list[AttrDict] = []
            files: list[AttrDict] = []
            async for attr in self.iterdir(top, pid=pid, async_=True, **kwargs):
                if attr["is_directory"]:
                    dirs.append(attr)
                else:
                    files.append(attr)
            if yield_me and topdown:
                parent = await self.get_path(top, pid=pid, async_=True)
                yield parent, dirs, files
            for attr in dirs:
                async for subattr in self._walk_dfs_async(
                    attr, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                ):
                    yield subattr
            if yield_me and not topdown:
                parent = await self.get_path(top, pid=pid, async_=True)
                yield parent, dirs, files
        except OSError as e:
            if callable(onerror):
                ret = onerror(e)
                if isawaitable(ret):
                    await ret
            elif onerror:
                raise

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
            async def request():
                async for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    async_=True, 
                    **kwargs, 
                ):
                    yield path, [a["name"] for a in dirs], [a["name"] for a in files]
        else:
            def request():
                for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    **kwargs, 
                ):
                    yield path, [a["name"] for a in dirs], [a["name"] for a in files]
        return request()

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
        if async_:
            if topdown is None:
                return self._walk_bfs_async(
                    top, 
                    pid=pid, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    **kwargs, 
                )
            else:
                return self._walk_dfs_async(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    **kwargs, 
                )
        elif topdown is None:
            return self._walk_bfs(
                top, 
                pid=pid, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                **kwargs, 
            )
        else:
            return self._walk_dfs(
                top, 
                pid=pid, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
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
            async def request():
                async for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    async_=True, 
                    **kwargs, 
                ):
                    yield path, [path_class(a) for a in dirs], [path_class(a) for a in files]
        else:
            def request():
                for path, dirs, files in self.walk_attr(
                    top, 
                    pid=pid, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    **kwargs, 
                ):
                    yield path, [path_class(a) for a in dirs], [path_class(a) for a in files]
        return request()

    list = listdir_path
    dict = dictdir_path

    cd = chdir
    pwd = getcwd
    ls = listdir
    la = listdir_attr
    ll = listdir_path

