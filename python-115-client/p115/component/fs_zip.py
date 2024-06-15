#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115ZipPath", "P115ZipFileSystem"]

import errno

from collections import deque
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from datetime import datetime
from functools import cached_property
from itertools import count, islice
from os import fspath, stat_result, PathLike
from posixpath import join as joinpath
from stat import S_IFDIR, S_IFREG
from typing import cast, Never, Self

from posixpatht import escape, joins, splits, path_is_dir_form

from .client import check_response, P115Client, ExtractProgress, P115Url
from .fs_base import AttrDict, IDOrPathType, P115PathBase, P115FileSystemBase


def normalize_info(
    info: Mapping, 
    **extra_data, 
) -> AttrDict:
    timestamp = info.get("time") or 0
    is_directory = info["file_category"] == 0
    return {
        "name": info["file_name"], 
        "is_directory": is_directory, 
        "file_category": info["file_category"], 
        "size": info["size"], 
        "ico": info.get("ico", "folder" if is_directory else ""), 
        "time": datetime.fromtimestamp(timestamp), 
        "timestamp": timestamp, 
        **extra_data, 
    }


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
    pid_to_children: MutableMapping[int, tuple[AttrDict]]
    full_loaded: bool
    path_class = P115ZipPath

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        id_or_pickcode: int | str, 
        request: None | Callable = None, 
    ):
        super().__init__(client, request)
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

    @classmethod
    def login(
        cls, 
        /, 
        id_or_pickcode: int | str, 
        cookie = None, 
        app: str = "web", 
    ) -> Self:
        return cls(P115Client(cookie, app=app), id_or_pickcode)

    @check_response
    def fs_files(
        self, 
        /, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
    ) -> dict:
        return self.client.extract_list(
            pickcode=self.pickcode, 
            path=path, 
            next_marker=next_marker, 
            page_count=page_count, 
            request=self.request, 
        )

    @cached_property
    def create_time(self, /) -> datetime:
        "创建时间"
        return self.client.get_fs(request=self.request).attr(self.file_id)["ptime"]

    def _attr(self, id: int = 0, /) -> AttrDict:
        try:
            return self.id_to_attr[id]
        except KeyError:
            pass
        if self.full_loaded:
            raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")
        if id == 0:
            attr = self.id_to_attr[0] = {
                "id": 0, 
                "parent_id": 0, 
                "name": "", 
                "path": "/", 
                "is_directory": True, 
                "size": 0, 
                "time": self.create_time, 
                "timestamp": int(self.create_time.timestamp()), 
                "file_category": 0, 
                "fs": self, 
                "ancestors": [{"id": 0, "name": ""}], 
            }
            return attr
        dq = deque((0,))
        get, put = dq.popleft, dq.append
        while dq:
            for attr in self.iterdir(get()):
                if attr["id"] == id:
                    return attr
                if attr["is_directory"]:
                    put(attr["id"])
        self.__dict__["full_loaded"] = True
        raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")

    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
        force_directory: bool = False, 
    ) -> AttrDict:
        if isinstance(path, PathLike):
            path = fspath(path)
        if pid is None:
            pid = self.id
        if not path or path == ".":
            return self._attr(pid)

        parents = 0
        if isinstance(path, str):
            if not force_directory:
                force_directory = path_is_dir_form(path)
            patht, parents = splits(path)
            if not (patht or parents):
                return self._attr(pid)
        else:
            if not force_directory:
                force_directory = path[-1] == ""
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
            ancestors = self.get_ancestors(pid)
            if parents:
                if parents >= len(ancestors):
                    pid = 0
                else:
                    pid = cast(int, ancestors[-parents-1]["id"])
                    ancestor_patht = ["", *(a["name"] for a in ancestors[1:-parents])]
            else:
                ancestor_patht = ["", *(a["name"] for a in ancestors[1:])]
        if not patht:
            return self._attr(pid)

        if pid == 0:
            dirname = ""
            ancestors_paths: list[str] = [(dirname := f"{dirname}/{escape(name)}") for name in patht[1:]]
        else:
            dirname = joins(ancestor_patht)
            ancestors_paths = [(dirname := f"{dirname}/{escape(name)}") for name in patht]

        fullpath = ancestors_paths[-1]
        path_to_id = self.path_to_id
        if path_to_id:
            if not force_directory and (id := path_to_id.get(fullpath)):
                return self._attr(id)
            if (id := path_to_id.get(fullpath + "/")):
                return self._attr(id)
        if self.full_loaded:
            raise FileNotFoundError(
                errno.ENOENT, 
                f"no such path {fullpath!r} (in {pid!r})", 
            )

        parent: int | AttrDict
        for i in reversed(range(len(ancestors_paths)-1)):
            if path_to_id and (id := path_to_id.get((dirname := ancestors_paths[i]) + "/")):
                parent = self._attr(id)
                i += 1
                break
        else:
            i = 0
            parent = pid

        if pid == 0:
            i += 1

        last_idx = len(patht) - 1
        for i, name in enumerate(patht[i:], i):
            for attr in self.iterdir(parent):
                if attr["name"] == name:
                    if force_directory or i < last_idx:
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
                    f"no such file {name!r} (in {parent} @ {ancestors_paths[i]!r})", 
                )
        return attr

    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: bool = True, 
        force_directory: bool = False, 
    ) -> AttrDict:
        "获取属性"
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            attr = id_or_path.__dict__
            if refresh:
                attr = self._attr(attr["id"])
        elif isinstance(id_or_path, AttrDict):
            attr = id_or_path
            if refresh:
                attr = self._attr(attr["id"])
        elif isinstance(id_or_path, int):
            attr = self._attr(id_or_path)
        else:
            return self._attr_path(id_or_path, pid, force_directory=force_directory)
        if force_directory and not attr["is_directory"]:
            raise NotADirectoryError(
                errno.ENOTDIR, 
                f"{attr['id']} (id={attr['id']}) is not directory"
            )
        return attr

    def extract(
        self, 
        /, 
        paths: str | Sequence[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
    ) -> ExtractProgress:
        "解压缩到网盘"
        return self.client.extract_file_future(self.pickcode, paths, dirname, to_pid, request=self.request)

    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> list[dict]:
        "获取各个上级目录的少量信息（从根目录到当前目录）"
        return self.attr(id_or_path, pid)["ancestors"]

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
    ) -> P115Url:
        "获取下载链接"
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{attr['path']!r} (id={attr['id']!r}) is a directory")
        return self.client.extract_download_url(
            self.pickcode, 
            attr["path"], 
            headers=headers, 
            request=self.request, 
        )

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        start: int = 0, 
        stop: None | int = None, 
        page_size: int = 999, 
        **kwargs, 
    ) -> Iterator[AttrDict]:
        """迭代获取目录内直属的文件或目录的信息
        """
        if stop is not None and (start >= 0 and stop >= 0 or start < 0 and stop < 0) and start >= stop:
            return iter(())
        if page_size <= 0 or page_size > 999:
            page_size = 999
        path_class = type(self).path_class
        if isinstance(id_or_path, int):
            attr = self._attr(id_or_path)
        elif isinstance(id_or_path, AttrDict):
            attr = id_or_path
        elif isinstance(id_or_path, path_class):
            attr = id_or_path.__dict__
        else:
            attr = self._attr_path(id_or_path, pid, force_directory=True)
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
            def iterdir():
                get_files = self.fs_files
                path_to_id = self.path_to_id
                data = get_files(path=dirname, page_count=page_size)["data"]
                for info in data["list"]:
                    attr = normalize_info(info, fs=self)
                    path = joinpath(dirname, escape(attr["name"]))
                    attr.update(id=nextid(), parent_id=id, path=path)
                    attr["ancestors"] = [*ancestors, {"id": attr["id"], "name": attr["name"]}]
                    path_to_id[path + "/"[:attr["is_directory"]]] = attr["id"]
                    yield attr
                next_marker = data["next_marker"]
                while next_marker:
                    data = get_files(path=dirname, next_marker=next_marker, page_count=page_size)["data"]
                    for info in data["list"]:
                        attr = normalize_info(info, fs=self)
                        path = joinpath(dirname, escape(attr["name"]))
                        attr.update(id=nextid(), parent_id=id, path=path)
                        attr["ancestors"] = [*ancestors, {"id": attr["id"], "name": attr["name"]}]
                        path_to_id[path + "/"[:attr["is_directory"]]] = attr["id"]
                        yield attr
                    next_marker = data["next_marker"]
            children = self.pid_to_children[id] = tuple(iterdir())
            self.id_to_attr.update((attr["id"], attr) for attr in children)
        count = len(children)
        return iter(children[start:stop])

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> stat_result:
        "检查路径的属性，就像 `os.stat`"
        attr = self.attr(id_or_path, pid)
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

