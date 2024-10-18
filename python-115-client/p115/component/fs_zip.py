#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115ZipPath", "P115ZipFileSystem"]

import errno

from collections import deque
from collections.abc import (
    AsyncIterator, Callable, Coroutine, Iterator, Mapping, MutableMapping, Sequence, 
)
from copy import deepcopy
from datetime import datetime
from functools import cached_property, partial
from itertools import count, islice
from os import fspath, stat_result, PathLike
from posixpath import join as joinpath
from stat import S_IFDIR, S_IFREG
from typing import cast, overload, Any, Literal, Never, Self

from dictattr import AttrDict
from iterutils import run_gen_step
from p115client import check_response, P115URL
from posixpatht import escape, joins, splits, path_is_dir_form

from .client import P115Client, ExtractProgress
from .fs_base import IDOrPathType, P115PathBase, P115FileSystemBase


def normalize_attr(info: Mapping, /) -> AttrDict[str, Any]:
    timestamp = info.get("time") or 0
    is_directory = info["file_category"] == 0
    return AttrDict({
        "name": info["file_name"], 
        "is_directory": is_directory, 
        "file_category": info["file_category"], 
        "size": info["size"], 
        "ico": info.get("ico", "folder" if is_directory else ""), 
        "time": datetime.fromtimestamp(timestamp), 
        "timestamp": timestamp, 
    })


# TODO: 兼容 pathlib.Path 和 zipfile.Path 的接口
class P115ZipPath(P115PathBase):
    fs: P115ZipFileSystem


# TODO: 参考 zipfile 模块的接口设计 namelist、filelist 等属性，以及其它的和 zipfile 兼容的接口
# TODO: 当文件特别多时，可以用 zipfile 等模块来读取文件列表
class P115ZipFileSystem(P115FileSystemBase[P115ZipPath]):
    file_id: int
    pickcode: str
    path_to_id: MutableMapping[str, int]
    id_to_attr: MutableMapping[int, AttrDict]
    pid_to_children: MutableMapping[int, tuple[AttrDict, ...]]
    full_loaded: bool
    path_class = P115ZipPath

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        id_or_pickcode: int | str, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        super().__init__(client, request, async_request)
        client = self.client
        request = self.request
        tempfs = client.get_fs(request=request)
        if isinstance(id_or_pickcode, int):
            file_id = id_or_pickcode
            attr = tempfs.attr(file_id)
            pickcode = attr["pickcode"]
            self.__dict__["create_time"] = attr["ptime"]
        else:
            pickcode = id_or_pickcode
            file_id = tempfs.get_id_from_pickcode(pickcode)
        resp = check_response(client.extract_push_progress(pickcode, request=request))
        if resp["data"]["extract_status"]["unzip_status"] != 4:
            raise OSError(errno.EIO, "file was not decompressed")
        self.__dict__.update(
            id=0, 
            path="/", 
            file_id=file_id, 
            pickcode=pickcode, 
            path_to_id={"/": 0}, 
            id_to_attr={}, 
            pid_to_children={}, 
            full_loaded=False, 
            _nextid=count(1).__next__, 
        )

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attributes")

    @overload
    def fs_files(
        self, 
        /, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_files(
        self, 
        /, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files(
        self, 
        /, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return check_response(self.client.extract_list( # type: ignore
            pickcode=self.pickcode, 
            path=path, 
            next_marker=next_marker, 
            page_count=page_count, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @cached_property
    def create_time(self, /) -> datetime:
        "创建时间"
        return self.client.get_fs(request=self.request).attr(self.file_id)["ptime"]

    @overload
    def _attr(
        self, 
        id: int, 
        /, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def _attr(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def _attr(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        def gen_step():
            try:
                return self.id_to_attr[id]
            except KeyError:
                pass
            if self.full_loaded:
                raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")
            if id == 0:
                attr = self.id_to_attr[0] = AttrDict({
                    "id": 0, 
                    "parent_id": 0, 
                    "name": "", 
                    "path": "/", 
                    "is_directory": True, 
                    "size": 0, 
                    "time": self.create_time, 
                    "timestamp": int(self.create_time.timestamp()), 
                    "file_category": 0, 
                    "ico": "folder", 
                    "ancestors": [{"id": 0, "name": ""}], 
                })
                return attr
            dq = deque((0,))
            get, put = dq.popleft, dq.append
            if async_:
                async def request():
                    while dq:
                        async for attr in self.iterdir(get(), async_=True):
                            if attr["id"] == id:
                                return attr
                            if attr["is_directory"]:
                                put(attr["id"])
                    self.__dict__["full_loaded"] = True
                    raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")
                yield request
            else:
                while dq:
                    for attr in self.iterdir(get()):
                        if attr["id"] == id:
                            return attr
                        if attr["is_directory"]:
                            put(attr["id"])
                self.__dict__["full_loaded"] = True
                raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")
        return run_gen_step(gen_step, async_=async_)

    @overload
    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        def gen_step():
            nonlocal path, pid, ensure_dir

            if isinstance(path, PathLike):
                path = fspath(path)
            if pid is None:
                pid = self.id
            if not path or path == ".":
                return (yield partial(self._attr, pid, async_=async_))

            parents = 0
            if isinstance(path, str):
                if not ensure_dir:
                    ensure_dir = path_is_dir_form(path)
                patht, parents = splits(path)
                if not (patht or parents):
                    return (yield partial(self._attr, pid, async_=async_))
            else:
                if not ensure_dir:
                    ensure_dir = path[-1] == ""
                patht = [path[0], *(p for p in path[1:] if p)]
            if patht == [""]:
                return self._attr(0)
            elif patht and patht[0] == "":
                pid = 0

            ancestor_patht: list[str] = []
            if pid == 0:
                if patht[0] != "":
                    patht.insert(0, "")
            else:
                ancestors = yield partial(self.get_ancestors, pid, async_=async_)
                if parents:
                    if parents >= len(ancestors):
                        pid = 0
                    else:
                        pid = cast(int, ancestors[-parents-1]["id"])
                        ancestor_patht = ["", *(a["name"] for a in ancestors[1:-parents])]
                else:
                    ancestor_patht = ["", *(a["name"] for a in ancestors[1:])]
            if not patht:
                return (yield partial(self._attr, pid, async_=async_))

            if pid == 0:
                dirname = ""
                ancestors_paths: list[str] = [(dirname := f"{dirname}/{escape(name)}") for name in patht[1:]]
            else:
                dirname = joins(ancestor_patht)
                ancestors_paths = [(dirname := f"{dirname}/{escape(name)}") for name in patht]

            fullpath = ancestors_paths[-1]
            path_to_id = self.path_to_id
            if path_to_id:
                if not ensure_dir and (id := path_to_id.get(fullpath)):
                    return (yield partial(self._attr, id, async_=async_))
                if (id := path_to_id.get(fullpath + "/")):
                    return (yield partial(self._attr, id, async_=async_))
            if self.full_loaded:
                raise FileNotFoundError(
                    errno.ENOENT, 
                    f"no such path {fullpath!r} (in {pid!r})", 
                )

            parent: int | AttrDict
            for i in reversed(range(len(ancestors_paths)-1)):
                if path_to_id and (id := path_to_id.get((dirname := ancestors_paths[i]) + "/")):
                    parent = yield partial(self._attr, id, async_=async_)
                    i += 1
                    break
            else:
                i = 0
                parent = pid

            if pid == 0:
                i += 1

            attr: AttrDict
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
                            if isinstance(parent, AttrDict):
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
                        if isinstance(parent, AttrDict):
                            parent = parent["id"]
                        raise FileNotFoundError(
                            errno.ENOENT, 
                            f"no such file {name!r} (in {parent} @ {joins(patht[:i])!r})", 
                        )
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
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
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_dir: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        "获取属性"
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, path_class):
                attr = id_or_path.attr
            elif isinstance(id_or_path, AttrDict):
                attr = id_or_path
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

    # TODO: 支持异步
    def extract(
        self, 
        /, 
        paths: str | Sequence[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
    ) -> ExtractProgress:
        "解压缩到网盘"
        return self.client.extract_file_future(
            self.pickcode, 
            paths, 
            dirname, 
            to_pid, 
            request=self.request, 
        )

    @overload
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "获取各个上级目录的少量信息（从根目录到当前目录）"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            return deepcopy(attr["ancestors"])
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
                self.client.extract_download_url, 
                self.pickcode, 
                attr["path"], 
                headers=headers, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            ))
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
        *, 
        async_: Literal[False] = False, 
        **payload, 
    ) -> Iterator[AttrDict]:
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
        *, 
        async_: Literal[True], 
        **payload, 
    ) -> AsyncIterator[AttrDict]:
        ...
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        start: int = 0, 
        stop: None | int = None, 
        page_size: int = 1_000, 
        *, 
        async_: Literal[False, True] = False, 
        **payload, 
    ) -> Iterator[AttrDict] | AsyncIterator[AttrDict]:
        """迭代获取目录内直属的文件或目录的信息
        """
        path_class = type(self).path_class
        if page_size <= 0 or page_size > 999:
            page_size = 999
        def gen_step():
            nonlocal start, stop
            if stop is not None and (start >= 0 and stop >= 0 or start < 0 and stop < 0) and start >= stop:
                return ()
            if isinstance(id_or_path, int):
                attr = yield partial(self._attr, id_or_path, async_=async_)
            elif isinstance(id_or_path, AttrDict):
                attr = id_or_path
            elif isinstance(id_or_path, path_class):
                attr = id_or_path.attr
            else:
                attr = yield partial(
                    self._attr_path, 
                    id_or_path, 
                    pid=pid, 
                    ensure_dir=True, 
                    async_=async_, 
                )
            if not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['path']!r} (id={attr['id']!r}) is not a directory", 
                )
            id = attr["id"]
            ancestors = attr["ancestors"]
            try:
                children = self.pid_to_children[id]
            except KeyError:
                nextid = self.__dict__["_nextid"]
                dirname = attr["path"]
                get_files = self.fs_files
                path_to_id = self.path_to_id
                ls: list[AttrDict] = []
                add = ls.append
                resp = yield partial(
                    get_files, 
                    path=dirname, 
                    page_count=page_size, 
                    async_=async_, 
                )
                data = resp["data"]
                for info in data["list"]:
                    attr = normalize_attr(info)
                    path = joinpath(dirname, escape(attr["name"]))
                    attr.update(id=nextid(), parent_id=id, path=path)
                    attr["ancestors"] = [*ancestors, {"id": attr["id"], "name": attr["name"]}]
                    path_to_id[path + "/"[:attr["is_directory"]]] = attr["id"]
                    add(attr)
                next_marker = data["next_marker"]
                while next_marker:
                    resp = yield partial(
                        get_files, 
                        path=dirname, 
                        ext_marker=next_marker, 
                        page_count=page_size, 
                        async_=async_, 
                    )
                    data = resp["data"]
                    for info in data["list"]:
                        attr = normalize_attr(info)
                        path = joinpath(dirname, escape(attr["name"]))
                        attr.update(id=nextid(), parent_id=id, path=path)
                        attr["ancestors"] = [*ancestors, {"id": attr["id"], "name": attr["name"]}]
                        path_to_id[path + "/"[:attr["is_directory"]]] = attr["id"]
                        add(attr)
                    next_marker = data["next_marker"]
                children = self.pid_to_children[id] = tuple(ls)
                self.id_to_attr.update((attr["id"], attr) for attr in children)
            return children[start:stop]
        return run_gen_step(gen_step, async_=async_, as_iter=True)

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
        "检查路径的属性，就像 `os.stat`"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            is_dir = attr["is_directory"]
            timestamp: float = attr["timestamp"]
            return stat_result((
                (S_IFDIR if is_dir else S_IFREG) | 0o444, # mode
                cast(int, attr["id"]), # ino
                cast(int, attr["parent_id"]), # dev
                1, # nlink
                self.client.user_id, # uid
                1, # gid
                cast(int, 0 if is_dir else attr["size"]), # size
                timestamp, # atime
                timestamp, # mtime
                timestamp, # ctime
            ))
        return run_gen_step(gen_step, async_=async_)

