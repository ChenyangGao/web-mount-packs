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
from json import loads
from mimetypes import guess_type
from os import fsdecode, fspath, fstat, lstat, makedirs, scandir, stat_result, path as ospath, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split as splitpath, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError, COPY_BUFSIZE # type: ignore
from stat import S_IFDIR, S_IFREG
from typing import cast, overload, Any, IO, Literal, Never, Optional, Self, TypeAlias
from types import MappingProxyType, MethodType
from urllib.parse import quote
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
from urlopen import urlopen
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

    def __and__(self, path: PathType, /) -> AlistPath:
        return type(self)(
            self.fs, 
            commonpath((self["path"], self.fs.abspath(path))), 
            password=self.password, 
        )

    # TODO: 增加异步
    def __call__(self, /) -> AlistPath:
        self.__dict__.update(self.fs.attr(self.path))
        return self

    def __contains__(self, key, /) -> bool:
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self["path"] == path["path"]

    def __fspath__(self, /) -> str:
        return self["path"]

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.__dict__.get("accessed"):
            self()
        return self.__dict__[key]

    def __ge__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self["path"], path["path"])) == path["path"]

    def __gt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client or self["path"] == path["path"]:
            return False
        return commonpath((self["path"], path["path"])) == path["path"]

    def __hash__(self, /) -> int:
        return hash((self.fs.client, self["path"]))

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self["path"], path["path"])) == self["path"]

    def __lt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client or self["path"] == path["path"]:
            return False
        return commonpath((self["path"], path["path"])) == self["path"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}({', '.join(f'{k}={v!r}' for k, v in self.__dict__.items())})>"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __str__(self, /) -> str:
        return self["path"]

    def __truediv__(self, path: PathType, /) -> AlistPath:
        return self.joinpath(path)

    def set_password(self, value, /):
        self.__dict__["password"] = str(value)

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

    def copy(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
        overwrite_or_ignore: None | bool = None, 
    ) -> Optional[AlistPath]:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.copy(
            self, 
            dst_path, 
            dst_password=dst_password, 
            overwrite_or_ignore=overwrite_or_ignore, 
            recursive=True, 
        )
        if not dst:
            return None
        return type(self)(self.fs, dst, dst_password)

    def download(
        self, 
        /, 
        to_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        refresh: None | bool = None, 
    ):
        return self.fs.download_tree(
            self, 
            to_dir, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
            refresh=refresh, 
        )

    def exists(self, /) -> bool:
        try:
            self()
            return True
        except FileNotFoundError:
            return False

    def get_url(self, /, ensure_ascii: bool = True) -> str:
        return self.fs.get_url(self, ensure_ascii=ensure_ascii)

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
    ) -> Iterator[AlistPath]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case
        )

    def is_absolute(self, /) -> bool:
        return True

    @method
    def is_dir(self, /) -> bool:
        try:
            return self["is_dir"]
        except FileNotFoundError:
            return False

    def is_file(self, /) -> bool:
        try:
            return not self["is_dir"]
        except FileNotFoundError:
            return False

    def is_symlink(self, /) -> bool:
        return False

    def isdir(self, /) -> bool:
        return self.fs.isdir(self)

    def isfile(self, /) -> bool:
        return self.fs.isfile(self)

    def iter(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], None | bool]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: None | bool = None, 
    ) -> Iterator[AlistPath]:
        return self.fs.iter(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def joinpath(self, *paths: PathType) -> AlistPath:
        if not paths:
            return self
        path = self["path"]
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new, self.password)

    def listdir(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
    ) -> list[str]:
        return self.fs.listdir(
            self, 
            page=page, 
            per_page=per_page, 
            refresh=refresh, 
        )

    def listdir_attr(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
    ) -> list[dict]:
        return self.fs.listdir_attr(
            self, 
            page=page, 
            per_page=per_page, 
            refresh=refresh, 
        )

    def listdir_path(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        refresh: None | bool = None, 
    ) -> list[AlistPath]:
        return self.fs.listdir_path(
            self, 
            page=page, 
            per_page=per_page, 
            refresh=refresh, 
        )

    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
    ) -> bool:
        pattern = "/" + "/".join(t[0] for t in translate_iter(path_pattern))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self["path"]) is not None

    @property
    def media_type(self, /) -> None | str:
        if not self.is_file():
            return None
        return guess_type(self["path"])[0] or "application/octet-stream"

    def mkdir(self, /, exist_ok: bool = True):
        self.fs.makedirs(self, exist_ok=exist_ok)

    def move(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.move(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self["path"] == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    @cached_property
    def name(self, /) -> str:
        return basename(self["path"])

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
    def parent(self, /) -> AlistPath:
        path = self["path"]
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path), self.password)

    @cached_property
    def parents(self, /) -> tuple[AlistPath, ...]:
        path = self["path"]
        if path == "/":
            return ()
        parents: list[AlistPath] = []
        cls, fs, password = type(self), self.fs, self.password
        parent = dirname(path)
        while path != parent:
            parents.append(cls(fs, parent, password))
            path, parent = parent, dirname(parent)
        return tuple(parents)

    @cached_property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *self["path"][1:].split("/"))

    def read_bytes(self, /, start: int = 0, stop: Optional[int] = None) -> bytes:
        return self.fs.read_bytes(self, start, stop)

    def read_bytes_range(self, /, bytes_range: str = "0-") -> bytes:
        return self.fs.read_bytes_range(self, bytes_range)

    def read_block(
        self, 
        /, 
        size: int = 0, 
        offset: int = 0, 
    ) -> bytes:
        if size <= 0:
            return b""
        return self.fs.read_block(self, size, offset)

    def read_text(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> str:
        return self.fs.read_text(self, encoding=encoding, errors=errors, newline=newline)

    def relative_to(self, other: PathType, /) -> str:
        if isinstance(other, (AttrDict, AlistPath)):
            other = cast(str, other["path"])
        else:
            other = fspath(other)
            if not other.startswith("/"):
                other = self.fs.abspath(other)
        path = self["path"]
        if path == other:
            return ""
        elif path.startswith(other + "/"):
            return path[len(other)+1:]
        raise ValueError(f"{path!r} is not in the subpath of {other!r}")

    @cached_property
    def relatives(self, /) -> tuple[str]:
        def it(path):
            stop = len(path)
            while stop:
                stop = path.rfind("/", 0, stop)
                yield path[stop+1:]
        return tuple(it(self["path"]))

    def remove(self, /, recursive: bool = True):
        self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.rename(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self["path"] == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def renames(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.renames(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self["path"] == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def replace(
        self, 
        /, 
        dst_path: PathType, 
        dst_password: None | str = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.replace(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self["path"] == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
    ) -> Iterator[AlistPath]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def rmdir(self, /):
        self.fs.rmdir(self)

    @property
    def root(self, /) -> AlistPath:
        return type(self)(
            self.fs, 
            self.fs.storage_of(self), 
            self.password, 
        )

    def samefile(self, path: PathType, /) -> bool:
        if type(self) is type(path):
            return self == path
        return path in ("", ".") or self["path"] == self.fs.abspath(path)

    def stat(self, /) -> stat_result:
        return self.fs.stat(self)

    @cached_property
    def stem(self, /) -> str:
        return splitext(basename(self["path"]))[0]

    @cached_property
    def suffix(self, /) -> str:
        return splitext(basename(self["path"]))[1]

    @cached_property
    def suffixes(self, /) -> tuple[str, ...]:
        return tuple("." + part for part in basename(self["path"]).split(".")[1:])

    def touch(self, /):
        self.fs.touch(self)

    unlink = remove

    @cached_property
    def url(self, /) -> str:
        return self.fs.get_url(self)

    @property
    def raw_url(self, /) -> str:
        return self["raw_url"]

    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: None | bool = None, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        return self.fs.walk(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def walk_attr(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: None | bool = None, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        return self.fs.walk_attr(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def walk_path(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: None | bool = None, 
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        return self.fs.walk_path(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def with_name(self, name: str, /) -> AlistPath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> AlistPath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> AlistPath:
        return self.parent.joinpath(self.stem + suffix)

    def write_bytes(
        self, 
        /, 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
    ):
        self.fs.write_bytes(self, data)

    def write_text(
        self, 
        /, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ):
        self.fs.write_text(
            self, 
            text, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )


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
        path: PathType = "/", 
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

    # TODO 需要优化
    def __setitem__(
        self, 
        /, 
        path: PathType = "", 
        file: None | str | bytes | bytearray | memoryview | PathLike = None, 
    ):
        if file is None:
            return self.touch(path)
        elif isinstance(file, PathLike):
            if ospath.isdir(file):
                return self.upload_tree(file, path, no_root=True, overwrite_or_ignore=True)
            else:
                return self.upload(file, path, overwrite_or_ignore=True)
        elif isinstance(file, str):
            return self.write_text(path, file)
        else:
            return self.write_bytes(path, file)

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
            resp = yield partial(
                self.client.admin_setting_list, 
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
            resp = yield partial(
                self.client.admin_setting_reset_token, 
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
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_get(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
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
        return check_response(self.client.fs_get( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **self.request_kwargs, 
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
    def fs_list_storage(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_list_storage(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list_storage(
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
    def fs_remove_storage(
        self, 
        id: int | str, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_remove_storage(
        self, 
        id: int | str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_remove_storage(
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
            attr = (yield partial(
                self.fs_get, 
                path, 
                password, 
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
                attr = yield partial(
                    self.attr, 
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
                src_attr = yield partial(
                    self.attr, 
                    src_path, 
                    src_password, 
                    async_=async_, 
                )
                src_path = cast(str, src_attr["path"])
                if src_attr["is_dir"]:
                    if recursive:
                        return (yield partial(
                            self.copytree, 
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

                dst_attr: None | AttrDict | AlistPath
                if isinstance(dst_path, (AttrDict, AlistPath)):
                    dst_attr = dst_path
                    dst_path = cast(str, dst_attr["path"])
                    dst_dir, dst_name = splitpath(dst_path)
                else:
                    dst_attr = None
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
                        dst_attr = yield partial(
                            self.attr, 
                            dst_path, 
                            dst_password, 
                            async_=async_, 
                        )
                    dst_password = dst_password or dst_attr.get("password", "")
                except FileNotFoundError:
                    yield partial(
                        self.makedirs, 
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
                        yield partial(
                            self.remove, 
                            dst_attr, 
                            async_=async_, 
                        )
                    else:
                        raise FileExistsError(
                            errno.EEXIST, 
                            f"destination path already exists: {src_path!r} -> {dst_path!r}", 
                        )

                if src_name == dst_name:
                    resp = yield partial(
                        self.fs_copy, 
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
                    src_storage = yield partial(
                        self.storage_of, 
                        src_dir, 
                        src_password, 
                        async_=async_, 
                    )
                    dst_storage = yield partial(
                        self.storage_of, 
                        dst_dir, 
                        dst_password, 
                        async_=async_, 
                    )
                    if src_storage != dst_storage:
                        # NOTE: 跨 storage 复制为不同名字的文件，则转化为上传任务
                        resp = yield partial(
                            self.fs_put, 
                            URL(self.get_url(src_path)), 
                            dst_path, 
                            as_task=True, 
                            filesize=src_attr["size"], 
                            async_=async_, 
                        )
                        task = resp["data"]["task"]
                        task["dst_path"] = dst_path
                        return task

                    if not (yield partial(
                        self.exists, 
                        joinpath(dst_dir, src_name), 
                        async_=async_
                    )):
                        yield partial(
                            self.fs_copy, 
                            src_dir, 
                            dst_dir, 
                            [src_name], 
                            async_=async_, 
                        )
                        yield partial(
                            self.fs_rename, 
                            joinpath(dst_dir, src_name), 
                            dst_name, 
                            async_=async_, 
                        )
                    else:
                        tempdirname = str(uuid4())
                        tempdir = joinpath(dst_dir, tempdirname)
                        yield partial(
                            self.fs_mkdir, 
                            tempdir, 
                            async_=async_, 
                        )
                        try:
                            yield partial(
                                self.fs_copy, 
                                src_dir, 
                                tempdir, 
                                [src_name], 
                                async_=async_, 
                            )
                            yield partial(
                                self.fs_rename, 
                                joinpath(tempdir, src_name), 
                                dst_name, 
                                async_=async_, 
                            )
                            yield partial(
                                self.fs_move, 
                                tempdir, 
                                dst_dir, 
                                [dst_name], 
                                async_=async_, 
                            )
                        finally:
                            yield partial(
                                self.fs_remove, 
                                dst_dir, 
                                [tempdirname], 
                                async_=async_, 
                            )
                    return dst_path
            except OSError as e:
                if onerror is True:
                    raise
                elif onerror is False or onerror is None:
                    pass
                else:
                    onerror(e)
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
                src_attr = yield partial(
                    self.attr, 
                    src_path, 
                    src_password, 
                    async_=async_, 
                )
                if not src_attr["is_dir"]:
                    return (yield partial(
                        self.copy, 
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

                dst_attr: None | AttrDict | AlistPath
                if isinstance(dst_path, (AttrDict, AlistPath)):
                    dst_attr = dst_path
                    dst_path = cast(str, dst_attr["path"])
                    dst_dir, dst_name = splitpath(dst_path)
                else:
                    dst_path = fspath(dst_path)
                    dst_attr = None
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
                        dst_attr = yield partial(
                            self.attr, 
                            dst_path, 
                            dst_password, 
                            async_=async_, 
                        )
                    dst_password = dst_password or dst_attr.get("password", "")
                except FileNotFoundError:
                    yield partial(
                        self.makedirs, 
                        dst_dir, 
                        dst_password, 
                        exist_ok=True, 
                        async_=async_, 
                    )
                    if src_name == dst_name:
                        if as_task:
                            yield partial(
                                self.fs_copy, 
                                src_dir, 
                                dst_dir, 
                                [src_name], 
                                async_=async_, 
                            )
                            return dst_path
                    yield partial(
                        self.fs_mkdir, 
                        dst_path, 
                        async_=async_, 
                    )
                else:
                    if not dst_attr["is_dir"]:
                        raise NotADirectoryError(
                            errno.ENOTDIR, 
                            f"destination path is not directory: {src_path!r} -> {dst_path!r}", 
                        )

                sub_srcattrs = yield partial(
                    self.listdir_attr, 
                    src_attr, 
                    src_password, 
                    refresh=True, 
                    async_=async_, 
                )
            except OSError as e:
                if onerror is True:
                    raise
                elif onerror is False or onerror is None:
                    pass
                else:
                    onerror(e)
                return None

            result = {}
            for sub_srcattr in sub_srcattrs:
                if sub_srcattr["is_dir"]:
                    result[sub_srcattr["path"]] = (yield partial(
                        self.copytree, 
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
                    result[sub_srcattr["path"]] = (yield partial(
                        self.copy, 
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
                attr = yield partial(
                    self.attr, 
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
            attr = yield partial(
                self.attr, 
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
                    pathes = yield partial(
                        self.listdir_attr, 
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
                if subpath["is_directory"]:
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
                        async_=async_, 
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
            if isinstance(path, (AttrDict, AlistPath)):
                path = cast(str, path["path"])
            else:
                path = self.abspath(path)
            try:
                yield partial(
                    self.attr, 
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
            resp = yield partial(
                self.fs_list, 
                path, 
                password=password, 
                refresh=refresh, 
                per_page=1, 
                async_=async_, 
            )
            return resp["data"]["total"]
        return run_gen_step(gen_step, async_=async_)

    def get_url(
        self, 
        /, 
        path: PathType = "", 
        token: bool | str = "", 
        expire_timestamp: int = 0, 
        ensure_ascii: bool = True, 
    ) -> str:
        if isinstance(path, (AttrDict, AlistPath)):
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
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
            nonlocal pattern, dirname
            if not pattern:
                try:
                    attr = yield partial(
                        self.attr, 
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
                    pattern = joinpath(re_escape(dirname), "/".join(t[0] for t in splitted_pats))
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
                        attr = yield partial(
                            self.attr, 
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
                if any(typ == "dstar" for _, typ, _ in splitted_pats):
                    pattern = joinpath(re_escape(dirname), "/".join(t[0] for t in splitted_pats[i:]))
                    match = re_compile(pattern).fullmatch
                    return YieldFrom(self.iter(
                        dirname, 
                        password=password, 
                        max_depth=-1, 
                        predicate=lambda p: match(p["path"]) is not None, 
                        async_=async_, 
                    ), identity=True)
            path = AlistPath(self, dirname, password)
            if not (yield path.is_dir(async_=async_)):
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
                    elif (yield subpath.is_dir(async_=async_)):
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
                attr = yield partial(
                    self.attr, 
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
                attr = yield partial(
                    self.attr, 
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
            if isinstance(path, (AttrDict, AlistPath)):
                if "hash_info" in path:
                    return path["hash_info"] is None
                if not password:
                    password = path.get("password", "")
                path = cast(str, path["path"])
            else:
                path = self.abspath(path)
            if path == "/":
                return True
            try:
                return any(path == s["mount_path"] for s in self.list_storage())
            except PermissionError:
                attr = yield self.attr(path, password, async_=async_)
                try:
                    return attr.get("hash_info") is None
                except FileNotFoundError:
                    return False
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
        async_: AsyncLiteral[True], 
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
            dq: deque[tuple[int, AlistPath]] = deque()
            push, pop = dq.append, dq.popleft
            try:
                attr = yield self.attr(top, password, async_=async_)
                if not password:
                    password = attr.get("password", "")
            except OSError:
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
                async_=async_, 
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
                async_=async_, 
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
    ) -> Iterator[dict]:
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
    ) -> AsyncIterator[dict]:
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
    ) -> Iterator[dict] | AsyncIterator[dict]:
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
    def list_storage(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def list_storage(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_storage(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        def gen_step():
            resp = yield self.fs_list_storage(async_=async_)
            return resp["data"]["content"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def listdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
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
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def listdir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        def gen_step():
            if page <= 0 or per_page <= 0:
                resp = yield self.fs_dirs(
                    path, 
                    password, 
                    refresh=refresh, 
                    async_=async_, 
                )
                data = resp["data"]
            else:
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
            return [item["name"] for item in data]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def listdir_attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
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
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[AttrDict]]:
        ...
    def listdir_attr(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[AttrDict] | Coroutine[Any, Any, list[AttrDict]]:
        def gen_step():
            nonlocal page, per_page
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
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
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
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[AlistPath]]:
        ...
    def listdir_path(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
        page: int = 1, 
        per_page: int = 0, 
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
        async_: Literal[False, True] = False, 
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
        async_: Literal[False] = False, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def makedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        exist_ok: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            if isinstance(path, (AttrDict, AlistPath)):
                if not password:
                    password = path.get("password", "")
                path = cast(str, path["path"])
            else:
                path = self.abspath(path)
            if path == "/":
                return "/"
            if not exist_ok and self.exists(path, password, async_=async_):
                raise FileExistsError(errno.EEXIST, path)
            self.fs_mkdir(path, async_=async_)
            return path
        return run_gen_step(gen_step, async_=async_)

    def mkdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
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
        if self.is_storage(path, password, async_=async_):
            raise PermissionError(
                errno.EPERM, 
                f"can't directly create a storage by `mkdir`: {path!r}", 
            )
        try:
            self.attr(path, password, async_=async_)
        except FileNotFoundError as e:
            dir_ = dirname(path)
            if not self.attr(dir_, password, async_=async_)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, dir_) from e
            self.fs_mkdir(path, async_=async_)
            return path
        else:
            raise FileExistsError(errno.EEXIST, path)

    def move(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        if isinstance(src_path, (AttrDict, AlistPath)):
            if not src_password:
                src_password = src_path.get("password", "")
            src_path = src_path["path"]
        else:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, (AttrDict, AlistPath)):
            if not dst_password:
                dst_password = dst_path.get("password", "")
            dst_path = dst_path["path"]
        else:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
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
        src_attr = self.attr(src_path, src_password, async_=async_)
        try:
            dst_attr = self.attr(dst_path, dst_password, async_=async_)
        except FileNotFoundError:
            return self.rename(src_path, dst_path, src_password, dst_password, async_=async_)
        else:
            if dst_attr["is_dir"]:
                dst_filename = basename(src_path)
                dst_filepath = joinpath(dst_path, dst_filename)
                if self.exists(dst_filepath, dst_password, async_=async_):
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"destination path {dst_filepath!r} already exists", 
                    )
                self.fs_move(dirname(src_path), dst_path, [dst_filename], async_=async_)
                return dst_filepath
            raise FileExistsError(errno.EEXIST, f"destination path {dst_path!r} already exists")

    def open(
        self, 
        /, 
        path: PathType, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> HTTPFileReader | IO:
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        path = self.as_path(path, password, async_=async_)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path['path']!r} is a directory")
        return self.client.open(
            path.url, 
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

    def read_bytes(
        self, 
        /, 
        path: PathType, 
        start: int = 0, 
        stop: Optional[int] = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes:
        path = self.as_path(path, password, async_=async_)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path['path']!r} is a directory")
        return self.client.read_bytes(path.url, start, stop)

    def read_bytes_range(
        self, 
        /, 
        path: PathType, 
        bytes_range: str = "0-", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes:
        path = self.as_path(path, password, async_=async_)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path['path']!r} is a directory")
        return self.client.read_bytes_range(path.url, bytes_range)

    def read_block(
        self, 
        /, 
        path: PathType, 
        size: int = 0, 
        offset: int = 0, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bytes:
        if size <= 0:
            return b""
        path = self.as_path(path, password, async_=async_)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path['path']!r} is a directory")
        return self.client.read_block(path.url, size, offset)

    def read_text(
        self, 
        /, 
        path: PathType, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ):
        return self.open(
            path, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            password=password, 
            async_=async_, 
        ).read()

    def remove(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        recursive: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if path == "/":
            if recursive:
                try:
                    storages = self.list_storage()
                except PermissionError:
                    self.fs_remove("/", self.listdir("/", password, refresh=True), async_=async_)
                else:
                    for storage in storages:
                        self.fs_remove_storage(storage["id"])
                return
            else:
                raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        attr = self.attr(path, password, async_=async_)
        if attr["is_dir"]:
            if not recursive:
                if attr.get("hash_info") is None:
                    raise PermissionError(errno.EPERM, f"remove a storage is not allowed: {path!r}")
                raise IsADirectoryError(errno.EISDIR, path)
            try:
                storages = self.list_storage()
            except PermissionError:
                if attr.get("hash_info") is None:
                    raise
            else:
                for storage in storages:
                    if commonpath((storage["mount_path"], path)) == path:
                        self.fs_remove_storage(storage["id"])
                        return
        self.fs_remove(dirname(path), [basename(path)], async_=async_)

    def removedirs(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ):
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        dirlen = self.dirlen
        remove_storage = self.fs_remove_storage
        if dirlen(path, password, async_=async_):
            raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        try:
            storages = self.list_storage()
        except PermissionError:
            if self.attr(path, password, async_=async_)["hash_info"] is None:
                raise
            storages = []
        else:
            for storage in storages:
                if storage["mount_path"] == path:
                    remove_storage(storage["id"])
                    break
        parent_dir = dirname(path)
        del_dir = ""
        try:
            while dirlen(parent_dir, password, async_=async_) <= 1:
                for storage in storages:
                    if storage["mount_path"] == parent_dir:
                        remove_storage(storage["id"])
                        del_dir = ""
                        break
                else:
                    del_dir = parent_dir
                parent_dir = dirname(parent_dir)
            if del_dir:
                self.fs_remove(parent_dir, [basename(del_dir)], async_=async_)
        except OSError as e:
            pass

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
    ) -> str:
        if isinstance(src_path, (AttrDict, AlistPath)):
            if not src_password:
                src_password = src_path.get("password", "")
            src_path = src_path["path"]
        else:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, (AttrDict, AlistPath)):
            if not dst_password:
                dst_password = dst_path.get("password", "")
            dst_path = dst_path["path"]
        else:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            return dst_path
        if src_path == "/" or dst_path == "/":
            raise OSError(errno.EINVAL, f"invalid argument: {src_path!r} -> {dst_path!r}")
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
        src_attr = self.attr(src_path, src_password, async_=async_)
        try:
            dst_attr = self.attr(dst_path, dst_password, async_=async_)
        except FileNotFoundError:
            if src_attr.get("hash_info") is None:
                for storage in self.list_storage():
                    if src_path == storage["mount_path"]:
                        storage["mount_path"] = dst_path
                        self.client.admin_storage_update(storage)
                        break
                return dst_path
            elif src_dir == dst_dir:
                self.fs_rename(src_path, dst_name, async_=async_)
                return dst_path
            if not self.attr(dst_dir, dst_password, async_=async_)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"{dst_dir!r} is not a directory: {src_path!r} -> {dst_path!r}")
        else:
            if replace:
                if dst_attr.get("hash_info") is None:
                    raise PermissionError(
                        errno.EPERM, 
                        f"replace a storage {dst_path!r} is not allowed: {src_path!r} -> {dst_path!r}", 
                    )
                elif src_attr["is_dir"]:
                    if dst_attr["is_dir"]:
                        if self.dirlen(dst_path, dst_password, async_=async_):
                            raise OSError(errno.ENOTEMPTY, f"directory {dst_path!r} is not empty: {src_path!r} -> {dst_path!r}")
                    else:
                        raise NotADirectoryError(errno.ENOTDIR, f"{dst_path!r} is not a directory: {src_path!r} -> {dst_path!r}")
                elif dst_attr["is_dir"]:
                    raise IsADirectoryError(errno.EISDIR, f"{dst_path!r} is a directory: {src_path!r} -> {dst_path!r}")
                self.fs_remove(dst_dir, [dst_name], async_=async_)
            else:
                raise FileExistsError(errno.EEXIST, f"{dst_path!r} already exists: {src_path!r} -> {dst_path!r}")
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

    def renames(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        if isinstance(src_path, (AttrDict, AlistPath)):
            if not src_password:
                src_password = src_path.get("password", "")
            src_path = src_path["path"]
        else:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, (AttrDict, AlistPath)):
            if not dst_password:
                dst_password = dst_path.get("password", "")
            dst_path = dst_path["path"]
        else:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        dst = self.rename(src_path, dst_path, src_password, dst_password, async_=async_)
        if dirname(src_path) != dirname(dst_path):
            try:
                self.removedirs(dirname(src_path), src_password, async_=async_)
            except OSError:
                pass
        return dst

    def replace(
        self, 
        /, 
        src_path: PathType, 
        dst_path: PathType, 
        src_password: str = "", 
        dst_password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        return self.rename(src_path, dst_path, src_password, dst_password, replace=True, async_=async_)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: PathType = "", 
        ignore_case: bool = False, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AlistPath]:
        if not pattern:
            return self.iter(dirname, password=password, max_depth=-1, async_=async_)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, password=password, ignore_case=ignore_case, async_=async_)

    def rmdir(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ):
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif self.is_storage(path, password, async_=async_):
            raise PermissionError(errno.EPERM, f"remove a storage by `rmdir` is not allowed: {path!r}")
        elif not self.attr(path, password, async_=async_)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        elif not self.is_empty(path, password, async_=async_):
            raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        self.fs_remove(dirname(path), [basename(path)], async_=async_)

    def rmtree(
        self, 
        /, 
        path: PathType, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ):
        self.remove(path, password, recursive=True, async_=async_)

    def scandir(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        refresh: None | bool = None, 
    ) -> Iterator[AlistPath]:
        for item in self.listdir_attr(
            path, 
            password, 
            refresh=refresh, 
            async_=async_, 
        ):
            yield AlistPath(self, **item)

    def stat(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> stat_result:
        attr = self.attr(path, password, async_=async_)
        is_dir = attr.get("is_dir", False)
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o777, # mode
            0, # ino
            0, # dev
            1, # nlink
            0, # uid
            0, # gid
            attr.get("size", 0), # size
            attr["atime"], # atime
            attr["mtime"], # mtime
            attr["ctime"], # ctime
        ))

    def storage_of(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if path == "/":
            return "/"
        try:
            storages = self.list_storage()
        except PermissionError:
            while True:
                try:
                    attr = self.attr(path, password, async_=async_)
                except FileNotFoundError:
                    continue
                else:
                    if attr.get("hash_info") is None:
                        return path
                finally:
                    ppath = dirname(path)
                    if ppath == path:
                        return "/"
                    path = ppath
            return "/"
        else:
            storage = "/"
            for s in storages:
                mount_path = s["mount_path"]
                if path == mount_path:
                    return mount_path
                elif commonpath((path, mount_path)) == mount_path and len(mount_path) > len(storage):
                    storage = mount_path
            return storage

    def touch(
        self, 
        /, 
        path: PathType = "", 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if not self.exists(path, password, async_=async_):
            dir_ = dirname(path)
            if not self.attr(dir_, password, async_=async_)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
            return self.upload(BytesIO(), path, password, async_=async_)
        return path

    def upload(
        self, 
        /, 
        file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        overwrite_or_ignore: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        if hasattr(file, "read"):
            if not fspath(path):
                try:
                    path = ospath.basename(getattr(file, "name"))
                except AttributeError as e:
                    raise OSError(errno.EINVAL, "Please specify the upload path") from e
        else:
            local_path = fsdecode(file)
            file = open(local_path, "rb")
            if not fspath(path):
                path = ospath.basename(local_path)
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        try:
            attr = self.attr(path, password, async_=async_)
        except FileNotFoundError:
            pass
        else:
            if overwrite_or_ignore is None:
                raise FileExistsError(errno.EEXIST, path)
            elif attr["is_dir"]:
                raise IsADirectoryError(errno.EISDIR, path)
            elif not overwrite_or_ignore:
                return path
            self.fs_remove(dirname(path), [basename(path)], async_=async_)
        size: int
        if hasattr(file, "getbuffer"):
            size = len(getattr(file, "getbuffer")())
        else:
            try:
                fd = getattr(file, "fileno")()
            except (UnsupportedOperation, AttributeError):
                size = 0
            else:
                size = fstat(fd).st_size
        if size:
            self.fs_put(file, path, as_task=as_task, async_=async_)
        else:
            # NOTE: Because I previously found that AList does not support chunked transfer.
            #   - https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Transfer-Encoding
            self.fs_form(file, path, as_task=as_task, async_=async_)
        return path

    def upload_tree(
        self, 
        /, 
        local_path: PathType, 
        path: PathType = "", 
        password: str = "", 
        as_task: bool = False, 
        no_root: bool = False, 
        overwrite_or_ignore: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        if isinstance(path, (AttrDict, AlistPath)):
            if not password:
                password = path.get("password", "")
            path = cast(str, path["path"])
        else:
            path = self.abspath(path)
        if self.isfile(path):
            raise NotADirectoryError(errno.ENOTDIR, path)
        try:
            it = scandir(local_path)
        except NotADirectoryError:
            return self.upload(
                local_path, 
                joinpath(path, ospath.basename(local_path)), 
                password, 
                as_task=as_task, 
                overwrite_or_ignore=overwrite_or_ignore, 
                async_=async_, 
            )
        else:
            if not no_root:
                path = joinpath(path, ospath.basename(local_path))
            for entry in it:
                if entry.is_dir():
                    self.upload_tree(
                        entry.path, 
                        joinpath(path, entry.name), 
                        password, 
                        as_task=as_task, 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        async_=async_, 
                    )
                else:
                    self.upload(
                        entry.path, 
                        joinpath(path, entry.name), 
                        password, 
                        as_task=as_task, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        async_=async_, 
                    )
            return path

    unlink = remove

    def _walk_bfs(
        self, 
        /, 
        top: PathType = "", 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        dq: deque[tuple[int, str]] = deque()
        push, pop = dq.append, dq.popleft
        if isinstance(top, AlistPath):
            if not password:
                password = top.get("password", "")
            top = top["path"]
        else:
            top = self.abspath(top)
        top = cast(str, top)
        push((0, top))
        while dq:
            depth, parent = pop()
            depth += 1
            try:
                push_me = max_depth < 0 or depth < max_depth
                if min_depth <= 0 or depth >= min_depth:
                    dirs: list[dict] = []
                    files: list[dict] = []
                    for attr in self.listdir_attr(parent, password, refresh=refresh, async_=async_):
                        if attr["is_dir"]:
                            dirs.append(attr)
                            if push_me:
                                push((depth, attr["path"]))
                        else:
                            files.append(attr)
                    yield parent, dirs, files
                elif push_me:
                    for attr in self.listdir_attr(parent, password, refresh=refresh, async_=async_):
                        if attr["is_dir"]:
                            push((depth, attr["path"]))
            except OSError as e:
                if callable(onerror):
                    onerror(e)
                elif onerror:
                    raise

    def _walk_dfs(
        self, 
        /, 
        top: PathType = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: None | bool = None, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
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
            top = top["path"]
        else:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_attr(top, password, refresh=refresh, async_=async_)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        dirs: list[dict] = []
        files: list[dict] = []
        for attr in ls:
            if attr["is_dir"]:
                dirs.append(attr)
            else:
                files.append(attr)
        if yield_me and topdown:
            yield top, dirs, files
        for attr in dirs:
            yield from self._walk_dfs(
                attr["path"], 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                async_=async_, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

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
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        for path, dirs, files in self.walk_attr(
            top, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            password=password, 
            refresh=refresh, 
            async_=async_, 
        ):
            yield path, [a["name"] for a in dirs], [a["name"] for a in files]

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
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        if topdown is None:
            return self._walk_bfs(
                top, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                async_=async_, 
            )
        else:
            return self._walk_dfs(
                top, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                async_=async_, 
            )

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
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        for path, dirs, files in self.walk_attr(
            top, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            password=password, 
            refresh=refresh, 
            async_=async_, 
        ):
            yield (
                path, 
                [AlistPath(self, **a) for a in dirs], 
                [AlistPath(self, **a) for a in files], 
            )

    def write_bytes(
        self, 
        /, 
        path: PathType, 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
        password: str = "", 
        as_task: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = BytesIO(data)
        return self.upload(
            data, 
            path, 
            password=password, 
            as_task=as_task, 
            overwrite_or_ignore=True, 
            async_=async_, 
        )

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
    ):
        bio = BytesIO()
        if text:
            if encoding is None:
                encoding = "utf-8"
            tio = TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)
            tio.write(text)
            tio.flush()
            bio.seek(0)
        return self.write_bytes(path, bio, password=password, as_task=as_task, async_=async_)

    cd  = chdir
    cp  = copy
    pwd = getcwd
    ls  = listdir
    la  = listdir_attr
    ll  = listdir_path
    mv  = move
    rm  = remove

