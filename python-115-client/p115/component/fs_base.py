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
    Callable, Iterable, Iterator, ItemsView, KeysView, Mapping, Sequence, ValuesView, 
)
from functools import cached_property
from io import UnsupportedOperation
from mimetypes import guess_type
from os import fsdecode, fspath, lstat, makedirs, scandir, stat, stat_result, PathLike
from os import path as ospath
from posixpath import join as joinpath, splitext
from re import compile as re_compile, escape as re_escape
from stat import S_IFDIR, S_IFREG # TODO: common stat method
from time import time
from typing import (
    cast, Any, Generic, IO, Literal, Never, Self, TypeAlias, TypeVar, 
)
from types import MappingProxyType
from urllib.parse import parse_qsl, urlparse

from download import DownloadTask
from filewrap import SupportsWrite
from httpfile import HTTPFileReader
from glob_pattern import translate_iter
from posixpatht import basename, commonpath, dirname, escape, joins, normpath, splits, unescape

from .client import check_response, P115Client


AttrDict: TypeAlias = dict # TODO: TypedDict with extra keys
IDOrPathType: TypeAlias = int | str | PathLike[str] | Sequence[str] | AttrDict
P115FSType = TypeVar("P115FSType", bound="P115FileSystemBase")
P115PathType = TypeVar("P115PathType", bound="P115PathBase")


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
        self.__dict__.update(self.fs.attr(self.id))
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

    def dictdir(self, /, **kwargs) -> dict[int, str]:
        return self.fs.dictdir(self, **kwargs)

    def dictdir_attr(self, /, **kwargs) -> dict[int, AttrDict]:
        return self.fs.dictdir_attr(self, **kwargs)

    def dictdir_path(self, /, **kwargs) -> dict[int, Self]:
        return self.fs.dictdir_path(self, **kwargs)

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

    def enumdir(self, /, **kwargs) -> Iterator[str]:
        return self.fs.enumdir(self if self.is_dir() else self["parent_id"], **kwargs)

    def exists(self, /) -> bool:
        return self.fs.exists(self)

    @property
    def file_extension(self, /) -> None | str:
        if not self.is_file():
            return None
        return splitext(basename(self.path))[1]

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[Self]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self["parent_id"], 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
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

    def isdir(self, /) -> bool:
        return self.fs.isdir(self)

    def isfile(self, /) -> bool:
        return self.fs.isfile(self)

    def inode(self, /) -> int:
        return self.id

    def iter(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Self], None | bool] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> Iterator[Self]:
        return self.fs.iter(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            **kwargs, 
        )

    def iterdir(self, /, **kwargs) -> Iterator[AttrDict]:
        return self.fs.iterdir(self if self.is_dir() else self["parent_id"], **kwargs)

    def join(self, *names: str) -> Self:
        if not names:
            return self
        attr = self.fs.attr(names, self.id)
        return type(self)(attr)

    def joinpath(self, *paths: str | PathLike[str]) -> Self:
        if not paths:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        if path != "/" and path_new.startswith(path + "/"):
            attr = self.fs.attr(path_new[len(path)+1:], self.id)
        else:    
            attr = self.fs.attr(path_new)
        return type(self)(attr)

    @property
    def length(self, /) -> int:
        if self.is_dir():
            return len(tuple(self.fs.iterdir()))
        return self["size"]

    def listdir(self, /, **kwargs) -> list[str]:
        return self.fs.listdir(self if self.is_dir() else self["parent_id"], **kwargs)

    def listdir_attr(self, /, **kwargs) -> list[AttrDict]:
        return self.fs.listdir_attr(self if self.is_dir() else self["parent_id"], **kwargs)

    def listdir_path(self, /, **kwargs) -> list[Self]:
        return self.fs.listdir_path(self if self.is_dir() else self["parent_id"], **kwargs)

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

    @property
    def media_type(self, /) -> None | str:
        if not self.is_file():
            return None
        return guess_type(self.path)[0] or "application/octet-stream"

    @property
    def name(self, /) -> str:
        return basename(self.path)

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

    @property
    def parent(self, /) -> Self:
        if self.id == 0:
            return self
        return type(self)(self.fs.attr(self["parent_id"]))

    @property
    def parents(self, /) -> tuple[Self, ...]:
        parents: list[Self] = []
        cls = type(self)
        path = self
        while path.id != 0:
            path = cls(self.fs.attr(path["parent_id"]))
            parents.append(path)
        return tuple(parents)

    @property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *splits(self.path, do_unescape=False)[0][1:])

    @property
    def patht(self, /) -> tuple[str, ...]:
        return tuple(splits(self.path)[0])

    def read_bytes(
        self, 
        /, 
        start: int = 0, 
        stop: None | int = None, 
    ) -> bytes:
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

    @property
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

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[Self]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self["parent_id"], 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
        )

    @cached_property
    def root(self, /) -> Self:
        return type(self)(self.fs.attr(0))

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if type(self) is type(path):
            return self == path
        return path in ("", ".") or self.path == self.fs.abspath(path)

    def scandir(self, /, **kwargs) -> Iterator[Self]:
        return self.fs.scandir(self if self.is_dir() else self["parent_id"], **kwargs)

    def stat(self, /) -> stat_result:
        return self.fs.stat(self)

    @property
    def stem(self, /) -> str:
        return splitext(basename(self.path))[0]

    @property
    def suffix(self, /) -> str:
        return splitext(basename(self.path))[1]

    @property
    def suffixes(self, /) -> tuple[str, ...]:
        return tuple("." + part for part in basename(self.path).split(".")[1:])

    @property
    def url(self, /) -> str:
        ns = self.__dict__
        try:
            url_expire_time = ns["url_expire_time"]
            if time() + 5 * 60 < url_expire_time:
                return ns["url"]
        except KeyError:
            pass
        url = ns["url"] = self.fs.get_url(self)
        ns["url_expire_time"] = int(parse_qsl(urlparse(url).query)[0][1])
        return url

    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        return self.fs.walk(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            **kwargs, 
        )

    def walk_attr(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        return self.fs.walk_attr(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            **kwargs, 
        )

    def walk_path(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[Self], list[Self]]]:
        return self.fs.walk_path(
            self if self.is_dir() else self["parent_id"], 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
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

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = P115Client(client)
        ns = self.__dict__
        ns["client"] = client
        if request is not None:
            ns["request"] = request

    def __contains__(self, id_or_path: IDOrPathType, /) -> bool:
        return self.exists(id_or_path)

    def __getitem__(self, id_or_path: IDOrPathType, /) -> P115PathType:
        return self.as_path(id_or_path)

    def __iter__(self, /) -> Iterator[P115PathType]:
        return self.iter(max_depth=-1)

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

    @abstractmethod
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> AttrDict:
        ...

    @abstractmethod
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
    ) -> str:
        ...

    @abstractmethod
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        **kwargs, 
    ) -> Iterator[AttrDict]:
        ...

    def abspath(self, path: str | PathLike[str] = "", /) -> str:
        return self.get_path(path, self.id)

    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> P115PathType:
        path_class = type(self).path_class
        attr: AttrDict
        if isinstance(id_or_path, path_class):
            return id_or_path
        elif isinstance(id_or_path, dict):
            attr = cast(AttrDict, id_or_path)
        elif isinstance(id_or_path, int):
            attr = self.attr(id_or_path)
        else:
            attr = self.attr(id_or_path, pid)
        attr["fs"] = self
        return path_class(attr)

    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: None | int = None, 
    ) -> int:
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            id = id_or_path.id
            self.__dict__.update(
                id = id, 
                path = id_or_path["path"], 
            )
            return id
        elif id_or_path in (0, "/"):
            self.__dict__.update(id=0, path="/")
            return 0
        if isinstance(id_or_path, PathLike):
            id_or_path = fspath(id_or_path)
        if not id_or_path or id_or_path == ".":
            return self.id
        attr = self.attr(id_or_path, pid)
        if self.id == attr["id"]:
            return self.id
        elif attr["is_directory"]:
            self.__dict__.update(
                id = attr["id"], 
                path = self.get_path(id_or_path, pid), 
            )
            return attr["id"]
        else:
            raise NotADirectoryError(
                errno.ENOTDIR, f"{id_or_path!r} (in {pid!r}) is not a directory")

    def dictdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        **kwargs, 
    ) -> dict[int, str]:
        if full_path:
            return {attr["id"]: attr["path"] for attr in self.iterdir(id_or_path, pid, **kwargs)}
        else:
            return {attr["id"]: attr["name"] for attr in self.iterdir(id_or_path, pid, **kwargs)}

    def dictdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        **kwargs, 
    ) -> dict[int, AttrDict]:
        return {attr["id"]: attr for attr in self.iterdir(id_or_path, pid, **kwargs)}

    def dictdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        **kwargs, 
    ) -> dict[int, P115PathType]:
        path_class = type(self).path_class
        return {attr["id"]: path_class(attr) for attr in self.iterdir(id_or_path, pid, **kwargs)}

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
                path = self.attr(id_or_path, pid)["name"]
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
            lambda: self.get_url(id_or_path, pid), 
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
        attr = self.attr(id_or_path, pid)
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

    def enumdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        **kwargs, 
    ) -> Iterator[str]:
        if full_path:
            return (attr["path"] for attr in self.iterdir(id_or_path, pid, **kwargs))
        else:
            return (attr["name"] for attr in self.iterdir(id_or_path, pid, **kwargs))

    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> bool:
        path_class = type(self).path_class
        try:
            if isinstance(id_or_path, path_class):
                id_or_path()
            else:
                self.attr(id_or_path, pid)
            return True
        except FileNotFoundError:
            return False

    def getcid(self, /) -> int:
        return self.id

    def getcwd(self, /, fetch_attr: bool = False) -> str:
        if fetch_attr:
            return self.attr(self.id)["path"]
        return self.path

    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> int:
        if isinstance(id_or_path, int):
            return id_or_path
        path_class = type(self).path_class
        if pid is None and (not id_or_path or id_or_path == "."):
            return self.id
        elif isinstance(id_or_path, path_class):
            return id_or_path.id
        if id_or_path == "/":
            return 0
        try:
            path_to_id = getattr(self, "path_to_id", None)
            if path_to_id is not None:
                path = self.get_path(id_or_path, pid)
                return path_to_id[path]
        except LookupError:
            pass
        return self.attr(id_or_path, pid)["id"]

    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> str:
        if isinstance(id_or_path, int):
            id = id_or_path
            if id == 0:
                return "/"
            return self.attr(id)["path"]
        path_class = type(self).path_class
        if pid is None and (not id_or_path or id_or_path == "."):
            return self.path
        elif isinstance(id_or_path, path_class):
            return id_or_path.path
        elif isinstance(id_or_path, dict):
            return id_or_path["path"]
        if isinstance(id_or_path, (str, PathLike)):
            path = fspath(id_or_path)
            if not path.startswith("/"):
                ppath = self.path if pid is None else joins(self.get_patht(pid))
                if path in ("", "."):
                    return ppath
                path = joinpath(ppath, path)
            return normpath(path)
        else:
            path = joins(id_or_path)
            if not path.startswith("/"):
                ppath = self.path if pid is None else joins(self.get_patht(pid))
                if not path:
                    return ppath
                path = joinpath(ppath, path)
        return path

    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> list[str]:
        if isinstance(id_or_path, int):
            id = id_or_path
            if id == 0:
                return [""]
            return splits(self.attr(id)["path"])[0]
        path_class = type(self).path_class
        if pid is None and (not id_or_path or id_or_path == "."):
            return splits(self.path)[0]
        elif isinstance(id_or_path, path_class):
            return splits(id_or_path.path)[0]
        elif isinstance(id_or_path, dict):
            return splits(id_or_path["path"])[0]
        patht: Sequence[str]
        if isinstance(id_or_path, (str, PathLike)):
            path = fspath(id_or_path)
            if path.startswith("/"):
                return splits(path)[0]
            elif path in ("", "."):
                if pid is None:
                    return splits(self.path)[0]
                return self.get_patht(pid)
            patht, parents = splits(path)
        else:
            patht = id_or_path
            if not patht[0]:
                return [p for i, p in enumerate(patht) if not i or p]
            parents = 0
        if pid is None:
            pid = self.id
        ppatht = self.get_patht(pid)
        if parents:
            idx = min(parents, len(ppatht) - 1)
            ppatht = ppatht[:-idx]
        if patht:
            ppatht.extend(patht)
        return ppatht

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[P115PathType]:
        if pattern == "*":
            return self.iter(dirname)
        elif pattern == "**":
            return self.iter(dirname, max_depth=-1)
        path_class = type(self).path_class
        if not pattern:
            try:
                attr = self.attr(dirname)
            except FileNotFoundError:
                return iter(())
            else:
                attr["fs"] = self
                return iter((path_class(attr),))
        elif not pattern.lstrip("/"):
            attr = self.attr(0)
            attr["fs"] = self
            return iter((path_class(attr),))
        splitted_pats = tuple(translate_iter(
            pattern, allow_escaped_slash=allow_escaped_slash))
        dirname_as_id = isinstance(dirname, (int, path_class))
        dirid: int
        if isinstance(dirname, path_class):
            dirid = dirname.id
        elif isinstance(dirname, int):
            dirid = dirname
        if pattern.startswith("/"):
            dir_ = "/"
        else:
            dir_ = self.get_path(dirname)
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
                        attr = self.attr(dir2, dirid)
                    else:
                        attr = self.attr(dir_)
                except FileNotFoundError:
                    return iter(())
                else:
                    attr["fs"] = self
                    return iter((path_class(attr),))
            elif typ == "dstar" and i + 1 == len(splitted_pats):
                if dirname_as_id:
                    return self.iter(dir2, dirid, max_depth=-1)
                else:
                    return self.iter(dir_, max_depth=-1)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dir_), "/".join(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                if dirname_as_id:
                    return self.iter(
                        dir2, 
                        dirid, 
                        max_depth=-1, 
                        predicate=lambda p: match(p.path) is not None, 
                    )
                else:
                    return self.iter(
                        dir_, 
                        max_depth=-1, 
                        predicate=lambda p: match(p.path) is not None, 
                    )
        cref_cache: dict[int, Callable] = {}
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
        if dirname_as_id:
            attr = self.attr(dir2, dirid)
        else:
            attr = self.attr(dir_)
        if not attr["is_directory"]:
            return iter(())
        attr["fs"] = self
        path = path_class(attr)
        return glob_step_match(path, i)

    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> bool:
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            return id_or_path["is_directory"]
        try:
            return self.attr(id_or_path, pid)["is_directory"]
        except FileNotFoundError:
            return False

    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> bool:
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            return not id_or_path["is_directory"]
        try:
            return not self.attr(id_or_path, pid)["is_directory"]
        except FileNotFoundError:
            return False

    def _iter_bfs(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], None | bool] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        dq: deque[tuple[int, P115PathType]] = deque()
        push, pop = dq.append, dq.popleft
        path_class = type(self).path_class
        path = self.as_path(top, pid)
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
                for attr in self.iterdir(path, **kwargs):
                    path = path_class(attr)
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
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], None | bool] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        if not max_depth:
            return
        global_yield_me = True
        if min_depth > 1:
            global_yield_me = False
            min_depth -= 1
        elif min_depth <= 0:
            path = self.as_path(top, pid)
            pred = predicate(path) if predicate else True
            if pred is None:
                return
            elif pred:
                yield path
            if path.is_file():
                return
            min_depth = 1
            top = path.id
        if max_depth > 0:
            max_depth -= 1
        path_class = type(self).path_class
        try:
            for attr in self.iterdir(top, pid, **kwargs):
                path = path_class(attr)
                yield_me = global_yield_me
                if yield_me and predicate:
                    pred = predicate(path)
                    if pred is None:
                        continue
                    yield_me = pred 
                if yield_me and topdown:
                    yield path
                if path.is_dir():
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

    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[P115PathType], None | bool] = None, 
        onerror: bool | Callable[[OSError], bool] = False, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        if topdown is None:
            return self._iter_bfs(
                top, 
                pid, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                **kwargs, 
            )
        else:
            return self._iter_dfs(
                top, 
                pid, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                onerror=onerror, 
                **kwargs, 
            )

    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        full_path: bool = False, 
        **kwargs, 
    ) -> list[str]:
        if full_path:
            return [attr["path"] for attr in self.iterdir(id_or_path, pid, **kwargs)]
        else:
            return [attr["name"] for attr in self.iterdir(id_or_path, pid, **kwargs)]

    def listdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        **kwargs, 
    ) -> list[AttrDict]:
        return list(self.iterdir(id_or_path, pid, **kwargs))

    def listdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        **kwargs, 
    ) -> list[P115PathType]:
        path_class = type(self).path_class
        return [path_class(attr) for attr in self.iterdir(id_or_path, pid, **kwargs)]

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
        url = self.get_url(id_or_path, pid)
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

    def read_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        stop: None | int = None, 
        pid: None | int = None, 
    ) -> bytes:
        url = self.get_url(id_or_path, pid)
        return self.client.read_bytes(url, start, stop)

    def read_bytes_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: None | int = None, 
    ) -> bytes:
        url = self.get_url(id_or_path, pid)
        return self.client.read_bytes_range(url, bytes_range)

    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        size: int = 0, 
        offset: int = 0, 
        pid: None | int = None, 
    ) -> bytes:
        if size <= 0:
            return b""
        url = self.get_url(id_or_path, pid)
        return self.client.read_block(url, size, offset)

    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        pid: None | int = None, 
    ):
        return self.open(
            id_or_path, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            pid=pid, 
        ).read()

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[P115PathType]:
        if not pattern:
            return self.iter(dirname, max_depth=-1)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, ignore_case=ignore_case, allow_escaped_slash=allow_escaped_slash)

    def scandir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        return map(type(self).path_class, self.iterdir(id_or_path, pid, **kwargs))

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> stat_result:
        raise UnsupportedOperation(errno.ENOSYS, 
            "`stat()` is currently not supported, use `attr()` instead."
        )

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
        push((0, self.attr(top, pid)))
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
            for attr in self.iterdir(top, pid, **kwargs):
                if attr["is_directory"]:
                    dirs.append(attr)
                else:
                    files.append(attr)
            if yield_me and topdown:
                yield self.get_path(top, pid), dirs, files
            for attr in dirs:
                yield from self._walk_dfs(
                    attr, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                )
            if yield_me and not topdown:
                yield self.get_path(top, pid), dirs, files
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise

    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        for path, dirs, files in self.walk_attr(
            top, 
            pid, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            **kwargs, 
        ):
            yield path, [a["name"] for a in dirs], [a["name"] for a in files]

    def walk_attr(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[AttrDict], list[AttrDict]]]:
        if topdown is None:
            return self._walk_bfs(
                top, 
                pid, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                **kwargs, 
            )
        else:
            return self._walk_dfs(
                top, 
                pid, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                **kwargs, 
            )

    def walk_path(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        topdown: None | bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable[[OSError], bool] = None, 
        **kwargs, 
    ) -> Iterator[tuple[str, list[P115PathType], list[P115PathType]]]:
        path_class = type(self).path_class
        for path, dirs, files in self.walk_attr(
            top, 
            pid, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            **kwargs, 
        ):
            yield path, [path_class(a) for a in dirs], [path_class(a) for a in files]

    list = listdir_path
    dict = dictdir_path

    cd = chdir
    pwd = getcwd
    ls = listdir
    la = listdir_attr
    ll = listdir_path

