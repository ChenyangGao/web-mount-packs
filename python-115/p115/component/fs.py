#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Path", "P115FileSystem"]

import errno

from asyncio import Lock as AsyncLock
from collections import deque, UserString
from collections.abc import (
    AsyncIterable, AsyncIterator, Callable, Coroutine, ItemsView, Iterable, Iterator, 
    Mapping, Sequence, 
)
from functools import cached_property, partial
from io import BytesIO, TextIOWrapper
from itertools import accumulate, cycle, islice
from json import JSONDecodeError
from os import path as ospath, fspath, remove, rmdir, scandir, stat_result, PathLike
from pathlib import Path
from posixpath import splitext
from shutil import SameFileError
from stat import S_IFDIR, S_IFREG
from threading import Lock
from time import time
from typing import cast, overload, Any, Literal, Self, SupportsIndex
from uuid import uuid4
from warnings import warn
from weakref import WeakValueDictionary

from dictattr import AttrDict
from filewrap import Buffer, SupportsRead
from http_request import SupportsGeturl
from iterutils import run_gen_step, run_gen_step_iter, Yield, YieldFrom
from p115client import check_response, normalize_attr, P115URL
from posixpatht import escape, joins, normpath, split, splits, path_is_dir_form
from yarl import URL

from .client import P115Client
from .fs_base import IDOrPathType, P115PathBase, P115FileSystemBase


class LRUDict(dict):

    def __init__(self, /, maxsize: int = 0):
        self.maxsize = maxsize

    def __setitem__(self, key, value, /):
        self.pop(key, None)
        super().__setitem__(key, value)
        self.clean()

    def clean(self, /):
        if (maxsize := self.maxsize) > 0:
            pop = self.pop
            while len(self) > maxsize:
                try:
                    pop(next(iter(self)), None)
                except RuntimeError:
                    pass

    def setdefault(self, key, default=None, /):
        value = super().setdefault(key, default)
        self.clean()
        return value

    def update(self, iterable=None, /, **pairs):
        pop = self.pop
        setitem = self.__setitem__
        if iterable:
            if isinstance(iterable, Mapping):
                try:
                    iterable = iterable.items()
                except (AttributeError, TypeError):
                    iterable = ItemsView(iterable)
            for key, val in iterable:
                pop(key, None)
                setitem(key, val)
        if pairs:
            for key, val in pairs.items():
                pop(key, None)
                setitem(key, val)
        self.clean()


class AttrDictWithAncestors(AttrDict):

    def __contains__(self, key, /) -> bool:
        if key == "ancestors":
            return True
        return super().__contains__(key)

    def __iter__(self, /):
        yield from super().__iter__()
        if not super().__contains__("ancestors"):
            yield "ancestors"

    def __getitem__(self, key, /):
        match key:
            case "ancestor_path":
                return super().__getitem__("path")
            case "path":
                return str(super().__getitem__("path"))
            case "ancestors":
                if super().__contains__("ancestors"):
                    return super().__getitem__(key)
                else:
                    return super().__getitem__("path").ancestors
            case _:
                return super().__getitem__(key)

    def __getattr__(self, attr, /):
        if attr == "ancestors":
            return self["ancestors"]
        raise AttributeError(attr)


class Ancestor(dict[str, int | str]):

    def __init__(
        self, 
        /, 
        id: int, 
        name: str, 
        parent_id: int = 0, 
        is_directory: bool = True, 
        parent: None | Self = None, 
    ):
        super().__init__(
            id=id, 
            name=name, 
            parent_id=parent_id, 
            is_directory=is_directory, 
        )
        self.parent = parent

    def __bool__(self, /) -> bool:
        return True

    def __eq__(self, value, /) -> bool:
        return self is value or super().__eq__(value)

    def __getitem__(self, key, /):
        if isinstance(key, SupportsIndex):
            if not isinstance(key, int):
                key = key.__index__()
            if key < 0:
                ancestor = self
                for _ in range(key, -1):
                    ancestor = ancestor.parent # type: ignore
                    if ancestor is None:
                        raise IndexError(key)
                return ancestor
            return self.ancestors[key]
        elif isinstance(key, slice):
            return self.ancestors[key]
        return super().__getitem__(key)

    def __getattr__(self, attr, /):
        try:
            return self[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __hash__(self, /) -> int: # type: ignore
        return id(self)

    def __str__(self, /) -> str:
        return str(self.path)

    @property
    def ancestors(self, /) -> list[Self]:
        if self["id"] == 0 or self.parent is None:
            return [self]
        ancestors = self.parent.ancestors
        ancestors.append(self)
        return ancestors

    @cached_property
    def ancestor_path(self, /) -> P115AncestorPath:
        return P115AncestorPath(self)

    @property
    def path(self, /) -> str:
        if self["id"] == 0 or self.parent is None:
            return "/"
        return joins(self.patht)

    @property
    def patht(self, /) -> list[str]:
        if self["id"] == 0 or self.parent is None:
            return [""]
        return [a["name"] for a in self.ancestors]


class P115AncestorPath(UserString):
    __slots__ = "self"
    __class__ = str # type: ignore

    def __init__(self, _self: Ancestor, /):
        self.self = _self

    def __hash__(self, /) -> int:
        return id(self)

    def __getattr__(self, attr, /):
        return getattr(self.self, attr)

    @property
    def data(self, /) -> str:
        return self.self.path

    @data.setter
    def data(self, value, /):
        raise TypeError("can't set data property")


class P115Path(P115PathBase):
    fs: P115FileSystem

    @property
    def ancestors(self, /) -> list[Ancestor]:
        try:
            return self["ancestors"]
        except KeyError:
            ancestors = self.fs.get_ancestors(self.id)
            self.attr["path"] = ancestors[-1].ancestor_path
            return ancestors

    @property
    def path(self, /) -> str:
        try:
            return self["path"]
        except KeyError:
            return self.ancestors[-1].path

    @property
    def length(self, /):
        if self.is_dir():
            return self.fs.dirlen(self.id)
        return self["size"]

    @property
    def desc(self, /):
        return self.fs.desc(self)

    @desc.setter
    def desc(self, /, desc: str = ""):
        return self.fs.desc(self, desc=desc)

    @property
    def score(self, /) -> bool:
        return self["score"]

    @score.setter
    def score(self, /, score: bool = True):
        self.fs.score(self, score=score)

    @property
    def star(self, /) -> bool:
        return self["star"]

    @star.setter
    def star(self, /, star: bool = True):
        self.fs.star(self, star=star)

    @overload
    def copy(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
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
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | Self]:
        ...
    def copy(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | Self | Coroutine[Any, Any, None | Self]:
        def gen_step():
            attr = yield self.fs.copy(
                self, 
                dst_path, 
                pid=pid, 
                overwrite=overwrite, 
                onerror=onerror, 
                recursive=True, 
                async_=async_, 
            )
            if attr is None:
                return None
            return type(self)(self.fs, attr)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def count(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def count(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def count(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "文件夹中的项目数（直属的文件和目录计数）"
        if self["is_directory"]:
            return self.fs.count(self, async_=async_)
        else:
            return self.fs.count(self["parent_id"], async_=async_)

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
            return type(self)(
                self.fs, 
                (yield self.fs.makedirs(
                    self, 
                    exist_ok=exist_ok, 
                    async_=async_, 
                )), 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def move(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def move(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def move(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            attr = yield partial(
                self.fs.move, 
                self, 
                dst_path, 
                pid=pid, 
                async_=async_, 
            )
            self.__dict__.clear()
            self.__dict__.update(attr)
            return self
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        recursive: bool = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def remove(
        self, 
        /, 
        recursive: bool = True, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def remove(
        self, 
        /, 
        recursive: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        return self.fs.remove(
            self, 
            recursive=recursive, 
            async_=async_, 
        )

    @overload
    def rename(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def rename(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def rename(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            attr = yield partial(
                self.fs.rename, 
                self, 
                dst_path, 
                pid=pid, 
                async_=async_, 
            )
            self.__dict__.clear()
            self.__dict__.update(attr)
            return self
        return run_gen_step(gen_step, async_=async_)

    @overload
    def renames(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def renames(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def renames(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            attr = yield partial(
                self.fs.renames, 
                self, 
                dst_path, 
                pid=pid, 
                async_=async_, 
            )
            self.__dict__.clear()
            self.__dict__.update(attr)
            return self
        return run_gen_step(gen_step, async_=async_)

    @overload
    def replace(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> Self:
        ...
    @overload
    def replace(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def replace(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            attr = yield partial(
                self.fs.replace, 
                self, 
                dst_path, 
                pid=pid, 
                async_=async_, 
            )
            self.__dict__.clear()
            self.__dict__.update(attr)
            return self
        return run_gen_step(gen_step, async_=async_)

    @overload
    def rmdir(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def rmdir(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def rmdir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        return self.fs.rmdir(self, async_=async_)

    @overload
    def search(
        self, 
        /, 
        async_: Literal[False] = False, 
        **payload, 
    ) -> Iterator[P115Path]:
        ...
    @overload
    def search(
        self, 
        /, 
        async_: Literal[True], 
        **payload, 
    ) -> AsyncIterator[P115Path]:
        ...
    def search(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **payload, 
    ) -> Iterator[P115Path] | AsyncIterator[P115Path]:
        return self.fs.search(self, async_=async_, **payload)

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
            return type(self)(
                self.fs, 
                (yield partial(
                    self.fs.touch, 
                    self, 
                    async_=async_, 
                )), 
            )
        return run_gen_step(gen_step, async_=async_)

    unlink = remove

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
            return type(self)(
                self.fs, 
                (yield self.fs.write_bytes(
                    self, 
                    data, 
                    async_=async_, 
                )), 
            )
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
            return type(self)(
                self.fs, 
                (yield self.fs.write_text(
                    self, 
                    text, 
                    encoding=encoding, 
                    errors=errors, 
                    newline=newline, 
                    async_=async_, 
                )), 
            )
        return run_gen_step(gen_step, async_=async_)

    cp = copy
    mv = move
    rm = remove


class P115FileSystem(P115FileSystemBase[P115Path]):
    id_to_attr: WeakValueDictionary[int, AttrDict]
    id_to_ancestor: WeakValueDictionary[int, Ancestor]
    id_to_readdir: None | dict[int, dict[int, AttrDict]] = None
    path_to_id: None | dict[str, int] = None
    refresh: bool = True
    path_class = P115Path
    root_ancestor: Ancestor = Ancestor(id=0, name="")

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        password: str = "", 
        cache_id_to_readdir: bool | int = False, 
        cache_path_to_id: bool | int = False, 
        refresh: bool = True, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        super().__init__(client, request, async_request)

        def make_cache(cache_size):
            if not cache_size:
                return None
            elif cache_size is True or cache_size < 0:
                return {}
            else:
                return LRUDict(cache_size)

        self._iterdir_locks: WeakValueDictionary[int, AttrDictWithAncestors] = WeakValueDictionary()
        self.__dict__.update(
            id = 0, 
            path = "/", 
            password = password, 
            id_to_attr = WeakValueDictionary(), 
            id_to_ancestor = WeakValueDictionary(), 
            id_to_readdir = make_cache(cache_id_to_readdir), 
            path_to_id = make_cache(cache_path_to_id), 
            refresh = refresh, 
        )

    def __delitem__(self, id_or_path: IDOrPathType, /):
        self.rmtree(id_or_path)

    def __len__(self, /) -> int:
        return self.dirlen(self.id)

    def __setitem__(
        self, 
        id_or_path: IDOrPathType, 
        file: ( None | str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] ), 
        /, 
    ):
        if file is None:
            return self.touch(id_or_path)
        elif isinstance(file, PathLike):
            if ospath.isdir(file):
                return list(self.upload_tree(file, id_or_path, no_root=True, overwrite=True))
            else:
                return self.upload(file, id_or_path, overwrite=True)
        elif isinstance(file, str):
            return self.write_text(id_or_path, file)
        else:
            return self.write_bytes(id_or_path, file)

    @property
    def password(self, /) -> str:
        return self.__dict__["password"]

    @password.setter
    def password(self, /, password: str = ""):
        self.__dict__["password"] = password

    @overload
    def fs_mkdir(
        self, 
        name: str, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        name: str, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir(
        self, 
        name: str, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.fs_mkdir( # type: ignore
            {"cname": name, "pid": pid}, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def fs_copy(
        self, 
        id: int | Iterable[int], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        id: int | Iterable[int], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        id: int | Iterable[int], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.fs_copy( # type: ignore
            id, 
            pid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def fs_delete(
        self, 
        id: int | Iterable[int], 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_delete(
        self, 
        id: int | Iterable[int], 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_delete(
        self, 
        id: int | Iterable[int], 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.fs_delete( # type: ignore
            id, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def fs_move(
        self, 
        id: int | Iterable[int], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        id: int | Iterable[int], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        id: int | Iterable[int], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.fs_move( # type: ignore
            id, 
            pid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def fs_rename(
        self, 
        pair: tuple[int, str] | Iterable[tuple[int, str]], 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        pair: tuple[int, str] | Iterable[tuple[int, str]], 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        pair: tuple[int, str] | Iterable[tuple[int, str]], 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.fs_rename( # type: ignore
            pair, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def fs_file(
        self, 
        id: int, 
        /, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_file(
        self, 
        id: int, 
        /, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_file(
        self, 
        id: int, 
        /, 
        *, 
        _g = cycle((True, False)).__next__, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        def gen_step():
            resp = yield self.client.fs_file(
                {"file_id": id}, 
                base_url=_g(), 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            if resp["state"]:
                return resp
            match resp["code"]:
                # {'state': False, 'code': 20018, 'message': '文件不存在或已删除。'}
                # {'state': False, 'code': 800001, 'message': '目录不存在。'}
                case 20018 | 800001:
                    raise FileNotFoundError(errno.ENOENT, resp)
                # {'state': False, 'code': 990002, 'message': '参数错误。'}
                case 990002:
                    raise OSError(errno.EINVAL, resp)
                case _:
                    raise OSError(errno.EIO, resp)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_file_skim(
        self, 
        id: int, 
        /, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_file_skim(
        self, 
        id: int, 
        /, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_file_skim(
        self, 
        id: int, 
        /, 
        *, 
        _g = cycle((True, False)).__next__, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        def gen_step():
            resp = yield partial(
                self.client.fs_file_skim, 
                id, 
                base_url=_g(), 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            if resp["state"]:
                return resp
            if resp.get("error") == "文件不存在":
                raise FileNotFoundError(errno.ENOENT, resp)
            raise OSError(errno.EIO, resp)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_files(
        self, 
        payload: None | int | dict = None, 
        /, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_files(
        self, 
        payload: None | int | dict = None, 
        /, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files(
        self, 
        payload: None | int | dict = None, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if payload is None:
            id = self.id
            payload = {"cid": id}
        elif isinstance(payload, int):
            id = payload
            payload = {"cid": id}
        else:
            id = int(payload["cid"])
        def gen_step():
            resp = yield self.client.fs_files_app(
                payload, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            resp = check_response(resp)
            if int(resp["path"][-1]["cid"]) != id:
                raise NotADirectoryError(errno.ENOTDIR, f"{id!r} is not a directory")
            return resp
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_search(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_search(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        if isinstance(payload, str):
            payload = {"cid": self.id, "search_value": payload}
        return check_response(self.client.fs_search( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def fs_upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] ), 
        name: str, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def fs_upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        name: str, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def fs_upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        name: str, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        if pid is None:
            pid = self.id
        def gen_step():
            nonlocal name
            resp = yield partial(
                self.client.upload_file, 
                file, 
                filename=name, 
                pid=pid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            data = resp["data"]
            if "file_id" in data:
                file_id = int(data["file_id"])
                try:
                    return (yield partial(self._attr, file_id, async_=async_))
                except FileNotFoundError:
                    yield partial(self.fs_files, {"cid": pid, "limit": 2}, async_=async_)
                    return (yield partial(self._attr, file_id, async_=async_))
            else:
                pickcode = data["pickcode"]
                try:
                    id = yield partial(
                        self.get_id_from_pickcode, 
                        pickcode, 
                        use_web_api=data["file_size"] < 1024 * 1024 * 115, 
                        async_=async_, 
                    )
                    return (yield partial(self._attr, id, async_=async_))
                except FileNotFoundError:
                    yield partial(self.fs_files, {"cid": pid, "limit": 2}, async_=async_)
                    id = yield partial(self.get_id_from_pickcode, pickcode, async_=async_)
                    return (yield partial(self._attr, id, async_=async_))
                except OSError:
                    for attr in self.iterdir(pid):
                        if attr["pickcode"] == pickcode:
                            return attr
                    raise
        return run_gen_step(gen_step, async_=async_)

    @overload
    def space_summury(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def space_summury(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def space_summury(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.fs_space_summury( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    def _clear_cache(self, attr: int | dict, /):
        if isinstance(attr, int):
            try:
                attr = cast(dict, self.id_to_attr[attr])
            except KeyError:
                return
        is_directory = attr["is_directory"]
        if id_to_readdir := self.id_to_readdir:
            if id := attr["id"]:
                try:
                    id_to_readdir[attr["parent_id"]].pop(id, None)
                except KeyError:
                    pass
            if is_directory:
                dq = deque((id,))
                get, put = dq.popleft, dq.append
                while dq:
                    if children := id_to_readdir.pop(get(), None):
                        for subid, subattr in children.items():
                            if subattr["is_directory"]:
                                put(subid)
        if path_to_id := self.path_to_id:
            if is_directory:
                startswith = str.startswith
                dirname = str(attr["path"]) + "/"
                for p in tuple(p for p in path_to_id if startswith(p, dirname)):
                    path_to_id.pop(p, None)
            else:
                path_to_id.pop(str(attr["path"]), None)

    @overload
    def _attr(
        self, 
        id: int = 0, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def _attr(
        self, 
        id: int = 0, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def _attr(
        self, 
        id: int = 0, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        def gen_step():
            nonlocal refresh

            if refresh is None:
                refresh = self.refresh
            id_to_attr = self.id_to_attr
            if not refresh and id_to_attr:
                try:
                    return id_to_attr[id]
                except KeyError:
                    pass

            if id == 0:
                resp = yield self.fs_files(
                    {"asc": 0, "cid": 0, "custom_order": 1, "fc_mix": 1, "limit": 2, "show_dir": 1, "o": "user_utime"}, 
                    async_=async_, 
                )
                now = time()
                if resp["count"] == 0:
                    mtime = 0
                else:
                    info = resp["data"][0]
                    get_key = info.get
                    mtime = int(get_key("te") or get_key("upt") or get_key("ptime") or get_key("user_ptime"))
                attr: AttrDict = AttrDictWithAncestors(
                    is_directory=True, 
                    id=0, 
                    parent_id=0, 
                    pickcode=None, 
                    name="", 
                    size=None, 
                    sha1=None, 
                    ico="folder", 
                    utime=now, 
                    mtime=mtime, 
                    user_utime=mtime, 
                    ctime=0, 
                    user_ptime=0, 
                    atime=now, 
                    user_otime=now, 
                    time=now, 
                    path=self.root_ancestor.ancestor_path, 
                )
            else:
                try:
                    resp = yield self.fs_file(id, async_=async_)
                except FileNotFoundError as e:
                    self._clear_cache(id)
                    raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}") from e
                attr = cast(AttrDictWithAncestors, normalize_attr(resp["data"][0], dict_cls=AttrDictWithAncestors))
                yield self._get_ancestors(attr, async_=async_)

            id_to_readdir = self.id_to_readdir
            pid = attr["parent_id"]
            attr_old: None | AttrDict = id_to_attr.get(id)
            if attr_old:
                path_old = str(attr_old["path"])
                if id_to_readdir and attr_old["parent_id"] != attr["parent_id"]:
                    try:
                        id_to_readdir[attr_old["parent_id"]].pop(id, None)
                    except KeyError:
                        pass
                attr_old.update(attr)
            else:
                path_old = ""
                id_to_attr[id] = attr

            if id_to_readdir is not None:
                if id:
                    id_to_readdir.setdefault(pid, {})[id] = attr
                else:
                    self.__dict__["root"] = attr

            if id:
                path_to_id = self.path_to_id
                if path_to_id is not None:
                    path = str(attr["path"])
                    is_directory = attr["is_directory"]
                    path_to_id[path + "/"[:is_directory]] = id
                    if path_old and path_old != path:
                        path_to_id.pop(path_old + "/"[:is_directory], None)

            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def _attr_path(
        self, 
        path: str | UserString | PathLike[str] | Sequence[str] = "/", 
        /, 
        pid: None | int = None, 
        ensure_dir: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def _attr_path(
        self, 
        path: str | UserString | PathLike[str] | Sequence[str] = "/", 
        /, 
        pid: None | int = None, 
        ensure_dir: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def _attr_path(
        self, 
        path: str | UserString | PathLike[str] | Sequence[str] = "/", 
        /, 
        pid: None | int = None, 
        ensure_dir: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        def gen_step():
            nonlocal path, pid, ensure_dir

            get_attr_by_id = self._attr

            if pid is None:
                pid = self.id
            if isinstance(path, PathLike):
                path = fspath(path)
            if not path or path == ".":
                return (yield get_attr_by_id(pid, async_=async_))
            parents = 0
            if isinstance(path, (str, UserString)):
                path = str(path)
                if ensure_dir is None:
                    ensure_dir = path_is_dir_form(path)
                patht, parents = splits(path)
                if not (patht or parents):
                    return (yield get_attr_by_id(pid, async_=async_))
            else:
                if ensure_dir is None:
                    ensure_dir = path[-1] == ""
                patht = [path[0], *(p for p in path[1:] if p)]
            if patht == [""]:
                return get_attr_by_id(0)
            elif patht and patht[0] == "":
                pid = 0

            ancestor_patht: list[str] = []
            if pid == 0:
                if patht[0] != "":
                    patht.insert(0, "")
            else:
                ancestors = yield self._get_ancestors(pid, async_=async_)
                if parents:
                    if parents >= len(ancestors):
                        pid = 0
                    else:
                        pid = cast(int, ancestors[-parents]["parent_id"])
                        ancestor_patht = ["", *(a["name"] for a in ancestors[1:-parents])]
                else:
                    ancestor_patht = ["", *(a["name"] for a in ancestors[1:])]
            if not patht:
                return (yield get_attr_by_id(pid, async_=async_))

            if pid == 0:
                dirname = ""
                ancestors_paths: list[str] = [(dirname := f"{dirname}/{escape(name)}") for name in patht[1:]]
                dirname = ""
                ancestors_paths2: list[str] = [(dirname := f"{dirname}/{name}") for name in patht[1:]]
                ancestors_with_slashes: tuple[int, ...] = tuple(accumulate("/" in name for name in patht[1:]))
            else:
                dirname = joins(ancestor_patht)
                ancestors_paths = [(dirname := f"{dirname}/{escape(name)}") for name in patht]
                dirname = "/".join(ancestor_patht)
                ancestors_paths2 = [(dirname := f"{dirname}/{name}") for name in patht]
                initial = sum("/" in name for name in ancestor_patht)
                ancestors_with_slashes = tuple(accumulate(("/" in name for name in patht), initial=initial))[1:]

            path_to_id = self.path_to_id
            if path_to_id:
                fullpath = ancestors_paths[-1]
                if not ensure_dir and (id := path_to_id.get(fullpath)):
                    try:
                        attr = yield get_attr_by_id(id, async_=async_)
                        if str(attr["path"]) == fullpath:
                            return attr
                        else:
                            del path_to_id[fullpath]
                    except FileNotFoundError:
                        pass
                if (id := path_to_id.get(fullpath + "/")):
                    try:
                        attr = yield get_attr_by_id(id, async_=async_)
                        if str(attr["path"]) == fullpath:
                            return attr
                        else:
                            del path_to_id[fullpath + "/"]
                    except FileNotFoundError:
                        pass

            def get_dir_id(path: str, /):
                result = check_response((yield self.client.fs_dir_getid(
                    path, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))
                id = int(result["id"])
                if id == 0:
                    raise FileNotFoundError(errno.ENOENT, f"directory {path!r} does not exist")
                if path_to_id is not None:
                    path_to_id[path + "/"] = id
                return id

            if not ancestors_with_slashes[-1]:
                try:
                    id = cast(int, (yield from get_dir_id(ancestors_paths2[-1])))
                    return (yield get_attr_by_id(id, async_=async_))
                except FileNotFoundError:
                    if ensure_dir:
                        raise

            parent: int | AttrDictWithAncestors
            for i in reversed(range(len(ancestors_paths)-1)):
                if path_to_id and (id := path_to_id.get((dirname := ancestors_paths[i]) + "/")):
                    try:
                        parent = cast(AttrDictWithAncestors, (yield get_attr_by_id(id, async_=async_)))
                        if str(parent["path"]) == dirname:
                            i += 1
                            break
                        else:
                            del path_to_id[dirname]
                    except FileNotFoundError:
                        pass
                elif not ancestors_with_slashes[i]:
                    parent = cast(int, (yield from get_dir_id(ancestors_paths2[i])))
                    i += 1
                    break
            else:
                i = 0
                parent = pid

            if pid == 0:
                i += 1

            last_idx = len(patht) - 1
            if async_:
                for i, name in enumerate(patht[i:], i):
                    async def step():
                        nonlocal attr, parent
                        async for attr in self.iterdir(parent, async_=True):
                            if attr["name"] == name:
                                if ensure_dir or i < last_idx:
                                    if attr["is_directory"]:
                                        parent = attr
                                        break
                                else:
                                    break
                        else:
                            if isinstance(parent, AttrDictWithAncestors):
                                parent = parent["id"]
                            raise FileNotFoundError(
                                errno.ENOENT, 
                                f"no such file {name!r} (in {parent} @ {joins(patht[:i])!r})", 
                            )
                    yield step
            else:
                for i, name in enumerate(patht[i:], i):
                    for attr in self.iterdir(parent):
                        if attr["name"] == name:
                            if ensure_dir or i < last_idx:
                                if attr["is_directory"]:
                                    parent = attr
                                    break
                            else:
                                break
                    else:
                        if isinstance(parent, AttrDictWithAncestors):
                            parent = parent["id"]
                        raise FileNotFoundError(
                            errno.ENOENT, 
                            f"no such file {name!r} (in {parent} @ {joins(patht[:i])!r})", 
                        )
            return attr
        return run_gen_step(gen_step, async_=async_)

    def _get_ancestors_from_response(
        self, 
        resp: None | dict = None, 
        /, 
        attr: None | dict = None, 
    ) -> list[Ancestor]:
        id_to_ancestor = self.id_to_ancestor
        path_to_id = self.path_to_id
        parent = self.root_ancestor
        ancestors: list[Ancestor] = [parent]
        if resp:
            # TODO: 检查一下 ancestors 列表，和目前已经保存的是否有差别，如果有差别，就要执行批量更新 path_to_id
            #       更新顺序应该是从路径的长到短（后往前），判断依据 1) name 2) parent_id
            #       如果已经存在错误的，就进行删除，已经存在正确的就跳过，而更新其实就是替换
            for p in resp["path"][1:]:
                cid = int(p["cid"])
                try:
                    ancestor = id_to_ancestor[cid]
                except KeyError:
                    ancestor = id_to_ancestor[cid] = Ancestor(
                        id=cid, 
                        parent_id=int(p["pid"]), 
                        name=p["name"], 
                        parent=parent, 
                    )
                else:
                    ancestor.update(parent_id=int(p["pid"]), name=p["name"])
                    ancestor.parent = parent
                ancestors.append(ancestor)
                parent = ancestor
        if attr:
            cid = attr["id"]
            if not cid:
                attr["path"] = parent.ancestor_path
                return ancestors
            try:
                ancestor = id_to_ancestor[cid]
            except KeyError:
                ancestor = id_to_ancestor[cid] = Ancestor(
                    id=cid, 
                    parent_id=attr["parent_id"], 
                    name=attr["name"], 
                    is_directory=attr["is_directory"], 
                    parent=parent, 
                )
            else:
                ancestor.update(parent_id=attr["parent_id"], name=attr["name"])
                ancestor.parent = parent
            ancestors.append(ancestor)
            attr["path"] = ancestor.ancestor_path
        if path_to_id is not None:
            path = "/"
            for ancestor in ancestors[1:]:
                path += ancestor["name"] + "/"[:ancestor["is_directory"]]
                path_to_id[path] = ancestor["id"]
        return ancestors

    @overload
    def _get_ancestors(
        self, 
        id_or_attr: int | dict = 0, 
        /, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[Ancestor]:
        ...
    @overload
    def _get_ancestors(
        self, 
        id_or_attr: int | dict = 0, 
        /, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[Ancestor]]:
        ...
    def _get_ancestors(
        self, 
        id_or_attr: int | dict = 0, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[Ancestor] | Coroutine[Any, Any, list[Ancestor]]:
        def gen_step():
            if isinstance(id_or_attr, int):
                id = id_or_attr
                attr = None
            else:
                attr = id_or_attr
                id = attr["parent_id"]
            if ancestor := self.id_to_ancestor.get(id):
                if attr is None:
                    return ancestor
                else:
                    ancestor = Ancestor(
                        id=id, 
                        parent_id=attr["parent_id"], 
                        name=attr["name"], 
                        is_directory=attr["is_directory"], 
                        parent=ancestor, 
                    )
                    attr["path"] = ancestor.ancestor_path
                    return ancestor
            elif id:
                resp = yield self.fs_files({"cid": id, "limit": 2}, async_=async_)
                return self._get_ancestors_from_response(resp, attr)
            else:
                return self._get_ancestors_from_response(None, attr)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "获取属性"
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, path_class):
                attr = id_or_path.attr
                if refresh:
                    attr = yield partial(self._attr, attr["id"], async_=async_)
            elif isinstance(id_or_path, AttrDictWithAncestors):
                attr = id_or_path
                if refresh:
                    attr = yield partial(self._attr, attr["id"], async_=async_)
            elif isinstance(id_or_path, int):
                attr = yield partial(self._attr, id_or_path, async_=async_)
            else:
                return (yield partial(
                    self._attr_path, 
                    id_or_path, 
                    pid=pid, 
                    ensure_dir=ensure_dir, 
                    async_=async_, 
                ))
            if ensure_dir and not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['id']} (id={attr['id']}) is not directory"
                )
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        start: int = 0, 
        stop: None | int = None, 
        page_size: int = 1_000, 
        order: Literal["", "file_name", "file_size", "file_type", "user_utime", "user_ptime", "user_otime"] = "file_name", 
        asc: bool = True, 
        fc_mix: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **kwargs, 
    ) -> Iterator[AttrDictWithAncestors]:
        ...
    @overload
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        start: int = 0, 
        stop: None | int = None, 
        page_size: int = 1_000, 
        order: Literal["", "file_name", "file_size", "file_type", "user_utime", "user_ptime", "user_otime"] = "file_name", 
        asc: bool = True, 
        fc_mix: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **kwargs, 
    ) -> AsyncIterator[AttrDictWithAncestors]:
        ...
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        start: int = 0, 
        stop: None | int = None, 
        page_size: int = 1_000, 
        order: Literal["", "file_name", "file_size", "file_type", "user_utime", "user_ptime", "user_otime"] = "file_name", 
        asc: bool = True, 
        fc_mix: bool = False, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **kwargs, 
    ) -> Iterator[AttrDictWithAncestors] | AsyncIterator[AttrDictWithAncestors]:
        """迭代获取目录内直属的文件或目录的信息

        :param id_or_path: id 或 路径
        :param pid: `id_or_path`是相对路径时，所在的目录 id
        :param start: 开始索引
        :param stop: 结束索引（不含）
        :param page_size: 每一次迭代，预读的数据条数
        :param order: 排序
            - "":           不排序（按照默认排序）
            - "file_name":  文件名
            - "file_size":  文件大小
            - "file_type":  文件种类
            - "user_utime": 修改时间
            - "user_ptime": 创建时间
            - "user_otime": 上次打开时间
        :param asc: 是否升序排列
        :param fc_mix: 是否目录和文件混合，如果为 False 则目录在前
        :param refresh: 是否刷新，如果为 True，则会从网上获取，而不是直接返回已缓存的数据
        :param async_: 是否异步执行

        :return: 如果`async_`为 True，返回异步迭代器，如果为 False，返回迭代器
        """
        if page_size <= 0:
            page_size = 1_000
        if refresh is None:
            refresh = self.refresh
        seen: set[int] = set()
        seen_add = seen.add
        payload: dict = {"custom_order": 1, "o": order, "asc": int(asc), "fc_mix": int(fc_mix)}

        id_to_attr = self.id_to_attr
        id_to_readdir = self.id_to_readdir
        path_to_id = self.path_to_id

        def normalize_attr2(attr, ancestor, /):
            attr = normalize_attr(attr, dict_cls=AttrDictWithAncestors)
            if (cid := attr["id"]) in seen:
                raise RuntimeError(f"{attr['parent_id']} detected count changes during iteration")
            seen_add(cid)
            is_directory = attr["is_directory"]
            attr["path"] = Ancestor(
                id=cid, 
                parent_id=attr["parent_id"], 
                name=attr["name"], 
                is_directory=is_directory, 
                parent=ancestor, 
            ).ancestor_path
            path = str(attr["path"])
            if path_to_id is not None:
                path_to_id[path + "/"[:is_directory]] = cid
            try:
                attr_old = id_to_attr[cid]
            except KeyError:
                id_to_attr[cid] = attr
            else:
                if id_to_readdir and attr_old["parent_id"] != attr["parent_id"]:
                    try:
                        id_to_readdir[attr_old["parent_id"]].pop(cid, None)
                    except KeyError:
                        pass
                if path_to_id and path != (path_old := attr_old["path"]):
                    path_to_id.pop(str(path_old) + "/"[:is_directory], None)
                attr_old.update(attr)
            return attr

        def gen_step():
            nonlocal start, stop
            if stop is not None and (start >= 0 and stop >= 0 or start < 0 and stop < 0) and start >= stop:
                return

            if isinstance(id_or_path, int):
                id = id_or_path
            else:
                id = yield self.get_id(id_or_path, pid=pid, ensure_dir=True, async_=async_)
 
            payload["cid"] = id
            payload["limit"] = page_size
            offset = int(payload.setdefault("offset", 0))
            if offset < 0:
                offset = payload["offset"] = 0

            if refresh or not id_to_readdir or id not in id_to_readdir:
                get_files = self.fs_files
                get_ancestors = self._get_ancestors_from_response
                if id_to_readdir is None:
                    def iterdir():
                        nonlocal start, stop
                        count = -1
                        if start < 0:
                            count = yield self.dirlen(id, async_=async_)
                            start += count
                            if start < 0:
                                start = 0
                        elif start >= 100:
                            count = yield self.dirlen(id, async_=async_)
                            if start >= count:
                                return
                        if stop is not None:
                            if stop < 0:
                                if count < 0:
                                    count = yield self.dirlen(id, async_=async_)
                                stop += count
                            if start >= stop or stop <= 0:
                                return
                            total = stop - start
                        payload["offset"] = start
                        if stop is not None and total < page_size:
                            payload["limit"] = total
                        resp = yield get_files(payload, async_=async_)
                        ancestor = get_ancestors(resp)[-1]
                        count = resp["count"]
                        if start >= count:
                            return
                        elif stop is None or stop > count:
                            total = count - start
                        for attr in resp["data"]:
                            yield Yield(normalize_attr2(attr, ancestor))
                        if total <= page_size:
                            return
                        for _ in range((total - 1) // page_size):
                            payload["offset"] += len(resp["data"])
                            resp = yield get_files(payload, async_=async_)
                            ancestor = get_ancestors(resp)[-1]
                            if resp["count"] != count:
                                raise RuntimeError(f"{id} detected count changes during iteration")
                            for attr in resp["data"]:
                                yield Yield(normalize_attr2(attr, ancestor))
                    return YieldFrom(run_gen_step_iter(iterdir(), async_=async_))
                else:
                    def iterdir():
                        children = id_to_readdir.get(id)
                        if children:
                            children = dict(children)
                        payload.update({"custom_order": 1, "o": "user_utime", "asc": 0, "fc_mix": 1, "offset": 0})
                        done = False
                        if children:
                            can_merge = True
                            payload["limit"] = min(16, page_size)
                            mtime_groups: dict[int, set[int]] = {}
                            for cid, item in sorted(children.items(), key=lambda t: t[1]["mtime"], reverse=True):
                                try:
                                    mtime_groups[item["mtime"]].add(cid)
                                except KeyError:
                                    mtime_groups[item["mtime"]] = {cid}
                            n = len(children)
                            it = iter(mtime_groups.items())
                            his_mtime, his_ids = next(it)
                        else:
                            can_merge = False
                            payload["limit"] = page_size

                        class Break(Exception):
                            pass

                        def process(resp, /):
                            nonlocal can_merge, done, his_mtime, his_ids, n 
                            attr: AttrDictWithAncestors
                            for info in resp["data"]:
                                attr = normalize_attr2(info, ancestor)
                                if can_merge:
                                    cur_mtime = attr["mtime"]
                                    try:
                                        while his_mtime > cur_mtime:
                                            if children:
                                                for id in his_ids:
                                                    children.pop(id, None)
                                            n -= len(his_ids)
                                            if not n:
                                                can_merge = False
                                                raise Break
                                            his_mtime, his_ids = next(it)
                                        if his_mtime == cur_mtime:
                                            cur_id = attr["id"]
                                            if cur_id in his_ids:
                                                n -= 1
                                                if count - len(seen) == n:
                                                    yield Yield(attr)
                                                    for attr in cast(dict[int, AttrDictWithAncestors], children).values():
                                                        if attr["id"] not in seen:
                                                            yield Yield(attr)
                                                    done = True
                                                    return
                                                his_ids.remove(cur_id)
                                    except Break:
                                        pass
                                yield Yield(attr)

                        resp = yield get_files(payload, async_=async_)
                        count = resp["count"]
                        ancestor = get_ancestors(resp)[-1]
                        yield from process(resp)
                        payload["limit"] = page_size
                        for _ in range((count - len(resp["data"]) - 1) // page_size + 1):
                            if done:
                                return
                            payload["offset"] += len(resp["data"])
                            resp = yield get_files(payload, async_=async_)
                            if resp["count"] != count:
                                raise RuntimeError(f"{id} detected count changes during iteration")
                            ancestor = get_ancestors(resp)[-1]
                            yield from process(resp)

                    if async_:
                        async def request():
                            d: AttrDictWithAncestors = AttrDictWithAncestors(lock=Lock(), alock=AsyncLock())
                            async with self._iterdir_locks.setdefault(id, d)["alock"]:
                                return {a["id"]: a async for a in run_gen_step_iter(iterdir, async_=True)}
                        children = yield request
                    else:
                        d: AttrDictWithAncestors = AttrDictWithAncestors(lock=Lock(), alock=AsyncLock())
                        with self._iterdir_locks.setdefault(id, d)["lock"]:
                            children = {a["id"]: a for a in run_gen_step_iter(iterdir, async_=False)}
                    id_to_readdir[id] = children
            else:
                children = id_to_readdir[id]
            if fc_mix and not order:
                return islice(children.values(), start, stop)
            count = len(children)
            if start is None:
                start = 0
            elif start < 0:
                start += count
                if start < 0:
                    start = 0
            if stop is None:
                stop = count
            elif stop < 0:
                stop += count
            if start >= stop or stop <= 0 or start >= count:
                return
            values = list(children.values())
            if order:
                match order:
                    case "file_name":
                        key = lambda attr: attr["name"]
                    case "file_size":
                        key = lambda attr: attr.get("size") or 0
                    case "file_type":
                        key = lambda attr: (True, "") if attr["is_directory"] else (False, splitext(attr["name"])[-1])
                    case "user_utime":
                        key = lambda attr: attr["user_utime"]
                    case "user_ptime":
                        key = lambda attr: attr["user_ptime"]
                    case "user_otime":
                        key = lambda attr: attr["user_otime"]
                values.sort(key=key, reverse=not asc)
            if not fc_mix:
                values.sort(key=lambda attr: not attr["is_directory"], reverse=not asc)
            return YieldFrom(values[start:stop])
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def copy(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> None | AttrDictWithAncestors:
        ...
    @overload
    def copy(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | AttrDictWithAncestors]:
        ...
    def copy(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | AttrDictWithAncestors | Coroutine[Any, Any, None | AttrDictWithAncestors]:
        "复制文件"
        def gen_step():
            nonlocal src_path, dst_path
            try:
                src_attr = yield partial(self.attr, src_path, pid=pid, async_=async_)
                src_path = str(src_attr["path"])
                if src_attr["is_directory"]:
                    if recursive:
                        return (yield partial(
                            self.copytree, 
                            src_attr, 
                            dst_path, 
                            pid=pid, 
                            overwrite=overwrite, 
                            onerror=onerror, 
                            async_=async_, 
                        ))
                    raise IsADirectoryError(
                        errno.EISDIR, 
                        f"source path is a directory: {src_path!r} -> {dst_path!r}", 
                    )

                src_patht = yield partial(self.get_patht, src_path, async_=async_)
                *src_dirt, src_name = src_patht
                src_id = src_attr["id"]
                try:
                    dst_attr = yield partial(self.attr, dst_path, pid=pid, async_=async_)
                except FileNotFoundError:
                    if isinstance(dst_path, int):
                        raise

                    dst_patht = yield partial(self.get_patht, dst_path, pid=pid, async_=async_)
                    *dst_dirt, dst_name = dst_patht
                    dst_path = joins(dst_patht)
                    if dst_patht == src_patht[:len(dst_patht)]:
                        raise PermissionError(
                            errno.EPERM, 
                            f"copy a file to its ancestor path is not allowed: {src_path!r} -> {dst_path!r}", 
                        )
                    elif src_patht == dst_patht[:len(src_patht)]:
                        raise PermissionError(
                            errno.EPERM, 
                            f"copy a file to its descendant path is not allowed: {src_path!r} -> {dst_path!r}", 
                        )

                    if src_dirt == dst_dirt:
                        dst_pid = src_attr["parent_id"]
                    else:
                        dst_parent = yield partial(self.makedirs, dst_patht[:-1], async_=async_)
                        dst_pid = dst_parent["id"]
                else:
                    if src_id == dst_attr["id"]:
                        raise SameFileError(src_path)
                    elif dst_attr["is_directory"]:
                        raise IsADirectoryError(
                            errno.EISDIR, 
                            f"destination is a directory: {src_path!r} -> {dst_path!r}", 
                        )
                    elif overwrite:
                        yield partial(self.remove, dst_attr, async_=async_)
                    else:
                        raise FileExistsError(
                            errno.EEXIST, 
                            f"destination already exists: {src_path!r} -> {dst_path!r}", 
                        )
                    dst_pid = dst_attr["parent_id"]

                if splitext(src_name)[1] != splitext(dst_name)[1]:
                    # TODO: 专门编写一个工具函数，可以把网盘里的一个文件，秒传到网盘的另一个地方，如果文件不能被秒传，或者文件被封禁，可以直接一点点上传，但需要打开选项
                    # TODO: 如果秒传失败，但文件小于一定值，则直接上传
                    # TODO: 上面所提到的函数，可以给 rename 和 copy 所使用
                    # TODO: 增删改查函数，都增加一个timeout参数，如果系统繁忙中，可以等多少时间，也可以无限等
                    resp = yield self.client.upload_file_init(
                        filename=dst_name, 
                        filesize=src_attr["size"], 
                        filesha1=src_attr["sha1"], 
                        read_range_bytes_or_hash=lambda rng: self.read_bytes_range( # type: ignore
                            src_attr, 
                            bytes_range=rng, 
                            async_=async_, 
                        ), 
                        pid=dst_pid, 
                        request=self.async_request if async_ else self.request, 
                        async_=async_, # type: ignore
                    )
                    check_response(resp)
                    dst_name = resp["data"]["file_name"]
                    return (yield partial(
                        self.attr, 
                        [dst_name], 
                        pid=dst_pid, 
                        async_=async_, 
                    ))
                elif src_name == dst_name:
                    yield partial(self.fs_copy, src_id, dst_pid, async_=async_)
                    return (yield partial(
                        self.attr, 
                        [dst_name], 
                        pid=dst_pid, 
                        async_=async_, 
                    ))
                else:
                    resp = yield partial(self.fs_mkdir, str(uuid4()), async_=async_)
                    tempdir_id = int(resp["cid"])
                    try:
                        yield partial(self.fs_copy, src_id, tempdir_id, async_=async_)
                        dst_id = (yield partial(
                            self.attr, 
                            [src_name], 
                            pid=tempdir_id, 
                            async_=async_
                        ))["id"]
                        resp = yield partial(self.fs_rename, (dst_id, dst_name), async_=async_)
                        if resp["data"]:
                            dst_name = resp["data"][str(dst_id)]
                        yield partial(self.fs_move, dst_id, pid=dst_pid, async_=async_)
                    finally:
                        yield partial(self.fs_delete, tempdir_id, async_=async_)
                    return (yield partial(self.attr, dst_id, async_=async_))
            except OSError as e:
                if onerror is True:
                    raise
                elif onerror is False or onerror is None:
                    pass
                else:
                    onerror(e)
                return None
        return run_gen_step(gen_step, async_=async_)

    # TODO: 使用 fs_batch_* 方法，尽量加快执行速度，但是如果任务数过大（大于 5 万）而报错，则尝试对任务进行拆分
    # TODO: 删除、还原、复制、移动等操作均遵此例，也就是尽量用 batch 方法
    @overload
    def copytree(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False] = False, 
    ) -> None | AttrDictWithAncestors:
        ...
    @overload
    def copytree(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None | AttrDictWithAncestors]:
        ...
    def copytree(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | AttrDictWithAncestors | Coroutine[Any, Any, None | AttrDictWithAncestors]:
        "复制路径"
        def gen_step():
            nonlocal src_path, dst_path
            try:
                src_attr = yield partial(self.attr, src_path, pid=pid, async_=async_)
                if not src_attr["is_directory"]:
                    return (yield partial(
                        self.copy, 
                        src_attr, 
                        dst_path, 
                        pid=pid, 
                        overwrite=overwrite, 
                        onerror=onerror, 
                        async_=async_, 
                    ))

                src_id = src_attr["id"]
                src_path = str(src_attr["path"])
                src_name = src_attr["name"]
                try:
                    dst_attr = yield partial(self.attr, dst_path, pid=pid, async_=async_)
                except FileNotFoundError:
                    if isinstance(dst_path, int):
                        raise
                    dst_patht = yield partial(
                        self.get_patht, 
                        dst_path, 
                        pid=pid, 
                        async_=async_, 
                    )
                    if len(dst_patht) == 1:
                        dst_id = 0
                        dst_name = src_name
                    else:
                        dst_parent = yield partial(
                            self.makedirs, 
                            dst_patht[:-1], 
                            exist_ok=True, 
                            async_=async_, 
                        )
                        dst_id = dst_parent["id"]
                        dst_name = dst_patht[-1]
                    try:
                        if src_name == dst_name:
                            yield partial(self.fs_copy, src_id, pid=dst_id, async_=async_)
                            return (yield partial(
                                self.attr, 
                                [dst_name], 
                                pid=dst_id, 
                                async_=async_, 
                            ))
                    except (OSError, JSONDecodeError):
                        pass
                    dst_attr = yield partial(
                        self.makedirs, 
                        [dst_name], 
                        pid=dst_id, 
                        exist_ok=True, 
                        async_=async_, 
                    )
                    dst_id = dst_parent["id"]
                    dst_attrs_map = {}
                else:
                    dst_path = str(dst_attr["path"])
                    if not dst_attr["is_directory"]:
                        raise NotADirectoryError(
                            errno.ENOTDIR, 
                            f"destination path {dst_path!r} is not directory", 
                        )
                    dst_id = dst_attr["id"]
                    if src_id == dst_id:
                        raise SameFileError(src_path)
                    elif any(a["id"] == src_id for a in dst_attr["ancestors"]):
                        raise PermissionError(
                            errno.EPERM, 
                            f"copy a directory as its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
                        )
                    dst_attrs_map = {
                        a["name"]: a 
                        for a in (yield partial(self.listdir_attr, dst_id, async_=async_))
                    }

                src_attrs = yield partial(self.listdir_attr, src_id, async_=async_)
            except OSError as e:
                if onerror is True:
                    raise
                elif onerror is False or onerror is None:
                    pass
                else:
                    onerror(e)
                return None

            src_files: list[int] = []
            payload: dict = dict(pid=dst_id, overwrite=overwrite, onerror=onerror)
            for attr in src_attrs:
                payload["src_path"] = attr
                if attr["name"] in dst_attrs_map:
                    payload["dst_path"] = dst_attrs_map[attr["name"]]
                    if attr["is_directory"]:
                        yield partial(self.copytree, async_=async_, **payload)
                    else:
                        yield partial(self.copy, async_=async_, **payload)
                elif attr["is_directory"]:
                    payload["dst_path"] = [attr["name"]]
                    yield partial(self.copytree, async_=async_, **payload)
                else:
                    src_files.append(attr["id"])
            if src_files:
                for i in range(0, len(src_files), 50_000):
                    yield partial(
                        self.fs_copy, 
                        src_files[i:i+50_000], 
                        pid=dst_id, 
                        async_=async_, 
                    )
            return dst_attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def count(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def count(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def count(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "文件夹中的项目数（直属的文件和目录计数）"
        def gen_step():
            id = yield self.get_id(id_or_path, pid=pid, async_=async_)
            resp = yield self.fs_files(
                {"cid": id, "limit": 2, "folder_count": 1}, 
                async_=async_, 
            )
            return {
                "count": resp["count"], 
                "file_count": resp["file_count"], 
                "folder_count": resp["folder_count"], 
                "path": resp["path"], 
            }
        return run_gen_step(gen_step, async_=async_)

    @overload
    def desc(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        desc: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def desc(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        desc: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def desc(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        desc: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        """目录的描述文本（支持 HTML）
        :param desc: 如果为 None，返回描述文本；否则，设置文本
        """
        def gen_step():
            fid = yield self.get_id(id_or_path, pid=pid, async_=async_)
            if fid == 0:
                return ""
            if desc is None:
                return check_response((yield self.client.fs_desc(
                    fid, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))["desc"]
            else:
                return check_response((yield self.client.fs_desc_set(
                    fid, 
                    desc, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))["file_description"]
        return run_gen_step(gen_step, async_=async_)

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
        "文件夹中的项目数（直属的文件和目录计数）"
        def gen_step():
            count = yield self.count(id_or_path, pid=pid, async_=async_)
            return count["count"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[Ancestor]:
        ...
    @overload
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[Ancestor]]:
        ...
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[Ancestor] | Coroutine[Any, Any, list[Ancestor]]:
        "获取各个上级目录的少量信息（从根目录到当前目录）"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            return attr["ancestors"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_id_from_pickcode(
        self, 
        /, 
        pickcode: str = "", 
        use_web_api: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def get_id_from_pickcode(
        self, 
        /, 
        pickcode: str = "", 
        use_web_api: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_id_from_pickcode(
        self, 
        /, 
        pickcode: str = "", 
        use_web_api: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int | Coroutine[Any, Any, int]:
        "由 pickcode 获取 id（通过下载接口获取）"
        def gen_step():
            if not pickcode:
                return 0
            info = yield partial(
                self.get_info_from_pickcode, 
                pickcode, 
                use_web_api=use_web_api, 
                async_=async_, 
            )
            return info["id"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_info_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def get_info_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def get_info_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "由 pickcode 获取一些目录信息（通过下载接口获取）"
        def gen_step():
            resp = yield partial(
                self.client.download_url, 
                pickcode, 
                strict=False, 
                use_web_api=use_web_api, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return resp.__dict__
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
        if isinstance(id_or_path, int) and self.id_to_readdir is None:
            def gen_step():
                patht = yield self.get_patht(id_or_path, async_=async_)
                return joins(patht)
            return run_gen_step(gen_step, async_=async_)
        return super().get_path(id_or_path, pid=pid, async_=async_)

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
        if isinstance(id_or_path, int) and self.id_to_readdir is None:
            def gen_step():
                id = id_or_path
                ls = [""]
                if id:
                    resp = yield self.fs_files({"cid": id, "limit": 2}, async_=async_)
                    if int(resp["path"][-1]["cid"]) == id:
                        ls.extend(p["name"] for p in resp["path"][1:])
                    else:
                        resp = yield self.fs_file(id, async_=async_)
                        info = resp["data"][0]
                        pid, name = int(info["cid"]), info["n"]
                        if pid:
                            resp = yield self.fs_files({"cid": pid, "limit": 2}, async_=async_)
                            ls.extend(p["name"] for p in resp["path"][1:])
                        ls.append(name)
                return ls
            return run_gen_step(gen_step, async_=async_)
        return super().get_patht(id_or_path, pid=pid, async_=async_)

    @overload
    def get_pickcode(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def get_pickcode(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_pickcode(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        "获取 pickcode"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            return attr.get("pickcode", "")
        return run_gen_step(gen_step, async_=async_)

    @overload
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
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        "获取下载链接"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            if attr["is_directory"]:
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"{attr['path']!r} (id={attr['id']!r}) is a directory", 
                )
            return (yield partial(
                self.client.download_url, 
                attr["pickcode"], 
                use_web_api=attr.get("violated", False) and attr["size"] < 1024 * 1024 * 115, 
                headers=headers, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_url_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> P115URL:
        ...
    @overload
    def get_url_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def get_url_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        "由 pickcode 获取下载链接"
        return self.client.download_url(
            pickcode, 
            use_web_api=use_web_api, 
            headers=headers, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        )

    # TODO: 如果超过 5 万个文件，则需要分批进入隐藏模式
    @overload
    def hide(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        show: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def hide(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        show: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def hide(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        show: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        "把路径隐藏或显示（如果隐藏，只能在隐藏模式中看到）"
        def gen_step():
            if show is None:
                attr = yield self.attr(id_or_path, pid=pid, async_=async_)
                return attr["hidden"]
            else:
                fid = yield self.get_id(id_or_path, pid=pid, async_=async_)
                if fid == 0:
                    return False
                hidden = not show
                resp = yield self.client.fs_hide(
                    {"hidden": int(hidden), "fid[0]": fid}, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )
                check_response(resp)
                return hidden
        return run_gen_step(gen_step, async_=async_)

    @overload
    def hidden_mode(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def hidden_mode(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def hidden_mode(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        "是否进入隐藏模式"
        def gen_step():
            resp = yield partial(
                self.client.user_setting, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return resp["data"]["show"] == "1"
        return run_gen_step(gen_step, async_=async_)

    @overload
    def hidden_switch(
        self, 
        /, 
        show: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def hidden_switch(
        self, 
        /, 
        show: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def hidden_switch(
        self, 
        /, 
        show: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "切换隐藏模式，如果需要进入隐藏模式，需要提供密码"
        def gen_step():
            nonlocal show
            if show is None:
                show = not (yield partial(self.hidden_mode, async_=async_))
            resp = yield partial(
                self.client.fs_hidden_switch, 
                {
                    "show": int(show), 
                    "safe_pwd": password or self.password, 
                }, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return check_response(resp)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter_repeat(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        page_size: int = 1150, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[AttrDictWithAncestors]:
        ...
    @overload
    def iter_repeat(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        page_size: int = 1150, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[AttrDictWithAncestors]:
        ...
    def iter_repeat(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        page_size: int = 1150, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AttrDictWithAncestors] | AsyncIterator[AttrDictWithAncestors]:
        "获取重复文件（不含当前这个）"
        if page_size <= 0:
            page_size = 1150
        def gen_step():
            payload: dict = {
                "file_id": (yield self.get_id(id_or_path, pid=pid, async_=async_)), 
                "offset": 0, 
                "limit": page_size, 
                "format": "json", 
            }
            request = partial(
                self.client.fs_repeat_sha1, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            while True:
                resp = yield request(payload)
                data = check_response(resp)["data"]
                yield YieldFrom(data)
                if len(data) < page_size:
                    break
                payload["offset"] += page_size
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def labels(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        labels: None | int | str | Iterable[int | str] = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def labels(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        labels: None | int | str | Iterable[int | str] = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def labels(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        labels: None | int | str | Iterable[int | str] = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        """文件或目录的标签（请提前创建好相关的标签）
        :param labels: 分成几种情况
            - 如果为 None，返回标签列表
            - 如果为 int (标签 id) 或 str（标签名称），增加此标签
            - 如果为 tuple，替换为所罗列的标签
            - 如果为 Iterable，增加所罗列的标签
        """
        def gen_step():
            attr = yield self.attr(id_or_path, pid=pid, async_=async_)
            if attr["id"] == 0:
                return []
            attr_labels = attr["labels"]
            if labels is None:
                pass
            elif isinstance(labels, (int, str)):
                label = yield self.client.label.get(labels, async_=async_)
                if label is not None and label["id"] not in (l["id"] for l in attr_labels):
                    check_response((yield self.client.fs_label_set(
                        attr["id"], 
                        ",".join((*(l["id"] for l in attr_labels), label["id"])), 
                        request=self.async_request if async_ else self.request, 
                        async_=async_, 
                    )))
                    attr_labels.append(label)
            else:
                label_map = {l["id"]: l for l in self.client.label.list()}
                label_namemap = {l["name"]: l for l in label_map.values()}
                if isinstance(labels, tuple):
                    my_labels = {}
                else:
                    my_labels = {l["id"]: l for l in attr_labels}
                for key in labels:
                    my_label = (label_map if isinstance(key, int) else label_namemap)[str(key)]
                    my_labels.setdefault(my_label["id"], my_label)
                check_response((yield self.client.fs_label_set(
                    attr["id"], 
                    ",".join(my_labels), 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))
                attr_labels[:] = my_labels.values()
            return attr_labels
        return run_gen_step(gen_step, async_=async_)

    @overload
    def makedirs(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        exist_ok: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def makedirs(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        exist_ok: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def makedirs(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        exist_ok: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "创建目录，如果上级目录不存在，则会进行创建"
        def gen_step():
            nonlocal path, pid
            if isinstance(path, int):
                attr = yield partial(self.attr, path, async_=async_)
                if attr["is_directory"]:
                    return attr
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['path']!r} (id={attr['id']}) is not a directory", 
                )
            path_class = type(self).path_class
            if isinstance(path, (AttrDictWithAncestors, path_class)):
                path = str(path["path"])
            path = cast(str | PathLike | Sequence[str], path)
            if isinstance(path, (str, PathLike)):
                patht, parents = splits(fspath(path))
            else:
                patht = [p for i, p in enumerate(path) if not i or p]
                parents = 0
            if pid is None:
                pid = self.id
            elif patht[0] == "":
                pid = 0
            if not patht:
                if parents:
                    ancestors = yield partial(self.get_ancestors, pid, async_=async_)
                    idx = min(parents-1, len(ancestors))
                    pid = cast(int, ancestors[-idx]["id"])
                return (yield partial(self._attr, pid, async_=async_))
            elif patht == [""]:
                return self._attr(0)
            exists = False
            for name in patht:
                try:
                    attr = yield partial(
                        self._attr_path, 
                        [name], 
                        pid=pid, 
                        ensure_dir=True, 
                        async_=async_, 
                    )
                except FileNotFoundError:
                    exists = False
                    resp = yield partial(self.fs_mkdir, name, pid=pid, async_=async_)
                    pid = int(resp["cid"])
                    attr = yield partial(self._attr, pid, async_=async_)
                else:
                    exists = True
                    pid = cast(int, attr["id"])
            if not exist_ok and exists:
                raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) exists")
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def mkdir(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def mkdir(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def mkdir(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "创建目录"
        def gen_step():
            nonlocal path, pid
            if isinstance(path, int):
                attr = yield partial(self.attr, path, async_=async_)
                if attr["is_directory"]:
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"{attr['path']!r} (id={attr['id']}) already exists", 
                    )
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['path']!r} (id={attr['id']}) is not a directory", 
                )
            path_class = type(self).path_class
            if isinstance(path, (AttrDictWithAncestors, path_class)):
                path = str(path["path"])
            path = cast(str | PathLike | Sequence[str], path)
            if isinstance(path, (str, PathLike)):
                patht, parents = splits(fspath(path))
            else:
                patht = [p for i, p in enumerate(path) if not i or p]
                parents = 0
            if not patht or patht == [""]:
                raise OSError(errno.EINVAL, f"invalid path: {path!r}")
            if pid is None:
                pid = self.id
            elif patht[0] == "":
                pid = 0
            if parents:
                ancestors = yield partial(self.get_ancestors, pid, async_=async_)
                idx = min(parents-1, len(ancestors))
                pid = cast(int, ancestors[-idx]["id"])
            get_attr = self._attr_path
            for i, name in enumerate(patht, 1):
                try:
                    attr = yield partial(
                        get_attr, 
                        [name], 
                        pid=pid, 
                        ensure_dir=True, 
                        async_=async_, 
                    )
                except FileNotFoundError:
                    break
                else:
                    pid = cast(int, attr["id"])
            else:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"{path!r} (in {pid!r}) already exists", 
                )
            if i < len(patht):
                raise FileNotFoundError(
                    errno.ENOENT, 
                    f"{path!r} (in {pid!r}) missing superior directory", 
                )
            resp = yield partial(self.fs_mkdir, name, pid=pid, async_=async_)
            return (yield partial(self.attr, int(resp["cid"]), async_=async_))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def move(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def move(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def move(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "重命名路径，如果目标路径是目录，则移动到其中"
        def gen_step():
            nonlocal src_path, dst_path
            try:
                dst_attr = yield partial(self.attr, dst_path, pid=pid, async_=async_)
            except FileNotFoundError:
                return (yield partial(self.rename, src_path, dst_path, pid=pid, async_=async_))
            src_attr = yield partial(self.attr, src_path, pid=pid, async_=async_)
            src_id = src_attr["id"]
            dst_id = dst_attr["id"]
            if src_id == dst_id or src_attr["parent_id"] == dst_id:
                return src_attr
            src_path = str(src_attr["path"])
            dst_path = str(dst_attr["path"])
            if any(a["id"] == src_id for a in dst_attr["ancestors"]):
                raise PermissionError(
                    errno.EPERM, 
                    f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}"
                )
            if dst_attr["is_directory"]:
                return (yield partial(
                    self.rename, 
                    src_attr, 
                    [src_attr["name"]], 
                    pid=dst_attr["id"], 
                    async_=async_, 
                ))
            raise FileExistsError(
                errno.EEXIST, 
                f"destination already exists: {src_path!r} -> {dst_path!r}", 
            )
        return run_gen_step(gen_step, async_=async_)

    # TODO: 由于 115 网盘不支持删除里面有超过 5 万个文件等目录，因此执行失败时需要拆分任务
    # TODO: 就算删除和还原执行返回成功，后台可能依然在执行，需要等待几秒钟，前一批完成再执行下一批
    #       {'state': False, 'error': '删除[...]操作尚未执行完成，请稍后再试！', 'errno': 990009, 'errtype': 'war'}
    @overload
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        recursive: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        recursive: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        recursive: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "删除文件"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            id = attr["id"]
            if attr["is_directory"]:
                if not recursive:
                    raise IsADirectoryError(
                        errno.EISDIR, 
                        f"{attr['path']!r} (id={id!r}) is a directory", 
                    )
                if id == 0:
                    ls: list[AttrDictWithAncestors] = yield partial(self.listdir_attr, 0, async_=async_)
                    for subattr in ls:
                        yield partial(self.remove, subattr, recursive=True, async_=async_)
                    return attr
            yield partial(self.fs_delete, id, async_=async_)
            self._clear_cache(attr)
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def removedirs(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def removedirs(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def removedirs(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "逐级往上尝试删除空目录"
        def gen_step():
            attr = yield partial(
                self.attr, 
                id_or_path, 
                pid=pid, 
                ensure_dir=True, 
                async_=async_, 
            )
            id = attr["id"]
            delid = 0
            parent = attr
            get_files = self.fs_files
            while id:
                files = yield partial(get_files, {"cid": id, "limit": 2}, async_=async_)
                if files["count"] > 1:
                    break
                delid = id
                id = int(files["path"][-1]["pid"])
                parent = {
                    "id": delid, 
                    "parent_id": id, 
                    "name": files["path"][-1]["name"], 
                    "is_directory": True, 
                    "path": "/" + joins([p["name"] for p in files["path"][1:]]), 
                }
            if delid:
                yield partial(self.fs_delete, delid)
                self._clear_cache(parent)
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def rename(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        replace: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def rename(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        replace: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def rename(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        replace: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "重命名路径"
        def gen_step():
            nonlocal src_path, dst_path
            src_attr = yield partial(self.attr, src_path, pid=pid, async_=async_)
            src_id = src_attr["id"]
            src_path = str(src_attr["path"])
            src_patht = splits(src_path)[0]
            try:
                dst_attr = yield self.attr(dst_path, pid=pid, async_=async_)
            except FileNotFoundError:
                dst_patht = yield self.get_patht(dst_path, pid=pid, async_=async_)
                dst_path = joins(dst_patht)
                if dst_patht == src_patht[:len(dst_patht)]:
                    raise PermissionError(
                        errno.EPERM, 
                        f"rename a path to its ancestor is not allowed: {src_path!r} -> {dst_path!r}", 
                    )
                elif src_patht == dst_patht[:len(src_patht)]:
                    raise PermissionError(
                        errno.EPERM, 
                        f"rename a path to its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
                    )
                dst_parent = yield partial(self.makedirs, dst_patht[:-1], exist_ok=True, async_=async_)
                dst_pid = dst_parent["id"]
            else:
                dst_id = dst_attr["id"]
                if src_id == dst_id:
                    return dst_attr
                if replace:
                    if src_attr["is_directory"]:
                        if dst_attr["is_directory"]:
                            if (yield partial(self.dirlen, dst_attr["id"], async_=async_)):
                                raise OSError(
                                    errno.ENOTEMPTY, 
                                    f"source is directory, but destination is non-empty directory: {src_path!r} -> {dst_path!r}", 
                                )
                        else:
                            raise NotADirectoryError(
                                errno.ENOTDIR, 
                                f"source is directory, but destination is not a directory: {src_path!r} -> {dst_path!r}", 
                            )
                    elif dst_attr["is_directory"]:
                        raise IsADirectoryError(
                            errno.EISDIR, 
                            f"source is file, but destination is directory: {src_path!r} -> {dst_path!r}", 
                        )
                    yield partial(self.fs_delete, dst_id, async_=async_)
                else:
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"destination already exists: {src_path!r} -> {dst_path!r}", 
                    )
                dst_pid = dst_attr["parent_id"]
                dst_path = str(dst_attr["path"])
                dst_patht = splits(dst_path)[0]

            *src_dirt, src_name = src_patht
            *dst_dirt, dst_name = dst_patht
            src_ext = splitext(src_name)[1]
            dst_ext = splitext(dst_name)[1]

            if src_dirt == dst_dirt and (src_attr["is_directory"] or src_ext == dst_ext):
                yield partial(self.fs_rename, (src_id, dst_name), async_=async_)
            elif src_name == dst_name:
                yield partial(self.fs_move, src_id, dst_pid, async_=async_)
            elif src_attr["is_directory"]:
                yield partial(self.fs_rename, (src_id, str(uuid4())), async_=async_)
                try:
                    yield partial(self.fs_move, src_id, dst_pid, async_=async_)
                    try:
                        yield partial(self.fs_rename, (src_id, dst_name), async_=async_)
                    except:
                        yield partial(self.fs_move, (src_id, src_attr["parent_id"]), async_=async_)
                        raise
                except:
                    yield partial(self.fs_rename, (src_id, src_name), async_=async_)
                    raise
            elif src_ext == dst_ext:
                yield partial(self.fs_move, src_id, dst_pid, async_=async_)
                try:
                    yield partial(self.fs_rename, (src_id, dst_name), async_=async_)
                except:
                    yield partial(self.fs_move, src_id, src_attr["parent_id"], async_=async_)
                    raise
            else:
                resp = yield self.client.upload_file_init(
                    filename=dst_name, 
                    filesize=src_attr["size"], 
                    filesha1=src_attr["sha1"], 
                    read_range_bytes_or_hash=lambda rng: self.read_bytes_range( # type: ignore
                        src_attr, 
                        bytes_range=rng, 
                        async_=async_, 
                    ), 
                    pid=dst_pid, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, # type: ignore
                )
                check_response(resp)
                status = resp["status"]
                statuscode = resp.get("statuscode", 0)
                if status == 2 and statuscode == 0:
                    pass
                elif status == 1 and statuscode == 0:
                    warn(f"wrong sha1 {src_attr['sha1']!r} found, will attempt to upload directly: {src_attr!r}")
                    resp = yield partial(
                        self.client.upload_file, 
                        self.open(src_attr, "rb", buffering=0), 
                        dst_name, 
                        pid=dst_pid, 
                        upload_directly=True, 
                        request=self.async_request if async_ else self.request, 
                        async_=async_, 
                    )
                else:
                    raise OSError(resp)
                yield partial(self.fs_delete, src_id, async_=async_)
                data = resp["data"]
                if "file_id" in data:
                    return (yield partial(self.attr, int(data["file_id"]), async_=async_))
                else:
                    dst_name = data["file_name"]
                    return (yield partial(self.attr, [dst_name], pid=dst_pid, async_=async_))
            return (yield partial(self.attr, src_id, async_=async_))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def renames(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def renames(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def renames(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "重命名路径，如果文件被移动到其它目录中，则尝试从原来的上级目录逐级往上删除空目录"
        def gen_step():
            attr = yield partial(self.attr, src_path, pid=pid, async_=async_)
            parent_id = attr["parent_id"]
            attr = yield partial(self.rename, attr, dst_path, pid=pid, async_=async_)
            if parent_id != attr["parent_id"]:
                yield partial(self.removedirs, parent_id, async_=async_)
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def replace(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def replace(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def replace(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "替换路径"
        return self.rename(src_path, dst_path, pid=pid, replace=True, async_=async_)

    @overload
    def rmdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def rmdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def rmdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "删除空目录"
        def gen_step():
            attr = yield partial(
                self.attr, 
                id_or_path, 
                pid=pid, 
                ensure_dir=True, 
                async_=async_, 
            )
            id = attr["id"]
            if id == 0:
                raise PermissionError(
                    errno.EPERM, 
                    "remove the root directory is not allowed", 
                )
            elif (yield partial(self.dirlen, id, async_=async_)):
                raise OSError(
                    errno.ENOTEMPTY, 
                    f"directory is not empty: {attr['path']!r} (id={attr['id']!r})", 
                )
            yield partial(self.fs_delete, id, async_=async_)
            self._clear_cache(attr) 
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def rmtree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def rmtree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def rmtree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "删除路径"
        return self.remove(id_or_path, pid, recursive=True, async_=async_)

    @overload
    def score(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        score: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def score(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        score: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, int]:
        ...
    def score(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        score: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int | Coroutine[Any, Any, int]:
        """文件或目录的分数
        :param star: 如果为 None，返回分数；否则，设置分数
        """
        def gen_step():
            if score is None:
                attr = yield self.attr(id_or_path, pid=pid, async_=async_)
                return attr.get("score", 0)
            else:
                fid = yield self.get_id(id_or_path, pid=pid, async_=async_)
                if fid == 0:
                    return 0
                yield self.client.fs_score_set(
                    fid, 
                    score, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )
                return score
        return run_gen_step(gen_step, async_=async_)

    @overload
    def search(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        page_size: int = 1_000, 
        *, 
        async_: Literal[False] = False, 
        **payload, 
    ) -> Iterator[P115Path]:
        ...
    @overload
    def search(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        page_size: int = 1_000, 
        *, 
        async_: Literal[True], 
        **payload, 
    ) -> AsyncIterator[P115Path]:
        ...
    def search(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        page_size: int = 1_000, 
        *, 
        async_: Literal[False, True] = False, 
        **payload, 
    ) -> Iterator[P115Path] | AsyncIterator[P115Path]:
        """搜索目录

        :param payload:
            - asc: 0 | 1 = <default> # 是否升序排列
            - count_folders: 0 | 1 = <default>
            - date: str = <default> # 筛选日期
            - fc_mix: 0 | 1 = <default> # 是否目录和文件混合，如果为 0 则目录在前
            - file_label: int | str = <default> # 标签 id
            - format: str = "json" # 输出格式（不用管）
            - o: str = <default>
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
            - offset: int = 0  # 索引偏移，索引从 0 开始计算
            - pick_code: str = <default>
            - search_value: str = "." # 搜索文本，可以是 sha1
            - show_dir: 0 | 1 = 1
            - source: str = <default>
            - star: 0 | 1 = <default>
            - suffix: str = <default>
            - type: int | str = <default>
                # 文件类型：
                # - 所有: 0
                # - 文档: 1
                # - 图片: 2
                # - 音频: 3
                # - 视频: 4
                # - 压缩包: 5
                # - 应用: 6
                # - 书籍: 7
                # - 仅文件: 99
        """
        if page_size <= 0:
            page_size = 1_000
        def gen_step():
            attr = yield self.attr(id_or_path, pid=pid, async_=async_)
            if attr["is_directory"]:
                payload["cid"] = attr["id"]
            else:
                payload["cid"] = attr["parent_id"]
            payload["limit"] = page_size
            offset = int(payload.setdefault("offset", 0))
            if offset < 0:
                payload["offset"] = 0
            search = self.fs_search
            while True:
                resp = yield search(payload, async_=async_)
                if resp["offset"] != offset:
                    break
                data = resp["data"]
                if not data:
                    return
                for attr in data:
                    attr = normalize_attr(attr, dict_cls=AttrDictWithAncestors)
                    yield Yield(P115Path(self, attr))
                offset = payload["offset"] = offset + resp["page_size"]
                if offset >= resp["count"] or offset >= 10_000:
                    break
                if offset + page_size > 10_000:
                    payload["page_size"] = 10_000 - offset
        return run_gen_step_iter(gen_step, async_=async_)

    @overload
    def star(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        star: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def star(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        star: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def star(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        star: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        """文件或目录的星标
        :param star: 如果为 None，返回星标是否已设置；如果为 True，设置星标；如果为 False，取消星标
        """
        def gen_step():
            if star is None:
                attr = yield self.attr(id_or_path, pid=pid, async_=async_)
                return attr.get("star", False)
            else:
                fid = yield self.get_id(id_or_path, pid=pid, async_=async_)
                if fid == 0:
                    return False
                check_response((yield self.client.fs_star_set(
                    fid, 
                    star, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))
                return star
        return run_gen_step(gen_step, async_=async_)

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
        "检查文件或目录的属性，就像 `os.stat`"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            is_dir = attr["is_directory"]
            return stat_result((
                (S_IFDIR if is_dir else S_IFREG) | 0o777, # mode
                cast(int, attr["id"]), # ino
                cast(int, attr["parent_id"]), # dev
                1, # nlink
                self.client.user_id, # uid
                1, # gid
                0 if is_dir else attr["size"], # size
                cast(float, attr.get("atime", 0)), # atime
                cast(float, attr.get("mtime", 0)), # mtime
                cast(float, attr.get("ctime", 0)), # ctime
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        is_dir: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        is_dir: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        is_dir: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        """检查路径是否存在，当不存在时，如果 is_dir 是 False 时，则创建空文件，否则创建空目录
        """
        def gen_step():
            try:
                return (yield partial(self.attr, id_or_path, pid=pid, async_=async_))
            except FileNotFoundError:
                if isinstance(id_or_path, int):
                    raise ValueError(f"no such id: {id_or_path!r}")
                elif is_dir:
                    return (yield partial(self.mkdir, id_or_path, pid=pid, async_=async_))
                else:
                    return (yield partial(self.upload, b"", id_or_path, pid=pid, async_=async_))
        return run_gen_step(gen_step, async_=async_)

    # TODO: 增加功能，返回一个 Task 对象，可以获取上传进度，可随时取消
    # TODO: 因为文件名可以重复，因此确保上传成功后再删除
    @overload
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "上传文件"
        def gen_step():
            nonlocal path, pid
            path_class = type(self).path_class
            unchecked = True
            name = ""
            if isinstance(path, int):
                attr = yield partial(self.attr, path, async_=async_)
            elif isinstance(path, AttrDictWithAncestors):
                attr = path
            elif isinstance(path, path_class):
                attr = path.attr
            elif isinstance(path, (str, PathLike)):
                path = normpath(fspath(path))
                if path == "/":
                    pid = 0
                elif not path:
                    pid = self.id if pid is None else pid
                else:
                    dirname, name = split(path)
                    if name == ".." or not name:
                        attr = yield partial(self.attr, path, pid=pid, async_=async_)
                        pid = attr["pid"]
                        name = ""
                    else:
                        dattr = yield partial(self.attr, dirname, pid=pid, async_=async_)
                        pid = dattr["id"]
                unchecked = False
            else:
                patht = [*path[:1], *(p for p in path[1:] if p)]
                if not patht:
                    pid = self.id if pid is None else pid
                elif patht == [""]:
                    pid = 0
                else:
                    *dirname_t, name = patht
                    dattr = yield partial(self.attr, dirname_t, pid=pid, async_=async_)
                    pid = dattr["id"]
                unchecked = False
            if unchecked:
                if attr["is_directory"]:
                    pid = attr["id"]
                elif overwrite:
                    try:
                        yield partial(self.remove, attr["id"], async_=async_)
                    except FileNotFoundError:
                        pass
                    pid = attr["parent_id"]
                    name = attr["name"]
                else:
                    raise FileExistsError(errno.EEXIST, f"remote path {attr['path']!r} (id={attr['id']}) already exists")
            resp = yield partial(self.fs_upload, file, name, pid=pid, async_=async_)
            if remove_done and isinstance(file, (str, PathLike)):
                try:
                    remove(file)
                except OSError:
                    pass
            return resp
        return run_gen_step(gen_step, async_=async_)

    # TODO: 支持异步
    # TODO: 上传和下载都要支持多线程
    # TODO: 返回上传任务的迭代器，包含进度相关信息，以及最终的响应信息
    # TODO: 增加参数，submit，可以把任务提交给线程池
    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str] = ".", 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        no_root: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        predicate: None | Callable[[Path], bool] = None, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
    ) -> Iterator[AttrDictWithAncestors]:
        "上传到路径"
        remote_path_attr_map: None | dict[str, AttrDictWithAncestors] = None
        try:
            attr = self.attr(path, pid=pid)
        except FileNotFoundError:
            if isinstance(path, int):
                raise ValueError(f"no such id: {path!r}")
            attr = self.makedirs(path, pid=pid, exist_ok=True)
            remote_path_attr_map = {}
        else:
            if not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['path']!r} (id={attr['id']!r}) is not a directory", 
                )
        pid = cast(int, attr["id"])

        local_path = ospath.normpath(local_path)
        try:
            try:
                if predicate is None:
                    subpaths = tuple(scandir(local_path))
                else:
                    subpaths = tuple(filter(lambda e: predicate(Path(e)), scandir(local_path)))
                if not subpaths:
                    return
            except NotADirectoryError:
                try:
                    yield self.upload(
                        local_path, 
                        [ospath.basename(local_path)], 
                        pid=pid, 
                        overwrite=overwrite, 
                        remove_done=remove_done, 
                    )
                except OSError as e:
                    if onerror is True:
                        raise e
                    elif onerror is False or onerror is None:
                        pass
                    else:
                        onerror(e)
                    return
            if not no_root:
                attr = self.makedirs(
                    [ospath.basename(local_path)], 
                    pid=pid, 
                    exist_ok=True, 
                )
                pid = attr["id"]
                remote_path_attr_map = {}
            elif remote_path_attr_map is None:
                remote_path_attr_map = {a["name"]: a for a in self.iterdir(pid)}
        except OSError as e:
            if onerror is True:
                raise e
            elif onerror is False or onerror is None:
                pass
            else:
                onerror(e)
            return

        for entry in subpaths:
            name = entry.name
            isdir = entry.is_dir()
            remote_path_attr = remote_path_attr_map.get(name)
            if remote_path_attr and isdir != remote_path_attr["is_directory"]:
                if onerror is True:
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"remote path {remote_path_attr['path']!r} already exists", 
                    )
                elif onerror is False or onerror is None:
                    pass
                else:
                    onerror(FileExistsError(
                        errno.EEXIST, 
                        f"remote path {remote_path_attr['path']!r} already exists"), 
                    )
                return
            if isdir:
                if remote_path_attr is None:
                    yield from self.upload_tree(
                        entry, 
                        [name], 
                        pid=pid, 
                        no_root=True, 
                        overwrite=overwrite, 
                        remove_done=remove_done, 
                        onerror=onerror, 
                    )
                else:
                    yield from self.upload_tree(
                        entry, 
                        remote_path_attr, 
                        no_root=True, 
                        overwrite=overwrite, 
                        remove_done=remove_done, 
                        onerror=onerror, 
                    )
                if remove_done:
                    try:
                        rmdir(entry)
                    except OSError:
                        pass
            else:
                try:
                    if remote_path_attr is None:
                        yield self.upload(
                            entry, 
                            [name], 
                            pid=pid, 
                            overwrite=overwrite, 
                            remove_done=remove_done, 
                        )
                    else:
                        yield self.upload(
                            entry, 
                            remote_path_attr, 
                            overwrite=overwrite, 
                            remove_done=remove_done, 
                        )
                except OSError as e:
                    if onerror is True:
                        raise e
                    elif onerror is False or onerror is None:
                        pass
                    else:
                        onerror(e)

    unlink = remove

    @overload
    def write_bytes(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        data: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] ) = b"", 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def write_bytes(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        data: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ) = b"", 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def write_bytes(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        data: ( str | PathLike | URL | SupportsGeturl | Buffer | 
                SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ) = b"", 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "向文件写入二进制数据，如果文件已存在则替换"
        return self.upload(
            data, # type: ignore
            id_or_path, 
            pid=pid, 
            overwrite=True, 
            async_=async_, # type: ignore
        )

    @overload
    def write_text(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        text: str = "", 
        pid: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDictWithAncestors:
        ...
    @overload
    def write_text(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        text: str = "", 
        pid: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDictWithAncestors]:
        ...
    def write_text(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        text: str = "", 
        pid: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDictWithAncestors | Coroutine[Any, Any, AttrDictWithAncestors]:
        "向文件写入文本数据，如果文件已存在则替换"
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
        return self.write_bytes(id_or_path, bio, pid=pid, async_=async_)

    cp = copy
    mv = move
    rm = remove

# TODO: 上传和下载都返回一个 Future 对象，可以获取信息和完成情况，以及可以重试等操作
# TODO: 为 path_to_id 的更新，设计更完备的算法
# TODO: 基于 fs_search 实现 search，但可用的参数更少，另外其实 如果 fs_files 指定 type、suffix 这类的，那么相当于是 search
# TODO: 移除 path_to_id 映射，以简化缓存更新策略，以后只保留 id_to_ancestor 这类的缓存 
