#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Path", "P115FileSystem"]

import errno

from collections import deque, ChainMap
from collections.abc import (
    Callable, Iterable, Iterator, Mapping, MutableMapping, Sequence, 
)
from datetime import datetime
from io import BytesIO, TextIOWrapper
from itertools import islice
from json import JSONDecodeError
from os import (
    path as ospath, fsdecode, fspath, makedirs, remove, rmdir, scandir, stat_result, PathLike
)
from pathlib import Path
from posixpath import join as joinpath, splitext
from shutil import SameFileError
from stat import S_IFDIR, S_IFREG
from typing import cast, Literal, Optional, Self
from uuid import uuid4
from yarl import URL

from filewrap import Buffer, SupportsRead
from http_request import SupportsGeturl
from posixpatht import basename, commonpath, dirname, escape, joins, normpath, splits, unescape

from .client import check_response, P115Client
from .fs_base import AttrDict, IDOrPathType, P115PathBase, P115FileSystemBase


def normalize_info(
    info: Mapping, 
    keep_raw: bool = False, 
    **extra_data, 
) -> AttrDict:
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
    for k1, k2, k3 in (
        ("te", "etime", "mtime"), 
        ("tu", "utime", None), 
        ("tp", "ptime", "ctime"), 
        ("to", "open_time", "atime"), 
        ("t", "time", None), 
    ):
        if k1 in info:
            try:
                t = int(info[k1])
                info2[k2] = datetime.fromtimestamp(t)
                if k3:
                    info2[k3] = t
            except ValueError:
                pass
    if "pc" in info:
        info2["pickcode"] = info["pc"]
    if "fl" in info:
        info2["labels"] = info["fl"]
    if "score" in info:
        info2["score"] = int(info["score"])
    if "m" in info:
        info2["star"] = bool(info["m"])
    if "issct" in info:
        info2["shortcut"] = bool(info["issct"])
    if "hdf" in info:
        info2["hidden"] = bool(info["hdf"])
    if "fdes" in info:
        info2["described"] = bool(info["fdes"])
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


class P115Path(P115PathBase):
    fs: P115FileSystem

    @property
    def length(self, /):
        if self.is_dir():
            return self.fs.dirlen(self.id)
        return self["size"]

    @property
    def desc(self, /):
        return self.fs.desc(self)

    @desc.setter
    def desc(self, /, desc: str = ""):
        return self.fs.desc(self, desc=desc)

    @property
    def score(self, /) -> bool:
        return self["score"]

    @score.setter
    def score(self, /, score: bool = True):
        self.fs.score(self, score=score)

    @property
    def star(self, /) -> bool:
        return self["star"]

    @star.setter
    def star(self, /, star: bool = True):
        self.fs.star(self, star=star)

    def copy(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: bool | Callable[[OSError], bool] = True, 
    ) -> None | Self:
        attr = self.fs.copy(
            self, 
            dst_path, 
            pid=pid, 
            overwrite=overwrite, 
            onerror=onerror, 
            recursive=True, 
        )
        if attr is None:
            return None
        return type(self)(attr)

    def mkdir(self, /, exist_ok: bool = True) -> Self:
        self.__dict__.update(self.fs.makedirs(self, exist_ok=exist_ok))
        return self

    def move(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> Self:
        self.__dict__.update(self.fs.move(self, dst_path, pid))
        return self

    def remove(self, /, recursive: bool = True) -> AttrDict:
        return self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> Self:
        self.__dict__.update(self.fs.rename(self, dst_path, pid))
        return self

    def renames(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> Self:
        self.__dict__.update(self.fs.renames(self, dst_path, pid))
        return self

    def replace(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> Self:
        self.__dict__.update(self.fs.replace(self, dst_path, pid))
        return self

    def rmdir(self, /) -> AttrDict:
        return self.fs.rmdir(self)

    def search(self, /, **payload) -> Iterator[P115Path]:
        return self.fs.search(self, **payload)

    def touch(self, /) -> Self:
        self.__dict__.update(self.fs.touch(self))
        return self

    unlink = remove

    def write_bytes(
        self, 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
    ) -> Self:
        self.__dict__.update(self.fs.write_bytes(self, data))
        return self

    def write_text(
        self, 
        /, 
        text: str = "", 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> Self:
        self.__dict__.update(self.fs.write_text(
            self, 
            text, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        ))
        return self


class P115FileSystem(P115FileSystemBase[P115Path]):
    attr_cache: Optional[MutableMapping[int, dict]]
    path_to_id: Optional[MutableMapping[str, int]]
    get_version: Optional[Callable]
    path_class = P115Path

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        password: str = "", 
        attr_cache: Optional[MutableMapping[int, dict]] = None, 
        path_to_id: Optional[MutableMapping[str, int]] = None, 
        get_version: Optional[Callable] = lambda attr: attr.get("mtime", 0), 
    ):
        if isinstance(client, str):
            client = P115Client(client)
        if attr_cache is not None:
            attr_cache = {}
        if type(path_to_id) is dict:
            path_to_id["/"] = 0
        elif path_to_id is not None:
            path_to_id = ChainMap(path_to_id, {"/": 0})
        self.__dict__.update(
            client = client, 
            id = 0, 
            path = "/", 
            password = password, 
            path_to_id = path_to_id, 
            attr_cache = attr_cache, 
            get_version = get_version, 
        )

    def __delitem__(self, id_or_path: IDOrPathType, /):
        self.rmtree(id_or_path)

    def __len__(self, /) -> int:
        return self.dirlen(self.id)

    def __setitem__(
        self, 
        id_or_path: IDOrPathType, 
        file: ( None | str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        /, 
    ):
        if file is None:
            return self.touch(id_or_path)
        elif isinstance(file, PathLike):
            if ospath.isdir(file):
                return list(self.upload_tree(file, id_or_path, no_root=True, overwrite=True))
            else:
                return self.upload(file, id_or_path, overwrite=True)
        elif isinstance(file, str):
            return self.write_text(id_or_path, file)
        else:
            return self.write_bytes(id_or_path, file)

    @classmethod
    def login(
        cls, 
        /, 
        cookie = None, 
        app: str = "web", 
        **kwargs, 
    ) -> Self:
        kwargs["client"] = P115Client(cookie, app=app)
        return cls(**kwargs)

    @property
    def password(self, /) -> str:
        return self.__dict__["password"]

    @password.setter
    def password(self, /, password: str = ""):
        self.__dict__["password"] = password

    @check_response
    def fs_mkdir(self, name: str, /, pid: int = 0) -> AttrDict:
        return self.client.fs_mkdir({"cname": name, "pid": pid})

    @check_response
    def fs_copy(self, id: int, /, pid: int = 0) -> AttrDict:
        return self.client.fs_copy(id, pid)

    @check_response
    def fs_delete(self, id: int, /) -> AttrDict:
        return self.client.fs_delete(id)

    @check_response
    def fs_move(self, id: int, /, pid: int = 0) -> AttrDict:
        return self.client.fs_move(id, pid)

    @check_response
    def fs_rename(self, id: int, name: str, /) -> AttrDict:
        return self.client.fs_rename(id, name)

    @check_response
    def fs_batch_copy(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
    ) -> AttrDict:
        return self.client.fs_batch_copy(payload, pid)

    @check_response
    def fs_batch_delete(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
    ) -> AttrDict:
        return self.client.fs_batch_delete(payload)

    @check_response
    def fs_batch_move(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
    ) -> AttrDict:
        return self.client.fs_batch_move(payload, pid)

    @check_response
    def fs_batch_rename(
        self, 
        payload: dict | Iterable[tuple[int | str, str]], 
        /, 
    ) -> AttrDict:
        return self.client.fs_batch_rename(payload)

    def fs_info(self, id: int, /) -> AttrDict:
        result = self.client.fs_info({"file_id": id})
        if result["state"]:
            return result
        match result["code"]:
            # {'state': False, 'code': 20018, 'message': '文件不存在或已删除。'}
            case 20018:
                raise FileNotFoundError(result)
            # {'state': False, 'code': 990002, 'message': '参数错误。'}
            case 990002:
                raise OSError(errno.EINVAL, result)
            case _:
                raise OSError(errno.EIO, result)

    def fs_files(self, /, payload: dict) -> AttrDict:
        id = int(payload["id"])
        resp = check_response(self.client.fs_files(payload))
        if int(resp["path"][-1]["cid"]) != id:
            raise NotADirectoryError(errno.ENOTDIR, f"{id!r} is not a directory")
        return resp

    @check_response
    def fs_search(self, payload: str | dict, /) -> AttrDict:
        return self.client.fs_search(payload)

    @check_response
    def space_summury(self, /) -> AttrDict:
        return self.client.fs_space_summury()

    def _upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        name: str, 
        pid: None | int = None, 
    ) -> AttrDict:
        if pid is None:
            pid = self.id
        data = check_response(self.client.upload_file(file, name, pid))["data"]
        if "file_id" in data:
            file_id = int(data["file_id"])
            try:
                return self._attr(file_id)
            except FileNotFoundError:
                self.fs_files({"cid": pid, "limit": 1})
                return self._attr(file_id)
        else:
            name = data["file_name"]
            try:
                return self._attr_path([name], pid)
            except FileNotFoundError:
                self.fs_files({"cid": pid, "limit": 1})
                return self._attr_path([name], pid)

    def _clear_cache(self, attr: dict, /):
        attr_cache = self.attr_cache
        if attr_cache is None:
            return
        id = attr["id"]
        pid = attr["parent_id"]
        if id:
            try:
                attr_cache[pid]["children"].pop(id, None)
            except:
                pass
        if attr["is_directory"]:
            path_to_id = self.path_to_id
            if path_to_id is None:
                pop_path = None
            else:
                def pop_path(path):
                    try:
                        del path_to_id[path]
                    except:
                        pass
            startswith = str.startswith
            dq = deque((id,))
            get, put = dq.popleft, dq.append
            while dq:
                id = get()
                try:
                    cache = attr_cache[id]
                    del attr_cache[id]
                except KeyError:
                    pass
                else:
                    for subid, subattr in cache["children"].items():
                        if pop_path is not None:
                            pop_path(subattr["path"])
                        if subattr["is_directory"]:
                            put(subid)
            if path_to_id is not None and pop_path is not None:
                dirname = attr["path"]
                pop_path(dirname)
                dirname += "/"
                for k in tuple(k for k in path_to_id if startswith(k, dirname)):
                    pop_path(k)

    def _update_cache_path(self, attr: dict, new_attr: dict, /):
        attr_cache = self.attr_cache
        if attr_cache is None:
            return
        id = attr["id"]
        opid = attr["parent_id"]
        npid = new_attr["parent_id"]
        if id and opid != npid:
            try:
                attr_cache[opid]["children"].pop(id, None)
            except:
                pass
            try:
                attr_cache[npid]["children"][id] = new_attr
            except:
                pass
        if attr["is_directory"]:
            path_to_id = self.path_to_id
            if path_to_id is None:
                pop_path = None
            else:
                def pop_path(path):
                    try:
                        del path_to_id[path]
                    except:
                        pass
            startswith = str.startswith
            old_path = attr["path"]
            new_path = new_attr["path"]
            if pop_path is not None:
                pop_path(old_path)
            if path_to_id is not None:
                path_to_id[new_path] = id
            old_path += "/"
            new_path += "/"
            len_old_path = len(old_path)
            dq = deque((id,))
            get, put = dq.popleft, dq.append
            while dq:
                id = get()
                try:
                    cache = attr_cache[id]
                    del attr_cache[id]
                except KeyError:
                    pass
                else:
                    for subid, subattr in cache["children"].items():
                        subpath = subattr["path"]
                        if startswith(subpath, old_path):
                            new_subpath = subattr["path"] = new_path + subpath[len_old_path:]
                            if pop_path is not None:
                                pop_path(subpath)
                            if path_to_id is not None:
                                path_to_id[new_subpath] = subid
                        if subattr["is_directory"]:
                            put(subid)
            if path_to_id is not None and pop_path is not None:
                for k in tuple(k for k in path_to_id if startswith(k, old_path)):
                    pop_path(k)

    def _attr(self, id: int, /)  -> AttrDict:
        if id == 0:
            last_update = datetime.now()
            return {
                "id": 0, 
                "parent_id": 0, 
                "name": "", 
                "path": "/", 
                "is_directory": True, 
                "etime": last_update, 
                "utime": last_update, 
                "ptime": datetime.fromtimestamp(0), 
                "open_time": last_update, 
                "fs": self, 
            }
        attr_cache = self.attr_cache
        get_version = self.get_version
        if attr_cache is None:
            attrs = None
        else:
            attrs = attr_cache.get(id)
        if attrs and "attr" in attrs and get_version is None:
            return attrs["attr"]
        try:
            data = self.fs_info(id)["data"][0]
        except OSError as e:
            raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}") from e
        attr = normalize_info(data, fs=self)
        pid = attr["parent_id"]
        attr_old = None
        if attr_cache is not None:
            if get_version is None:
                version = None
            else:
                version = get_version(attr)
            if attrs is None or "attr" not in attrs:
                if attrs is None:
                    attr_cache[id] = {"attr": attr}
                else:
                    attrs["attr"] = attr
                try:
                    pid_attrs = attr_cache[pid]
                except LookupError:
                    pid_attrs = attr_cache[pid] = {}
                try:
                    children = pid_attrs["children"]
                except LookupError:
                    children = pid_attrs["children"] = {}
                children[id] = attr
            else:
                attr_old = attrs["attr"]
                if version != attrs.get("version"):
                    attrs.pop("version", None)
                attr_old.update(attr)
                attr = attr_old
        if "path" not in attr:
            if pid:
                path = attr["path"] = joins(
                    (*(a["name"] for a in self._dir_get_ancestors(pid)), attr["name"]))
            else:
                path = attr["path"] = "/" + escape(attr["name"])
            path_to_id = self.path_to_id
            if path_to_id is not None:
                path_to_id[path] = id
                if attr_old and path != attr_old["path"]:
                    try:
                        del path_to_id[attr_old["path"]]
                    except LookupError:
                        pass
        return attr

    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
    )  -> AttrDict:
        if isinstance(path, PathLike):
            path = fspath(path)
        if isinstance(path, str):
            if path.startswith("/"):
                pid = 0
        elif path and path[0] == "":
            pid = 0
        if pid is None:
            pid = self.id
        if not path or path == ".":
            return self._attr(pid)
        patht = self.get_patht(path, pid)
        fullpath = joins(patht)
        path_to_id = self.path_to_id
        if path_to_id is not None and fullpath in path_to_id:
            id = path_to_id[fullpath]
            try:
                attr = self._attr(id)
                if attr["path"] == fullpath:
                    return attr
            except FileNotFoundError:
                pass
            try:
                del path_to_id[fullpath]
            except:
                pass
        attr = self._attr(pid)
        for name in patht[len(self.get_patht(attr["path"])):]:
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

    def _dir_get_ancestors(self, id: int, /) -> list[dict]:
        ls = [{"name": "", "id": 0, "parent_id": 0, "is_directory": True}]
        if id:
            ls.extend(
                {"name": p["name"], "id": int(p["cid"]), "parent_id": int(p["pid"]), "is_directory": True} 
                for p in self.fs_files({"cid": id, "limit": 1})["path"][1:]
            )
        return ls

    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    )  -> AttrDict:
        "获取属性"
        if isinstance(id_or_path, P115Path):
            return id_or_path.__dict__
        elif isinstance(id_or_path, dict):
            return id_or_path
        elif isinstance(id_or_path, int):
            return self._attr(id_or_path)
        else:
            return self._attr_path(id_or_path, pid)

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: bool = False, 
        page_size: int = 1_000, 
        **payload, 
    ) -> Iterator[AttrDict]:
        """迭代获取目录内直属的文件或目录的信息
        payload:
            - asc: 0 | 1 = 1     # 是否升序排列
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1
            - custom_order: int | str = <default>
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - format: str = "json"
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - natsort: 0 | 1 = <default>
            - o: str = "file_name"
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
            - offset: int = 0    # 索引偏移，索引从 0 开始计算
            - record_open_time: 0 | 1 = 1
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1
            - snap: 0 | 1 = <default>
            - source: str = <default>
            - star: 0 | 1 = <default> # 是否星标文件
            - suffix: str = <default> # 后缀名
            - type: int | str = <default>
                # 文件类型：
                # - 所有: 0
                # - 文档: 1
                # - 图片: 2
                # - 音频: 3
                # - 视频: 4
                # - 压缩包: 5
                # - 应用: 6
                # - 书籍: 7
        """
        if page_size <= 0:
            page_size = 1_000
        path_to_id = self.path_to_id
        attr_cache = self.attr_cache
        get_version = self.get_version
        version = None
        if attr_cache is None and isinstance(id_or_path, int):
            id = id_or_path
        else:
            attr = None
            if not refresh:
                path_class = type(self).path_class
                if isinstance(id_or_path, dict):
                    attr = id_or_path
                elif isinstance(id_or_path, path_class):
                    attr = id_or_path.__dict__
            if attr is None:
                attr = self.attr(id_or_path, pid)
            if not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['path']!r} (id={attr['id']!r}) is not a directory", 
                )
            id = attr["id"]
            if get_version is not None:
                version = get_version(attr)
        payload["cid"] = id
        payload["limit"] = page_size
        offset = int(payload.setdefault("offset", 0))
        if offset < 0:
            offset = payload["offset"] = 0
        if attr_cache is None:
            pid_attrs = None
        else:
            pid_attrs = attr_cache.get(id)
        if (
            refresh or 
            pid_attrs is None or 
            "version" not in pid_attrs or
            version != pid_attrs["version"]
        ):
            def normalize_attr(attr, dirname, /, **extra):
                attr = normalize_info(attr, **extra)
                path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                if path_to_id is not None:
                    path_to_id[path] = attr["id"]
                if attr_cache is not None:
                    try:
                        id_attrs = attr_cache[attr["id"]]
                    except LookupError:
                        attr_cache[attr["id"]] = {"attr": attr}
                    else:
                        try:
                            old_attr = id_attrs["attr"]
                        except LookupError:
                            id_attrs["attr"] = attr
                        else:
                            if path != old_attr["path"] and path_to_id is not None:
                                try:
                                    del path_to_id[old_attr["path"]]
                                except LookupError:
                                    pass
                            old_attr.update(attr)
                return attr
            def iterdir():
                get_files = self.fs_files
                resp = get_files(payload)
                dirname = joins(("", *(a["name"] for a in resp["path"][1:])))
                if path_to_id is not None:
                    path_to_id[dirname] = id
                count = resp["count"]
                for attr in resp["data"]:
                    yield normalize_attr(attr, dirname, fs=self)
                for offset in range(page_size, count, 1 << 10):
                    payload["offset"] = offset
                    resp = get_files(payload)
                    if resp["count"] != count:
                        raise RuntimeError(f"{id} detected count changes during iteration")
                    for attr in resp["data"]:
                        yield normalize_attr(attr, dirname, fs=self)
            if attr_cache is None:
                return iterdir()
            else:
                payload["offset"] = 0
                children = {a["id"]: a for a in iterdir()}
                attrs = attr_cache[id] = {"version": version, "attr": attr, "children": children}
        else:
            children = pid_attrs["children"]
        return islice(children.values(), offset, None)

    def copy(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
    ) -> None | AttrDict:
        "复制文件"
        try:
            src_attr = self.attr(src_path, pid)
            src_path = cast(str, src_attr["path"])
            if src_attr["is_directory"]:
                if recursive:
                    return self.copytree(
                        src_attr, 
                        dst_path, 
                        pid=pid, 
                        overwrite=overwrite, 
                        onerror=onerror, 
                    )
                raise IsADirectoryError(errno.EISDIR, f"source path is a directory: {src_path!r}")

            src_patht = self.get_patht(src_path)
            *src_dirt, src_name = src_patht
            src_id = src_attr["id"]
            try:
                dst_attr = self.attr(dst_path, pid)
            except FileNotFoundError:
                if isinstance(dst_path, int):
                    raise

                dst_patht = self.get_patht(dst_path, pid)
                *dst_dirt, dst_name = dst_patht
                dst_path = joins(dst_patht)
                if dst_patht == src_patht[:len(dst_patht)]:
                    raise PermissionError(
                        errno.EPERM, 
                        f"copy a file to its ancestor path is not allowed: {src_path!r} -> {dst_path!r}", 
                    )
                elif src_patht == dst_patht[:len(src_patht)]:
                    raise PermissionError(
                        errno.EPERM, 
                        f"copy a file to its descendant path is not allowed: {src_path!r} -> {dst_path!r}", 
                    )

                if src_dirt == dst_dirt:
                    dst_pid = src_attr["parent_id"]
                else:
                    dst_pattr = self.makedirs(dst_patht[:-1])
                    dst_pid = dst_pattr["id"]
            else:
                if src_id == dst_attr["id"]:
                    raise SameFileError(src_path)
                elif dst_attr["is_directory"]:
                    raise IsADirectoryError(
                        errno.EISDIR, 
                        f"destination is a directory: {src_path!r} -> {dst_path!r}", 
                    )
                elif overwrite:
                    self.remove(dst_attr)
                else:
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"destination already exists: {src_path!r} -> {dst_path!r}", 
                    )
                dst_pid = dst_attr["parent_id"]

            if splitext(src_name)[1] != splitext(dst_name)[1]:
                dst_name = check_response(self.client.upload_file_init)(
                    filename=dst_name, 
                    filesize=src_attr["size"], 
                    file_sha1=src_attr["sha1"], 
                    read_range_bytes_or_hash=lambda rng: self.read_bytes_range(src_id, rng), 
                    pid=dst_pid, 
                )["data"]["file_name"]
                return self.attr([dst_name], dst_pid)
            elif src_name == dst_name:
                self.fs_copy(src_id, dst_pid)
                return self.attr([dst_name], dst_pid)
            else:
                tempdir_id = int(self.fs_mkdir(str(uuid4()))["id"])
                try:
                    self.fs_copy(src_id, tempdir_id)
                    dst_id = self.attr([src_name], tempdir_id)["id"]
                    resp = self.fs_rename(dst_id, dst_name)
                    if resp["data"]:
                        dst_name = resp["data"][str(dst_id)]
                    self.fs_move(dst_id, dst_pid)
                finally:
                    self.fs_delete(tempdir_id)
                return self.attr(dst_id)
        except OSError as e:
            if onerror is True:
                raise
            elif onerror is False:
                pass
            else:
                onerror(e)
            return None

    # TODO: 使用 fs_batch_* 方法，尽量加快执行速度，但是如果任务数过大（大于 5 万）而报错，则尝试对任务进行拆分
    # TODO: 删除、还原、复制、移动等操作均遵此例，也就是尽量用 batch 方法
    def copytree(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: bool | Callable[[OSError], bool] = True, 
    ) -> None | AttrDict:
        "复制路径"
        try:
            src_attr = self.attr(src_path, pid)
            if not src_attr["is_directory"]:
                return self.copy(
                    src_attr, 
                    dst_path, 
                    pid=pid, 
                    overwrite=overwrite, 
                    onerror=onerror, 
                )

            src_id = src_attr["id"]
            src_path = src_attr["path"]
            src_name = src_attr["name"]
            try:
                dst_attr = self.attr(dst_path, pid)
            except FileNotFoundError:
                if isinstance(dst_path, int):
                    raise
                dst_patht = self.get_patht(dst_path, pid)
                if len(dst_patht) == 1:
                    dst_id = 0
                    dst_name = src_name
                else:
                    dst_pattr = self.makedirs(dst_patht[:-1], exist_ok=True)
                    dst_id = dst_pattr["id"]
                    dst_name = dst_patht[-1]
                try:
                    if src_name == dst_name:
                        self.fs_copy(src_id, dst_id)
                        return self.attr([dst_name], dst_id)
                except (OSError, JSONDecodeError):
                    pass
                dst_attr = self.makedirs([dst_name], pid=dst_id, exist_ok=True)
                dst_id = dst_pattr["id"]
                dst_attrs_map = {}
            else:
                dst_path = dst_attr["path"]
                if not dst_attr["is_directory"]:
                    raise NotADirectoryError(
                        errno.ENOTDIR, 
                        f"destination path {dst_path!r} is not directory", 
                    )
                dst_id = dst_attr["id"]
                if src_id == dst_id:
                    raise SameFileError(src_path)
                elif any(a["id"] == src_id for a in self.get_ancestors(dst_id)):
                    raise PermissionError(
                        errno.EPERM, 
                        f"copy a directory as its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
                    )
                dst_attrs_map = {a["name"]: a for a in self.listdir_attr(dst_id)}

            src_attrs = self.listdir_attr(src_id)
        except OSError as e:
            if onerror is True:
                raise
            elif onerror is False:
                pass
            else:
                onerror(e)
            return None

        src_files: list[int] = []
        payload: dict = dict(pid=dst_id, overwrite=overwrite, onerror=onerror)
        for attr in src_attrs:
            payload["src_path"] = attr
            if attr["name"] in dst_attrs_map:
                payload["dst_path"] = dst_attrs_map[attr["name"]]
                if attr["is_directory"]:
                    self.copytree(**payload)
                else:
                    self.copy(**payload)
            elif attr["is_directory"]:
                payload["dst_path"] = [attr["name"]]
                self.copytree(**payload)
            else:
                src_files.append(attr["id"])
        if src_files:
            for i in range(0, len(src_files), 50_000):
                self.fs_batch_copy(src_files[i:i+50_000], dst_id)
        return dst_attr

    def desc(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        desc: None | str = None, 
    ) -> str:
        """目录的描述文本（支持 HTML）
        :param desc: 如果为 None，返回描述文本；否则，设置文本
        """
        fid = self.get_id(id_or_path, pid)
        if fid == 0:
            return ""
        if desc is None:
            return check_response(self.client.fs_desc_get(fid))["desc"]
        else:
            return check_response(self.client.fs_desc(fid, desc))["file_description"]

    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> list[dict]:
        "获取各个上级目录的少量信息（从根目录到当前目录）"
        attr = self.attr(id_or_path, pid)
        ls = self._dir_get_ancestors(attr["parent_id"])
        ls.append({"name": attr["name"], "id": attr["id"], "parent_id": attr["parent_id"], "is_directory": attr["is_directory"]})
        return ls

    def dirlen(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
    ) -> int:
        "文件夹中的项目数（直属的文件和目录计数）"
        return self.fs_files({"cid": self.get_id(id_or_path, pid), "limit": 1})["count"]

    def get_id_from_pickcode(self, /, pickcode: str = "") -> int:
        "由 pickcode 获取 id"
        if not pickcode:
            return 0
        return self.get_info_from_pickcode(pickcode)["id"]

    def get_info_from_pickcode(self, /, pickcode: str) -> AttrDict:
        "由 pickcode 获取一些目录信息"
        return self.client.download_url(pickcode, strict=False, detail=True).__dict__

    def get_pickcode(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
    ) -> str:
        "获取 pickcode"
        return self.attr(id_or_path, pid).get("pickcode", "")

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: Optional[Mapping] = None, 
        detail: bool = False, 
    ) -> str:
        "获取下载链接"
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{attr['path']!r} (id={attr['id']!r}) is a directory")
        return self.client.download_url(
            attr["pickcode"], 
            use_web_api=attr.get("violated", False) and attr["size"] < 1024 * 1024 * 115, 
            detail=detail, 
            headers=headers, 
        )

    def get_url_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        headers: Optional[Mapping] = None, 
        detail: bool = False, 
    ) -> str:
        "由 pickcode 获取下载链接"
        return self.client.download_url(
            pickcode, 
            detail=detail, 
            headers=headers, 
        )

    # TODO: 如果超过 5 万个文件，则需要分批进入隐藏模式
    def hide(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        show: None | bool = None, 
    ) -> bool:
        "把路径隐藏或显示（如果隐藏，只能在隐藏模式中看到）"
        if show is None:
            return self.attr(id_or_path, pid)["hidden"]
        else:
            fid = self.get_id(id_or_path, pid)
            if fid == 0:
                return False
            hidden = not show
            check_response(self.client.fs_files_hidden({"hidden": int(hidden), "fid[0]": fid}))
            return hidden

    @property
    def hidden_mode(self, /) -> bool:
        "是否进入隐藏模式"
        return self.client.user_setting()["data"]["show"] == "1"

    def hidden_switch(
        self, 
        /, 
        show: None | bool = None, 
        password: str = "", 
    ):
        "切换隐藏模式，如果需要进入隐藏模式，需要提供密码"
        if show is None:
            show = not self.hidden_mode
        check_response(self.client.fs_hidden_switch({"show": int(show), "safe_pwd": password or self.password}))

    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> bool:
        "路径是否为空文件或空目录"
        attr: dict | P115Path
        if isinstance(id_or_path, P115Path):
            attr = id_or_path
        else:
            try:
                attr = self.attr(id_or_path, pid)
            except FileNotFoundError:
                return True
        if attr["is_directory"]:
            return self.dirlen(attr["id"]) > 0
        return attr["size"] == 0

    def iter_repeat(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        page_size: int = 1150, 
    ) -> Iterator[AttrDict]:
        "获取重复文件（不含当前这个）"
        if page_size <= 0:
            page_size = 1150
        payload = {
            "file_id": self.get_id(id_or_path, pid), 
            "offset": 0, 
            "limit": page_size, 
            "format": "json", 
        }
        while True:
            data = check_response(self.client.fs_get_repeat(payload))["data"]
            yield from data
            if len(data) < page_size:
                break
            payload["offset"] += page_size # type: ignore

    def labels(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> list[dict]:
        "获取路径的标签"
        return self.attr(id_or_path, pid)["labels"]

    def makedirs(
        self, 
        path: str | PathLike[str] | Sequence[str] | AttrDict, 
        /, 
        pid: None | int = None, 
        exist_ok: bool = False, 
    ) -> AttrDict:
        "创建目录，如果上级目录不存在，则会进行创建"
        if isinstance(path, dict):
            patht, parents = splits(path["path"])
        elif isinstance(path, (str, PathLike)):
            patht, parents = splits(fspath(path))
        else:
            patht = [p for p in path if p]
            parents = 0
        if pid is None:
            pid = self.id
        get_attr = self.attr
        if not patht:
            if parents:
                ancestors = self.get_ancestors(pid)
                idx = min(parents-1, len(ancestors))
                pid = cast(int, ancestors[-idx]["id"])
            return get_attr(pid)
        elif patht == [""]:
            return get_attr(0)
        exists = False
        for name in patht:
            try:
                attr = get_attr([name], pid)
            except FileNotFoundError:
                exists = False
                resp = self.fs_mkdir(name, pid)
                pid = int(resp["cid"])
                attr = get_attr(pid)
            else:
                exists = True
                if not attr["is_directory"]:
                    raise NotADirectoryError(
                        errno.ENOTDIR, 
                        f"{path!r} (in {pid!r}): there is a superior non-directory", 
                    )
                pid = attr["id"]
        if not exist_ok and exists:
            raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) exists")
        return attr

    def mkdir(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
    ) -> AttrDict:
        "创建目录"
        if isinstance(path, (int, dict)):
            return self.attr(path)
        elif isinstance(path, (str, PathLike)):
            patht, parents = splits(fspath(path))
        else:
            patht = [p for p in path if p]
            parents = 0
        if not patht or patht == [""]:
            raise OSError(errno.EINVAL, f"invalid path: {path!r}")
        if pid is None:
            pid = self.id
        if parents:
            ancestors = self.get_ancestors(pid)
            idx = min(parents-1, len(ancestors))
            pid = ancestors[-idx]["id"]
        get_attr = self._attr_path
        for i, name in enumerate(patht, 1):
            try:
                attr = get_attr([name], pid)
            except FileNotFoundError:
                break
            else:
                if not attr["is_directory"]:
                    raise NotADirectoryError(
                        errno.ENOTDIR, 
                        f"{attr['id']!r} ({name!r} in {pid!r}) not a directory", 
                    )
                pid = attr["id"]
        else:
            raise FileExistsError(
                errno.EEXIST, f"{path!r} (in {pid!r}) already exists")
        if i < len(patht):
            raise FileNotFoundError(
                errno.ENOENT, 
                f"{path!r} (in {pid!r}) missing superior directory", 
            )
        resp = self.fs_mkdir(name, pid)
        return self.attr(int(resp["cid"]))

    def move(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> AttrDict:
        "重命名路径，如果目标路径是目录，则移动到其中"
        try:
            dst_attr = self.attr(dst_path, pid)
        except FileNotFoundError:
            return self.rename(src_path, dst_path, pid)
        src_attr = self.attr(src_path, pid)
        src_id = src_attr["id"]
        dst_id = dst_attr["id"]
        if src_id == dst_id or src_attr["parent_id"] == dst_id:
            return src_attr
        src_path = src_attr["path"]
        dst_path = dst_attr["path"]
        if any(a["id"] == src_id for a in self.get_ancestors(dst_id)):
            raise PermissionError(
                errno.EPERM, 
                f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}"
            )
        if dst_attr["is_directory"]:
            return self.rename(src_attr, [src_attr["name"]], pid=dst_attr["id"])
        raise FileExistsError(
            errno.EEXIST, 
            f"destination already exists: {src_path!r} -> {dst_path!r}", 
        )

    # TODO: 由于 115 网盘不支持删除里面有超过 5 万个文件等目录，因此执行失败时需要拆分任务
    # TODO: 就算删除和还原执行返回成功，后台可能依然在执行，需要等待前一批完成再执行下一批
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        recursive: bool = False, 
    ) -> AttrDict:
        "删除文件"
        attr = self.attr(id_or_path, pid)
        id = attr["id"]
        if attr["is_directory"]:
            if not recursive:
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"{attr['path']!r} (id={id!r}) is a directory", 
                )
            if id == 0:
                for subattr in self.iterdir(0):
                    self.remove(subattr, recursive=True)
                return attr
        self.fs_delete(id)
        self._clear_cache(attr)
        return attr

    def removedirs(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
    ) -> AttrDict:
        "逐级往上尝试删除空目录"
        attr = self.attr(id_or_path, pid)
        id = attr["id"]
        if not attr["is_directory"]:
            raise NotADirectoryError(
                errno.ENOTDIR, 
                f"{attr['path']!r} (id={id!r}) is not a directory", 
            )
        delid = 0
        pattr = attr
        get_files = self.fs_files
        while id:
            files = get_files({"id": id, "limit": 1})
            if files["count"] > 1:
                break
            delid = id
            id = int(files["path"][-1]["pid"])
            pattr = {
                "id": delid, 
                "parent_id": id, 
                "is_directory": True, 
                "path": "/" + joins([p["name"] for p in files["path"][1:]]), 
            }
        if delid:
            self.fs_delete(delid)
            self._clear_cache(pattr)
        return attr

    def rename(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        replace: bool = False, 
    ) -> AttrDict:
        "重命名路径"
        src_attr = self.attr(src_path, pid)
        src_id = src_attr["id"]
        src_path = src_attr["path"]
        src_patht = self.get_patht(src_path)
        try:
            dst_attr = self.attr(dst_path, pid)
        except FileNotFoundError:
            dst_patht = self.get_patht(dst_path, pid)
            dst_path = joins(dst_patht)
            if dst_patht == src_patht[:len(dst_patht)]:
                raise PermissionError(
                    errno.EPERM, 
                    f"rename a path to its ancestor is not allowed: {src_path!r} -> {dst_path!r}", 
                )
            elif src_patht == dst_patht[:len(src_patht)]:
                raise PermissionError(
                    errno.EPERM, 
                    f"rename a path to its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
                )
            dst_pattr = self.makedirs(dst_patht[:-1], exist_ok=True)
            dst_pid = dst_pattr["id"]
        else:
            dst_id = dst_attr["id"]
            if src_id == dst_id:
                return dst_attr
            if replace:
                if src_attr["is_directory"]:
                    if dst_attr["is_directory"]:
                        if self.dirlen(dst_attr["id"]):
                            raise OSError(
                                errno.ENOTEMPTY, 
                                f"source is directory, but destination is non-empty directory: {src_path!r} -> {dst_path!r}", 
                            )
                    else:
                        raise NotADirectoryError(
                            errno.ENOTDIR, 
                            f"source is directory, but destination is not a directory: {src_path!r} -> {dst_path!r}", 
                        )
                elif dst_attr["is_directory"]:
                    raise IsADirectoryError(
                        errno.EISDIR, 
                        f"source is file, but destination is directory: {src_path!r} -> {dst_path!r}", 
                    )
                self.fs_delete(dst_id)
            else:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"destination already exists: {src_path!r} -> {dst_path!r}", 
                )
            dst_pid = dst_attr["parent_id"]
            dst_path = dst_attr["path"]
            dst_patht = self.get_patht(dst_path)

        *src_dirt, src_name = src_patht
        *dst_dirt, dst_name = dst_patht
        src_ext = splitext(src_name)[1]
        dst_ext = splitext(dst_name)[1]

        if src_dirt == dst_dirt and (src_attr["is_directory"] or src_ext == dst_ext):
            self.fs_rename(src_id, dst_name)
        elif src_name == dst_name:
            self.fs_move(src_id, dst_pid)
        elif not src_attr["is_directory"] and src_ext != dst_ext:
            dst_name = check_response(self.client.upload_file_init)(
                dst_name, 
                filesize=src_attr["size"], 
                file_sha1=src_attr["sha1"], 
                read_range_bytes_or_hash=lambda rng: self.read_bytes_range(src_id, rng), 
                pid=dst_pid, 
            )["data"]["file_name"]
            self.fs_delete(src_id)
            return self.attr([dst_name], dst_pid)
        else:
            self.fs_rename(src_id, str(uuid4()))
            try:
                self.fs_move(src_id, dst_pid)
                try:
                    self.fs_rename(src_id, dst_name)
                except:
                    self.fs_move(src_id, src_attr["parent_id"])
                    raise
            except:
                self.fs_rename(src_id, src_name)
                raise
        return self.attr(src_id)

    def renames(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> AttrDict:
        "重命名路径，如果文件被移动到其它目录中，则尝试从原来的上级目录逐级往上删除空目录"
        attr = self.attr(src_path, pid)
        parent_id = attr["parent_id"]
        attr = self.rename(attr, dst_path, pid=pid)
        if parent_id != attr["parent_id"]:
            self.removedirs(parent_id)
        return attr

    def replace(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> AttrDict:
        "替换路径"
        return self.rename(src_path, dst_path, pid=pid, replace=True)

    def rmdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
    ) -> AttrDict:
        "删除空目录"
        attr = self.attr(id_or_path, pid)
        id = attr["id"]
        if id == 0:
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{id_or_path!r} (in {pid!r}) is not a directory")
        elif self.fs_files({"id": id, "limit": 1})["count"]:
            raise OSError(errno.ENOTEMPTY, f"directory is not empty: {id_or_path!r} (in {pid!r})")
        self.fs_delete(id)
        self._clear_cache(attr) 
        return attr

    def rmtree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
    ) -> AttrDict:
        "删除路径"
        return self.remove(id_or_path, pid, recursive=True)

    def score(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        score: None | int = None, 
    ) -> int:
        """路径的分数
        :param star: 如果为 None，返回分数；否则，设置分数
        """
        if score is None:
            return self.attr(id_or_path, pid).get("score", 0)
        else:
            fid = self.get_id(id_or_path, pid)
            if fid == 0:
                return 0
            self.client.fs_score(fid, score)
            return score

    def search(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        page_size: int = 1_000, 
        **payload, 
    ) -> Iterator[P115Path]:
        """搜索目录
        :param payload:
            - asc: 0 | 1 = <default> # 是否升序排列
            - count_folders: 0 | 1 = <default>
            - date: str = <default> # 筛选日期
            - fc_mix: 0 | 1 = <default> # 是否目录置顶，0 为置顶
            - file_label: int | str = <default> # 标签 id
            - format: str = "json" # 输出格式（不用管）
            - o: str = <default>
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
            - offset: int = 0  # 索引偏移，索引从 0 开始计算
            - pick_code: str = <default>
            - search_value: str = <default>
            - show_dir: 0 | 1 = 1
            - source: str = <default>
            - star: 0 | 1 = <default>
            - suffix: str = <default>
            - type: int | str = <default>
                # 文件类型：
                # - 所有: 0
                # - 文档: 1
                # - 图片: 2
                # - 音频: 3
                # - 视频: 4
                # - 压缩包: 5
                # - 应用: 6
                # - 书籍: 7
        """
        if page_size <= 0:
            page_size = 1_000
        attr = self.attr(id_or_path, pid)
        payload["cid"] = attr["id"]
        payload["limit"] = page_size
        offset = int(payload.setdefault("offset", 0))
        if offset < 0:
            payload["offset"] = 0
        if not attr["is_directory"]:
            payload.setdefault("search_value", attr["sha1"])
        search = self.fs_search
        while True:
            resp = search(payload)
            if resp["offset"] != offset:
                break
            data = resp["data"]
            if not data:
                return
            for attr in resp["data"]:
                attr = normalize_info(attr, fs=self)
                yield P115Path(attr)
            offset = payload["offset"] = offset + resp["page_size"]
            if offset >= resp["count"]:
                break

    def star(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        star: None | bool = None, 
    ) -> bool:
        """路径的星标
        :param star: 如果为 None，返回星标是否已设置；如果为 True，设置星标；如果为 False，取消星标
        """
        if star is None:
            return self.attr(id_or_path, pid).get("star", False)
        else:
            fid = self.get_id(id_or_path, pid)
            if fid == 0:
                return False
            check_response(self.client.fs_star(fid, star))
            return star

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
    ) -> stat_result:
        "检查路径的属性，就像 `os.stat`"
        attr = self.attr(id_or_path, pid)
        is_dir = attr["is_directory"]
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o777, # mode
            cast(int, attr["id"]), # ino
            cast(int, attr["parent_id"]), # dev
            1, # nlink
            self.client.user_id, # uid
            1, # gid
            0 if is_dir else attr["size"], # size
            cast(float, attr.get("atime", 0)), # atime
            cast(float, attr.get("mtime", 0)), # mtime
            cast(float, attr.get("ctime", 0)), # ctime
        ))

    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        is_dir: bool = False, 
    ) -> AttrDict:
        """检查路径是否存在，当不存在时，如果 is_dir 是 False 时，则创建空文件，否则创建空目录
        """
        try:
            return self.attr(id_or_path, pid)
        except FileNotFoundError:
            if isinstance(id_or_path, int):
                raise ValueError(f"no such id: {id_or_path!r}")
            elif is_dir:
                return self.mkdir(id_or_path, pid)
            else:
                return self.upload(b"", id_or_path, pid=pid)

    # TODO: 增加功能，返回一个 Task 对象，可以获取上传进度，可随时取消
    # TODO: 参数 file 支持更多类型
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        remove_done: bool = False, 
    ) -> AttrDict:
        "上传文件"
        name: str = ""
        if not path:
            pid = self.id if pid is None else self.get_id(pid)
        else:
            attr: Mapping
            if isinstance(path, int):
                attr = self.attr(path)
            elif isinstance(path, (str, PathLike)):
                dirname, name = ospath.split(path)
                attr = self.attr(dirname, pid)
            elif isinstance(path, Sequence):
                if len(path) == 1 and path[0] == "":
                    attr = self.attr(0)
                else:
                    *dirname_t, name = path
                    attr = self.attr(dirname_t, pid)
            else:
                attr = path
            pid = attr["id"]
            if attr["is_directory"]:
                if name:
                    try:
                        attr = self.attr([name], pid)
                        if attr["is_directory"]:
                            pid = attr["id"]
                            name = ""
                    except FileNotFoundError:
                        pass
            if not attr["is_directory"]:
                if name:
                    raise NotADirectoryError(errno.ENOTDIR, f"parent path {attr['path']!r} is not directory")
                elif overwrite:
                    self.remove(attr)
                    name = attr["name"]
                    pid = attr["parent_id"]
                else:
                    raise FileExistsError(errno.EEXIST, f"remote path {attr['path']!r} already exists")

        resp = self._upload(file, name, pid)
        if remove_done and isinstance(file, (str, PathLike)):
            try:
                remove(file)
            except OSError:
                pass
        return resp

    # TODO: 上传和下载都要支持多线程
    # TODO: 返回上传任务的迭代器，包含进度相关信息，以及最终的响应信息
    # TODO: 增加参数，submit，可以把任务提交给线程池
    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str] = ".", 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        no_root: bool = False, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        predicate: None | Callable[[Path], bool] = None, 
        onerror: bool | Callable[[OSError], bool] = True, 
    ) -> Iterator[AttrDict]:
        "上传到路径"
        remote_path_attr_map: None | dict[str, dict] = None
        try:
            attr = self.attr(path, pid)
        except FileNotFoundError:
            if isinstance(path, int):
                raise ValueError(f"no such id: {path!r}")
            attr = self.makedirs(path, pid=pid, exist_ok=True)
            remote_path_attr_map = {}
        else:
            if not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['path']!r} (id={attr['id']!r}) is not a directory", 
                )
        pid = cast(int, attr["id"])

        local_path = ospath.normpath(local_path)
        try:
            try:
                if predicate is None:
                    subpaths = tuple(scandir(local_path))
                else:
                    subpaths = tuple(filter(lambda e: predicate(Path(e)), scandir(local_path)))
                if not subpaths:
                    return
            except NotADirectoryError:
                try:
                    yield self.upload(
                        local_path, 
                        [ospath.basename(local_path)], 
                        pid=pid, 
                        overwrite=overwrite, 
                        remove_done=remove_done, 
                    )
                except OSError as e:
                    if onerror is True:
                        raise e
                    elif onerror is False:
                        pass
                    else:
                        onerror(e)
                    return
            if not no_root:
                attr = self.makedirs(
                    [ospath.basename(local_path)], 
                    pid=pid, 
                    exist_ok=True, 
                )
                pid = attr["id"]
                remote_path_attr_map = {}
            elif remote_path_attr_map is None:
                remote_path_attr_map = {a["name"]: a for a in self.iterdir(pid)}
        except OSError as e:
            if onerror is True:
                raise e
            elif onerror is False:
                pass
            else:
                onerror(e)
            return

        for entry in subpaths:
            name = entry.name
            isdir = entry.is_dir()
            remote_path_attr = remote_path_attr_map.get(name)
            if remote_path_attr and isdir != remote_path_attr["is_directory"]:
                if onerror is True:
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"remote path {remote_path_attr['path']!r} already exists", 
                    )
                elif onerror is False:
                    pass
                else:
                    onerror(FileExistsError(
                        errno.EEXIST, 
                        f"remote path {remote_path_attr['path']!r} already exists"), 
                    )
                return
            if isdir:
                if remote_path_attr is None:
                    yield from self.upload_tree(
                        entry, 
                        [name], 
                        pid=pid, 
                        no_root=True, 
                        overwrite=overwrite, 
                        remove_done=remove_done, 
                        onerror=onerror, 
                    )
                else:
                    yield from self.upload_tree(
                        entry, 
                        remote_path_attr, 
                        no_root=True, 
                        overwrite=overwrite, 
                        remove_done=remove_done, 
                        onerror=onerror, 
                    )
                if remove_done:
                    try:
                        rmdir(entry)
                    except OSError:
                        pass
            else:
                try:
                    if remote_path_attr is None:
                        yield self.upload(
                            entry, 
                            [name], 
                            pid=pid, 
                            overwrite=overwrite, 
                            remove_done=remove_done, 
                        )
                    else:
                        yield self.upload(
                            entry, 
                            remote_path_attr, 
                            overwrite=overwrite, 
                            remove_done=remove_done, 
                        )
                except OSError as e:
                    if onerror is True:
                        raise e
                    elif onerror is False:
                        pass
                    else:
                        onerror(e)

    unlink = remove

    def write_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        pid: None | int = None, 
    ) -> AttrDict:
        "向文件写入二进制数据，如果文件已存在则替换"
        return self.upload(data, id_or_path, pid=pid, overwrite=True)

    def write_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        text: str = "", 
        pid: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> AttrDict:
        "向文件写入文本数据，如果文件已存在则替换"
        bio = BytesIO()
        if text:
            if encoding is None:
                encoding = "utf-8"
            tio = TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)
            tio.write(text)
            tio.flush()
            bio.seek(0)
        return self.write_bytes(id_or_path, data=bio, pid=pid)

    cp = copy
    mv = move
    rm = remove

