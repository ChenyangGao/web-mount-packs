#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

"""Python CloudDrive web API wrapper.

This is a web API wrapper works with the running "CloudDrive" server, and provide some methods, which refer to `os` and `shutil` modules.

- CloudDrive official website: https://www.clouddrive2.com/index.html
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 9)
__all__ = ["CloudDriveClient", "CloudDrivePath", "CloudDriveFileSystem"]

import errno

from datetime import datetime
from collections.abc import Callable, ItemsView, Iterator, KeysView, Mapping, Sequence, ValuesView
from functools import cached_property, partial, update_wrapper
from io import BytesIO, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE
from os import fsdecode, fspath, makedirs, scandir, stat_result, path as ospath, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError
from stat import S_IFDIR, S_IFREG
from typing import cast, Any, IO, Literal, Never, Optional
from types import MappingProxyType
from urllib.parse import quote
from uuid import uuid4
from warnings import warn

from dateutil.parser import parse as parse_datetime
from google.protobuf.json_format import MessageToDict # type: ignore
from grpc import StatusCode, RpcError # type: ignore

from .client import Client
import CloudDrive_pb2 # type: ignore

from .util.file import HTTPFileReader, SupportsRead, SupportsWrite
from .util.response import get_content_length
from .util.text import posix_glob_translate_iter
from .util.urlopen import urlopen


def check_response(func, /):
    def wrapper(*args, **kwds):
        try:
            return func(*args, **kwds)
        except RpcError as e:
            if not hasattr(e, "code"):
                raise
            fargs = (func, args, kwds)
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
                    raise OSError(errno.EREMOTE, fargs, e.details()) from e
    return update_wrapper(wrapper, func)


class CloudDriveClient(Client):

    @cached_property
    def fs(self, /) -> CloudDriveFileSystem:
        return CloudDriveFileSystem(self)

    def get_url(self, /, path: str) -> str:
        return self.download_baseurl + quote(path, safe="?&=")

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
        if key not in self.__dict__ and self.__dict__.get("lastest_update"):
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
        dst = self.fs.copy(self, dst_path, overwrite_or_ignore=overwrite_or_ignore)
        if not dst:
            return None
        return type(self)(self.fs, dst)

    def copytree(
        self, 
        /, 
        dst_dir: str | PathLike[str], 
    ) -> CloudDrivePath:
        dst = self.fs.copytree(self, dst_dir)
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

    def get_url(self, /) -> str:
        return self.fs.get_url(self)

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
        try:
            return self["isDirectory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def is_file(self, /) -> bool:
        try:
            return not self["isDirectory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return True

    def is_symlink(self, /) -> bool:
        return False

    def isdir(self, /) -> bool:
        return self.fs.isdir(self)

    def isfile(self, /) -> bool:
        return self.fs.isfile(self)

    def iter(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
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
        return self.fs.listdir(
            self, 
            refresh=refresh, 
        )

    def listdir_attr(
        self, 
        /, 
        refresh: Optional[bool] = None, 
    ) -> list[dict]:
        return self.fs.listdir_attr(
            self, 
            refresh=refresh, 
        )

    def listdir_path(
        self, 
        /, 
        refresh: Optional[bool] = None, 
    ) -> list[CloudDrivePath]:
        return self.fs.listdir_path(
            self, 
            refresh=refresh, 
        )

    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
    ) -> bool:
        pattern = "/" + "".join(t[0] for t in posix_glob_translate_iter(path_pattern))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

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

    @cached_property
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
        topdown: bool = True, 
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

    def walk_path(
        self, 
        /, 
        topdown: bool = True, 
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
        channel = None, 
    ) -> CloudDriveFileSystem:
        return cls(CloudDriveClient(origin, username, password, channel=channel))

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
        dirname, name = split(path)
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
        dir_, name = split(path)
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
        finally:
            client.CloseFile(CloudDrive_pb2.CloseFileRequest(fileHandle=fh))

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
        fetch_attr: bool = False, 
        _check: bool = True, 
    ) -> CloudDrivePath:
        if not isinstance(path, CloudDrivePath):
            if _check:
                path = self.abspath(path)
            path = CloudDrivePath(self, path)
        if fetch_attr:
            path()
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
        attr["path"] = path
        attr["lastest_update"] = datetime.now()
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
        _check: bool = True, 
    ) -> str:
        raise UnsupportedOperation(errno.ENOSYS, "copy")

    def copytree(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
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
            attr = self._attr(path)
            is_dir = attr.isDirectory
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
        _check: bool = True, 
    ) -> str:
        if isinstance(path, CloudDrivePath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.get_url(path)

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
        splitted_pats = tuple(posix_glob_translate_iter(pattern))
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
                pattern = joinpath(re_escape(dirname), "".join(t[0] for t in splitted_pats))
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
                pattern = joinpath(re_escape(dirname), "".join(t[0] for t in splitted_pats[i:]))
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

    def iter(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if not max_depth:
            return
        if _check:
            top = self.abspath(top)
            if refresh is None:
                refresh = self.refresh
        top = cast(str, top)
        refresh = cast(bool, refresh)
        try:
            it = self._iterdir(top, refresh=refresh)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        for attr in it:
            path = CloudDrivePath(self, joinpath(top, attr.name), **MessageToDict(attr))
            yield_me = min_depth <= 0
            if yield_me and predicate:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred 
            if yield_me and topdown:
                yield path
            if attr.isDirectory:
                yield from self.iter(
                    path.path, 
                    refresh=refresh, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    _check=_check, 
                )
            if yield_me and not topdown:
                yield path

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
        lastest_update = datetime.now()
        for attr in map(MessageToDict, self._iterdir(path, refresh=refresh)):
            attr["path"] = joinpath(path, attr["name"])
            attr["lastest_update"] = lastest_update
            yield attr

    def list_storage(self, /) -> list[dict]:
        return [MessageToDict(a) for a in self._iterdir("/")]

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
    ) -> dict:
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
            raise SameFileError(src_path)
        if commonpath((src_path, dst_path)) == dst_path:
            raise PermissionError(errno.EPERM, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_attr = self._attr(src_path)
        try:
            dst_attr = self._attr(dst_path)
        except FileNotFoundError:
            self.rename(src_path, dst_path, _check=False)
        else:
            if dst_attr.isDirectory:
                dst_filename = basename(src_path)
                dst_filepath = joinpath(dst_path, dst_filename)
                if self.exists(dst_filepath, _check=False):
                    raise FileExistsError(errno.EEXIST, f"destination path {dst_filepath!r} already exists")
                self._move([src_path], dst_path)
                return dst_filepath
            else:
                self.rename(src_path, dst_path, _check=False)
        return dst_path

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
        if commonpath((src_path, dst_path)) == dst_path:
            raise PermissionError(errno.EPERM, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        src_attr = self._attr(src_path)
        try:
            dst_attr = self._attr(dst_path)
        except FileNotFoundError:
            if src_dir == dst_dir:
                self._rename((src_path, dst_name))
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
            self._rename((src_path, dst_name))
        else:
            if commonpath((src_dir, dst_dir)) == "/":
                raise PermissionError(errno.EPERM, f"cross clouds/storages movement does not allow renaming: [{src_dir!r}]{src_path!r} -> [{src_dir!r}]{dst_path!r}")
            tempname = f"{uuid4()}{splitext(src_name)[1]}"
            self._rename((src_path, tempname))
            try:
                self._move([joinpath(src_dir, tempname)], dst_dir)
                try:
                    self._rename((joinpath(dst_dir, tempname), dst_name))
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
        if path == "/":
            return
        elif dirname(path) == "/":
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
        lastest_update = datetime.now()
        for attr in self._search_iter(path, search_for, refresh=refresh, fuzzy=fuzzy):
            yield CloudDrivePath(self, path, lastest_update=lastest_update, **MessageToDict(attr))

    # TODO: 需要进一步实现，更准确的 st_mode
    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ):
        attr = self.attr(path, _check=_check)
        is_dir = attr.get("isDirectory", False)
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o777, 
            0, 
            0, 
            1, 
            0, 
            0, 
            0 if is_dir else int(attr["size"]), 
            parse_datetime(attr["accessTime"]).timestamp(), 
            parse_datetime(attr["writeTime"]).timestamp(), 
            parse_datetime(attr["createTime"]).timestamp(), 
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
        self._upload(path)
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
        self._upload(path, file)
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

    def walk(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        if not max_depth:
            return
        if _check:
            top = self.abspath(top)
            if refresh is None:
                refresh = self.refresh
        top = cast(str, top)
        refresh = cast(bool, refresh)
        try:
            it = self._iterdir(top, refresh=refresh)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        dirs: list[str] = []
        files: list[str] = []
        for attr in it:
            (dirs if attr.isDirectory else files).append(attr.name)
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        if min_depth <= 0 and topdown:
            yield top, dirs, files
        for dir_ in dirs:
            yield from self.walk(
                joinpath(top, dir_), 
                refresh=refresh, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if min_depth <= 0 and not topdown:
            yield top, dirs, files

    def walk_path(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[CloudDrivePath], list[CloudDrivePath]]]:
        if not max_depth:
            return
        if _check:
            top = self.abspath(top)
            if refresh is None:
                refresh = self.refresh
        top = cast(str, top)
        refresh = cast(bool, refresh)
        try:
            it = self._iterdir(top, refresh=refresh)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        dirs: list[CloudDrivePath] = []
        files: list[CloudDrivePath] = []
        for attr in it:
            (dirs if attr.isDirectory else files).append(
                CloudDrivePath(self, joinpath(top, attr.name), **MessageToDict(attr)))
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        if yield_me and topdown:
            yield top, dirs, files
        for dir_ in dirs:
            yield from self.walk_path(
                dir_.path, 
                refresh=refresh, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

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
    pwd = getcwd
    ls  = listdir
    ll  = listdir_path
    rm  = remove

