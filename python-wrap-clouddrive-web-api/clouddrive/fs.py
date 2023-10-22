#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["CloudDrivePath", "CloudDriveFile", "CloudDriveFileSystem"]

from functools import update_wrapper
from http.client import HTTPResponse
from io import BufferedReader, BytesIO, RawIOBase, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE
from os import PathLike, fspath, makedirs, scandir, path as os_path
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split, splitext
from shutil import copyfileobj, SameFileError
from socket import SocketIO
from typing import cast, Callable, Iterator, Mapping, Optional, Protocol, Sequence, TypeVar
from types import MappingProxyType
from urllib.parse import quote
from urllib.request import urlopen, Request
from uuid import uuid4
from warnings import warn

from google.protobuf.json_format import MessageToDict # type: ignore
from grpc import StatusCode, RpcError # type: ignore

from .client import CloudDriveClient
import CloudDrive_pb2 # type: ignore


_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object: ...


class SupportsRead(Protocol[_T_co]):
    def read(self, __length: int = ...) -> _T_co: ...


def grpc_exc_redirect(fn, /):
    def wrapper(*args, **kwds):
        try:
            return fn(*args, **kwds)
        except RpcError as e:
            if not hasattr(e, "code"):
                raise
            match e.code():
                case StatusCode.PERMISSION_DENIED:
                    raise PermissionError(1, args)
                case StatusCode.NOT_FOUND:
                    raise FileNotFoundError(2, args)
                case StatusCode.ALREADY_EXISTS:
                    raise FileExistsError(17, args)
                case StatusCode.UNIMPLEMENTED:
                    raise UnsupportedOperation(22, args)
                # case StatusCode.UNAUTHENTICATED:
                #     ...
            raise OSError(22, args) from e
    return update_wrapper(wrapper, fn)


class lazyproperty:

    def __init__(self, func):
        self.func = func
        self.name = func.__name__

    def __get__(self, instance, type):
        if instance is None:
            return self
        value = self.func(instance)
        instance.__dict__[self.name] = value
        return value


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
        super().__setattr__("__dict__", attr)
        attr["fs"] = fs
        attr["path"] = fs.abspath(path)

    def __and__(self, path: str | PathLike[str], /) -> CloudDrivePath:
        return type(self)(self.fs, commonpath((self.path, self.fs.abspath(path))))

    def __call__(self, /):
        self.__dict__.update(self.fs.attr(self.path, _check=False))
        return self

    def __contains__(self, key, /):
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return isinstance(path, CloudDrivePath) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if "name" not in self.__dict__:
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
        return hash(self.fs.client.origin) ^ hash(self.path)

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /):
        if not isinstance(path, CloudDrivePath) or self.fs.client.origin != path.fs.client.origin:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __lt__(self, path, /):
        if not isinstance(path, CloudDrivePath) or self.fs.client.origin != path.fs.client.origin or self.path == path.path:
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

    @property
    def anchor(self, /) -> str:
        return "/"

    def as_uri(self, /) -> str:
        return self.url

    @property
    def attr(self, /) -> MappingProxyType:
        return MappingProxyType(self.__dict__)

    def exists(self, /) -> bool:
        return self.fs.exists(self.path, _check=False)

    def glob(self, /, pattern: str) -> Iterator[CloudDrivePath]:
        raise NotImplementedError("glob")

    def isdir(self, /) -> bool:
        return self.fs.isdir(self.path, _check=False)

    @property
    def is_dir(self, /):
        try:
            return self["isDirectory"]
        except KeyError:
            return False

    def isfile(self, /) -> bool:
        return self.fs.isfile(self.path, _check=False)

    @property
    def is_file(self, /) -> bool:
        return not self.is_dir

    def iterdir(
        self, 
        /, 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[CloudDrivePath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
    ) -> Iterator[CloudDrivePath]:
        return self.fs.iterdir(
            self.path, 
            refresh=refresh, 
            topdown=topdown, 
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
        if path == path:
            return self
        return type(self)(self.fs, path)

    def match(self, /, path_pattern: str) -> bool:
        raise NotImplementedError("match")

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
        orig_mode = mode
        if "b" in mode:
            mode = mode.replace("b", "", 1)
            open_text_mode = False
        else:
            mode = mode.replace("t", "", 1)
            open_text_mode = True
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise ValueError(f"invalid (or unsupported) mode: {orig_mode!r}")
        if buffering is None:
            if open_text_mode:
                buffering = DEFAULT_BUFFER_SIZE
            else:
                buffering = 0
        if buffering == 0:
            if open_text_mode:
                raise ValueError("can't have unbuffered text I/O")
            return CloudDriveFile(self, mode)
        line_buffering = False
        buffer_size: int
        if buffering < 0:
            buffer_size = DEFAULT_BUFFER_SIZE
        elif buffering == 1:
            if not open_text_mode:
                warn("line buffering (buffering=1) isn't supported in binary mode, "
                     "the default buffer size will be used", RuntimeWarning)
            buffer_size = DEFAULT_BUFFER_SIZE
            line_buffering = True
        else:
            buffer_size = buffering
        raw = CloudDriveFile(self, mode)
        buffer = BufferedReader(raw, buffer_size)
        if open_text_mode:
            return TextIOWrapper(
                buffer, 
                encoding=encoding, 
                errors=errors, 
                newline=newline, 
                line_buffering=line_buffering, 
            )
        else:
            return buffer

    @lazyproperty
    def parent(self, /) -> CloudDrivePath:
        path = self.path
        if path == "/":
            return self
        parent = dirname(path)
        if path == parent:
            return self
        return type(self)(self.fs, parent)

    @lazyproperty
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

    @lazyproperty
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *self.path[1:].split("/"))

    def read_bytes(self, /):
        return self.open("rb").read()

    def read_text(
        self, 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
    ):
        return self.open(encoding=encoding, errors=errors).read()

    def remove(self, /, recursive: bool = False):
        self.fs.remove(self.path, recursive=recursive, _check=False)

    def rename(self, /, dst_path: str | PathLike[str]) -> CloudDrivePath:
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

    def rglob(self, /, pattern: str) -> Iterator[CloudDrivePath]:
        raise NotImplementedError("rglob")

    def rmdir(self, /):
        self.fs.rmdir(self.path, _check=False)

    @lazyproperty
    def root(self, /):
        parents = self.parents
        if not parents:
            return self
        elif len(parents) == 1:
            return self
        return parents[-2]

    def samefile(self, path: str | PathLike[str], /) -> bool:
        return self.path == self.fs.abspath(path)

    def stat(self, /):
        return self.fs.stat(self.path, _check=False)

    @lazyproperty
    def stem(self, /):
        return splitext(basename(self.path))[0]

    @lazyproperty
    def suffix(self, /):
        return splitext(basename(self.path))[1]

    @lazyproperty
    def suffixes(self, /):
        return tuple("." + part for part in basename(self.path).split(".")[1:])

    def touch(self, /):
        self.fs.touch(self.path, _check=False)

    unlink = remove

    @lazyproperty
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


class CloudDriveFile(RawIOBase):
    "Open a file from the CloudDrive server."
    path: CloudDrivePath
    mode: str
    url: str
    resp: HTTPResponse
    file: SocketIO
    _seekable: bool
    length: int
    position: int
    closed: bool

    def __init__(self, /, path: CloudDrivePath, mode: str = "r"):
        if mode != "r":
            if mode in ("r+", "+r", "w", "w+", "+w", "a", "a+", "+a", "x", "x+", "+x"):
                raise NotImplementedError(f"`mode` not currently supported: {mode!r}")
            raise ValueError(f"invalid mode: {mode!r}")
        ns = self.__dict__
        ns["path"] = path
        ns["mode"] = mode
        ns["url"]  = path.url
        ns["resp"] = resp = urlopen(ns["url"])
        ns["file"] = resp.fp.raw
        ns["_seekable"] = resp.headers.get("accept-ranges") == "bytes"
        ns["length"] = ns["size"] = resp.length
        ns["position"] = 0
        ns["closed"] = False

    def __del__(self, /):
        try:
            self.close()
        except:
            pass

    def __enter__(self, /):
        return self

    def __exit__(self, /, *exc_info):
        self.close()

    def __iter__(self, /):
        return self

    def __next__(self, /) -> bytes:
        line = self.readline()
        if line:
            return line
        else:
            raise StopIteration

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(path={self.path!r}, mode={self.mode!r})"

    def __setattr__(self, attr, val, /):
        raise TypeError("can't set attribute")

    def close(self, /):
        self.resp.close()
        self.__dict__["closed"] = True

    @property
    def fileno(self, /):
        raise self.file.fileno()

    def flush(self, /):
        return self.file.flush()

    def isatty(self, /):
        return False

    @lazyproperty
    def name(self, /) -> str:
        return self.path["name"]

    def read(self, size: int = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0 or self.position >= self.length:
            return b""
        if self.file.closed:
            self.reconnect()
        data = self.file.read(size) or b""
        self.__dict__["position"] += len(data)
        return data

    def readable(self, /) -> bool:
        return True

    def readinto(self, buffer, /) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if self.file.closed:
            self.reconnect()
        size = self.file.readinto(buffer) or 0
        self.__dict__["position"] += size
        return size

    def readline(self, size: Optional[int] = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size is None:
            size = -1
        if size == 0 or self.position >= self.length:
            return b""
        if self.file.closed:
            self.reconnect()
        data = self.file.readline(size) or b""
        self.__dict__["position"] += len(data)
        return data

    def readlines(self, hint: int = -1, /) -> list[bytes]:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if self.file.closed:
            self.reconnect()
        ls = self.file.readlines(hint)
        self.__dict__["position"] += sum(map(len, ls))
        return ls

    def reconnect(self, /, start: Optional[int] = None):
        if start is None:
            start = self.position
        elif start < 0:
            start = self.length + start
            if start < 0:
                start = 0
        self.resp.close()
        ns = self.__dict__
        ns["resp"] = resp = urlopen(Request(self.url, headers={"Range": f"bytes={start}-"}))
        ns["file"] = resp.fp.raw
        ns["position"] = start

    def seek(self, pos: int, whence: int = 0, /) -> int:
        if not self._seekable:
            raise TypeError("not a seekable stream")
        if whence == 0:
            if pos < 0:
                raise ValueError(f"negative seek position: {pos!r}")
            old_pos = self.position
            if old_pos == pos:
                return pos
            # If only move forward within 1MB, directly read and discard
            elif old_pos < pos <= old_pos + 1024 * 1024:
                try:
                    self.read(pos - old_pos)
                    return pos
                except Exception:
                    pass
            self.reconnect(pos)
            return pos
        elif whence == 1:
            if pos == 0:
                return self.position
            return self.seek(self.position + pos)
        elif whence == 2:
            return self.seek(self.length + pos)
        else:
            raise ValueError(f"whence value unsupported: {whence!r}")

    def seekable(self, /) -> bool:
        return True

    def tell(self, /) -> int:
        return self.position

    def truncate(self, size: Optional[int] = None, /):
        raise UnsupportedOperation("truncate")

    def writable(self, /) -> bool:
        return False

    def write(self, b, /) -> int:
        raise UnsupportedOperation("write")

    def writelines(self, lines, /):
        raise UnsupportedOperation("writelines")


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

    @grpc_exc_redirect
    def _attr(self, path: str, /):
        return self.client.FindFileByPath(CloudDrive_pb2.FindFileByPathRequest(path=path))

    @grpc_exc_redirect
    def _delete(self, path: str, /, *paths: str):
        if paths:
            return self.client.DeleteFiles(CloudDrive_pb2.MultiFileRequest(path=[path, *paths]))
        else:
            return self.client.DeleteFile(CloudDrive_pb2.FileRequest(path=path))

    @grpc_exc_redirect
    def _delete_cloud(self, name: str, username: str, /):
        return self.client.RemoveCloudAPI(CloudDrive_pb2.RemoveCloudAPIRequest(
                cloudName=name, userName=username))

    @grpc_exc_redirect
    def _iterdir(self, path: str, /, refresh: bool = False):
        it = self.client.GetSubFiles(CloudDrive_pb2.ListSubFileRequest(path=path, forceRefresh=refresh))
        return (a for m in it for a in m.subFiles)

    @grpc_exc_redirect
    def _mkdir(self, path: str, /):
        dir_, name = split(path)
        return self.client.CreateFolder(CloudDrive_pb2.CreateFolderRequest(parentPath=dir_, folderName=name))

    @grpc_exc_redirect
    def _move(self, paths: Sequence[str], dst_dir: str, /):
        if not paths:
            raise ValueError("empty paths")
        return self.client.MoveFile(CloudDrive_pb2.MoveFileRequest(theFilePaths=paths, destPath=dst_dir))

    @grpc_exc_redirect
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

    @grpc_exc_redirect
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

    @grpc_exc_redirect
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
            raise NotADirectoryError(20, path)

    def copy(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = True, 
        _check: bool = True, 
    ):
        raise UnsupportedOperation("copy")

    def copytree(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        raise UnsupportedOperation("copytree")

    def download(
        self, 
        /, 
        path: str | PathLike[str], 
        local_path_or_file: str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
            if self._attr(path).isDirectory:
                raise IsADirectoryError(21, path)
        path = cast(str, path)
        url = self.client.download_baseurl + quote(path, safe="?&=")
        f = urlopen(url)
        try:
            file: SupportsWrite
            if hasattr(local_path_or_file, "write"):
                file = cast(SupportsWrite[bytes] | TextIOWrapper, local_path_or_file)
                if isinstance(file, TextIOWrapper):
                    file = file.buffer
            else:
                if overwrite_or_ignore is None:
                    mode = "xb"
                else:
                    mode = "wb"
                    if not overwrite_or_ignore and os_path.lexists(local_path_or_file):
                        return
                if local_path_or_file:
                    file = open(local_path_or_file, mode)
                else:
                    file = open(basename(path), mode)
            copyfileobj(f, file)
        finally:
            f.close()

    def download_tree(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        dir_: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
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
        if dir_:
            makedirs(dir_, exist_ok=True)
        if isdir:
            if not no_root:
                dir_ = os_path.join(dir_, basename(path))
                makedirs(dir_, exist_ok=True)
            for pattr in self._iterdir(path, refresh=refresh):
                name = pattr.name
                if pattr.isDirectory:
                    self.download_tree(
                        joinpath(path, name), 
                        os_path.join(dir_, name), 
                        refresh=refresh, 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.download(
                        joinpath(path, name), 
                        os_path.join(dir_, name), 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                os_path.join(dir_, basename(path)), 
                overwrite_or_ignore=overwrite_or_ignore, 
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

    def iterdir(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
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
        if max_depth > 0:
            max_depth -= 1
        for attr in it:
            path = CloudDrivePath(self, joinpath(top, attr.name), **MessageToDict(attr))
            yield_me = True
            if predicate:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred
            if topdown and yield_me:
                yield path
            if attr.isDirectory:
                yield from self.iterdir(
                    path.path, 
                    refresh=refresh, 
                    topdown=topdown, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    _check=_check, 
                )
            if not topdown and yield_me:
                yield path

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
            raise FileExistsError(17, path)
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
            raise PermissionError(1, "create root directory is not allowed (because it has always existed)")
        elif dirname(path) == "/":
            raise PermissionError(1, f"can't directly create a cloud/storage by `mkdir`: {path!r}")
        try:
            self._attr(path)
        except FileNotFoundError as e:
            dir_ = dirname(path)
            if not self._attr(dir_).isDirectory:
                raise NotADirectoryError(20, dir_) from e
            self._mkdir(path)
        else:
            raise FileExistsError(17, path)

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
            raise PermissionError(1, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
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
                    raise FileExistsError(17, f"destination path {dst_filepath!r} already exists")
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
                raise PermissionError(1, "remove the root directory is not allowed")
        attr = self._attr(path)
        if attr.isDirectory:
            if not recursive:
                if dirname(path) == "/":
                    raise PermissionError(1, f"remove a storage is not allowed: {path!r}")
                raise IsADirectoryError(21, path)
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
            raise OSError(22, f"invalid argument: {src_path!r} -> {dst_path!r}")
        if dst_path.startswith(src_path):
            raise PermissionError(1, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
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
                raise NotADirectoryError(20, f"{dst_dir!r} is not a directory: {src_path!r} -> {dst_path!r}")
        else:
            if replace:
                if src_attr.isDirectory:
                    if dst_attr.isDirectory:
                        try:
                            next(self._iterdir(dst_path))
                        except StopIteration:
                            pass
                        else:
                            raise OSError(9, f"directory {dst_path!r} is not empty: {src_path!r} -> {dst_path!r}")
                    else:
                        raise NotADirectoryError(20, f"{dst_path!r} is not a directory: {src_path!r} -> {dst_path!r}")
                elif dst_attr.isDirectory:
                    raise IsADirectoryError(21, f"{dst_path!r} is a directory: {src_path!r} -> {dst_path!r}")
                self._delete(dst_path)
            else:
                raise FileExistsError(17, f"destination path already exists: {src_path!r} -> {dst_path!r}")
        if src_dir == "/":
            raise PermissionError(1, f"move a cloud/storage into another cloud/storage is not allowed: {src_path!r} -> {dst_path!r}")
        elif dst_path == "/":
            raise PermissionError(1, f"move a folder to the root directory (as a cloud/storage) is not allowed: {src_path!r} -> {dst_path!r}")
        if src_name == dst_name:
            if commonpath((src_dir, dst_dir)) == "/":
                warn("cross clouds/storages transport will retain the original file: {src_path!r} <-> {dst_path!r}")
            self._move([src_path], dst_dir)
        elif src_dir == dst_dir:
            self._rename((src_path, dst_name))
        else:
            if commonpath((src_dir, dst_dir)) == "/":
                raise PermissionError(1, f"cross clouds/storages transport does not allow renaming: {src_path!r} -> {dst_path!r}")
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
            raise PermissionError(1, "remove the root directory is not allowed")
        elif dirname(path) == "/":
            raise PermissionError(1, f"remove a cloud/storage is not allowed: {path!r}")
        elif _check and not self._attr(path).isDirectory:
            raise NotADirectoryError(20, path)
        elif not self.is_empty(path, _check=False):
            raise OSError(9, f"directory is not empty: {path!r}")
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
        raise NotImplementedError(
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
        raise NotImplementedError(
            "`stat()` is currently not supported, use `attr()` instead."
        )

    def touch(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            self._attr(path)
        except FileNotFoundError:
            dir_ = dirname(path)
            if dir_ == "/":
                raise PermissionError(1, f"can't create file in the root directory directly: {path!r}")
            if not self._attr(dir_).isDirectory:
                raise NotADirectoryError(2, f"parent path {dir_!r} is not a directory: {path!r}")
        self._upload(path)

    def upload(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        as_task: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        if hasattr(local_path_or_file, "read"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if not path:
                try:
                    path = os_path.basename(file.name) # type: ignore
                except AttributeError as e:
                    raise OSError(3, "Please specify the upload path") from e
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
                raise FileExistsError(17, path)
            elif attr.isDirectory:
                raise IsADirectoryError(21, path)
            elif not overwrite_or_ignore:
                return
            self._delete(path)
        self._upload(path, file)

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str], 
        path: str | PathLike[str] = "", 
        as_task: bool = False, 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            if not self._attr(path).isDirectory:
                raise NotADirectoryError(20, path)
        except FileNotFoundError:
            self.makedirs(path, exist_ok=True, _check=False)
        try:
            it = scandir(local_path)
        except NotADirectoryError:
            self.upload(
                local_path, 
                joinpath(path, os_path.basename(local_path)), 
                as_task=as_task, 
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
                        as_task=as_task, 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.upload(
                        entry.path, 
                        joinpath(path, entry.name), 
                        as_task=as_task, 
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
        if topdown:
            yield top, dirs, files
        if max_depth > 0:
            max_depth -= 1
        for dir_ in dirs:
            yield from self.walk(
                joinpath(top, dir_), 
                refresh=refresh, 
                topdown=topdown, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if not topdown:
            yield top, dirs, files

    def walk_attr(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
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
        if topdown:
            yield top, dirs, files
        if max_depth > 0:
            max_depth -= 1
        for dir_ in dirs:
            yield from self.walk_attr(
                dir_.path, 
                refresh=refresh, 
                topdown=topdown, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if not topdown:
            yield top, dirs, files

    cd  = chdir
    pwd = getcwd
    ls  = listdir
    ll  = listdir_attr
    rm  = remove

