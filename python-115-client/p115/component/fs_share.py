#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115SharePath", "P115ShareFileSystem"]

import errno

from collections import deque
from collections.abc import (
    Iterable, Iterator, Mapping, MutableMapping, Sequence
)
from datetime import datetime
from functools import cached_property
from os import fspath, stat_result, PathLike
from posixpath import join as joinpath
from re import compile as re_compile
from stat import S_IFDIR, S_IFREG
from time import time
from typing import cast, Never, Optional, Self

from patht import escape, joins

from .client import check_response, P115Client
from .fs_base import AttrDict, IDOrPathType, P115PathBase, P115FileSystemBase


CRE_SHARE_LINK_search = re_compile(r"/s/(?P<share_code>\w+)(\?password=(?P<receive_code>\w+))?").search


def normalize_info(
    info: Mapping, 
    keep_raw: bool = False, 
    **extra_data, 
) -> dict:
    if "fid" in info:
        fid = info["fid"]
        parent_id = info["id"]
        is_dir = False
    else:
        fid = info["id"]
        parent_id = info["pid"]
        is_dir = True
    info2 =  {
        "name": info["n"], 
        "is_directory": is_dir, 
        "size": info.get("s"), 
        "id": int(fid), 
        "parent_id": int(parent_id), 
        "sha1": info.get("sha"), 
    }
    timestamp = info2["timestamp"] = int(info2["t"])
    info2["time"] = datetime.fromtimestamp(timestamp)
    if "pc" in info:
        info2["pickcode"] = info["pc"]
    if "fl" in info:
        info2["labels"] = info["fl"]
    if "c" in info:
        info2["violated"] = bool(info["c"])
    if "u" in info:
        info2["thumb"] = info["u"]
    if "play_long" in info:
        info2["play_long"] = info["play_long"]
    if keep_raw:
        info2["raw"] = info
    if extra_data:
        info2.update(extra_data)
    return info2


class P115SharePath(P115PathBase):
    fs: P115ShareFileSystem


class P115ShareFileSystem(P115FileSystemBase[P115SharePath]):
    share_link: str
    share_code: str
    receive_code: str
    user_id: int
    path_to_id: MutableMapping[str, int]
    id_to_attr: MutableMapping[int, AttrDict]
    attr_cache: MutableMapping[int, tuple[AttrDict]]
    full_loaded: bool
    path_class = P115SharePath

    def __init__(self, /, client: P115Client, share_link: str):
        m = CRE_SHARE_LINK_search(share_link)
        if m is None:
            raise ValueError("not a valid 115 share link")
        self.__dict__.update(
            client=client, 
            cid=0, 
            path="/", 
            share_link=share_link, 
            share_code=m["share_code"], 
            receive_code= m["receive_code"] or "", 
            path_to_id={"/": 0}, 
            id_to_attr={}, 
            attr_cache={}, 
            full_loaded=False, 
        )
        self.__dict__["user_id"] = int(self.sharedata["userinfo"]["user_id"])

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}, share_link={self.share_link!r}, cid={self.cid!r}, path={self.path!r}) at {hex(id(self))}>"

    @classmethod
    def login(
        cls, 
        /, 
        share_link: str, 
        cookie = None, 
        app: str = "web", 
    ) -> Self:
        return cls(P115Client(cookie, login_app=app), share_link)

    @check_response
    def fs_files(
        self, 
        /, 
        id: int = 0, 
        limit: int = 32, 
        offset: int = 0, 
    ) -> dict:
        return self.client.share_snap({
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
            "cid": id, 
            "offset": offset, 
            "limit": limit, 
        })

    @check_response
    def _list(self, /, id: int = 0) -> dict:
        return self.client.share_downlist({
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
            "cid": id, 
        })

    @cached_property
    def create_time(self, /) -> datetime:
        return datetime.fromtimestamp(int(self.shareinfo["create_time"]))

    @property
    def sharedata(self, /) -> dict:
        return self.fs_files(limit=1)["data"]

    @property
    def shareinfo(self, /) -> dict:
        return self.sharedata["shareinfo"]

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
                "time": self.create_time, 
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
        pid: Optional[int] = None, 
    ) -> AttrDict:
        if isinstance(path, PathLike):
            path = fspath(path)
        if pid is None:
            pid = self.cid
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
        pid: Optional[int] = None, 
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

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
    ) -> str:
        path_class = type(self).path_class
        if isinstance(id_or_path, (int, path_class)):
            id = id_or_path if isinstance(id_or_path, int) else id_or_path.id
            if id in self.id_to_attr:
                attr = self.id_to_attr[id]
                if attr["is_directory"]:
                    raise IsADirectoryError(errno.EISDIR, f"{attr['path']!r} (id={attr['id']!r}) is a directory")
        else:
            attr = self.attr(id_or_path, pid)
            if attr["is_directory"]:
                raise IsADirectoryError(errno.EISDIR, f"{attr['path']!r} (id={attr['id']!r}) is a directory")
            id = attr["id"]
        return self.client.share_download_url({
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
            "file_id": id, 
        }, headers=headers)

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[AttrDict]:
        path_class = type(self).path_class
        if isinstance(id_or_path, int):
            attr = self.attr(id_or_path)
        elif isinstance(id_or_path, dict):
            attr = id_or_path
        elif isinstance(id_or_path, path_class):
            attr = id_or_path.__dict__
        else:
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
            dirname = attr["path"]
            def iterdir():
                page_size = 1 << 10
                get_files = self.fs_files
                path_to_id = self.path_to_id
                data = get_files(id, page_size)["data"]
                for attr in map(normalize_info, data["list"]):
                    attr["fs"] = self
                    path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                    path_to_id[path] = attr["id"]
                    yield attr
                for offset in range(page_size, data["count"], page_size):
                    data = get_files(id, page_size, offset)["data"]
                    for attr in map(normalize_info, data["list"]):
                        attr["fs"] = self
                        path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                        path_to_id[path] = attr["id"]
                        yield attr
            t = self.attr_cache[id] = tuple(iterdir())
            self.id_to_attr.update((attr["id"], attr) for attr in t)
            return iter(t)

    def receive(self, ids: int | str | Iterable[int | str], /, cid: int = 0):
        if isinstance(ids, int):
            ids = str(ids)
        elif isinstance(ids, Iterable):
            ids = ",".join(map(str, ids))
        if not ids:
            raise ValueError("no id (to file) to receive")
        payload = {
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
            "file_id": ids, 
            "cid": cid, 
        }
        return check_response(self.client.share_receive)(payload)

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> stat_result:
        attr = self.attr(id_or_path, pid)
        is_dir = attr["is_directory"]
        timestamp = attr["timestamp"], 
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o444, 
            attr["id"], 
            attr["parent_id"], 
            1, 
            self.user_id, 
            1, 
            0 if is_dir else attr["size"], 
            timestamp, 
            timestamp, 
            timestamp, 
        ))

