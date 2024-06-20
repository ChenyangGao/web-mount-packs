#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

"""Python CloudDrive web API wrapper.

This is a web API wrapper works with the running "CloudDrive" server, and provide some methods, which refer to `os` and `shutil` modules.

- CloudDrive official website: https://www.clouddrive2.com/index.html
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 12)
__all__ = [
    "CloudDriveClient", "CloudDrivePath", "CloudDriveFileSystem", 
    "CloudDriveDownloadTaskList", "CloudDriveUploadTaskList", 
]

import errno

from collections import deque
from collections.abc import (
    AsyncIterator, Callable, Coroutine, ItemsView, Iterable, Iterator, KeysView, Mapping, Sequence, ValuesView
)
from functools import cached_property, partial, update_wrapper
from inspect import isawaitable
from io import BytesIO, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE
from mimetypes import guess_type
from os import fsdecode, fspath, makedirs, scandir, stat_result, path as ospath, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split as splitpath, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError
from stat import S_IFDIR, S_IFREG
from time import time
from typing import cast, overload, Any, IO, Literal, Never, Optional
from types import MappingProxyType
from urllib.parse import quote
from uuid import uuid4
from warnings import warn

from dateutil.parser import parse as dt_parse
from google.protobuf.json_format import MessageToDict # type: ignore
from grpc import StatusCode, RpcError # type: ignore

from .client import Client
import CloudDrive_pb2 # type: ignore

from filewrap import SupportsRead, SupportsWrite
from glob_pattern import translate_iter
from httpfile import HTTPFileReader
from http_response import get_content_length
from urlopen import urlopen


def check_response(func, /):
    def raise_for_code(fargs, e):
        if not hasattr(e, "code"):
            raise
        match e.code():
            case StatusCode.PERMISSION_DENIED:
                raise PermissionError(errno.EPERM, fargs, e.details()) from e
            case StatusCode.NOT_FOUND:
                raise FileNotFoundError(errno.ENOENT, fargs, e.details()) from e
            case StatusCode.ALREADY_EXISTS:
                raise FileExistsError(errno.EEXIST, fargs, e.details()) from e
            case StatusCode.UNIMPLEMENTED:
                raise UnsupportedOperation(errno.ENOSYS, fargs, e.details()) from e
            case StatusCode.UNAUTHENTICATED:
                raise PermissionError(errno.EACCES, fargs, e.details()) from e
            case _:
                raise OSError(errno.EIO, fargs, e.details()) from e
    def wrapper(*args, **kwds):
        try:
            resp = func(*args, **kwds)
        except RpcError as e:
            raise_for_code((func, args, kwds), e)
        else:
            if isawaitable(resp):
                async def async_check(resp):
                    try:
                        return await resp
                    except RpcError as e:
                        raise_for_code((func, args, kwds), e)
                return async_check(resp)
            return resp
    return update_wrapper(wrapper, func)


def parse_as_timestamp(s: Optional[str] = None, /) -> float:
    if not s:
        return 0.0
    if s.startswith("0001-01-01"):
        return 0.0
    try:
        return dt_parse(s).timestamp()
    except:
        return 0.0


class CloudDriveClient(Client):

    @cached_property
    def fs(self, /) -> CloudDriveFileSystem:
        return CloudDriveFileSystem(self)

    @cached_property
    def download_tasklist(self, /) -> CloudDriveDownloadTaskList:
        return CloudDriveDownloadTaskList(self)

    @cached_property
    def upload_tasklist(self, /) -> CloudDriveUploadTaskList:
        return CloudDriveUploadTaskList(self)

    def get_url(
        self, 
        /, 
        path: str, 
        ensure_ascii: bool = True, 
    ) -> str:
        if ensure_ascii:
            return self.download_baseurl + quote(path, safe="@[]:!$&'()*+,;=")
        else:
            return self.download_baseurl + path.translate({0x23: "%23", 0x2F: "%2F", 0x3F: "%3F"})

    @staticmethod
    def open(
        url: str | Callable[[], str], 
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        **request_kwargs, 
    ) -> HTTPFileReader:
        """
        """
        _urlopen = urlopen
        if request_kwargs:
            _urlopen = partial(urlopen, **request_kwargs)
        return HTTPFileReader(
            url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
            urlopen=_urlopen, 
        )

    @staticmethod
    def read_bytes(
        url: str, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
        **request_kwargs, 
    ) -> bytes:
        """
        """
        length = None
        if start < 0:
            with urlopen(url) as resp:
                length = get_content_length(urlopen(url))
            if length is None:
                raise OSError(errno.ESPIPE, "can't determine content length")
            start += length
        if start < 0:
            start = 0
        if stop is None:
            bytes_range = f"{start}-"
        else:
            if stop < 0:
                if length is None:
                    with urlopen(url) as resp:
                        length = get_content_length(urlopen(url))
                if length is None:
                    raise OSError(errno.ESPIPE, "can't determine content length")
                stop += length
            if stop <= 0 or start >= stop:
                return b""
            bytes_range = f"{start}-{stop-1}"
        return __class__.read_bytes_range(url, bytes_range, headers=headers, **request_kwargs) # type: ignore

    @staticmethod
    def read_bytes_range(
        url: str, 
        bytes_range: str = "0-", 
        headers: Optional[Mapping] = None, 
        **request_kwargs, 
    ) -> bytes:
        """
        """
        if headers:
            headers = {**headers, "Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        else:
            headers = {"Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        with urlopen(url, headers=headers, **request_kwargs) as resp:
            if resp.status == 416:
                return b""
            return resp.read()

    @staticmethod
    def read_block(
        url: str, 
        size: int = 0, 
        offset: int = 0, 
        headers: Optional[Mapping] = None, 
        **request_kwargs, 
    ) -> bytes:
        """
        """
        if size <= 0:
            return b""
        return __class__.read_bytes(url, offset, offset+size, headers=headers, **request_kwargs) # type: ignore


class CloudDrivePath(Mapping, PathLike[str]):
    "CloudDrive path information."
    fs: CloudDriveFileSystem
    path: str

    def __init__(
        self, 
        /, 
        fs: CloudDriveFileSystem, 
        path: str | PathLike[str], 
        **attr, 
    ):
        attr.update(fs=fs, path=fs.abspath(path))
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> CloudDrivePath:
        return type(self)(self.fs, commonpath((self, self.fs.abspath(path))))

    def __call__(self, /) -> CloudDrivePath:
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
        if not type(self) is type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __gt__(self, path, /) -> bool:
        if not type(self) is type(path) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __hash__(self, /) -> int:
        return hash((self.fs.client, self.path))

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /) -> bool:
        if not type(self) is type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __lt__(self, path, /) -> bool:
        if not type(self) is type(path) or self.fs.client != path.fs.client or self.path == path.path:
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

    def __truediv__(self, path: str | PathLike[str], /) -> CloudDrivePath:
        return type(self).joinpath(self, path)

    @property
    def is_attr_loaded(self, /) -> bool:
        return "last_update" in self.__dict__

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
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> Optional[CloudDrivePath]:
        dst = self.fs.copy(
            self, 
            dst_path, 
            overwrite_or_ignore=overwrite_or_ignore, 
            recursive=True, 
        )
        if not dst:
            return None
        return type(self)(self.fs, dst)

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
            refresh=refresh, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
        )

    def exists(self, /) -> bool:
        return self.fs.exists(self)

    def get_url(
        self, 
        /, 
        ensure_ascii: bool = True, 
    ) -> str:
        return self.fs.get_url(self, ensure_ascii=ensure_ascii)

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
    ) -> Iterator[CloudDrivePath]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def is_absolute(self, /) -> bool:
        return True

    def is_dir(self, /):
        return self["isDirectory"]

    def is_file(self, /) -> bool:
        return not self["isDirectory"]

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
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
    ) -> Iterator[CloudDrivePath]:
        return self.fs.iter(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def joinpath(self, *paths: str | PathLike[str]) -> CloudDrivePath:
        if not paths:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new)

    def listdir(
        self, 
        /, 
        refresh: Optional[bool] = None, 
    ) -> list[str]:
        return self.fs.listdir(self, refresh=refresh)

    def listdir_attr(
        self, 
        /, 
        refresh: Optional[bool] = None, 
    ) -> list[dict]:
        return self.fs.listdir_attr(self, refresh=refresh)

    def listdir_path(
        self, 
        /, 
        refresh: Optional[bool] = None, 
    ) -> list[CloudDrivePath]:
        return self.fs.listdir_path(self, refresh=refresh)

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

    def move(self, /, dst_path: str | PathLike[str]) -> CloudDrivePath:
        dst = self.fs.move(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

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
    def parent(self, /) -> CloudDrivePath:
        path = self.path
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path))

    @cached_property
    def parents(self, /) -> tuple[CloudDrivePath, ...]:
        path = self.path
        if path == "/":
            return ()
        parents: list[CloudDrivePath] = []
        cls, fs = type(self), self.fs
        parent = dirname(path)
        while path != parent:
            parents.append(cls(fs, parent))
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

    def relative_to(self, other: str | CloudDrivePath, /) -> str:
        if isinstance(other, CloudDrivePath):
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

    def remove(self, /, recursive: bool = False):
        self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> CloudDrivePath:
        dst = self.fs.rename(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def renames(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> CloudDrivePath:
        dst = self.fs.renames(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> CloudDrivePath:
        dst = self.fs.replace(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
    ) -> Iterator[CloudDrivePath]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def rmdir(self, /):
        self.fs.rmdir(self)

    @cached_property
    def root(self, /) -> CloudDrivePath:
        if dirname(self.path) == "/":
            return self
        return self.parents[-2]

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
    ) -> Iterator[tuple[str, list[CloudDrivePath], list[CloudDrivePath]]]:
        return self.fs.walk_path(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def with_name(self, name: str, /) -> CloudDrivePath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> CloudDrivePath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> CloudDrivePath:
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


class CloudDriveFileSystem:
    """Implemented some file system methods by utilizing CloudDrive's web API 
    and referencing modules such as `os`, `posixpath`, `pathlib.Path` and `shutil`."""
    client: CloudDriveClient
    path: str
    refresh: bool

    def __init__(
        self, 
        /, 
        client: CloudDriveClient, 
        path: str | PathLike[str] = "/", 
        refresh: bool = False, 
    ):
        if path in ("", "/", ".", ".."):
            path = "/"
        else:
            path = "/" + normpath("/" + fspath(path)).lstrip("/")
        self.__dict__.update(client=client, path=path, refresh=refresh)

    def __contains__(self, path: str | PathLike[str], /) -> bool:
        return self.exists(path)

    def __delitem__(self, path: str | PathLike[str], /):
        self.rmtree(path)

    def __getitem__(self, path: str | PathLike[str], /) -> CloudDrivePath:
        return self.as_path(path)

    def __iter__(self, /) -> Iterator[CloudDrivePath]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, /, path: str | PathLike[str]) -> CloudDriveFileSystem:
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
        return f"{name}(client={self.client!r}, path={self.path!r}, refresh={self.refresh!r})"

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
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
    ) -> CloudDriveFileSystem:
        return cls(CloudDriveClient(origin, username, password))

    def set_refresh(self, value: bool, /):
        self.__dict__["refresh"] = value

    @check_response
    def _attr(self, path: str, /):
        return self.client.FindFileByPath(CloudDrive_pb2.FindFileByPathRequest(path=path))

    @check_response
    def _delete(self, path: str, /, *paths: str):
        if paths:
            return self.client.DeleteFiles(CloudDrive_pb2.MultiFileRequest(path=[path, *paths]))
        else:
            return self.client.DeleteFile(CloudDrive_pb2.FileRequest(path=path))

    @check_response
    def _delete_cloud(self, name: str, username: str, /):
        return self.client.RemoveCloudAPI(CloudDrive_pb2.RemoveCloudAPIRequest(
                cloudName=name, userName=username))

    @check_response
    def _iterdir(self, path: str, /, refresh: bool = False):
        it = self.client.GetSubFiles(CloudDrive_pb2.ListSubFileRequest(path=path, forceRefresh=refresh))
        it = iter(check_response(it.__next__), None)
        return (a for m in it for a in m.subFiles)

    @check_response
    def _mkdir(self, path: str, /):
        dirname, name = splitpath(path)
        return self.client.CreateFolder(
            CloudDrive_pb2.CreateFolderRequest(parentPath=dirname, folderName=name))

    @check_response
    def _move(self, paths: Sequence[str], dst_dir: str, /):
        if not paths:
            raise OSError(errno.EINVAL, "empty `paths`")
        return self.client.MoveFile(CloudDrive_pb2.MoveFileRequest(theFilePaths=paths, destPath=dst_dir))

    @check_response
    def _search_iter(
        self, 
        path: str, 
        search_for: str, 
        /, 
        refresh: bool = False, 
        fuzzy: bool = False, 
    ):
        it = self.client.GetSearchResults(CloudDrive_pb2.SearchRequest(
            path=path, 
            searchFor=search_for, 
            forceRefresh=refresh, 
            fuzzyMatch=fuzzy, 
        ))
        it = iter(check_response(it.__next__), None)
        return (a for m in it for a in m.subFiles)

    @check_response
    def _rename(self, pair: tuple[str, str], /, *pairs: tuple[str, str]):
        if pairs:
            return self.client.RenameFiles(CloudDrive_pb2.RenameFilesRequest(
                renameFiles=[
                    CloudDrive_pb2.RenameFileRequest(theFilePath=path, newName=name)
                    for path, name in (pair, *pairs)
                ]
            ))
        else:
            path, name = pair
            return self.client.RenameFile(CloudDrive_pb2.RenameFileRequest(theFilePath=path, newName=name))

    @check_response
    def _upload(self, path: str, file=None, /):
        client = self.client
        dir_, name = splitpath(path)
        fh = client.CreateFile(CloudDrive_pb2.CreateFileRequest(parentPath=dir_, fileName=name)).fileHandle
        try:
            if file is not None:
                offset = 0
                while data := file.read(DEFAULT_BUFFER_SIZE):
                    client.WriteToFile(CloudDrive_pb2.WriteFileRequest(
                        fileHandle=fh, 
                        startPos=offset, 
                        length=len(data), 
                        buffer=data, 
                        closeFile=False, 
                    ))
                    offset += len(data)
            return client.CloseFile(CloudDrive_pb2.CloseFileRequest(fileHandle=fh))
        except:
            client.CloseFile(CloudDrive_pb2.CloseFileRequest(fileHandle=fh))
            raise

    def abspath(self, path: str | PathLike[str] = "", /) -> str:
        if path == "/":
            return "/"
        elif path in ("", "."):
            return self.path
        elif isinstance(path, CloudDrivePath):
            return path.path
        path = fspath(path)
        if path.startswith("/"):
            return "/" + normpath(path).lstrip("/")
        return normpath(joinpath(self.path, path))

    def as_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> CloudDrivePath:
        if not isinstance(path, CloudDrivePath):
            if _check:
                path = self.abspath(path)
            path = CloudDrivePath(self, path)
        return path

    def attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = MessageToDict(self._attr(path))
        last_update = time()
        attr["path"] = attr.get("fullPathName") or path
        attr["ctime"] = parse_as_timestamp(attr.get("createTime"))
        attr["mtime"] = parse_as_timestamp(attr.get("writeTime"))
        attr["atime"] = parse_as_timestamp(attr.get("accessTime"))
        attr.setdefault("isDirectory", False)
        attr["last_update"] = last_update
        return attr

    def chdir(
        self, 
        /, 
        path: str | PathLike[str] = "/", 
        _check: bool = True, 
    ):
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == self.path:
            pass
        elif path == "/":
            self.__dict__["path"] = "/"
        elif self._attr(path).isDirectory:
            self.__dict__["path"] = path
        else:
            raise NotADirectoryError(errno.ENOTDIR, path)

    def copy(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = True, 
        recursive: bool = False, 
        _check: bool = True, 
    ) -> Optional[str]:
        raise UnsupportedOperation(errno.ENOSYS, "copy")

    def copytree(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Optional[str]:
        raise UnsupportedOperation(errno.ENOSYS, "copytree")

    def download(
        self, 
        /, 
        path: str | PathLike[str], 
        local_path_or_file: bytes | str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        _check: bool = True, 
    ):
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.attr(path, _check=False)
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
        url = self.client.download_baseurl + quote(path, safe="?&=")
        if download:
            download(url, file)
        else:
            with urlopen(url) as fsrc:
                copyfileobj(fsrc, file)

    def download_tree(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ):
        is_dir: bool
        if isinstance(path, CloudDrivePath):
            is_dir = path.is_dir()
            path = path.path
        elif _check:
            path = self.abspath(path)
            is_dir = self._attr(path).isDirectory
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
            for pathobj in self.listdir_path(path, refresh=refresh, _check=False):
                name = pathobj.name
                if pathobj.is_dir():
                    self.download_tree(
                        pathobj.name, 
                        ospath.join(local_dir, name), 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
                        refresh=refresh, 
                        _check=False, 
                    )
                else:
                    self.download(
                        pathobj.name, 
                        ospath.join(local_dir, name), 
                        write_mode=write_mode, 
                        download=download, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                ospath.join(local_dir, basename(path)), 
                write_mode=write_mode, 
                download=download, 
                _check=False, 
            )

    def exists(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            self.attr(path, _check=_check)
            return True
        except FileNotFoundError:
            return False

    def getcwd(self, /) -> str:
        return self.path

    def get_directory_capacity(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> int:
        return len(self.listdir_attr(path, refresh=refresh, _check=_check))

    def get_url(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        ensure_ascii: bool = True, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, CloudDrivePath):
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
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if pattern == "*":
            return self.iter(dirname, _check=_check)
        elif pattern == "**":
            return self.iter(dirname, max_depth=-1, _check=_check)
        elif not pattern:
            dirname = self.as_path(dirname, _check=_check)
            if dirname.exists():
                return iter((dirname,))
            return iter(())
        elif not pattern.lstrip("/"):
            return iter((CloudDrivePath(self, "/"),))
        splitted_pats = tuple(translate_iter(pattern))
        if pattern.startswith("/"):
            dirname = "/"
        elif isinstance(dirname, CloudDrivePath):
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
                if self.exists(dirname, _check=False):
                    return iter((CloudDrivePath(self, dirname),))
                return iter(())
            elif typ == "dstar" and i + 1 == len(splitted_pats):
                return self.iter(dirname, max_depth=-1, _check=False)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), "/".join(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                return self.iter(
                    dirname, 
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
        path = CloudDrivePath(self, dirname)
        if not path.is_dir():
            return iter(())
        return glob_step_match(path, i)

    def isdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        try:
            return self.attr(path, _check=_check)["isDirectory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def isfile(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        try:
            return not self.attr(path, _check=_check)["isDirectory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return True

    def is_empty(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self._attr(path)
        except FileNotFoundError:
            return True
        if attr.isDirectory:
            try:
                next(self._iterdir(path))
                return False
            except StopIteration:
                return True
        else:
            return int(attr.get("size", 0)) == 0

    def is_storage(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return path == "/" or dirname(path) == path

    def _iter_bfs(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        dq: deque[tuple[int, CloudDrivePath]] = deque()
        push, pop = dq.append, dq.popleft
        path = self.as_path(top)
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
                for path in self.listdir_path(path, refresh=refresh, _check=False):
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
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if not max_depth:
            return
        global_yield_me = True
        if min_depth > 1:
            global_yield_me = False
            min_depth -= 1
        elif min_depth <= 0:
            path = self.as_path(top)
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
            ls = self.listdir_path(top, refresh=refresh, _check=False)
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
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if topdown is None:
            return self._iter_bfs(
                top, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                refresh=refresh, 
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
                _check=_check, 
            )

    def iterdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[dict]:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        last_update = time()
        for attr in map(MessageToDict, self._iterdir(path, refresh=refresh)):
            attr["path"] = attr.get("fullPathName") or joinpath(path, attr["name"])
            attr["ctime"] = parse_as_timestamp(attr.get("createTime"))
            attr["mtime"] = parse_as_timestamp(attr.get("writeTime"))
            attr["atime"] = parse_as_timestamp(attr.get("accessTime"))
            attr.setdefault("isDirectory", False)
            attr["last_update"] = last_update
            yield attr

    def list_storage(self, /) -> list[dict]:
        return self.listdir_attr("/")

    def listdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> list[str]:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        return [a.name for a in self._iterdir(path, refresh)]

    def listdir_attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> list[dict]:
        return list(self.iterdir(path, refresh, _check=_check))

    def listdir_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> list[CloudDrivePath]:
        return [
            CloudDrivePath(self, **attr)
            for attr in self.iterdir(path, refresh, _check=_check)
        ]

    def makedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        exist_ok: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        if not exist_ok and self.exists(path, _check=False):
            raise FileExistsError(errno.EEXIST, path)
        return self._mkdir(path).folderCreated.fullPathName

    def mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "create root directory is not allowed (because it has always existed)")
        if dirname(path) == "/":
            raise PermissionError(errno.EPERM, f"can't directly create a cloud/storage by `mkdir`: {path!r}")
        try:
            self._attr(path)
        except FileNotFoundError as e:
            dir_ = dirname(path)
            if not self._attr(dir_).isDirectory:
                raise NotADirectoryError(errno.ENOTDIR, dir_) from e
            return self._mkdir(path).folderCreated.fullPathName
        else:
            raise FileExistsError(errno.EEXIST, path)

    def move(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, CloudDrivePath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, CloudDrivePath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
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
        src_attr = self._attr(src_path)
        try:
            dst_attr = self._attr(dst_path)
        except FileNotFoundError:
            return self.rename(src_path, dst_path, _check=False)
        else:
            if dst_attr.isDirectory:
                dst_filename = basename(src_path)
                dst_filepath = joinpath(dst_path, dst_filename)
                if self.exists(dst_filepath, _check=False):
                    raise FileExistsError(errno.EEXIST, f"destination path {dst_filepath!r} already exists")
                self._move([src_path], dst_path)
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
        _check: bool = True, 
    ):
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        path = self.as_path(path, _check=_check)
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
        _check: bool = True, 
    ) -> bytes:
        path = self.as_path(path, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_bytes(path.url, start, stop)

    def read_bytes_range(
        self, 
        /, 
        path: str | PathLike[str], 
        bytes_range: str = "0-", 
        _check: bool = True, 
    ) -> bytes:
        path = self.as_path(path, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_bytes_range(path.url, bytes_range)

    def read_block(
        self, 
        /, 
        path: str | PathLike[str], 
        size: int = 0, 
        offset: int = 0, 
        _check: bool = True, 
    ) -> bytes:
        if size <= 0:
            return b""
        path = self.as_path(path, _check=_check)
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
        _check: bool = True, 
    ):
        return self.open(
            path, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            _check=_check, 
        ).read()

    def remove(
        self, 
        /, 
        path: str | PathLike[str], 
        recursive: bool = False, 
        _check: bool = True, 
    ):
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            if recursive:
                for attr in self._iterdir("/"):
                    self._delete_cloud(attr.name, attr.CloudAPI.userName)
                return
            else:
                raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        attr = self._attr(path)
        if attr.isDirectory:
            if not recursive:
                if dirname(path) == "/":
                    raise PermissionError(errno.EPERM, f"remove a cloud/storage is not allowed: {path!r}")
                raise IsADirectoryError(errno.EISDIR, path)
            elif dirname(path) == "/":
                self._delete_cloud(attr.name, attr.CloudAPI.userName)
                return
        self._delete(path)

    def removedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        self.rmdir(path, _check=False)
        subpath = dirname(path)
        while subpath != path:
            path = subpath
            try:
                self.rmdir(path, _check=False)
            except OSError as e:
                break
            subpath = dirname(path)

    def rename(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        replace: bool = False, 
        _check: bool = True, 
    ) -> str:
        def _update_dst_path(resp):
            nonlocal dst_path
            d = MessageToDict(resp)
            if "resultFilePaths" in d:
                dst_path = d["resultFilePaths"][0]
        if isinstance(src_path, CloudDrivePath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, CloudDrivePath):
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
        src_attr = self._attr(src_path)
        try:
            dst_attr = self._attr(dst_path)
        except FileNotFoundError:
            if src_dir == dst_dir:
                _update_dst_path(self._rename((src_path, dst_name)))
                return dst_path
            if not self._attr(dst_dir).isDirectory:
                raise NotADirectoryError(errno.ENOTDIR, f"{dst_dir!r} is not a directory: {src_path!r} -> {dst_path!r}")
        else:
            if replace:
                if dirname(dst_path) == "/":
                    raise PermissionError(errno.EPERM, f"replace a storage {dst_path!r} is not allowed: {src_path!r} -> {dst_path!r}")
                elif src_attr.isDirectory:
                    if dst_attr.isDirectory:
                        try:
                            next(self._iterdir(dst_path))
                        except StopIteration:
                            pass
                        else:
                            raise OSError(errno.ENOTEMPTY, f"directory {dst_path!r} is not empty: {src_path!r} -> {dst_path!r}")
                    else:
                        raise NotADirectoryError(errno.ENOTDIR, f"{dst_path!r} is not a directory: {src_path!r} -> {dst_path!r}")
                elif dst_attr.isDirectory:
                    raise IsADirectoryError(errno.EISDIR, f"{dst_path!r} is a directory: {src_path!r} -> {dst_path!r}")
                self._delete(dst_path)
            else:
                raise FileExistsError(errno.EEXIST, f"{dst_path!r} already exists: {src_path!r} -> {dst_path!r}")
        if src_dir == "/":
            raise PermissionError(errno.EPERM, f"move a cloud/storage into another cloud/storage is not allowed: {src_path!r} -> {dst_path!r}")
        elif dst_path == "/":
            raise PermissionError(errno.EPERM, f"move a folder to the root directory (as a cloud/storage) is not allowed: {src_path!r} -> {dst_path!r}")
        if src_name == dst_name:
            if commonpath((src_dir, dst_dir)) == "/":
                warn("cross clouds/storages movement will retain the original file: {src_path!r} |-> {dst_path!r}")
            self._move([src_path], dst_dir)
        elif src_dir == dst_dir:
            _update_dst_path(self._rename((src_path, dst_name)))
        else:
            if commonpath((src_dir, dst_dir)) == "/":
                raise PermissionError(errno.EPERM, f"cross clouds/storages movement does not allow renaming: [{src_dir!r}]{src_path!r} -> [{src_dir!r}]{dst_path!r}")
            tempname = f"{uuid4()}{splitext(src_name)[1]}"
            self._rename((src_path, tempname))
            try:
                self._move([joinpath(src_dir, tempname)], dst_dir)
                try:
                    _update_dst_path(self._rename((joinpath(dst_dir, tempname), dst_name)))
                except:
                    self._move([joinpath(dst_dir, tempname)], src_dir)
                    raise
            except:
                self._rename((joinpath(src_dir, tempname), src_name))
                raise
        return dst_path

    def renames(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, CloudDrivePath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, CloudDrivePath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        dst = self.rename(src_path, dst_path, _check=False)
        if dirname(src_path) != dirname(dst_path):
            try:
                self.removedirs(dirname(src_path), _check=False)
            except OSError:
                pass
        return dst

    def replace(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        return self.rename(src_path, dst_path, replace=True, _check=_check)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if not pattern:
            return self.iter(dirname, max_depth=-1, _check=_check)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, ignore_case=ignore_case, _check=_check)

    def rmdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif dirname(path) == "/":
            raise PermissionError(errno.EPERM, f"remove a cloud/storage by `rmdir` is not allowed: {path!r}")
        attr = self._attr(path)
        if not attr.isDirectory:
            raise NotADirectoryError(errno.ENOTDIR, path)
        elif not self.is_empty(path, _check=False):
            raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        if dirname(path) == "/":
            self._delete_cloud(attr.name, attr.CloudAPI.userName)
        else:
            self._delete(path)

    def rmtree(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        self.remove(path, recursive=True, _check=_check)

    def scandir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        return iter(self.listdir_path(path, refresh=refresh, _check=_check))

    def search(
        self, 
        /, 
        search_for: str, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        fuzzy: bool = False, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        last_update = time()
        for attr in self._search_iter(path, search_for, refresh=refresh, fuzzy=fuzzy):
            yield CloudDrivePath(self, path, last_update=last_update, **MessageToDict(attr))

    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ):
        attr = self.attr(path, _check=_check)
        is_dir = attr["isDirectory"]
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o777, 
            0, # ino
            0, # dev
            1, # nlink
            0, # uid
            0, # gid
            0 if is_dir else int(attr["size"]), # size
            attr["atime"], # atime
            attr["mtime"], # mtime
            attr["ctime"], # ctime
        ))

    def storage_of(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        try:
            return path[:path.index("/", 1)]
        except ValueError:
            return path

    def touch(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.exists(path, _check=False):
            dir_ = dirname(path)
            if dir_ == "/":
                raise PermissionError(errno.EPERM, f"can't create file in the root directory directly: {path!r}")
            if not self._attr(dir_).isDirectory:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
            resp = self._upload(path)
            d = MessageToDict(resp)
            if "resultFilePaths" in d:
                path = cast(str, d["resultFilePaths"][0])
        return path

    def upload(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        file: SupportsRead[bytes]
        if hasattr(local_path_or_file, "read"):
            file = cast(SupportsRead[bytes], local_path_or_file)
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if not path:
                try:
                    path = ospath.basename(file.name) # type: ignore
                except AttributeError as e:
                    raise OSError(errno.EINVAL, "Please specify the upload path") from e
        else:
            file = open(local_path_or_file, "rb")
            if not path:
                path = ospath.basename(local_path_or_file)
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
            self.makedirs(dirname(path), exist_ok=True, _check=False)
        path = cast(str, path)
        try:
            attr = self._attr(path)
        except FileNotFoundError:
            pass
        else:
            if overwrite_or_ignore is None:
                raise FileExistsError(errno.EEXIST, path)
            elif attr.isDirectory:
                raise IsADirectoryError(errno.EISDIR, path)
            elif not overwrite_or_ignore:
                return path
            self._delete(path)
        resp = self._upload(path, file)
        d = MessageToDict(resp)
        if "resultFilePaths" in d:
            path = cast(str, d["resultFilePaths"][0])
        return path

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str], 
        path: str | PathLike[str] = "", 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            if not self._attr(path).isDirectory:
                raise NotADirectoryError(errno.ENOTDIR, path)
        except FileNotFoundError:
            self.makedirs(path, exist_ok=True, _check=False)
        try:
            it = scandir(local_path)
        except NotADirectoryError:
            return self.upload(
                local_path, 
                joinpath(path, ospath.basename(local_path)), 
                overwrite_or_ignore=overwrite_or_ignore, 
                _check=False, 
            )
        else:
            if not no_root:
                path = joinpath(path, ospath.basename(local_path))
                self.makedirs(path, exist_ok=True, _check=False)
            for entry in it:
                if entry.is_dir():
                    self.upload_tree(
                        entry.path, 
                        joinpath(path, entry.name), 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.upload(
                        entry.path, 
                        joinpath(path, entry.name), 
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
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        dq: deque[tuple[int, str]] = deque()
        push, pop = dq.append, dq.popleft
        if isinstance(top, CloudDrivePath):
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
                    for attr in self.iterdir(parent, refresh=refresh, _check=False):
                        if attr["isDirectory"]:
                            dirs.append(attr)
                            if push_me:
                                push((depth, attr["path"]))
                        else:
                            files.append(attr)
                    yield parent, dirs, files
                elif push_me:
                    for attr in self.iterdir(parent, refresh=refresh, _check=False):
                        if attr["isDirectory"]:
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
        if isinstance(top, CloudDrivePath):
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            dirs: list[dict] = []
            files: list[dict] = []
            for attr in self.iterdir(top, refresh=refresh, _check=False):
                if attr["isDirectory"]:
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
                    refresh=refresh, 
                    _check=False, 
                )
            if yield_me and not topdown:
                yield top, dirs, files
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return

    def walk(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: Optional[bool] = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None,
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        for path, dirs, files in self.walk_attr(
            top, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
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
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        if topdown is None:
            return self._walk_bfs(
                top, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
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
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[CloudDrivePath], list[CloudDrivePath]]]:
        for path, dirs, files in self.walk_attr(
            top, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
            _check=_check, 
        ):
            yield (
                path, 
                [CloudDrivePath(self, **a) for a in dirs], 
                [CloudDrivePath(self, **a) for a in files], 
            )

    def write_bytes(
        self, 
        /, 
        path: str | PathLike[str], 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
        _check: bool = True, 
    ):
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = BytesIO(data)
        return self.upload(data, path, overwrite_or_ignore=True, _check=_check)

    def write_text(
        self, 
        /, 
        path: str | PathLike[str], 
        text: str = "", 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
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
        return self.write_bytes(path, bio, _check=_check)

    cd  = chdir
    cp  = copy
    pwd = getcwd
    ls  = listdir
    la  = listdir_attr
    ll  = listdir_path
    mv  = move
    rm  = remove


class CloudDriveDownloadTaskList:
    "任务列表：下载"
    __slots__ = "client",

    def __init__(self, /, client: CloudDriveClient):
        self.client = client

    async def __aiter__(self, /) -> AsyncIterator[dict]:
        for t in await self._list_async():
            yield t

    def __iter__(self, /) -> Iterator[dict]:
        return iter(self._list_sync())

    @check_response
    def __len__(self, /) -> int:
        return self.client.GetDownloadFileCount().fileCount

    @check_response
    async def _list_async(self, /) -> list[dict]:
        resp = await self.client.GetDownloadFileList(async_=True)
        return [MessageToDict(t) for t in resp.downloadFiles]

    @check_response
    def _list_sync(self, /) -> list[dict]:
        resp = self.client.GetDownloadFileList()
        return [MessageToDict(t) for t in resp.downloadFiles]

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[None, None, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: bool = False, 
    ) -> list[dict] | Coroutine[None, None, list[dict]]:
        "列出所有任务"
        if async_:
            return self._list_async()
        else:
            return self._list_sync()


class CloudDriveUploadTaskList:
    "任务列表：复制"
    __slots__ = "client",

    def __init__(self, /, client: CloudDriveClient):
        self.client = client

    def __contains__(self, key: str, /) -> bool:
        return any(key == t["key"] for t in self._list_sync())

    def __delitem__(self, keys: None | str | Iterable[str], /):
        self.cancel(keys)

    def __getitem__(self, key: str, /) -> dict:
        for t in self._list_sync():
            if key == t["key"]:
                return t
        raise LookupError(f"no such key: {key!r}")

    async def __aiter__(self, /) -> AsyncIterator[dict]:
        for t in await self._list_async():
            yield t

    def __iter__(self, /) -> Iterator[dict]:
        return iter(self._list_sync())

    @check_response
    def __len__(self, /) -> int:
        return self.client.GetUploadFileCount().fileCount

    @overload
    def cancel(
        self, 
        /, 
        keys: None | str | Iterable[str] = None, 
        async_: Literal[False] = False, 
    ):
        ...
    @overload
    def cancel(
        self, 
        /, 
        keys: None | str | Iterable[str] = None, 
        async_: Literal[True] = True, 
    ) -> Coroutine:
        ...
    @check_response
    def cancel(
        self, 
        /, 
        keys: None | str | Iterable[str] = None, 
        async_: bool = False, 
    ):
        "取消某些任务"
        if keys is None:
            return self.client.CancelAllUploadFiles(async_=async_)
        if isinstance(keys, str):
            keys = keys,
        return self.client.CancelUploadFiles(CloudDrive_pb2.MultpleUploadFileKeyRequest(keys=keys), async_=async_)

    @overload
    def clear(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def clear(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[None, None, None]:
        ...
    @check_response
    def clear(
        self, 
        /, 
        async_: bool = False, 
    ) -> None | Coroutine[None, None, None]:
        "清空任务列表"
        return self.cancel()

    async def _get_async(
        self, 
        /, 
        key: str, 
        default=None, 
    ):
        return next((t for t in (await self._list_async()) if key == t["key"]), default)

    def _get_sync(
        self, 
        /, 
        key: str, 
        default=None, 
    ):
        return next((t for t in self._list_sync() if key == t["key"]), default)

    @overload
    def get(
        self, 
        /, 
        key: str, 
        default: Any, 
        async_: Literal[False] = False, 
    ) -> Any:
        ...
    @overload
    def get(
        self, 
        /, 
        key: str, 
        default: Any, 
        async_: Literal[True], 
    ) -> Coroutine[None, None, Any]:
        ...
    def get(
        self, 
        /, 
        key: str, 
        default=None, 
        async_: bool = False, 
    ) -> Any | Coroutine[None, None, Any]:
        "获取某个任务信息"
        if async_:
            return self._get_async(key, default)
        else:
            return self._get_sync(key, default)

    @overload
    def pause(
        self, 
        /, 
        keys: None | str | Iterable[str], 
        async_: Literal[False] = False, 
    ):
        ...
    @overload
    def pause(
        self, 
        /, 
        keys: None | str | Iterable[str], 
        async_: Literal[True], 
    ) -> Coroutine:
        ...
    @check_response
    def pause(
        self, 
        /, 
        keys: None | str | Iterable[str] = None, 
        async_: bool = False, 
    ):
        "暂停某些任务"
        if keys is None:
            return self.client.PauseAllUploadFiles(async_=async_)
        if isinstance(keys, str):
            keys = keys,
        return self.client.PauseUploadFiles(CloudDrive_pb2.MultpleUploadFileKeyRequest(keys=keys), async_=async_)

    @overload
    def resume(
        self, 
        /, 
        keys: None | str | Iterable[str], 
        async_: Literal[False] = False, 
    ):
        ...
    @overload
    def resume(
        self, 
        /, 
        keys: None | str | Iterable[str], 
        async_: Literal[True], 
    ) -> Coroutine:
        ...
    @check_response
    def resume(
        self, 
        /, 
        keys: None | str | Iterable[str] = None, 
        async_: bool = False, 
    ):
        "恢复某些任务"
        if keys is None:
            return self.client.ResumeAllUploadFiles(async_=async_)
        if isinstance(keys, str):
            keys = keys,
        return self.client.ResumeUploadFiles(CloudDrive_pb2.MultpleUploadFileKeyRequest(keys=keys), async_=async_)

    @check_response
    async def _list_async(
        self, 
        /, 
        page: int = 0, 
        page_size: int = 0, 
        filter: str = "", 
    ) -> list[dict]:
        if page_size <= 0:
            req = CloudDrive_pb2.GetUploadFileListRequest(getAll=True, filter=filter)
        else:
            if page < 0:
                page = 0
            req = CloudDrive_pb2.GetUploadFileListRequest(pageNumber=page, itemsPerPage=page_size, filter=filter)
        resp = await self.client.GetUploadFileList(req, async_=True)
        return [MessageToDict(t) for t in resp.uploadFiles]

    @check_response
    def _list_sync(
        self, 
        /, 
        page: int = 0, 
        page_size: int = 0, 
        filter: str = "", 
    ) -> list[dict]:
        if page_size <= 0:
            req = CloudDrive_pb2.GetUploadFileListRequest(getAll=True, filter=filter)
        else:
            if page < 0:
                page = 0
            req = CloudDrive_pb2.GetUploadFileListRequest(pageNumber=page, itemsPerPage=page_size, filter=filter)
        resp = self.client.GetUploadFileList(req)
        return [MessageToDict(t) for t in resp.uploadFiles]

    @overload
    def list(
        self, 
        /, 
        page: int, 
        page_size: int, 
        filter: str, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        page: int, 
        page_size: int, 
        filter: str, 
        async_: Literal[True], 
    ) -> Coroutine[None, None, list[dict]]:
        ...
    def list(
        self, 
        /, 
        page: int = 0, 
        page_size: int = 0, 
        filter: str = "", 
        async_: bool = False, 
    ) -> list[dict] | Coroutine[None, None, list[dict]]:
        "列出所有任务"
        if async_:
            return self._list_async(page, page_size, filter)
        else:
            return self._list_sync(page, page_size, filter)

    delete = remove = cancel

