#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["DuPanPath", "DuPanFileSystem"]

import errno

from collections.abc import Callable, ItemsView, Iterator, KeysView, Mapping, ValuesView
from functools import cached_property
from io import BytesIO, TextIOWrapper
from mimetypes import guess_type
from os import fsdecode, fspath, makedirs, scandir, stat_result, path as ospath, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split as splitpath, splitext
from re import compile as re_compile, escape as re_escape
from shutil import SameFileError
from stat import S_IFDIR, S_IFREG
from time import time
from typing import cast, Any, IO, Literal, Never, Optional
from types import MappingProxyType

from filewrap import SupportsRead, SupportsWrite
from glob_pattern import translate_iter
from httpfile import HTTPFileReader

from .client import DuPanClient, DuPanShareList
from .exception import check_response


class DuPanPath:
    fs: DuPanFileSystem
    path: str

    def __init__(
        self, 
        /, 
        fs: DuPanFileSystem, 
        path: str | PathLike[str], 
        **attr, 
    ):
        attr.update(fs=fs, path=fs.abspath(path))
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> DuPanPath:
        return type(self)(self.fs, commonpath((self, self.fs.abspath(path))))

    def __call__(self, /) -> DuPanPath:
        self.__dict__.update(self.fs.attr(self))
        return self

    def __contains__(self, key, /) -> bool:
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.__dict__.get("lastest_update"):
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

    def __truediv__(self, path: str | PathLike[str], /) -> DuPanPath:
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
    ) -> Optional[DuPanPath]:
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
    ):
        return self.fs.download_tree(
            self, 
            local_dir, 
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
    ) -> Iterator[DuPanPath]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def is_absolute(self, /) -> bool:
        return True

    def is_dir(self, /):
        try:
            return self["isdir"]
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def is_file(self, /) -> bool:
        try:
            return not self["isdir"]
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
        predicate: Optional[Callable[[DuPanPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
    ) -> Iterator[DuPanPath]:
        return self.fs.iter(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
        )

    def joinpath(self, *paths: str | PathLike[str]) -> DuPanPath:
        if not paths:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new)

    def listdir(self, /) -> list[str]:
        return self.fs.listdir(self)

    def listdir_attr(self, /) -> list[dict]:
        return self.fs.listdir_attr(self)

    def listdir_path(self, /) -> list[DuPanPath]:
        return self.fs.listdir_path(self)

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

    def move(self, /, dst_path: str | PathLike[str]) -> DuPanPath:
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
    def parent(self, /) -> DuPanPath:
        path = self.path
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path))

    @cached_property
    def parents(self, /) -> tuple[DuPanPath, ...]:
        path = self.path
        if path == "/":
            return ()
        parents: list[DuPanPath] = []
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

    def relative_to(self, other: str | DuPanPath, /) -> str:
        if isinstance(other, DuPanPath):
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
    ) -> DuPanPath:
        dst = self.fs.rename(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def renames(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> DuPanPath:
        dst = self.fs.renames(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> DuPanPath:
        dst = self.fs.replace(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
    ) -> Iterator[DuPanPath]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def rmdir(self, /):
        self.fs.rmdir(self)

    @cached_property
    def root(self, /) -> DuPanPath:
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
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        return self.fs.walk(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
        )

    def walk_path(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
    ) -> Iterator[tuple[str, list[DuPanPath], list[DuPanPath]]]:
        return self.fs.walk_path(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
        )

    def with_name(self, name: str, /) -> DuPanPath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> DuPanPath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> DuPanPath:
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


class DuPanFileSystem:
    client: DuPanClient
    path: str

    def __init__(
        self, 
        /, 
        client: DuPanClient, 
        path: str | PathLike[str] = "/", 
    ):
        if path in ("", "/", ".", ".."):
            path = "/"
        else:
            path = "/" + normpath("/" + fspath(path)).lstrip("/")
        self.__dict__.update(client=client, path=path)

    def __contains__(self, path: str | PathLike[str], /) -> bool:
        return self.exists(path)

    def __delitem__(self, path: str | PathLike[str], /):
        self.rmtree(path)

    def __getitem__(self, path: str | PathLike[str], /) -> DuPanPath:
        return self.as_path(path)

    def __iter__(self, /) -> Iterator[DuPanPath]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, /, path: str | PathLike[str]) -> DuPanFileSystem:
        self.chdir(path)
        return self

    def __len__(self, /) -> int:
        return len(self.listdir_attr())

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self.client!r}, path={self.path!r})"

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
    def login(cls, /, cookie=None, console_qrcode: bool = True) -> DuPanFileSystem:
        return cls(DuPanClient(cookie, console_qrcode=console_qrcode))

    def abspath(self, path: str | PathLike[str] = "", /) -> str:
        if path == "/":
            return "/"
        elif path in ("", "."):
            return self.path
        elif isinstance(path, DuPanPath):
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
    ) -> DuPanPath:
        if not isinstance(path, DuPanPath):
            if _check:
                path = self.abspath(path)
            path = DuPanPath(self, path)
        if fetch_attr:
            path()
        return path

    def attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        resp = self.client.fs_filemetas(path)
        lastest_update = time()
        err = resp["errno"]
        if err:
            resp["path"] = path
            if err == 12:
                raise FileNotFoundError(errno.ENOENT, resp)
            raise OSError(errno.EIO, resp)
        attr = resp["info"][0]
        attr["name"] = attr["server_filename"]
        attr["ctime"] = attr["local_ctime"]
        attr["mtime"] = attr["local_mtime"]
        attr["atime"] = lastest_update
        attr["lastest_update"] = lastest_update
        return attr

    def chdir(
        self, 
        /, 
        path: str | PathLike[str] = "/", 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == self.path:
            pass
        elif path == "/":
            self.__dict__["path"] = "/"
        elif self.attr(path, _check=False)["isdir"]:
            self.__dict__["path"] = path
        else:
            raise NotADirectoryError(errno.ENOTDIR, path)

    def copy(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = None, 
        recursive: bool = False, 
        _check: bool = True, 
    ) -> Optional[str]:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if _check:
            src_attr = self.attr(src_path, _check=False)
            if src_attr["isdir"]:
                if recursive:
                    return self.copytree(
                        src_path, 
                        dst_path, 
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
            dst_attr = self.attr(dst_path, _check=False)
        except FileNotFoundError:
            self.client.fs_copy([{"path": src_path, "dest": dst_dir, "newname": dst_name}])
        else:
            if dst_attr["isdir"]:
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
            self.client.fs_copy([{"path": src_path, "dest": dst_dir, "newname": dst_name, "ondup": "overwrite"}])
        return dst_path

    def copytree(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Optional[str]:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if _check:
            src_attr = self.attr(src_path, _check=False)
            if not src_attr["isdir"]:
                return self.copy(
                    src_path, 
                    dst_path, 
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
            dst_attr = self.attr(dst_path, _check=False)
        except FileNotFoundError:
            self.client.fs_copy([{"path": src_path, "dest": dst_dir, "newname": dst_name}])
        else:
            if not dst_attr["isdir"]:
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
                if attr["isdir"]:
                    self.copytree(
                        joinpath(src_path, attr["name"]), 
                        joinpath(dst_path, attr["name"]), 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.copy(
                        joinpath(src_path, attr["name"]), 
                        joinpath(dst_path, attr["name"]), 
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
        _check: bool = True, 
    ):
        raise NotImplementedError

    def download_tree(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        _check: bool = True, 
    ):
        is_dir: bool
        if isinstance(path, DuPanPath):
            is_dir = path.is_dir()
            path = path.path
        elif _check:
            path = self.abspath(path)
            is_dir = self.attr(path)["isdir"]
        else:
            is_dir = True
        path = cast(str, path)
        local_dir = fsdecode(local_dir)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        if is_dir:
            if not no_root:
                local_dir = ospath.join(local_dir, basename(path))
                if local_dir:
                    makedirs(local_dir, exist_ok=True)
            for pathobj in self.listdir_path(path, _check=False):
                name = pathobj.name
                if pathobj.is_dir():
                    self.download_tree(
                        pathobj.name, 
                        ospath.join(local_dir, name), 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
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

    def get_url(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.attr(path)
        if attr["isdir"]:
            raise OSError(errno.EISDIR, path)
        resp = self.client.get_url(attr["fs_id"])
        check_response(resp)
        return resp["dlink"][0]["dlink"]

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[DuPanPath]:
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
            return iter((DuPanPath(self, "/"),))
        splitted_pats = tuple(translate_iter(pattern))
        if pattern.startswith("/"):
            dirname = "/"
        elif isinstance(dirname, DuPanPath):
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
                    return iter((DuPanPath(self, dirname),))
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
        path = DuPanPath(self, dirname)
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
            return self.attr(path, _check=_check)["isdir"] == 1
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
            return not self.attr(path, _check=_check)["isdir"] == 0
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
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self.attr(path, _check=False)
        except FileNotFoundError:
            return True
        if attr["isdir"]:
            try:
                next(self.iterdir(path, page_size=1, _check=False))
                return False
            except StopIteration:
                return True
        else:
            return attr.get("size", 0)

    def iter(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[DuPanPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[DuPanPath]:
        if not max_depth:
            return
        if _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_path(top, _check=False)
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
        yield_me = min_depth <= 0
        for path in ls:
            if yield_me and predicate:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred 
            if yield_me and topdown:
                yield path
            if path.is_dir():
                yield from self.iter(
                    path.path, 
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
        page_size: int = 100, 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        if page_size <= 0:
            page_size = 100
        if not self.attr(path)["isdir"]:
            raise OSError(errno.ENOTDIR, path)
        payload = {"dir": path, "num": page_size, "page": 1}
        while True:
            resp = self.client.fs_list(payload)
            lastest_update = time()
            err = resp["errno"]
            if err:
                raise OSError(errno.EIO, path)
            ls = resp["list"]
            for attr in ls:
                attr["name"] = attr["server_filename"]
                attr["ctime"] = attr["local_ctime"]
                attr["mtime"] = attr["local_mtime"]
                attr["atime"] = lastest_update
                attr["lastest_update"] = lastest_update
                yield attr
            if len(ls) < page_size:
                break

    def listdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> list[str]:
        return list(attr["server_filename"] for attr in self.iterdir(path, page_size=10_000, _check=_check))

    def listdir_attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> list[dict]:
        return list(self.iterdir(path, page_size=10_000, _check=_check))

    def listdir_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> list[DuPanPath]:
        return [DuPanPath(self, **attr) for attr in self.iterdir(path, page_size=10_000, _check=_check)]

    def makedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        exist_ok: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        try:
            attr = self.attr(path, _check=False)
        except FileNotFoundError:
            return check_response(self.client.fs_mkdir(path))["path"]
        else:
            if exist_ok:
                if not attr["isdir"]:
                    raise NotADirectoryError(errno.ENOTDIR, path)
            else:
                raise FileExistsError(errno.EEXIST, path)
        return path

    def mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "create root directory is not allowed (because it has always existed)")
        try:
            self.attr(path)
        except FileNotFoundError as e:
            dir_ = dirname(path)
            if not self.attr(dir_)["isdir"]:
                raise NotADirectoryError(errno.ENOTDIR, dir_) from e
            check_response(self.client.fs_mkdir(path))
            return path
        else:
            raise FileExistsError(errno.EEXIST, path)

    def move(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
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
        src_attr = self.attr(src_path)
        try:
            dst_attr = self.attr(dst_path)
        except FileNotFoundError:
            dest, name = splitpath(dst_path)
            check_response(self.client.fs_move([{
                "path": src_path, 
                "dest": dest, 
                "newname": name, 
            }]))
            return dst_path
        else:
            if dst_attr["isdir"]:
                dst_filename = basename(src_path)
                dst_filepath = joinpath(dst_path, dst_filename)
                if self.exists(dst_filepath, _check=False):
                    raise FileExistsError(errno.EEXIST, f"destination path {dst_filepath!r} already exists")
                check_response(self.client.fs_move([{
                    "path": src_path, 
                    "dest": dst_path, 
                    "newname": dst_filename, 
                }]))
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
        url = self.get_url(path, _check=_check)
        return self.client.open(
            url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
        ).wrap(
            text_mode="b" not in mode, # type: ignore
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
        url = self.get_url(path, _check=_check)
        return self.client.read_bytes(url, start, stop)

    def read_bytes_range(
        self, 
        /, 
        path: str | PathLike[str], 
        bytes_range: str = "0-", 
        _check: bool = True, 
    ) -> bytes:
        url = self.get_url(path, _check=_check)
        return self.client.read_bytes_range(url, bytes_range)

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
        url = self.get_url(path, _check=_check)
        return self.client.read_block(url, size, offset)

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
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            if recursive:
                attrs = self.listdir_attr("/")
                if attrs:
                    check_response(self.client.fs_delete([attr["path"] for attr in attrs]))
                return
            else:
                raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        if self.attr(path)["isdir"] and not recursive:
            raise IsADirectoryError(errno.EISDIR, path)
        check_response(self.client.fs_delete([path]))

    def removedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
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
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
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
            raise PermissionError(errno.EPERM, f"rename a path as its ancestor is not allowed: {src_path!r} -> {dst_path!r}")
        elif cmpath == src_path:
            raise PermissionError(errno.EPERM, f"rename a path as its descendant is not allowed: {src_path!r} -> {dst_path!r}")
        dest, name = splitpath(dst_path)
        if replace:
            check_response(self.client.fs_move([{
                "path": src_path, 
                "dest": dest, 
                "newname": name, 
                "ondup": "overwrite", 
            }]))
        else:
            if self.exists(dst_path, _check=False):
                raise FileExistsError(errno.EEXIST, f"{dst_path!r} already exists: {src_path!r} -> {dst_path!r}")
            check_response(self.client.fs_move([{
                "path": src_path, 
                "dest": dest, 
                "newname": name
            }]))
        return dst_path

    def renames(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
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
    ) -> Iterator[DuPanPath]:
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
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        attr = self.attr(path)
        if not attr["isdir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        else:
            try:
                next(self.iterdir(path, page_size=1))
            except StopIteration:
                pass
            else:
                raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        check_response(self.client.fs_delete([path]))

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
        _check: bool = True, 
    ) -> Iterator[DuPanPath]:
        return iter(self.listdir_path(path, _check=_check))

    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ):
        attr = self.attr(path, _check=_check)
        return stat_result((
            (S_IFDIR if attr["isdir"] else S_IFREG) | 0o777, 
            0, # ino
            0, # dev
            1, # nlink
            0, # uid
            0, # gid
            attr["size"], # size
            attr["atime"], # atime
            attr["mtime"], # mtime
            attr["ctime"], # ctime
        ))

    def touch(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.exists(path, _check=False):
            dir_ = dirname(path)
            if not self.attr(dir_, _check=False)["isdir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
            return self.upload(BytesIO(), path, _check=False)
        return path

    # TODO: 如果文件特别多，需要分多次进行转存，但要保持目录结构
    def transfer(
        self, 
        /, 
        url: str, 
        password: str = "", 
        fsidlist: None | list[int] = None, 
        save_dir: str = "/", 
    ) -> dict:
        """转存文件到百度网盘

        :param url: 分享链接
        :param password: 密码（如果链接中包含密码，可以不传）
        :param fsidlist: 待转存的文件 id 列表
        :param save_dir: 存储到这个目录，默认是 /，也就是网盘根目录

        :return: 转存接口返回到 JSON 信息
        """
        self.makedirs(save_dir, exist_ok=True)
        share_list = DuPanShareList(url, password)
        if not fsidlist:
            fsidlist = [f["fs_id"] for f in share_list.fs_list_root()["file_list"]]
        return check_response(self.client.share_transfer(
            share_list.url, 
            params={
                "shareid": share_list.share_id, 
                "from": share_list.share_uk, 
                "sekey": share_list.randsk, 
                "ondup": "overwrite", 
            }, 
            data = {"fsidlist": fsidlist, "path": save_dir}, 
        ))

    def upload(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        raise NotImplementedError

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str], 
        path: str | PathLike[str] = "", 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            if not self.attr(path)["isdir"]:
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
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        if not max_depth:
            return
        if isinstance(top, DuPanPath):
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_attr(top, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if not ls:
            yield top, [], []
            return
        dirs: list[str] = []
        files: list[str] = []
        for attr in ls:
            if attr["isdir"]:
                dirs.append(attr["name"])
            else:
                files.append(attr["name"])
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        if yield_me and topdown:
            yield top, dirs, files
        for dir_ in dirs:
            yield from self.walk(
                joinpath(top, dir_), 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if yield_me and topdown:
            yield top, dirs, files

    def walk_attr(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        if not max_depth:
            return
        if isinstance(top, DuPanPath):
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_attr(top, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if not ls:
            yield top, [], []
            return
        dirs: list[dict] = []
        files: list[dict] = []
        for attr in ls:
            if attr["isdir"]:
                dirs.append(attr)
            else:
                files.append(attr)
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        if yield_me and topdown:
            yield top, dirs, files
        for dir_ in dirs:
            yield from self.walk_attr(
                dir_["path"], 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if yield_me and topdown:
            yield top, dirs, files

    def walk_path(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[DuPanPath], list[DuPanPath]]]:
        if not max_depth:
            return
        if isinstance(top, DuPanPath):
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_path(top, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if not ls:
            yield top, [], []
            return
        dirs: list[DuPanPath] = []
        files: list[DuPanPath] = []
        for path in ls:
            if path.is_dir():
                dirs.append(path)
            else:
                files.append(path)
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
    cp  = copy
    pwd = getcwd
    ls  = listdir
    la  = listdir_attr
    ll  = listdir_path
    mv  = move
    rm  = remove


# TODO: 上传下载使用百度网盘的openapi，直接使用 alist 已经授权的 token
# TODO: 百度网盘转存时，需要保持相对路径
# TODO: 等待 filemanager 任务完成
# TODO: 分享、回收站、分享转存、群分享转存等的接口封装
