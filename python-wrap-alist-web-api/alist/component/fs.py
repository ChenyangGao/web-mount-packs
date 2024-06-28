#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["AlistPath", "AlistFileSystem"]

import errno

from asyncio import get_running_loop, run, TaskGroup
from collections import deque
from collections.abc import (
    AsyncIterator, Awaitable, Callable, Coroutine, ItemsView, Iterable, Iterator, KeysView, Mapping, ValuesView
)
from functools import cached_property, partial, update_wrapper
from hashlib import sha256
from http.cookiejar import Cookie, CookieJar
from inspect import isawaitable
from io import BytesIO, TextIOWrapper, UnsupportedOperation
from json import loads
from mimetypes import guess_type
from os import fsdecode, fspath, fstat, makedirs, scandir, stat_result, path as ospath, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split as splitpath, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError
from stat import S_IFDIR, S_IFREG
from time import time
from typing import cast, overload, Any, IO, Literal, Never, Optional
from types import MappingProxyType, MethodType
from urllib.parse import quote
from uuid import uuid4
from warnings import filterwarnings, warn

from dateutil.parser import parse as dt_parse
from filewrap import bio_chunk_iter, bio_chunk_async_iter, SupportsRead, SupportsWrite
from glob_pattern import translate_iter
from httpfile import HTTPFileReader
from http_request import complete_url, encode_multipart_data, encode_multipart_data_async
from http_response import get_content_length
from httpx import AsyncClient, Client, Cookies, AsyncHTTPTransport, HTTPTransport
from httpx_request import request
from iterutils import run_gen_step
from multidict import CIMultiDict
from urlopen import urlopen

from .client import check_response, AlistClient


filterwarnings("ignore", category=DeprecationWarning)
parse_json = lambda _, content: loads(content)
httpx_request = partial(request, timeout=(5, 60, 60, 5))


class method:

    def __init__(self, func: Callable, /):
        self.__func__ = func

    def __get__(self, instance, type=None, /):
        if instance is None:
            return self
        return MethodType(self.__func__, instance)

    def __set__(self, instance, value, /):
        raise TypeError("can't set value")


def parse_as_timestamp(s: Optional[str] = None, /) -> float:
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
        path: str | PathLike[str] = "", 
        password: str = "", 
        **attr, 
    ):
        attr.update(fs=fs, path=fs.abspath(path), password=password)
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> AlistPath:
        return type(self)(
            self.fs, 
            commonpath((self.path, self.fs.abspath(path))), 
            password=self.password, 
        )

    def __call__(self, /) -> AlistPath:
        self.__dict__.update(self.fs.attr(self))
        return self

    def __contains__(self, key, /) -> bool:
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.__dict__.get("last_update"):
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
        return f"<{name}({', '.join(f'{k}={v!r}' for k, v in self.__dict__.items())})>"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> AlistPath:
        return self.joinpath(path)

    @property
    def is_attr_loaded(self, /) -> bool:
        return "last_update" in self.__dict__

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
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
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
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        refresh: Optional[bool] = None, 
    ):
        return self.fs.download_tree(
            self, 
            local_dir, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
            refresh=refresh, 
        )

    def exists(self, /) -> bool:
        return self.fs.exists(self)

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
        topdown: Optional[bool] = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
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

    def joinpath(self, *paths: str | PathLike[str]) -> AlistPath:
        if not paths:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new, self.password)

    def listdir(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        refresh: Optional[bool] = None, 
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
        refresh: Optional[bool] = None, 
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
        refresh: Optional[bool] = None, 
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
        return re_compile(pattern).fullmatch(self.path) is not None

    @property
    def media_type(self, /) -> Optional[str]:
        if not self.is_file():
            return None
        return guess_type(self.path)[0] or "application/octet-stream"

    def mkdir(self, /, exist_ok: bool = True):
        self.fs.makedirs(self, exist_ok=exist_ok)

    def move(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.move(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    @cached_property
    def name(self, /) -> str:
        return basename(self.path)

    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
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
        path = self.path
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path), self.password)

    @cached_property
    def parents(self, /) -> tuple[AlistPath, ...]:
        path = self.path
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
        return ("/", *self.path[1:].split("/"))

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
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ) -> str:
        return self.fs.read_text(self, encoding=encoding, errors=errors, newline=newline)

    def relative_to(self, other: str | AlistPath, /) -> str:
        if isinstance(other, AlistPath):
            other = other.path
        elif not other.startswith("/"):
            other = self.fs.abspath(other)
        path = self.path
        if path == other:
            return ""
        elif path.startswith(other+"/"):
            return path[len(other)+1:]
        raise ValueError(f"{path!r} is not in the subpath of {other!r}")

    @cached_property
    def relatives(self, /) -> tuple[str]:
        def it(path):
            stop = len(path)
            while stop:
                stop = path.rfind("/", 0, stop)
                yield path[stop+1:]
        return tuple(it(self.path))

    def remove(self, /, recursive: bool = True):
        self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.rename(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def renames(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.renames(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.replace(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
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

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if type(self) is type(path):
            return self == path
        return path in ("", ".") or self.path == self.fs.abspath(path)

    def stat(self, /) -> stat_result:
        return self.fs.stat(self)

    @cached_property
    def stem(self, /) -> str:
        return splitext(basename(self.path))[0]

    @cached_property
    def suffix(self, /) -> str:
        return splitext(basename(self.path))[1]

    @cached_property
    def suffixes(self, /) -> tuple[str, ...]:
        return tuple("." + part for part in basename(self.path).split(".")[1:])

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
        topdown: Optional[bool] = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: Optional[bool] = None, 
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
        topdown: Optional[bool] = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: Optional[bool] = None, 
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
        topdown: Optional[bool] = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: Optional[bool] = None, 
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
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
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

    def __init__(
        self, 
        /, 
        client: AlistClient, 
        path: str | PathLike[str] = "/", 
        refresh: bool = False, 
        request_kwargs: Optional[dict] = None, 
    ):
        if path in ("", "/", ".", ".."):
            path = "/"
        else:
            path = "/" + normpath("/" + fspath(path)).lstrip("/")
        if request_kwargs is None:
            request_kwargs = {}
        self.__dict__.update(client=client, path=path, refresh=refresh, request_kwargs=request_kwargs)

    def __contains__(self, path: str | PathLike[str], /) -> bool:
        return self.exists(path)

    def __delitem__(self, path: str | PathLike[str], /):
        self.rmtree(path)

    def __getitem__(self, path: str | PathLike[str], /) -> AlistPath:
        return self.as_path(path)

    def __iter__(self, /) -> Iterator[AlistPath]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, path: str | PathLike[str], /) -> AlistFileSystem:
        self.chdir(path)
        return self

    def __len__(self, /) -> int:
        return self.get_directory_capacity(self.path, _check=False)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self.client!r}, path={self.path!r}, refresh={self.refresh!r}, request_kwargs={self.request_kwargs!r})"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __setitem__(
        self, 
        /, 
        path: str | PathLike[str] = "", 
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

    def set_refresh(self, value: bool, /):
        self.__dict__["refresh"] = value

    @check_response
    def fs_batch_rename(
        self, 
        /, 
        rename_pairs: Iterable[tuple[str, str]], 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "src_dir": src_dir, 
            "rename_objects": [{
                "src_name": src_name, 
                "new_name": new_name, 
            } for src_name, new_name in rename_pairs]
        }
        return self.client.fs_batch_rename(payload, **self.request_kwargs)

    @check_response
    def fs_copy(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, AlistPath):
            dst_dir = dst_dir.path
        elif _check:
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self.client.fs_copy(payload, **self.request_kwargs)

    @check_response
    def fs_dirs(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        payload = {
            "path": path, 
            "password": password, 
            "refresh": refresh, 
        }
        return self.client.fs_dirs(payload, **self.request_kwargs)

    @check_response
    def fs_form(
        self, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.fs_form(local_path_or_file, path, as_task=as_task, **self.request_kwargs)

    @check_response
    def fs_get(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "password": password}
        return self.client.fs_get(payload, **self.request_kwargs)

    @check_response
    def fs_list(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        payload = {
            "path": path, 
            "password": password, 
            "page": page, 
            "per_page": per_page, 
            "refresh": refresh, 
        }
        return self.client.fs_list(payload, **self.request_kwargs)

    @check_response
    def fs_list_storage(self, /) -> dict:
        return self.client.admin_storage_list(**self.request_kwargs)

    @check_response
    def fs_mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return {"code": 200}
        return self.client.fs_mkdir({"path": path}, **self.request_kwargs)

    @check_response
    def fs_move(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> dict:
        if not names:
            return {"code": 200}
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, AlistPath):
            dst_dir = dst_dir.path
        elif _check:
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        if src_dir == dst_dir:
            return {"code": 200}
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self.client.fs_move(payload, **self.request_kwargs)

    @check_response
    def fs_put(
        self, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.fs_put(local_path_or_file, path, as_task=as_task, **self.request_kwargs)

    @check_response
    def fs_recursive_move(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, AlistPath):
            dst_dir = dst_dir.path
        elif _check:
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir}
        return self.client.fs_recursive_move(payload, **self.request_kwargs)

    @check_response
    def fs_regex_rename(
        self, 
        /, 
        src_name_regex: str, 
        new_name_regex: str, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "src_dir": src_dir, 
            "src_name_regex": src_name_regex, 
            "new_name_regex": new_name_regex, 
        }
        return self.client.fs_regex_rename(payload, **self.request_kwargs)

    @check_response
    def fs_remove(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> dict:
        if not names:
            return {"code": 200}
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"names": names, "dir": src_dir}
        return self.client.fs_remove(payload, **self.request_kwargs)

    @check_response
    def fs_remove_empty_directory(
        self, 
        /, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"src_dir": src_dir}
        return self.client.fs_remove_empty_directory(payload, **self.request_kwargs)

    @check_response
    def fs_remove_storage(self, id: int | str, /) -> dict:
        return self.client.admin_storage_delete(id, **self.request_kwargs)

    @check_response
    def fs_rename(
        self, 
        /, 
        path: str | PathLike[str], 
        name: str, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "name": name}
        return self.client.fs_rename(payload, **self.request_kwargs)

    @check_response
    def fs_search(
        self, 
        /, 
        keywords: str, 
        src_dir: str | PathLike[str] = "", 
        scope: Literal[0, 1, 2] = 0, 
        page: int = 1, 
        per_page: int = 0, 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            if not password:
                password = src_dir.password
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "parent": src_dir, 
            "keywords": keywords, 
            "scope": scope, 
            "page": page, 
            "per_page": per_page, 
            "password": password, 
        }
        return self.client.fs_search(payload, **self.request_kwargs)

    def abspath(self, /, path: str | PathLike[str] = "") -> str:
        if path == "/":
            return "/"
        elif path in ("", "."):
            return self.path
        elif isinstance(path, AlistPath):
            return path.path
        path = fspath(path)
        if path.startswith("/"):
            return "/" + normpath(path).lstrip("/")
        return normpath(joinpath(self.path, path))

    def as_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> AlistPath:
        if not isinstance(path, AlistPath):
            if _check:
                path = self.abspath(path)
            path = AlistPath(self, path, password)
        elif password:
            path = AlistPath(self, path.path, password)
        return path

    def attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.fs_get(path, password, _check=False)["data"]
        last_update = time()
        attr["ctime"] = int(parse_as_timestamp(attr.get("created")))
        attr["mtime"] = int(parse_as_timestamp(attr.get("modified")))
        attr["atime"] = int(last_update)
        attr["path"] = path
        attr["password"] = password
        attr["last_update"] = last_update
        return attr

    def chdir(
        self, 
        /, 
        path: str | PathLike[str] = "/", 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == self.path:
            pass
        elif path == "/":
            self.__dict__["path"] = "/"
        elif self.attr(path, password, _check=False)["is_dir"]:
            self.__dict__["path"] = path
        else:
            raise NotADirectoryError(errno.ENOTDIR, path)

    def copy(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        recursive: bool = False, 
        _check: bool = True, 
    ) -> Optional[str]:
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if _check:
            src_attr = self.attr(src_path, src_password, _check=False)
            if src_attr["is_dir"]:
                if recursive:
                    return self.copytree(
                        src_path, 
                        dst_path, 
                        src_password, 
                        dst_password, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                if overwrite_or_ignore == False:
                    return None
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"source path {src_path!r} is a directory: {src_path!r} -> {dst_path!r}", 
                )
        if src_path == dst_path:
            if overwrite_or_ignore is None:
                raise SameFileError(src_path)
            return None
        cmpath = commonpath((src_path, dst_path))
        if cmpath == dst_path:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a file as its ancestor is not allowed: {src_path!r} -> {dst_path!r}", 
            )
        elif cmpath == src_path:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a file as its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
            )
        src_dir, src_name = splitpath(src_path)
        dst_dir, dst_name = splitpath(dst_path)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            pass
        else:
            if dst_attr["is_dir"]:
                if overwrite_or_ignore == False:
                    return None
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"destination path {src_path!r} is a directory: {src_path!r} -> {dst_path!r}", 
                )
            elif overwrite_or_ignore is None:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"destination path {dst_path!r} already exists: {src_path!r} -> {dst_path!r}", 
                )
            elif not overwrite_or_ignore:
                return None
            self.fs_remove(dst_dir, [dst_name], _check=False)
        if src_name == dst_name:
            self.fs_copy(src_dir, dst_dir, [src_name], _check=False)
        else:
            src_storage = self.storage_of(src_dir, src_password, _check=False)
            dst_storage = self.storage_of(dst_dir, dst_password, _check=False)
            if src_storage != dst_storage:
                if overwrite_or_ignore == False:
                    return None
                raise PermissionError(
                    errno.EPERM, 
                    f"cross storages replication does not allow renaming: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}", 
                )
            tempdirname = str(uuid4())
            tempdir = joinpath(dst_dir, tempdirname)
            self.fs_mkdir(tempdir, _check=False)
            try:
                self.fs_copy(src_dir, tempdir, [src_name], _check=False)
                self.fs_rename(joinpath(tempdir, src_name), dst_name, _check=False)
                self.fs_move(tempdir, dst_dir, [dst_name], _check=False)
            finally:
                self.fs_remove(dst_dir, [tempdirname], _check=False)
        return dst_path

    def copytree(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Optional[str]:
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if _check:
            src_attr = self.attr(src_path, src_password, _check=False)
            if not src_attr["is_dir"]:
                return self.copy(
                    src_path, 
                    dst_path, 
                    src_password, 
                    dst_password, 
                    overwrite_or_ignore=overwrite_or_ignore, 
                    _check=False, 
                )
        if src_path == dst_path:
            if overwrite_or_ignore is None:
                raise SameFileError(src_path)
            return None
        elif commonpath((src_path, dst_path)) == dst_path:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a directory to its subordinate path is not allowed: {src_path!r} ->> {dst_path!r}", 
            )
        src_dir, src_name = splitpath(src_path)
        dst_dir, dst_name = splitpath(dst_path)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            if src_name == dst_name:
                self.fs_copy(src_dir, dst_dir, [src_name], _check=False)
                return dst_path
            self.makedirs(dst_path, dst_password, exist_ok=True, _check=False)
        else:
            if not dst_attr["is_dir"]:
                if overwrite_or_ignore == False:
                    return None
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"destination is not directory: {src_path!r} ->> {dst_path!r}", 
                )
            elif overwrite_or_ignore is None:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"destination already exists: {src_path!r} ->> {dst_path!r}", 
                )
        for attr in self.listdir_attr(src_path):
            if attr["is_dir"]:
                self.copytree(
                    joinpath(src_path, attr["name"]), 
                    joinpath(dst_path, attr["name"]), 
                    src_password=src_password, 
                    dst_password=dst_password, 
                    overwrite_or_ignore=overwrite_or_ignore, 
                    _check=False, 
                )
            else:
                self.copy(
                    joinpath(src_path, attr["name"]), 
                    joinpath(dst_path, attr["name"]), 
                    src_password=src_password, 
                    dst_password=dst_password, 
                    overwrite_or_ignore=overwrite_or_ignore, 
                    _check=False, 
                )
        return dst_path

    def download(
        self, 
        /, 
        path: str | PathLike[str], 
        local_path_or_file: bytes | str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.attr(path, password, _check=False)
        if attr["is_dir"]:
            raise IsADirectoryError(errno.EISDIR, path)
        if hasattr(local_path_or_file, "write"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
        else:
            local_path = fspath(local_path_or_file)
            mode: str = write_mode
            if mode:
                mode += "b"
            elif ospath.lexists(local_path):
                return
            else:
                mode = "wb"
            if local_path:
                file = open(local_path, mode)
            else:
                file = open(basename(path), mode)
        file = cast(SupportsWrite[bytes], file)
        url = attr["raw_url"]
        if download:
            download(url, file, headers=self.client.headers)
        else:
            with urlopen(url, headers=self.client.headers) as fsrc:
                copyfileobj(fsrc, file)

    def download_tree(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ):
        is_dir: bool
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            is_dir = path.is_dir()
            path = path.path
        elif _check:
            path = self.abspath(path)
            is_dir = self.attr(path, password, _check=False)["is_dir"]
        else:
            is_dir = True
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        local_dir = fsdecode(local_dir)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        if is_dir:
            if not no_root:
                local_dir = ospath.join(local_dir, basename(path))
                if local_dir:
                    makedirs(local_dir, exist_ok=True)
            for pathobj in self.listdir_path(path, password, refresh=refresh, _check=False):
                name = pathobj.name
                if pathobj.is_dir():
                    self.download_tree(
                        pathobj.path, 
                        ospath.join(local_dir, name), 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
                        password=password, 
                        refresh=refresh, 
                        _check=False, 
                    )
                else:
                    self.download(
                        pathobj.path, 
                        ospath.join(local_dir, name), 
                        write_mode=write_mode, 
                        download=download, 
                        password=password, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                ospath.join(local_dir, basename(path)), 
                write_mode=write_mode, 
                download=download, 
                password=password, 
                _check=False, 
            )

    def exists(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            self.attr(path, password, _check=_check)
            return True
        except FileNotFoundError:
            return False

    def getcwd(self, /) -> str:
        return self.path

    def get_directory_capacity(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> int:
        return self.fs_list(path, per_page=1, password=password, refresh=refresh, _check=_check)["data"]["total"]

    def get_url(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        ensure_ascii: bool = True, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.get_url(path, ensure_ascii=ensure_ascii)

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if pattern == "*":
            return self.iter(dirname, password=password, _check=_check)
        elif pattern == "**":
            return self.iter(dirname, password=password, max_depth=-1, _check=_check)
        elif not pattern:
            dirname = self.as_path(dirname, password, _check=_check)
            if dirname.exists():
                return iter((dirname,))
            return iter(())
        elif not pattern.lstrip("/"):
            return iter((AlistPath(self, "/", password),))
        splitted_pats = tuple(translate_iter(pattern))
        if pattern.startswith("/"):
            dirname = "/"
        elif isinstance(dirname, AlistPath):
            if not password:
                password = dirname.password
            dirname = dirname.path
        elif _check:
            dirname = self.abspath(dirname)
        dirname = cast(str, dirname)
        i = 0
        if ignore_case:
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), "/".join(t[0] for t in splitted_pats))
                match = re_compile("(?i:%s)" % pattern).fullmatch
                return self.iter(
                    dirname, 
                    password=password, 
                    max_depth=-1, 
                    predicate=lambda p: match(p.path) is not None, 
                    _check=False, 
                )
        else:
            typ = None
            for i, (pat, typ, orig) in enumerate(splitted_pats):
                if typ != "orig":
                    break
                dirname = joinpath(dirname, orig)
            if typ == "orig":
                if self.exists(dirname, password, _check=False):
                    return iter((AlistPath(self, dirname, password),))
                return iter(())
            elif typ == "dstar" and i + 1 == len(splitted_pats):
                return self.iter(dirname, password=password, max_depth=-1, _check=False)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), "/".join(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                return self.iter(
                    dirname, 
                    password=password, 
                    max_depth=-1, 
                    predicate=lambda p: match(p.path) is not None, 
                    _check=False, 
                )
        cref_cache: dict[int, Callable] = {}
        def glob_step_match(path, i):
            j = i + 1
            at_end = j == len(splitted_pats)
            pat, typ, orig = splitted_pats[i]
            if typ == "orig":
                subpath = path.joinpath(orig)
                if at_end:
                    if subpath.exists():
                        yield subpath
                elif subpath.is_dir():
                    yield from glob_step_match(subpath, j)
            elif typ == "star":
                if at_end:
                    yield from path.listdir_path()
                else:
                    for subpath in path.listdir_path():
                        if subpath.is_dir():
                            yield from glob_step_match(subpath, j)
            else:
                for subpath in path.listdir_path():
                    try:
                        cref = cref_cache[i]
                    except KeyError:
                        if ignore_case:
                            pat = "(?i:%s)" % pat
                        cref = cref_cache[i] = re_compile(pat).fullmatch
                    if cref(subpath.name):
                        if at_end:
                            yield subpath
                        elif subpath.is_dir():
                            yield from glob_step_match(subpath, j)
        path = AlistPath(self, dirname, password)
        if not path.is_dir():
            return iter(())
        return glob_step_match(path, i)

    def isdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            return self.attr(path, password, _check=_check)["is_dir"]
        except FileNotFoundError:
            return False

    def isfile(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            return not self.attr(path, password, _check=_check)["is_dir"]
        except FileNotFoundError:
            return False

    def is_empty(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self.attr(path, password, _check=False)
        except FileNotFoundError:
            return True
        if attr["is_dir"]:
            return self.get_directory_capacity(path, password, _check=False) == 0
        else:
            return attr["size"] == 0

    def is_storage(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return True
        try:
            return any(path == s["mount_path"] for s in self.list_storage())
        except PermissionError:
            try:
                return self.attr(path, password, _check=False).get("hash_info") is None
            except FileNotFoundError:
                return False

    def _iter_bfs(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        dq: deque[tuple[int, AlistPath]] = deque()
        push, pop = dq.append, dq.popleft
        path = self.as_path(top, password)
        if not path.is_attr_loaded:
            path()
        push((0, path))
        while dq:
            depth, path = pop()
            if min_depth <= 0:
                pred = predicate(path) if predicate else True
                if pred is None:
                    return
                elif pred:
                    yield path
                min_depth = 1
            if depth == 0 and (not path.is_dir() or 0 <= max_depth <= depth):
                return
            depth += 1
            try:
                for path in self.listdir_path(path, password, refresh=refresh, _check=False):
                    pred = predicate(path) if predicate else True
                    if pred is None:
                        continue
                    elif pred and depth >= min_depth:
                        yield path
                    if path.is_dir() and (max_depth < 0 or depth < max_depth):
                        push((depth, path))
            except OSError as e:
                if callable(onerror):
                    onerror(e)
                elif onerror:
                    raise

    def _iter_dfs(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if not max_depth:
            return
        global_yield_me = True
        if min_depth > 1:
            global_yield_me = False
            min_depth -= 1
        elif min_depth <= 0:
            path = self.as_path(top, password)
            if not path.is_attr_loaded:
                path()
            pred = predicate(path) if predicate else True
            if pred is None:
                return
            elif pred:
                yield path
            if path.is_file():
                return
            min_depth = 1
        if max_depth > 0:
            max_depth -= 1
        try:
            ls = self.listdir_path(top, password, refresh=refresh, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        for path in ls:
            yield_me = global_yield_me
            if yield_me and predicate:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred
            if yield_me and topdown:
                yield path
            if path.is_dir():
                yield from self.iter(
                    path, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    refresh=refresh, 
                    password=password, 
                    _check=_check, 
                )
            if yield_me and not topdown:
                yield path

    def iter(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: Optional[bool] = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if topdown is None:
            return self._iter_bfs(
                top, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                refresh=refresh, 
                password=password, 
                _check=_check, 
            )
        else:
            return self._iter_dfs(
                top, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                refresh=refresh, 
                password=password, 
                _check=_check, 
            )

    def iterdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> Iterator[dict]:
        yield from self.listdir_attr(
            path, 
            password, 
            refresh=refresh, 
            page=page, 
            per_page=per_page, 
            _check=_check, 
        )

    def list_storage(self, /) -> list[dict]:
        return self.fs_list_storage()["data"]["content"] or []

    def listdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> list[str]:
        return [item["name"] for item in self.listdir_attr(
            path, 
            password, 
            refresh=refresh, 
            page=page, 
            per_page=per_page, 
            _check=_check, 
        )]

    def listdir_attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> list[dict]:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        if not self.attr(path, password, _check=False)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        data = self.fs_list(
            path, 
            password, 
            refresh=refresh, 
            page=page, 
            per_page=per_page, 
            _check=False, 
        )["data"]
        last_update = time()
        content = data["content"]
        if not content:
            return []
        for attr in content:
            attr["ctime"] = int(parse_as_timestamp(attr.get("created")))
            attr["mtime"] = int(parse_as_timestamp(attr.get("modified")))
            attr["atime"] = int(last_update)
            attr["path"] = joinpath(path, attr["name"])
            attr["password"] = password
            attr["last_update"] = last_update
        return content

    def listdir_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> list[AlistPath]:
        return [
            AlistPath(self, **item) 
            for item in self.listdir_attr(
                path, 
                password, 
                refresh=refresh, 
                page=page, 
                per_page=per_page, 
                _check=_check, 
            )
        ]

    def makedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        exist_ok: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        if not exist_ok and self.exists(path, password, _check=False):
            raise FileExistsError(errno.EEXIST, path)
        self.fs_mkdir(path, _check=False)
        return path

    def mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(
                errno.EPERM, 
                "create root directory is not allowed (because it has always existed)", 
            )
        if self.is_storage(path, password, _check=False):
            raise PermissionError(
                errno.EPERM, 
                f"can't directly create a storage by `mkdir`: {path!r}", 
            )
        try:
            self.attr(path, password, _check=False)
        except FileNotFoundError as e:
            dir_ = dirname(path)
            if not self.attr(dir_, password, _check=False)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, dir_) from e
            self.fs_mkdir(path, _check=False)
            return path
        else:
            raise FileExistsError(errno.EEXIST, path)

    def move(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
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
        src_attr = self.attr(src_path, src_password, _check=False)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            return self.rename(src_path, dst_path, src_password, dst_password, _check=False)
        else:
            if dst_attr["is_dir"]:
                dst_filename = basename(src_path)
                dst_filepath = joinpath(dst_path, dst_filename)
                if self.exists(dst_filepath, dst_password, _check=False):
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"destination path {dst_filepath!r} already exists", 
                    )
                self.fs_move(dirname(src_path), dst_path, [dst_filename], _check=False)
                return dst_filepath
            raise FileExistsError(errno.EEXIST, f"destination path {dst_path!r} already exists")

    def open(
        self, 
        /, 
        path: str | PathLike[str], 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        password: str = "", 
        _check: bool = True, 
    ) -> HTTPFileReader | IO:
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
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
        path: str | PathLike[str], 
        start: int = 0, 
        stop: Optional[int] = None, 
        password: str = "", 
        _check: bool = True, 
    ) -> bytes:
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_bytes(path.url, start, stop)

    def read_bytes_range(
        self, 
        /, 
        path: str | PathLike[str], 
        bytes_range: str = "0-", 
        password: str = "", 
        _check: bool = True, 
    ) -> bytes:
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_bytes_range(path.url, bytes_range)

    def read_block(
        self, 
        /, 
        path: str | PathLike[str], 
        size: int = 0, 
        offset: int = 0, 
        password: str = "", 
        _check: bool = True, 
    ) -> bytes:
        if size <= 0:
            return b""
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_block(path.url, size, offset)

    def read_text(
        self, 
        /, 
        path: str | PathLike[str], 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        password: str = "", 
        _check: bool = True, 
    ):
        return self.open(
            path, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            password=password, 
            _check=_check, 
        ).read()

    def remove(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        recursive: bool = False, 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            if recursive:
                try:
                    storages = self.list_storage()
                except PermissionError:
                    self.fs_remove("/", self.listdir("/", password, refresh=True), _check=False)
                else:
                    for storage in storages:
                        self.fs_remove_storage(storage["id"])
                return
            else:
                raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        attr = self.attr(path, password, _check=False)
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
        self.fs_remove(dirname(path), [basename(path)], _check=False)

    def removedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        get_directory_capacity = self.get_directory_capacity
        remove_storage = self.fs_remove_storage
        if get_directory_capacity(path, password, _check=False):
            raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        try:
            storages = self.list_storage()
        except PermissionError:
            if self.attr(path, password, _check=False)["hash_info"] is None:
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
            while get_directory_capacity(parent_dir, password, _check=False) <= 1:
                for storage in storages:
                    if storage["mount_path"] == parent_dir:
                        remove_storage(storage["id"])
                        del_dir = ""
                        break
                else:
                    del_dir = parent_dir
                parent_dir = dirname(parent_dir)
            if del_dir:
                self.fs_remove(parent_dir, [basename(del_dir)], _check=False)
        except OSError as e:
            pass

    def rename(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        replace: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
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
        src_attr = self.attr(src_path, src_password, _check=False)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            if src_attr.get("hash_info") is None:
                for storage in self.list_storage():
                    if src_path == storage["mount_path"]:
                        storage["mount_path"] = dst_path
                        self.client.admin_storage_update(storage)
                        break
                return dst_path
            elif src_dir == dst_dir:
                self.fs_rename(src_path, dst_name, _check=False)
                return dst_path
            if not self.attr(dst_dir, dst_password, _check=False)["is_dir"]:
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
                        if self.get_directory_capacity(dst_path, dst_password, _check=False):
                            raise OSError(errno.ENOTEMPTY, f"directory {dst_path!r} is not empty: {src_path!r} -> {dst_path!r}")
                    else:
                        raise NotADirectoryError(errno.ENOTDIR, f"{dst_path!r} is not a directory: {src_path!r} -> {dst_path!r}")
                elif dst_attr["is_dir"]:
                    raise IsADirectoryError(errno.EISDIR, f"{dst_path!r} is a directory: {src_path!r} -> {dst_path!r}")
                self.fs_remove(dst_dir, [dst_name], _check=False)
            else:
                raise FileExistsError(errno.EEXIST, f"{dst_path!r} already exists: {src_path!r} -> {dst_path!r}")
        src_storage = self.storage_of(src_dir, src_password, _check=False)
        dst_storage = self.storage_of(dst_dir, dst_password, _check=False)
        if src_name == dst_name:
            if src_storage != dst_storage:
                warn("cross storages movement will retain the original file: {src_path!r} |-> {dst_path!r}")
            self.fs_move(src_dir, dst_dir, [src_name], _check=False)
        elif src_dir == dst_dir:
            self.fs_rename(src_path, dst_name, _check=False)
        else:
            if src_storage != dst_storage:
                raise PermissionError(
                    errno.EPERM, 
                    f"cross storages movement does not allow renaming: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}", 
                )
            tempname = f"{uuid4()}{splitext(src_name)[1]}"
            self.fs_rename(src_path, tempname, _check=False)
            try:
                self.fs_move(src_dir, dst_dir, [tempname], _check=False)
                try:
                    self.fs_rename(joinpath(dst_dir, tempname), dst_name, _check=False)
                except:
                    self.fs_move(dst_dir, src_dir, [tempname], _check=False)
                    raise
            except:
                self.fs_rename(joinpath(src_dir, tempname), src_name, _check=False)
                raise
        return dst_path

    def renames(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        dst = self.rename(src_path, dst_path, src_password, dst_password, _check=False)
        if dirname(src_path) != dirname(dst_path):
            try:
                self.removedirs(dirname(src_path), src_password, _check=False)
            except OSError:
                pass
        return dst

    def replace(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> str:
        return self.rename(src_path, dst_path, src_password, dst_password, replace=True, _check=_check)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if not pattern:
            return self.iter(dirname, password=password, max_depth=-1, _check=_check)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, password=password, ignore_case=ignore_case, _check=_check)

    def rmdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif self.is_storage(path, password, _check=False):
            raise PermissionError(errno.EPERM, f"remove a storage by `rmdir` is not allowed: {path!r}")
        elif not self.attr(path, password, _check=False)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        elif not self.is_empty(path, password, _check=False):
            raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        self.fs_remove(dirname(path), [basename(path)], _check=False)

    def rmtree(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        self.remove(path, password, recursive=True, _check=_check)

    def scandir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        for item in self.listdir_attr(
            path, 
            password, 
            refresh=refresh, 
            _check=_check, 
        ):
            yield AlistPath(self, **item)

    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> stat_result:
        attr = self.attr(path, password, _check=_check)
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
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        try:
            storages = self.list_storage()
        except PermissionError:
            while True:
                try:
                    attr = self.attr(path, password, _check=False)
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
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.exists(path, password, _check=False):
            dir_ = dirname(path)
            if not self.attr(dir_, password, _check=False)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
            return self.upload(BytesIO(), path, password, _check=False)
        return path

    def upload(
        self, 
        /, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        as_task: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        file: SupportsRead[bytes]
        if hasattr(local_path_or_file, "read"):
            if isinstance(local_path_or_file, TextIOWrapper):
                file = local_path_or_file.buffer
            else:
                file = cast(SupportsRead[bytes], local_path_or_file)
            if not fspath(path):
                try:
                    path = ospath.basename(local_path_or_file.name) # type: ignore
                except AttributeError as e:
                    raise OSError(errno.EINVAL, "Please specify the upload path") from e
        else:
            local_path = fsdecode(local_path_or_file)
            file = open(local_path, "rb")
            if not fspath(path):
                path = ospath.basename(local_path)
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self.attr(path, password, _check=False)
        except FileNotFoundError:
            pass
        else:
            if overwrite_or_ignore is None:
                raise FileExistsError(errno.EEXIST, path)
            elif attr["is_dir"]:
                raise IsADirectoryError(errno.EISDIR, path)
            elif not overwrite_or_ignore:
                return path
            self.fs_remove(dirname(path), [basename(path)], _check=False)
        size: int
        if hasattr(file, "getbuffer"):
            size = len(file.getbuffer()) # type: ignore
        else:
            try:
                fd = file.fileno() # type: ignore
            except (UnsupportedOperation, AttributeError):
                size = 0
            else:
                size = fstat(fd).st_size
        if size:
            self.fs_put(file, path, as_task=as_task, _check=False)
        else:
            # NOTE: Because I previously found that AList does not support chunked transfer.
            #   - https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Transfer-Encoding
            self.fs_form(file, path, as_task=as_task, _check=False)
        return path

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str], 
        path: str | PathLike[str] = "", 
        password: str = "", 
        as_task: bool = False, 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
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
                _check=False, 
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
                        _check=False, 
                    )
                else:
                    self.upload(
                        entry.path, 
                        joinpath(path, entry.name), 
                        password, 
                        as_task=as_task, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
            return path

    unlink = remove

    def _walk_bfs(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        dq: deque[tuple[int, str]] = deque()
        push, pop = dq.append, dq.popleft
        if isinstance(top, AlistPath):
            if not password:
                password = top.password
            top = top.path
        elif _check:
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
                    for attr in self.listdir_attr(parent, password, refresh=refresh, _check=False):
                        if attr["is_dir"]:
                            dirs.append(attr)
                            if push_me:
                                push((depth, attr["path"]))
                        else:
                            files.append(attr)
                    yield parent, dirs, files
                elif push_me:
                    for attr in self.listdir_attr(parent, password, refresh=refresh, _check=False):
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
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
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
                password = top.password
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_attr(top, password, refresh=refresh, _check=False)
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
                _check=False, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

    def walk(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: Optional[bool] = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        for path, dirs, files in self.walk_attr(
            top, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            password=password, 
            refresh=refresh, 
            _check=_check, 
        ):
            yield path, [a["name"] for a in dirs], [a["name"] for a in files]

    def walk_attr(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: Optional[bool] = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        if topdown is None:
            return self._walk_bfs(
                top, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                _check=_check, 
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
                _check=_check, 
            )

    def walk_path(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: Optional[bool] = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        for path, dirs, files in self.walk_attr(
            top, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            password=password, 
            refresh=refresh, 
            _check=_check, 
        ):
            yield (
                path, 
                [AlistPath(self, **a) for a in dirs], 
                [AlistPath(self, **a) for a in files], 
            )

    def write_bytes(
        self, 
        /, 
        path: str | PathLike[str], 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
        password: str = "", 
        as_task: bool = False, 
        _check: bool = True, 
    ):
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = BytesIO(data)
        return self.upload(
            data, 
            path, 
            password=password, 
            as_task=as_task, 
            overwrite_or_ignore=True, 
            _check=_check, 
        )

    def write_text(
        self, 
        /, 
        path: str | PathLike[str], 
        text: str = "", 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        password: str = "", 
        as_task: bool = False, 
        _check: bool = True, 
    ):
        bio = BytesIO()
        if text:
            if encoding is None:
                encoding = "utf-8"
            tio = TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)
            tio.write(text)
            tio.flush()
            bio.seek(0)
        return self.write_bytes(path, bio, password=password, as_task=as_task, _check=_check)

    cd  = chdir
    cp  = copy
    pwd = getcwd
    ls  = listdir
    la  = listdir_attr
    ll  = listdir_path
    mv  = move
    rm  = remove

