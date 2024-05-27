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
from itertools import islice
from os import fspath, stat_result, PathLike
from posixpath import join as joinpath
from re import compile as re_compile
from stat import S_IFDIR, S_IFREG
from time import time
from typing import cast, Never, Optional, Self

from posixpatht import escape, joins

from .client import check_response, P115Client
from .fs_base import AttrDict, IDOrPathType, P115PathBase, P115FileSystemBase


CRE_SHARE_LINK_search = re_compile(r"(?:/s/|share\.115\.com/)(?P<share_code>[a-z0-9]+)(\?password=(?P<receive_code>\w+))?").search


def normalize_info(
    info: Mapping, 
    keep_raw: bool = False, 
    **extra_data, 
) -> dict:
    if "fid" in info:
        fid = info["fid"]
        parent_id = info["cid"]
        is_dir = False
    else:
        fid = info["cid"]
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
    timestamp = info2["timestamp"] = int(info["t"])
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
    path_to_id: MutableMapping[str, int]
    id_to_attr: MutableMapping[int, AttrDict]
    attr_cache: MutableMapping[int, tuple[AttrDict]]
    full_loaded: bool
    path_class = P115SharePath

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        share_link: str, 
    ):
        m = CRE_SHARE_LINK_search(share_link)
        if m is None:
            raise ValueError("not a valid 115 share link")
        if isinstance(client, str):
            client = P115Client(client)
        self.__dict__.update(
            client=client, 
            id=0, 
            path="/", 
            share_link=share_link, 
            share_code=m["share_code"], 
            receive_code= m["receive_code"] or "", 
            path_to_id={"/": 0}, 
            id_to_attr={}, 
            attr_cache={}, 
            full_loaded=False, 
        )

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}, share_link={self.share_link!r}, id={self.id!r}, path={self.path!r}) at {hex(id(self))}>"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attributes")

    @classmethod
    def login(
        cls, 
        /, 
        share_link: str, 
        cookie = None, 
        app: str = "web", 
        **kwargs, 
    ) -> Self:
        return cls(P115Client(cookie, app=app), share_link, **kwargs)

    @check_response
    def fs_files(self, /, payload: dict) -> dict:
        """获取分享链接的某个文件夹中的文件和子文件夹的列表（包含详细信息）
        :param payload:
            - id: int | str = 0
            - limit: int = 32
            - offset: int = 0
            - asc: 0 | 1 = <default> # 是否升序排列
            - o: str = <default>
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
        """
        return self.client.share_snap({
            **payload, 
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
        })

    @check_response
    def downlist(self, /, id: int = 0) -> dict:
        """获取分享链接的某个文件夹中可下载的文件的列表（只含文件，不含文件夹，任意深度，简略信息）
        """
        return self.client.share_downlist({
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
            "cid": id, 
        })

    @cached_property
    def create_time(self, /) -> datetime:
        "分享的创建时间"
        return datetime.fromtimestamp(int(self.shareinfo["create_time"]))

    @cached_property
    def snap_id(self, /) -> int:
        "获取这个分享的 id"
        return int(self.shareinfo["snap_id"])

    @cached_property
    def user_id(self, /) -> int:
        "获取分享者的用户 id"
        return int(self.sharedata["userinfo"]["user_id"])

    @property
    def sharedata(self, /) -> dict:
        "获取分享的首页数据"
        return self.fs_files({"limit": 1})["data"]

    @property
    def shareinfo(self, /) -> dict:
        "获取分享信息"
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
        pid: Optional[int] = None, 
    ) -> AttrDict:
        "获取属性"
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
        "获取下载链接"
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
        page_size: int = 1_000, 
        **payload, 
    ) -> Iterator[AttrDict]:
        """迭代获取目录内直属的文件或目录的信息
        :param payload:
            - limit: int = 32
            - offset: int = 0
            - asc: 0 | 1 = <default> # 是否升序排列
            - o: str = <default>
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
        """
        if page_size <= 0:
            page_size = 1_000
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
        payload["cid"] = id
        payload["limit"] = page_size
        offset = int(payload.setdefault("offset", 0))
        if offset < 0:
            offset = payload["offset"] = 0
        else:
            payload["offset"] = 0
        try:
            return islice(self.attr_cache[id], offset, None)
        except KeyError:
            dirname = attr["path"]
            def iterdir():
                get_files = self.fs_files
                path_to_id = self.path_to_id
                data = get_files(payload)["data"]
                for attr in map(normalize_info, data["list"]):
                    attr["fs"] = self
                    path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                    path_to_id[path] = attr["id"]
                    yield attr
                for offset in range(page_size, data["count"], page_size):
                    payload["offset"] = offset
                    data = get_files(payload)["data"]
                    for attr in map(normalize_info, data["list"]):
                        attr["fs"] = self
                        path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                        path_to_id[path] = attr["id"]
                        yield attr
            t = self.attr_cache[id] = tuple(iterdir())
            self.id_to_attr.update((attr["id"], attr) for attr in t)
            return iter(t)

    def receive(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        to_pid: int = 0, 
    ) -> dict:
        """接收分享文件到网盘
        :param ids: 要转存到文件 id（这些 id 归属分享链接）
        :param to_pid: 你的网盘的一个目录 id（这个 id 归属你的网盘）
        """
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
            "cid": to_pid, 
        }
        return check_response(self.client.share_receive)(payload)

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> stat_result:
        "检查路径的属性，就像 `os.stat`"
        attr = self.attr(id_or_path, pid)
        is_dir = attr["is_directory"]
        timestamp: float = attr["timestamp"]
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o444, 
            cast(int, attr["id"]), 
            cast(int, attr["parent_id"]), 
            1, 
            self.user_id, 
            1, 
            cast(int, 0 if is_dir else attr["size"]), 
            timestamp, 
            timestamp, 
            timestamp, 
        ))

