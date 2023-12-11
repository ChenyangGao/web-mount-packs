#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

"""Python clouddrive web API wrapper.

This is a web API wrapper works with the running "clouddrive" server, and provide some methods, which refer to `os` and `shutil` modules.

- `clouddrive official website <https://www.clouddrive2.com/index.html>` 
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = ["CloudDriveClient", "CloudDrivePath", "CloudDriveFileReader", "CloudDriveFileSystem"]

import errno

from datetime import datetime
from functools import cached_property, update_wrapper
from io import BufferedReader, BytesIO, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE
from os import fspath, makedirs, scandir, path as os_path, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError
from typing import (
    cast, Callable, ItemsView, Iterator, KeysView, Mapping, Optional, Protocol, Sequence, 
    TypeVar, ValuesView, 
)
from types import MappingProxyType
from urllib.parse import quote
from uuid import uuid4
from warnings import warn

from google.protobuf.json_format import MessageToDict # type: ignore
from grpc import StatusCode, RpcError # type: ignore

from .client import Client
import CloudDrive_pb2 # type: ignore

from .util.file import HTTPFileReader
from .util.iter import posix_glob_translate_iter
from .util.property import funcproperty
from .util.urlopen import urlopen


_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object: ...


class SupportsRead(Protocol[_T_co]):
    def read(self, __length: int = ...) -> _T_co: ...


def _grpc_exc_redirect(fn, /):
    def wrapper(*args, **kwds):
        try:
            return fn(*args, **kwds)
        except RpcError as e:
            if not hasattr(e, "code"):
                raise
            fargs = (fn, args, kwds)
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
    return update_wrapper(wrapper, fn)


class CloudDriveClient(Client):

    @cached_property
    def fs(self, /) -> CloudDriveFileSystem:
        return CloudDriveFileSystem(self)


class CloudDrivePath(Mapping, PathLike[str]):
    "clouddrive path information."
    fs: CloudDriveFileSystem
    path: str

    def __init__(
        self, 
        /, 
        fs: CloudDriveFileSystem, 
        path: str | PathLike[str], 
        **attr, 
    ):
        super().__setattr__("__dict__", attr)
        attr["fs"] = fs
        attr["path"] = fs.abspath(path)
        attr["attr_last_fetched"] = None

    def __and__(self, path: str | PathLike[str], /) -> CloudDrivePath:
        return type(self)(self.fs, commonpath((self.path, self.fs.abspath(path))))

    def __call__(self, /):
        self.__dict__.update(self.fs.attr(self.path, _check=False))
        self.__dict__["attr_last_fetched"] = datetime.now()
        return self

    def __contains__(self, key, /):
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return isinstance(path, CloudDrivePath) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.attr_last_fetched:
            self()
        return self.__dict__[key]

    def __ge__(self, path, /):
        if not isinstance(path, CloudDrivePath) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __gt__(self, path, /):
        if not isinstance(path, CloudDrivePath) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __hash__(self, /):
        return hash(self.fs.client) ^ hash(self.path)

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /):
        if not isinstance(path, CloudDrivePath) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __lt__(self, path, /):
        if not isinstance(path, CloudDrivePath) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}({', '.join(f'{k}={v!r}' for k, v in self.__dict__.items())})>"

    def __setattr__(self, attr, val, /):
        raise TypeError("can't set attribute")

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> CloudDrivePath:
        return type(self).joinpath(self, path)

    def keys(self) -> KeysView:
        return self.__dict__.keys()

    def values(self) -> ValuesView:
        return self.__dict__.values()

    def items(self) -> ItemsView:
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
    ) -> Optional[AlistPath]:
        dst_path = self.fs.copy(self.path, dst_path, overwrite_or_ignore=overwrite_or_ignore)
        if dst_path:
            return type(self)(self.fs, dst_path)

    def copytree(
        self, 
        /, 
        dst_dir: str | PathLike[str], 
    ) -> AlistPath:
        dst_path = self.fs.copytree(src_path, dst_dir)
        return type(self)(self.fs, dst_path)

    def download(
        self, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal[""] | Literal["x"] | Literal["w"] | Literal["a"] = "w", 
        refresh: Optional[bool] = None, 
        download: Optional[Callable[str, SupportsWrite[bytes], Unpack[HeadersKeyword]], Any] = None, 
    ):
        return self.fs.download_tree(
            self.path, 
            local_dir, 
            refresh=refresh, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
        )

    def exists(self, /) -> bool:
        return self.fs.exists(self.path, _check=False)

    def glob(self, /, pattern: str, ignore_case: bool = False) -> Iterator[CloudDrivePath]:
        dirname = self.path if self.is_dir else self.parent.path
        return self.fs.glob(pattern, dirname, ignore_case=ignore_case, _check=False)

    def isdir(self, /) -> bool:
        return self.fs.isdir(self.path, _check=False)

    @property
    def is_dir(self, /):
        try:
            return self["isDirectory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def isfile(self, /) -> bool:
        return self.fs.isfile(self.path, _check=False)

    @property
    def is_file(self, /) -> bool:
        try:
            return not self["isDirectory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return True

    def iterdir(
        self, 
        /, 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
    ) -> Iterator[CloudDrivePath]:
        return self.fs.iterdir(
            self.path, 
            refresh=refresh, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            _check=False, 
        )

    def joinpath(self, *args: str | PathLike[str]) -> CloudDrivePath:
        if not args:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *args))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new)

    def listdir(
        self, 
        /, 
        refresh: Optional[bool] = None, 
    ) -> list[str]:
        return self.fs.listdir(
            self.path, 
            refresh=refresh, 
            _check=False, 
        )

    def listdir_attr(
        self, 
        /, 
        refresh: Optional[bool] = None, 
    ) -> list[CloudDrivePath]:
        return self.fs.listdir_attr(
            self.path, 
            refresh=refresh, 
            _check=False, 
        )

    def match(self, /, path_pattern: str, ignore_case: bool = False) -> bool:
        pattern = joinpath("/", *(t[0] for t in posix_glob_translate_iter(path_pattern)))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

    def mkdir(self, /):
        self.fs.mkdir(self.path, _check=False)

    def move(self, /, dst_path: str | PathLike[str]) -> CloudDrivePath:
        dst_path = self.fs.abspath(dst_path)
        dst_path = self.fs.move(self.path, dst_path, _check=False)
        return type(self)(self.fs, dst_path)

    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ):
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        if self.is_dir:
            raise IsADirectoryError(errno.EISDIR, self.path)
        return CloudDriveFileReader(self).wrap(
            text_mode="b" not in mode, 
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    @cached_property
    def parent(self, /) -> CloudDrivePath:
        path = self.path
        if path == "/":
            return self
        parent = dirname(path)
        if path == parent:
            return self
        return type(self)(self.fs, parent)

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

    def read_bytes(self, /):
        return self.open("rb").read()

    def read_bytes_range(self, /, bytes_range="0-", headers=None) -> bytes:
        if headers:
            headers = {**headers, "Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        else:
            headers = {"Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        with urlopen(self.url, headers=headers) as resp:
            return resp.read()

    def read_range(self, /, start=0, stop=None, headers=None) -> bytes:
        length = None
        if start < 0:
            length = urlopen(self.url).length
            start += length
        if start < 0:
            start = 0
        if stop is None:
            bytes_range = f"{start}-"
        else:
            if stop < 0:
                if length is None:
                    length = urlopen(self.url).length
                stop += length
            if stop <= 0 or start >= stop:
                return b""
            bytes_range = f"{start}-{stop-1}"
        return self.read_bytes_range(bytes_range, headers=headers)

    def read_text(
        self, 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
    ):
        return self.open(encoding=encoding, errors=errors).read()

    def remove(self, /, recursive: bool = False):
        self.fs.remove(self.path, recursive=recursive, _check=False)

    def rename(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> CloudDrivePath:
        dst_path = self.fs.abspath(dst_path)
        self.fs.rename(self.path, dst_path, _check=False)
        return type(self)(self.fs, dst_path)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> CloudDrivePath:
        dst_path = self.fs.abspath(dst_path)
        self.fs.replace(self.path, dst_path, _check=False)
        return type(self)(self.fs, dst_path)

    def rglob(self, /, pattern: str, ignore_case: bool = False) -> Iterator[CloudDrivePath]:
        dirname = self.path if self.is_dir else self.parent.path
        return self.fs.rglob(pattern, dirname, ignore_case=ignore_case, _check=False)

    def rmdir(self, /):
        self.fs.rmdir(self.path, _check=False)

    @cached_property
    def root(self, /) -> CloudDrivePath:
        parents = self.parents
        if not parents:
            return self
        elif len(parents) == 1:
            return self
        return parents[-2]

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if isinstance(path, CloudDrivePath):
            return self == path
        return self.path == self.fs.abspath(path)

    def stat(self, /):
        return self.fs.stat(self.path, _check=False)

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
        self.fs.touch(self.path, _check=False)

    unlink = remove

    @cached_property
    def url(self, /) -> str:
        return self.fs.client.download_baseurl + quote(self.path, safe="?&=")

    def with_name(self, name: str, /) -> CloudDrivePath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> CloudDrivePath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> CloudDrivePath:
        return self.parent.joinpath(self.stem + suffix)

    def write_bytes(self, data: bytes | bytearray, /):
        bio = BytesIO(data)
        return self.fs.upload(bio, self.path, overwrite_or_ignore=True, _check=False)

    def write_text(
        self, 
        text: str, 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ):
        bio = BytesIO()
        if text:
            tio = TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)
            tio.write(text)
            bio.seek(0)
        return self.fs.upload(bio, self.path, overwrite_or_ignore=True, _check=False)


class CloudDriveFileReader(HTTPFileReader):
    "Open a file from the clouddrive server."
    path: CloudDrivePath

    def __init__(self, /, path: CloudDrivePath):
        super().__init__(path.url)
        self.__dict__["path"] = path

    @cached_property
    def name(self, /) -> str:
        return self.path["name"]


class CloudDriveFileSystem:
    """Implemented some file system methods by utilizing clouddrive's web API 
    and referencing modules such as `os` and `shutil`."""
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
        ns = self.__dict__
        ns["client"] = client
        if path in ("", "/", ".", ".."):
            path = "/"
        else:
            path = "/" + normpath("/" + fspath(path)).lstrip("/")
        ns["path"] = path
        ns["refresh"] = refresh

    def __iter__(self, /):
        return self.iterdir(max_depth=-1)

    def __itruediv__(self, /, path: str | PathLike[str]):
        self.chdir(path)
        return self

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self.client!r}, path={self.path!r}, refresh={self.refresh!r})"

    def __setattr__(self, attr, val, /):
        if attr == "refresh":
            if not isinstance(val, bool):
                raise TypeError("can't set non-boolean value to `refresh`")
            self.__dict__["refresh"] = val
        else:
            raise TypeError("can't set attribute")

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

    @_grpc_exc_redirect
    def _attr(self, path: str, /):
        return self.client.FindFileByPath(CloudDrive_pb2.FindFileByPathRequest(path=path))

    @_grpc_exc_redirect
    def _delete(self, path: str, /, *paths: str):
        if paths:
            return self.client.DeleteFiles(CloudDrive_pb2.MultiFileRequest(path=[path, *paths]))
        else:
            return self.client.DeleteFile(CloudDrive_pb2.FileRequest(path=path))

    @_grpc_exc_redirect
    def _delete_cloud(self, name: str, username: str, /):
        return self.client.RemoveCloudAPI(CloudDrive_pb2.RemoveCloudAPIRequest(
                cloudName=name, userName=username))

    @_grpc_exc_redirect
    def _iterdir(self, path: str, /, refresh: bool = False):
        it = self.client.GetSubFiles(CloudDrive_pb2.ListSubFileRequest(path=path, forceRefresh=refresh))
        return (a for m in it for a in m.subFiles)

    @_grpc_exc_redirect
    def _mkdir(self, path: str, /):
        dir_, name = split(path)
        return self.client.CreateFolder(CloudDrive_pb2.CreateFolderRequest(parentPath=dir_, folderName=name))

    @_grpc_exc_redirect
    def _move(self, paths: Sequence[str], dst_dir: str, /):
        if not paths:
            raise OSError(errno.EINVAL, "empty `paths`")
        return self.client.MoveFile(CloudDrive_pb2.MoveFileRequest(theFilePaths=paths, destPath=dst_dir))

    @_grpc_exc_redirect
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
        return (a for m in it for a in m.subFiles)

    @_grpc_exc_redirect
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

    @_grpc_exc_redirect
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
        if path in ("", "."):
            return self.path
        elif isinstance(path, CloudDrivePath):
            return path.path
        return normpath(joinpath(self.path, path))

    def as_path(self, path: str | PathLike[str] = "") -> CloudDrivePath:
        return CloudDrivePath(self, path)

    def attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return MessageToDict(self._attr(path))

    def chdir(
        self, 
        /, 
        path: str | PathLike[str] = "/", 
        _check: bool = True, 
    ):
        if _check:
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
        local_path_or_file: str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        write_mode: Literal[""] | Literal["x"] | Literal["w"] | Literal["a"] = "w", 
        download: Optional[Callable[str, SupportsWrite[bytes]], Any] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
            if self._attr(path).isDirectory:
                raise IsADirectoryError(errno.EISDIR, path)
        path = cast(str, path)
        if hasattr(local_path_or_file, "write"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
        else:
            local_path = fspath(local_path_or_file)
            if write_mode:
                write_mode += "b"
            elif os_path.lexists(local_path):
                return
            else:
                write_mode = "wb"
            if local_path:
                file = open(local_path, write_mode)
            else:
                file = open(basename(path), write_mode)
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
        local_dir: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        no_root: bool = False, 
        write_mode: Literal[""] | Literal["x"] | Literal["w"] | Literal["a"] = "w", 
        download: Optional[Callable[str, SupportsWrite[bytes]], Any] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
            attr = self._attr(path)
            isdir = attr.isDirectory
        else:
            isdir = True
        path = cast(str, path)
        refresh = cast(bool, refresh)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        if isdir:
            if not no_root:
                local_dir = os_path.join(local_dir, basename(path))
                makedirs(local_dir, exist_ok=True)
            for pattr in self._iterdir(path, refresh=refresh):
                name = pattr.name
                if pattr.isDirectory:
                    self.download_tree(
                        joinpath(path, name), 
                        os_path.join(local_dir, name), 
                        refresh=refresh, 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
                        _check=False, 
                    )
                else:
                    self.download(
                        joinpath(path, name), 
                        os_path.join(local_dir, name), 
                        write_mode=write_mode, 
                        download=download, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                os_path.join(local_dir, basename(path)), 
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
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            self._attr(path)
            return True
        except FileNotFoundError:
            return False

    def getcwd(self, /) -> str:
        return self.path

    def glob(
        self, 
        /, 
        pattern: str, 
        dirname: str = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if pattern == "*":
            return self.iterdir(dirname, _check=_check)
        elif pattern == "**":
            return self.iterdir(dirname, max_depth=-1, _check=_check)
        elif not pattern:
            if _check:
                dirname = self.abspath(dirname)
            if self.exists(dirname, _check=False):
                return iter((CloudDrivePath(self, dirname),))
            return iter(())
        elif not pattern.lstrip("/"):
            return iter((CloudDrivePath(self, "/"),))
        splitted_pats = tuple(posix_glob_translate_iter(pattern))
        if pattern.startswith("/"):
            dirname = "/"
        elif _check:
            dirname = self.abspath(dirname)
        i = 0
        if ignore_case:
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), *(t[0] for t in splitted_pats))
                match = re_compile("(?i:%s)" % pattern).fullmatch
                return self.iterdir(
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
                return self.iterdir(dirname, max_depth=-1, _check=False)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), *(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                return self.iterdir(
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
                elif subpath.is_dir:
                    yield from glob_step_match(subpath, j)
            elif typ == "star":
                if at_end:
                    yield from path.listdir_attr()
                else:
                    for subpath in path.listdir_attr():
                        if subpath.is_dir:
                            yield from glob_step_match(subpath, j)
            else:
                for subpath in path.listdir_attr():
                    try:
                        cref = cref_cache[i]
                    except KeyError:
                        if ignore_case:
                            pat = "(?i:%s)" % pat
                        cref = cref_cache[i] = re_compile(pat).fullmatch
                    if cref(subpath.name):
                        if at_end:
                            yield subpath
                        elif subpath.is_dir:
                            yield from glob_step_match(subpath, j)
        path = CloudDrivePath(self, dirname)
        if not path.is_dir:
            return iter(())
        return glob_step_match(path, i)

    def isdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            return self._attr(path).isDirectory
        except FileNotFoundError:
            return False

    def isfile(
        self, 
        /, 
        path: str, 
        _check: bool = True, 
    ) -> bool:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            return not self._attr(path).isDirectory
        except FileNotFoundError:
            return False

    def is_empty(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        if _check:
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
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return path == "/" or dirname(path) == path

    def iterdir(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
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
                yield from self.iterdir(
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

    def list_storages(self, /) -> list[dict]:
        return [MessageToDict(a) for a in self._iterdir("/")]

    def listdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> list[str]:
        if _check:
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
    ) -> list[CloudDrivePath]:
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        return [
            CloudDrivePath(self, joinpath(path, attr.name), **MessageToDict(attr)) 
            for attr in self._iterdir(path, refresh)
        ]

    def makedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        exist_ok: bool = False, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return
        if not exist_ok and self.exists(path, _check=False):
            raise FileExistsError(errno.EEXIST, path)
        self._mkdir(path)

    def mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if _check:
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
            self._mkdir(path)
        else:
            raise FileExistsError(errno.EEXIST, path)

    def move(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            raise SameFileError(src_path)
        if dst_path.startswith(src_path):
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
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return CloudDrivePath(self, path).open(
            mode=mode, 
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    def remove(
        self, 
        /, 
        path: str | PathLike[str], 
        recursive: bool = False, 
        _check: bool = True, 
    ):
        if _check:
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
        if _check:
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
    ):
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            return
        if src_path == "/" or dst_path == "/":
            raise OSError(errno.EINVAL, f"invalid argument: {src_path!r} -> {dst_path!r}")
        if dst_path.startswith(src_path):
            raise PermissionError(errno.EPERM, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        src_attr = self._attr(src_path)
        try:
            dst_attr = self._attr(dst_path)
        except FileNotFoundError:
            if src_dir == dst_dir:
                self._rename((src_path, dst_name))
                return
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

    def renames(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        self.rename(src_path, dst_path, _check=False)
        if dirname(src_path) == dirname(dst_path):
            return
        try:
            self.removedirs(dirname(src_path), _check=False)
        except OSError:
            pass

    def replace(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ):
        self.rename(src_path, dst_path, replace=True, _check=_check)

    def rglob(
        self, 
        /, 
        pattern: str, 
        dirname: str = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if not pattern:
            return self.iterdir(dirname, max_depth=-1, _check=_check)
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
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif dirname(path) == "/":
            raise PermissionError(errno.EPERM, f"remove a cloud/storage by `rmdir` is not allowed: {path!r}")
        elif _check and not self._attr(path).isDirectory:
            raise NotADirectoryError(errno.ENOTDIR, path)
        elif not self.is_empty(path, _check=False):
            raise OSError(errno.ENOTEMPTY, f"directory is not empty: {path!r}")
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
    ):
        raise UnsupportedOperation(errno.ENOSYS, 
            "`scandir()` is currently not supported, use `iterdir()` instead."
        )

    def search(
        self, 
        /, 
        search_for: str, 
        path: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        fuzzy: bool = False, 
        _check: bool = True, 
    ) -> Iterator[CloudDrivePath]:
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        for attr in self._search_iter(path, search_for, refresh=refresh, fuzzy=fuzzy):
            yield CloudDrivePath(self, path, **MessageToDict(attr))

    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ):
        raise UnsupportedOperation(errno.ENOSYS, 
            "`stat()` is currently not supported, use `attr()` instead."
        )

    def storage_of(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if _check:
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
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.exists(path, _check=False):
            dir_ = dirname(path)
            if dir_ == "/":
                raise PermissionError(errno.EPERM, f"can't create file in the root directory directly: {path!r}")
            if not self._attr(dir_).isDirectory:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
        self._upload(path)

    def upload(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        file: SupportsRead[bytes]
        if hasattr(local_path_or_file, "read"):
            file = cast(SupportsRead[bytes], local_path_or_file)
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if not path:
                try:
                    path = os_path.basename(file.name) # type: ignore
                except AttributeError as e:
                    raise OSError(errno.EINVAL, "Please specify the upload path") from e
        else:
            file = open(local_path_or_file, "rb")
            if not path:
                path = os_path.basename(local_path_or_file)
        if _check:
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
                return
            self._delete(path)
        self._upload(path, file)

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str], 
        path: str | PathLike[str] = "", 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        if _check:
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
            self.upload(
                local_path, 
                joinpath(path, os_path.basename(local_path)), 
                overwrite_or_ignore=overwrite_or_ignore, 
                _check=False, 
            )
        else:
            if not no_root:
                path = joinpath(path, os_path.basename(local_path))
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

    def walk_attr(
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
            yield from self.walk_attr(
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

    cd  = chdir
    pwd = getcwd
    ls  = listdir
    ll  = listdir_attr
    rm  = remove

