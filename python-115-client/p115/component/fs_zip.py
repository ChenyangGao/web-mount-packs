#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115ZipPath", "P115ZipFileSystem"]

import errno

from collections import deque
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from datetime import datetime
from functools import cached_property
from itertools import count
from os import fspath, stat_result, PathLike
from posixpath import join as joinpath
from stat import S_IFDIR, S_IFREG
from typing import cast, Never, Self

from posixpatht import escape, joins

from .client import check_response, P115Client, ExtractProgress
from .fs_base import AttrDict, IDOrPathType, P115PathBase, P115FileSystemBase


def normalize_info(
    info: Mapping, 
    **extra_data, 
) -> dict:
    timestamp = info.get("time") or 0
    return {
        "name": info["file_name"], 
        "is_directory": info["file_category"] == 0, 
        "file_category": info["file_category"], 
        "size": info["size"], 
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
    file_id: None | int
    pickcode: str
    path_to_id: MutableMapping[str, int]
    id_to_attr: MutableMapping[int, AttrDict]
    attr_cache: MutableMapping[int, tuple[AttrDict]]
    full_loaded: bool
    path_class = P115ZipPath

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        id_or_pickcode: int | str, 
    ):
        file_id: None | int
        if isinstance(client, str):
            client = P115Client(client)
        if isinstance(id_or_pickcode, int):
            file_id = id_or_pickcode
            pickcode = client.fs.attr(file_id)["pickcode"]
        else:
            file_id = None
            pickcode = id_or_pickcode
        resp = check_response(client.extract_push_progress(pickcode))
        if resp["data"]["extract_status"]["unzip_status"] != 4:
            raise OSError(errno.EIO, "file was not decompressed")
        self.__dict__.update(
            client=client, 
            id=0, 
            path="/", 
            pickcode=pickcode, 
            file_id=file_id, 
            path_to_id={"/": 0}, 
            id_to_attr={}, 
            attr_cache={}, 
            full_loaded=False, 
            _nextid=count(1).__next__, 
        )
        if file_id is None:
            self.__dict__["create_time"] = datetime.fromtimestamp(0)

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
        )

    @cached_property
    def create_time(self, /) -> datetime:
        if self.file_id is None:
            return datetime.fromtimestamp(0)
        return self.client.fs.attr(self.file_id)["ptime"]

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
                "file_category": 0, 
                "is_directory": True, 
                "name": "", 
                "path": "/", 
                "size": 0, 
                "time": self.create_time, 
                "timestamp": int(self.create_time.timestamp()), 
                "fs": self, 
            }
            return attr
        dq = deque((0,))
        while dq:
            pid = dq.popleft()
            for attr in self.iterdir(pid):
                if attr["id"] == id:
                    return attr
                if attr["is_directory"]:
                    dq.append(attr["id"])
        self.__dict__["full_loaded"] = True
        raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")

    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
    ) -> AttrDict:
        if isinstance(path, PathLike):
            path = fspath(path)
        if pid is None:
            pid = self.id
        if not path or path == ".":
            return self._attr(pid)
        patht = self.get_patht(path, pid)
        fullpath = joins(patht)
        path_to_id = self.path_to_id
        if fullpath in path_to_id:
            id = path_to_id[fullpath]
            return self._attr(id)
        if self.full_loaded:
            raise FileNotFoundError(errno.ENOENT, f"no such file {path!r} (in {pid!r})")
        attr = self._attr(pid)
        for name in patht[len(self.get_patht(pid)):]:
            if not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, f"`pid` does not point to a directory: {pid!r}")
            for attr in self.iterdir(pid):
                if attr["name"] == name:
                    pid = cast(int, attr["id"])
                    break
            else:
                raise FileNotFoundError(errno.ENOENT, f"no such file {name!r} (in {pid!r})")
        return attr

    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> AttrDict:
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            return self._attr(id_or_path["id"])
        elif isinstance(id_or_path, dict):
            attr = id_or_path
            if "id" in attr:
                return self._attr(attr["id"])
            return self._attr_path(attr["path"])
        elif isinstance(id_or_path, int):
            return self._attr(id_or_path)
        else:
            return self._attr_path(id_or_path, pid)

    def extract(
        self, 
        /, 
        paths: str | Sequence[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
    ) -> ExtractProgress:
        return self.client.extract_file_future(self.pickcode, paths, dirname, to_pid)

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
    ) -> str:
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{attr['path']!r} (id={attr['id']!r}) is a directory")
        return self.client.extract_download_url(self.pickcode, attr["path"], headers=headers)

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        **kwargs, 
    ) -> Iterator[AttrDict]:
        attr = self.attr(id_or_path, pid)
        if not attr["is_directory"]:
            raise NotADirectoryError(
                errno.ENOTDIR, 
                f"{attr['path']!r} (id={attr['id']!r}) is not a directory", 
            )
        id = attr["id"]
        try:
            return iter(self.attr_cache[id])
        except KeyError:
            nextid = self.__dict__["_nextid"]
            dirname = attr["path"]
            def iterdir():
                get_files = self.fs_files
                path_to_id = self.path_to_id
                data = get_files(dirname, **kwargs)["data"]
                for info in data["list"]:
                    attr = normalize_info(info, fs=self)
                    path = joinpath(dirname, escape(attr["name"]))
                    attr.update(id=nextid(), parent_id=id, path=path)
                    path_to_id[path] = attr["id"]
                    yield attr
                next_marker = data["next_marker"]
                while next_marker:
                    data = get_files(dirname, next_marker, **kwargs)["data"]
                    for info in data["list"]:
                        attr = normalize_info(info, fs=self)
                        path = joinpath(dirname, escape(attr["name"]))
                        attr.update(id=nextid(), parent_id=id, path=path)
                        path_to_id[path] = attr["id"]
                        yield attr
                    next_marker = data["next_marker"]
            t = self.attr_cache[id] = tuple(iterdir())
            self.id_to_attr.update((attr["id"], attr) for attr in t)
            return iter(t)

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> stat_result:
        attr = self.attr(id_or_path, pid)
        is_dir = attr["is_directory"]
        timestamp: float = attr["timestamp"]
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o444, 
            cast(int, attr["id"]), 
            cast(int, attr["parent_id"]), 
            1, 
            self.client.user_id, 
            1, 
            cast(int, 0 if is_dir else attr["size"]), 
            timestamp, 
            timestamp, 
            timestamp, 
        ))

