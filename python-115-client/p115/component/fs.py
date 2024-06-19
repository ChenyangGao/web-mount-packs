#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Path", "P115FileSystem"]

import errno

from collections import deque, ChainMap
from collections.abc import (
    AsyncIterator, Awaitable, Callable, Iterable, Iterator, Mapping, MutableMapping, Sequence, 
)
from copy import deepcopy
from datetime import datetime
from functools import partial
from io import BytesIO, TextIOWrapper
from itertools import accumulate, islice
from json import JSONDecodeError
from os import (
    path as ospath, fsdecode, fspath, makedirs, remove, rmdir, scandir, 
    stat_result, PathLike
)
from pathlib import Path
from posixpath import join as joinpath, splitext
from shutil import SameFileError
from stat import S_IFDIR, S_IFREG
from typing import cast, overload, Literal, Self
from uuid import uuid4
from warnings import warn

from filewrap import Buffer, SupportsRead
from http_request import SupportsGeturl
from iterutils import run_gen_step
from posixpatht import (
    basename, commonpath, dirname, escape, joins, normpath, split, splits, 
    unescape, path_is_dir_form, 
)
from yarl import URL

from .client import check_response, P115Client, P115Url
from .fs_base import AttrDict, IDOrPathType, P115PathBase, P115FileSystemBase


def normalize_info(
    info: Mapping, 
    keep_raw: bool = False, 
    **extra_data, 
) -> AttrDict:
    if "fid" in info:
        fid = info["fid"]
        parent_id = info["cid"]
        is_directory = False
    else:
        fid = info["cid"]
        parent_id = info["pid"]
        is_directory = True
    info2 =  {
        "name": info["n"], 
        "is_directory": is_directory, 
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
    info2["ico"] = info.get("ico", "folder" if is_directory else "")
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
        onerror: None | bool | Callable[[OSError], bool] = True, 
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
        self.__dict__.update(self.fs.move(self, dst_path, pid=pid))
        return self

    def remove(self, /, recursive: bool = True) -> AttrDict:
        return self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> Self:
        self.__dict__.update(self.fs.rename(self, dst_path, pid=pid))
        return self

    def renames(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> Self:
        self.__dict__.update(self.fs.renames(self, dst_path, pid=pid))
        return self

    def replace(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
    ) -> Self:
        self.__dict__.update(self.fs.replace(self, dst_path, pid=pid))
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
    attr_cache: None | MutableMapping[int, dict]
    path_to_id: None | MutableMapping[str, int]
    get_version: None | Callable
    path_class = P115Path

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        password: str = "", 
        attr_cache: None | MutableMapping[int, dict] = None, 
        path_to_id: None | MutableMapping[str, int] = None, 
        get_version: None | Callable = lambda attr: attr.get("mtime", 0), 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        super().__init__(client, request, async_request)
        if attr_cache is not None:
            attr_cache = {}
        if type(path_to_id) is dict:
            path_to_id["/"] = 0
        elif path_to_id is not None:
            path_to_id = ChainMap(path_to_id, {"/": 0})
        self.__dict__.update(
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

    @property
    def password(self, /) -> str:
        return self.__dict__["password"]

    @password.setter
    def password(self, /, password: str = ""):
        self.__dict__["password"] = password

    @overload
    def fs_mkdir(
        self, 
        name: str, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        name: str, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_mkdir(
        self, 
        name: str, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_mkdir(
                {"cname": name, "pid": pid}, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_mkdir(
                {"cname": name, "pid": pid}, 
                request=self.request, 
            ))

    @overload
    def fs_copy(
        self, 
        id: int, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        id: int, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_copy(
        self, 
        id: int, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_copy(
                id, 
                pid, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_copy(
                id, 
                pid, 
                request=self.request, 
            ))

    @overload
    def fs_delete(
        self, 
        id: int, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_delete(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_delete(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_delete(
                id, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_delete(
                id, 
                request=self.request, 
            ))

    @overload
    def fs_move(
        self, 
        id: int, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        id: int, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_move(
        self, 
        id: int, 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_move(
                id, 
                pid, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_move(
                id, 
                pid, 
                request=self.request, 
            ))

    @overload
    def fs_rename(
        self, 
        id: int, 
        name: str, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        id: int, 
        name: str, 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_rename(
        self, 
        id: int, 
        name: str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_rename(
                id, 
                name, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_rename(
                id, 
                name, 
                request=self.request, 
            ))

    @overload
    def fs_batch_copy(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_batch_copy(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_batch_copy(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_batch_copy(
                payload, 
                pid=pid, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_batch_copy(
                payload, 
                pid=pid, 
                request=self.request, 
            ))

    @overload
    def fs_batch_delete(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_batch_delete(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_batch_delete(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_batch_delete(
                payload, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_batch_delete(
                payload, 
                request=self.request, 
            ))

    @overload
    def fs_batch_move(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_batch_move(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_batch_move(
        self, 
        payload: dict | Iterable[int | str], 
        /, 
        pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_batch_move(
                payload, 
                pid=pid, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_batch_move(
                payload, 
                pid=pid, 
                request=self.request, 
            ))

    @overload
    def fs_batch_rename(
        self, 
        payload: dict | Iterable[tuple[int | str, str]], 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_batch_rename(
        self, 
        payload: dict | Iterable[tuple[int | str, str]], 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_batch_rename(
        self, 
        payload: dict | Iterable[tuple[int | str, str]], 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_batch_rename(
                payload, 
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_batch_rename(
                payload, 
                request=self.request, 
            ))

    @overload
    def fs_info(
        self, 
        id: int, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_info(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_info(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        def gen_step():
            resp = yield partial(
                self.client.fs_info, 
                {"file_id": id}, 
                request=self.async_request, 
                async_=async_, 
            )
            if resp["state"]:
                return resp
            match resp["code"]:
                # {'state': False, 'code': 20018, 'message': '文件不存在或已删除。'}
                # {'state': False, 'code': 800001, 'message': '目录不存在。'}
                case 20018 | 800001:
                    raise FileNotFoundError(errno.ENOENT, resp)
                # {'state': False, 'code': 990002, 'message': '参数错误。'}
                case 990002:
                    raise OSError(errno.EINVAL, resp)
                case _:
                    raise OSError(errno.EIO, resp)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_files(
        self, 
        payload: None | int | dict = None, 
        /, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_files(
        self, 
        payload: None | int | dict = None, 
        /, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_files(
        self, 
        payload: None | int | dict = None, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if payload is None:
            id = self.id
            payload = {"cid": id}
        elif isinstance(payload, int):
            id = payload
            payload = {"cid": id}
        else:
            id = int(payload["cid"])
        if async_:
            async def check():
                resp = await self.client.fs_files(
                    payload, 
                    request=self.async_request, 
                    async_=True, 
                )
                result = check_response(resp)
                if int(result["path"][-1]["cid"]) != id:
                    raise NotADirectoryError(errno.ENOTDIR, f"{id!r} is not a directory")
                return result
            return check()
        else:
            resp = self.client.fs_files(
                payload, 
                request=self.request, 
            )
            result = check_response(resp)
            if int(result["path"][-1]["cid"]) != id:
                raise NotADirectoryError(errno.ENOTDIR, f"{id!r} is not a directory")
            return result

    @overload
    def fs_search(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def fs_search(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def fs_search(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if isinstance(payload, str):
            payload = {"cid": self.id, "search_value": payload}
        if async_:
            return self.client.fs_search(
                payload, 
                request=self.async_request, 
                async_=True, 
            )
        else:
            return self.client.fs_search(
                payload, 
                request=self.request, 
            )

    @overload
    def fs_upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        name: str, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def fs_upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        name: str, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[AttrDict]:
        ...
    def fs_upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        name: str, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        if pid is None:
            pid = self.id
        def gen_step():
            nonlocal name
            resp = yield partial(
                self.client.upload_file, 
                file, 
                filename=name, 
                pid=pid, 
                request=self.async_request, 
                async_=async_, 
            )
            data = resp["data"]
            if "file_id" in data:
                file_id = int(data["file_id"])
                try:
                    return (yield partial(self._attr, file_id, async_=async_))
                except FileNotFoundError:
                    yield partial(self.fs_files, {"cid": pid, "limit": 1}, async_=async_)
                    return (yield partial(self._attr, file_id, async_=async_))
            else:
                name = data["file_name"]
                try:
                    return (yield partial(
                        self._attr_path, 
                        [name], 
                        pid=pid, 
                        async_=async_, 
                    ))
                except FileNotFoundError:
                    yield partial(self.fs_files, {"cid": pid, "limit": 1}, async_=async_)
                    return (yield partial(
                        self._attr_path, 
                        [name], 
                        pid=pid, 
                        async_=async_, 
                    ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def space_summury(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def space_summury(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[dict]:
        ...
    def space_summury(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Awaitable[dict]:
        if async_:
            return check_response(self.client.fs_space_summury(
                request=self.async_request, 
                async_=True, 
            ))
        else:
            return check_response(self.client.fs_space_summury(
                request=self.request, 
            ))

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
            if path_to_id:
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
                        is_directory = subattr["is_directory"]
                        if path_to_id:
                            pop_path(subattr["path"] + "/"[:is_directory])
                        if is_directory:
                            put(subid)
            if path_to_id:
                dirname = attr["path"] + "/"
                pop_path(dirname)
                for k in tuple(k for k in path_to_id if startswith(k, dirname)):
                    pop_path(k)

    def _update_cache_path(
        self, 
        attr: dict, 
        new_attr: dict, 
        /, 
    ):
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
            if path_to_id:
                def pop_path(path):
                    try:
                        del path_to_id[path]
                    except:
                        pass
            startswith = str.startswith
            old_path = attr["path"] + "/"
            new_path = new_attr["path"] + "/"
            if path_to_id:
                pop_path(old_path)
            if path_to_id is not None:
                path_to_id[new_path] = id
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
                        is_directory = subattr["is_directory"]
                        subpath = subattr["path"]
                        if startswith(subpath, old_path):
                            new_subpath = subattr["path"] = new_path + subpath[len_old_path:]
                            if path_to_id:
                                pop_path(subpath + "/"[:is_directory])
                            if path_to_id is not None:
                                path_to_id[new_subpath + "/"[:is_directory]] = subid
                        if subattr["is_directory"]:
                            put(subid)
            if path_to_id:
                for k in tuple(k for k in path_to_id if startswith(k, old_path)):
                    pop_path(k)

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
    ) -> Awaitable[AttrDict]:
        ...
    def _attr(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        def gen_step():
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
                    "ancestors": [{"name": "", "id": 0, "parent_id": 0, "is_directory": True}], 
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
                info = yield partial(self.fs_info, id, async_=async_)
            except FileNotFoundError as e:
                raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}") from e
            data = info["data"][0]
            attr = normalize_info(data, fs=self)
            pid = attr["parent_id"]
            old_path = ""
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
                    old_path = attr_old["path"]
                    if version != attrs.get("version"):
                        attrs.pop("version", None)
                    attr_old.update(attr)
                    attr = attr_old
            if "path" not in attr:
                if pid:
                    ancestors = attr["ancestors"] = yield partial(self._dir_get_ancestors, pid, async_=async_)
                    ancestors.append({
                        "name": attr["name"], 
                        "id": attr["id"], 
                        "parent_id": attr["parent_id"], 
                        "is_directory": attr["is_directory"], 
                    })
                    path = attr["path"] = joins([a["name"] for a in ancestors])
                else:
                    attr["ancestors"] = [{
                        "name": attr["name"], 
                        "id": attr["id"], 
                        "parent_id": attr["parent_id"], 
                        "is_directory": attr["is_directory"], 
                    }]
                    path = attr["path"] = "/" + escape(attr["name"])
                path_to_id = self.path_to_id
                if path_to_id is not None:
                    is_directory = attr["is_directory"]
                    path_to_id[path + "/"[:is_directory]] = id
                    if old_path and old_path != path:
                        try:
                            del path_to_id[old_path + "/"[:is_directory]]
                        except LookupError:
                            pass
            return attr
        return run_gen_step(gen_step, async_=async_)

    @overload
    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
        force_directory: bool = False, 
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
        force_directory: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[AttrDict]:
        ...
    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: None | int = None, 
        force_directory: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        def gen_step():
            nonlocal path, pid, force_directory

            if pid is None:
                pid = self.id
            if isinstance(path, PathLike):
                path = fspath(path)
            if not path or path == ".":
                return (yield partial(self._attr, pid, async_=async_))
            parents = 0
            if isinstance(path, str):
                if not force_directory:
                    force_directory = path_is_dir_form(path)
                patht, parents = splits(path)
                if not (patht or parents):
                    return (yield partial(self._attr, pid, async_=async_))
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
                ancestors = yield partial(self._dir_get_ancestors, pid, async_=async_)
                if parents:
                    if parents >= len(ancestors):
                        pid = 0
                    else:
                        pid = cast(int, ancestors[-parents]["parent_id"])
                        ancestor_patht = ["", *(a["name"] for a in ancestors[1:-parents])]
                else:
                    ancestor_patht = ["", *(a["name"] for a in ancestors[1:])]
            if not patht:
                return (yield partial(self._attr, pid, async_=async_))

            if pid == 0:
                dirname = ""
                ancestors_paths: list[str] = [(dirname := f"{dirname}/{escape(name)}") for name in patht[1:]]
                dirname = ""
                ancestors_paths2: list[str] = [(dirname := f"{dirname}/{name}") for name in patht[1:]]
                ancestors_with_slashes = tuple(accumulate("/" in name for name in patht[1:]))
            else:
                dirname = joins(ancestor_patht)
                ancestors_paths = [(dirname := f"{dirname}/{escape(name)}") for name in patht]
                dirname = "/".join(ancestor_patht)
                ancestors_paths2 = [(dirname := f"{dirname}/{name}") for name in patht]
                ancestors_with_slashes = tuple(accumulate(
                    ("/" in name for name in patht), 
                    initial=sum("/" in name for name in patht[:len(ancestor_patht)]), # type: ignore
                ))[1:]

            path_to_id = self.path_to_id
            if path_to_id:
                fullpath = ancestors_paths[-1]
                if not force_directory and (id := path_to_id.get(fullpath)):
                    try:
                        attr = yield partial(self._attr, id, async_=async_)
                        if attr["path"] == fullpath:
                            return attr
                        else:
                            del path_to_id[fullpath]
                    except FileNotFoundError:
                        pass
                if (id := path_to_id.get(fullpath + "/")):
                    try:
                        attr = yield partial(self._attr, id, async_=async_)
                        if attr["path"] == fullpath:
                            return attr
                        else:
                            del path_to_id[fullpath + "/"]
                    except FileNotFoundError:
                        pass

            def get_dir_id(path: str):
                result = yield partial(self.client.fs_files_getid, path, async_=async_)
                id = int(result["id"])
                if id == 0:
                    raise FileNotFoundError(errno.ENOENT, f"directory {path!r} does not exist")
                if path_to_id is not None:
                    path_to_id[path + "/"] = id
                return id

            if not ancestors_with_slashes[-1]:
                try:
                    id = yield from get_dir_id(ancestors_paths2[-1])
                    return (yield partial(self._attr, id, async_=async_))
                except FileNotFoundError:
                    if force_directory:
                        raise

            parent: int | AttrDict
            for i in reversed(range(len(ancestors_paths)-1)):
                if path_to_id and (id := path_to_id.get((dirname := ancestors_paths[i]) + "/")):
                    try:
                        parent = cast(AttrDict, (yield partial(self._attr, id, async_=async_)))
                        if parent["path"] == dirname:
                            i += 1
                            break
                        else:
                            del path_to_id[dirname]
                    except FileNotFoundError:
                        pass
                elif not ancestors_with_slashes[i]:
                    parent = yield from get_dir_id(ancestors_paths2[i])
                    i += 1
                    break
            else:
                i = 0
                parent = pid

            if pid == 0:
                i += 1

            last_idx = len(patht) - 1
            if async_:
                for i, name in enumerate(patht[i:], i):
                    async def step():
                        nonlocal attr, parent
                        async for attr in self.iterdir(parent, async_=True):
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
                    yield step
            else:
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
        return run_gen_step(gen_step, async_=async_)

    @overload
    def _dir_get_ancestors(
        self, 
        id: int, 
        /, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def _dir_get_ancestors(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
    ) -> Awaitable[list[dict]]:
        ...
    def _dir_get_ancestors(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Awaitable[list[dict]]:
        def gen_step():
            ls = [{"name": "", "id": 0, "parent_id": 0, "is_directory": True}]
            if id:
                resp = yield partial(self.fs_files, {"cid": id, "limit": 1}, async_=async_)
                ls.extend({
                    "name": p["name"], 
                    "id": int(p["cid"]), 
                    "parent_id": int(p["pid"]), 
                    "is_directory": True, 
                } for p in resp["path"][1:])
            return ls
        return run_gen_step(gen_step, async_=async_)

    @overload
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: bool = True, 
        force_directory: bool = False, 
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
        refresh: bool = True, 
        force_directory: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[AttrDict]:
        ...
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: bool = True, 
        force_directory: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        "获取属性"
        def gen_step():
            path_class = type(self).path_class
            if isinstance(id_or_path, path_class):
                attr = id_or_path.__dict__
                if refresh:
                    attr = yield partial(self._attr, attr["id"], async_=async_)
            elif isinstance(id_or_path, AttrDict):
                attr = id_or_path
                if refresh:
                    attr = yield partial(self._attr, attr["id"], async_=async_)
            elif isinstance(id_or_path, int):
                attr = yield partial(self._attr, id_or_path, async_=async_)
            else:
                return (yield partial(
                    self._attr_path, 
                    id_or_path, 
                    pid=pid, 
                    force_directory=force_directory, 
                    async_=async_, 
                ))
            if force_directory and not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"{attr['id']} (id={attr['id']}) is not directory"
                )
            return attr
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
        refresh: bool = False, 
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
        refresh: bool = False, 
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
        refresh: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **payload, 
    ) -> Iterator[AttrDict] | AsyncIterator[AttrDict]:
        """迭代获取目录内直属的文件或目录的信息
        payload:
            - asc: 0 | 1 = <default> # 是否升序排列
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1
            - custom_order: int | str = <default>
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - format: str = "json"
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - natsort: 0 | 1 = <default>
            - o: str = <default>
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
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
        def normalize_attr(attr, ancestors, dirname, /, **extra):
            attr = normalize_info(attr, **extra)
            is_directory = attr["is_directory"]
            attr["ancestors"] = [*ancestors, {
                "id": attr["id"], 
                "parent_id": attr["parent_id"], 
                "name": attr["name"], 
                "is_directory": attr["is_directory"], 
            }]
            path = attr["path"] = dirname + escape(attr["name"])
            if path_to_id is not None:
                path_to_id[path + "/"[:is_directory]] = attr["id"]
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
                        if path_to_id and path != old_attr["path"]:
                            try:
                                del path_to_id[old_attr["path"] + "/"[:is_directory]]
                            except LookupError:
                                pass
                        old_attr.update(attr)
            return attr

        path_to_id = self.path_to_id
        attr_cache = self.attr_cache
        get_version = self.get_version
        if page_size <= 0:
            page_size = 1_000

        if async_:
            async def request():
                nonlocal start, stop
                if stop is not None and (start >= 0 and stop >= 0 or start < 0 and stop < 0) and start >= stop:
                    return
                version = None
                if attr_cache is None and isinstance(id_or_path, int):
                    id = id_or_path
                else:
                    attr = None
                    path_class = type(self).path_class
                    if not refresh:
                        if isinstance(id_or_path, AttrDict):
                            attr = id_or_path
                        elif isinstance(id_or_path, path_class):
                            attr = id_or_path.__dict__
                    if attr is None:
                        if isinstance(id_or_path, int):
                            attr = await self._attr(id_or_path, async_=True)
                        elif isinstance(id_or_path, (AttrDict, path_class)):
                            attr = await self._attr(id_or_path["id"], async_=True)
                        else:
                            attr = await self._attr_path(
                                id_or_path, 
                                pid=pid, 
                                force_directory=True, 
                                async_=True, 
                            )
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
                    async def iterdir(fetch_all: bool = True) -> AsyncIterator[AttrDict]:
                        nonlocal start, stop
                        get_files = self.fs_files
                        if fetch_all:
                            payload["offset"] = 0
                        else:
                            count = -1
                            if start < 0:
                                count = await self.dirlen(id, async_=True)
                                start += count
                                if start < 0:
                                    start = 0
                            elif start >= 100:
                                count = await self.dirlen(id, async_=True)
                                if start >= count:
                                    return
                            if stop is not None:
                                if stop < 0:
                                    if count < 0:
                                        count = await self.dirlen(id, async_=True)
                                    stop += count
                                if start >= stop or stop <= 0:
                                    return
                                total = stop - start
                            payload["offset"] = start
                            if stop is not None:
                                if total < page_size:
                                    payload["limit"] = total
                            set_order_payload = {}
                            if "o" in payload:
                                set_order_payload["user_order"] = payload["o"]
                            if "asc" in payload:
                                set_order_payload["user_asc"] = payload["asc"]
                            if set_order_payload:
                                set_order_payload["file_id"] = id
                                if "fc_mix" in payload:
                                    set_order_payload["fc_mix"] = payload["fc_mix"]
                                await self.client.fs_files_order(
                                    set_order_payload, 
                                    request=self.async_request, 
                                    async_=True, 
                                )
                        resp = await get_files(payload, async_=True)
                        ancestors = [{"name": "", "id": 0, "parent_id": 0, "is_directory": True}]
                        ancestors.extend(
                            {
                                "name": p["name"], 
                                "id": int(p["cid"]), 
                                "parent_id": int(p["pid"]), 
                                "is_directory": True, 
                            } for p in resp["path"][1:]
                        )
                        if len(ancestors) == 1:
                            dirname = "/"
                        else:
                            dirname = joins([cast(str, a["name"]) for a in ancestors]) + "/"
                        if path_to_id is not None:
                            path_to_id[dirname] = id
                        count = resp["count"]
                        if fetch_all:
                            total = count
                        elif start >= count:
                            return
                        elif stop is None or stop > count:
                            total = count - start
                        for attr in resp["data"]:
                            yield normalize_attr(attr, ancestors, dirname, fs=self)
                        if total <= page_size:
                            return
                        for _ in range((total - 1) // page_size):
                            payload["offset"] += page_size
                            resp = await get_files(payload, async_=True)
                            if resp["count"] != count:
                                raise RuntimeError(f"{id} detected count changes during iteration")
                            for attr in resp["data"]:
                                yield normalize_attr(attr, ancestors, dirname, fs=self)
                    if attr_cache is None:
                        async for attr in iterdir(False):
                            yield attr
                        return
                    else:
                        children = {a["id"]: a async for a in iterdir()}
                        attrs = attr_cache[id] = {"version": version, "attr": attr, "children": children}
                else:
                    children = pid_attrs["children"]
                count = len(children)
                if start is None:
                    start = 0
                elif start < 0:
                    start += count
                    if start < 0:
                        start = 0
                if stop is None:
                    stop = count
                elif stop < 0:
                    stop += count
                if start >= stop or stop <= 0 or start >= count:
                    return
                match payload.get("o"):
                    case "file_name":
                        key = lambda attr: attr["name"]
                    case "file_size":
                        key = lambda attr: attr.get("size") or 0
                    case "file_type":
                        key = lambda attr: attr.get("ico", "")
                    case "user_utime":
                        key = lambda attr: attr["utime"]
                    case "user_ptime":
                        key = lambda attr: attr["ptime"]
                    case "user_otime":
                        key = lambda attr: attr["open_time"]
                    case _:
                        for attr in islice(children.values(), start, stop):
                            yield attr
                        return
                for attr in sorted(
                    children.values(), 
                    key=key, 
                    reverse=payload.get("asc", True), 
                )[start:stop]:
                    yield attr
            return request()
        else:
            if stop is not None and (start >= 0 and stop >= 0 or start < 0 and stop < 0) and start >= stop:
                return iter(())
            version = None
            if attr_cache is None and isinstance(id_or_path, int):
                id = id_or_path
            else:
                attr = None
                path_class = type(self).path_class
                if not refresh:
                    if isinstance(id_or_path, AttrDict):
                        attr = id_or_path
                    elif isinstance(id_or_path, path_class):
                        attr = id_or_path.__dict__
                if attr is None:
                    if isinstance(id_or_path, int):
                        attr = self._attr(id_or_path)
                    elif isinstance(id_or_path, (AttrDict, path_class)):
                        attr = self._attr(id_or_path["id"])
                    else:
                        attr = self._attr_path(id_or_path, pid=pid, force_directory=True)
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
                def iterdir(fetch_all: bool = True) -> Iterator[AttrDict]:
                    nonlocal start, stop
                    get_files = self.fs_files
                    if fetch_all:
                        payload["offset"] = 0
                    else:
                        count = -1
                        if start < 0:
                            count = self.dirlen(id)
                            start += count
                            if start < 0:
                                start = 0
                        elif start >= 100:
                            count = self.dirlen(id)
                            if start >= count:
                                return
                        if stop is not None:
                            if stop < 0:
                                if count < 0:
                                    count = self.dirlen(id)
                                stop += count
                            if start >= stop or stop <= 0:
                                return
                            total = stop - start
                        payload["offset"] = start
                        if stop is not None:
                            if total < page_size:
                                payload["limit"] = total
                        set_order_payload = {}
                        if "o" in payload:
                            set_order_payload["user_order"] = payload["o"]
                        if "asc" in payload:
                            set_order_payload["user_asc"] = payload["asc"]
                        if set_order_payload:
                            set_order_payload["file_id"] = id
                            if "fc_mix" in payload:
                                set_order_payload["fc_mix"] = payload["fc_mix"]
                            self.client.fs_files_order(
                                set_order_payload, 
                                request=self.request, 
                            )
                    resp = get_files(payload)
                    ancestors = [{"name": "", "id": 0, "parent_id": 0, "is_directory": True}]
                    ancestors.extend(
                        {
                            "name": p["name"], 
                            "id": int(p["cid"]), 
                            "parent_id": int(p["pid"]), 
                            "is_directory": True, 
                        } for p in resp["path"][1:]
                    )
                    if len(ancestors) == 1:
                        dirname = "/"
                    else:
                        dirname = joins([cast(str, a["name"]) for a in ancestors]) + "/"
                    if path_to_id is not None:
                        path_to_id[dirname] = id
                    count = resp["count"]
                    if fetch_all:
                        total = count
                    elif start >= count:
                        return
                    elif stop is None or stop > count:
                        total = count - start
                    for attr in resp["data"]:
                        yield normalize_attr(attr, ancestors, dirname, fs=self)
                    if total <= page_size:
                        return
                    for _ in range((total - 1) // page_size):
                        payload["offset"] += page_size
                        resp = get_files(payload)
                        if resp["count"] != count:
                            raise RuntimeError(f"{id} detected count changes during iteration")
                        for attr in resp["data"]:
                            yield normalize_attr(attr, ancestors, dirname, fs=self)
                if attr_cache is None:
                    return iterdir(False)
                else:
                    children = {a["id"]: a for a in iterdir()}
                    attrs = attr_cache[id] = {"version": version, "attr": attr, "children": children}
            else:
                children = pid_attrs["children"]
            count = len(children)
            if start is None:
                start = 0
            elif start < 0:
                start += count
                if start < 0:
                    start = 0
            if stop is None:
                stop = count
            elif stop < 0:
                stop += count
            if start >= stop or stop <= 0 or start >= count:
                return iter(())
            match payload.get("o"):
                case "file_name":
                    key = lambda attr: attr["name"]
                case "file_size":
                    key = lambda attr: attr.get("size") or 0
                case "file_type":
                    key = lambda attr: attr.get("ico", "")
                case "user_utime":
                    key = lambda attr: attr["utime"]
                case "user_ptime":
                    key = lambda attr: attr["ptime"]
                case "user_otime":
                    key = lambda attr: attr["open_time"]
                case _:
                    return islice(children.values(), start, stop)
            return iter(sorted(
                children.values(), key=key, reverse=payload.get("asc", True), 
            )[start:stop])

    # TODO: 下面这些也需要添加异步

    def copy(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        overwrite: bool = False, 
        onerror: None | bool | Callable[[OSError], bool] = True, 
        recursive: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | AttrDict:
        "复制文件"
        try:
            src_attr = self.attr(src_path, pid=pid)
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
                dst_attr = self.attr(dst_path, pid=pid)
            except FileNotFoundError:
                if isinstance(dst_path, int):
                    raise

                dst_patht = self.get_patht(dst_path, pid=pid)
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
                    dst_parent = self.makedirs(dst_patht[:-1])
                    dst_pid = dst_parent["id"]
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
                    filesha1=src_attr["sha1"], 
                    read_range_bytes_or_hash=lambda rng: self.read_bytes_range(src_id, bytes_range=rng), 
                    pid=dst_pid, 
                    request=self.request, 
                )["data"]["file_name"]
                return self.attr([dst_name], pid=dst_pid)
            elif src_name == dst_name:
                self.fs_copy(src_id, dst_pid)
                return self.attr([dst_name], pid=dst_pid)
            else:
                tempdir_id = int(self.fs_mkdir(str(uuid4()))["id"])
                try:
                    self.fs_copy(src_id, tempdir_id)
                    dst_id = self.attr([src_name], pid=tempdir_id)["id"]
                    resp = self.fs_rename(dst_id, dst_name)
                    if resp["data"]:
                        dst_name = resp["data"][str(dst_id)]
                    self.fs_move(dst_id, pid=dst_pid)
                finally:
                    self.fs_delete(tempdir_id)
                return self.attr(dst_id)
        except OSError as e:
            if onerror is True:
                raise
            elif onerror is False or onerror is None:
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
        onerror: None | bool | Callable[[OSError], bool] = True, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> None | AttrDict:
        "复制路径"
        try:
            src_attr = self.attr(src_path, pid=pid)
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
                dst_attr = self.attr(dst_path, pid=pid)
            except FileNotFoundError:
                if isinstance(dst_path, int):
                    raise
                dst_patht = self.get_patht(dst_path, pid=pid)
                if len(dst_patht) == 1:
                    dst_id = 0
                    dst_name = src_name
                else:
                    dst_parent = self.makedirs(dst_patht[:-1], exist_ok=True)
                    dst_id = dst_parent["id"]
                    dst_name = dst_patht[-1]
                try:
                    if src_name == dst_name:
                        self.fs_copy(src_id, pid=dst_id)
                        return self.attr([dst_name], pid=dst_id)
                except (OSError, JSONDecodeError):
                    pass
                dst_attr = self.makedirs([dst_name], pid=dst_id, exist_ok=True)
                dst_id = dst_parent["id"]
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
            elif onerror is False or onerror is None:
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

    @overload
    def desc(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        desc: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def desc(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        desc: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[str]:
        ...
    def desc(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        desc: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Awaitable[str]:
        """目录的描述文本（支持 HTML）
        :param desc: 如果为 None，返回描述文本；否则，设置文本
        """
        def gen_step():
            fid = yield partial(self.get_id, id_or_path, pid=pid, async_=async_)
            if fid == 0:
                return ""
            if desc is None:
                return check_response((yield partial(
                    self.client.fs_desc_get, 
                    fid, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))["desc"]
            else:
                return check_response((yield partial(
                    self.client.fs_desc, 
                    fid, 
                    desc, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))["file_description"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[int]:
        ...
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int | Awaitable[int]:
        "文件夹中的项目数（直属的文件和目录计数）"
        def gen_step():
            id = yield partial(self.get_id, id_or_path, pid=pid, async_=async_)
            resp = yield partial(
                self.fs_files, 
                {"cid": id, "limit": 1}, 
                async_=async_, 
            )
            return resp["count"]
        return run_gen_step(gen_step, async_=async_)

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
    ) -> Awaitable[list[dict]]:
        ...
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Awaitable[list[dict]]:
        "获取各个上级目录的少量信息（从根目录到当前目录）"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            return deepcopy(attr["ancestors"])
        return run_gen_step(gen_step, async_=async_)

    def get_id_from_pickcode(
        self, 
        /, 
        pickcode: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int:
        "由 pickcode 获取 id"
        if not pickcode:
            return 0
        return self.get_info_from_pickcode(pickcode)["id"]

    def get_info_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "由 pickcode 获取一些目录信息"
        return self.client.download_url(
            pickcode, 
            strict=False, 
            request=self.request, 
        ).__dict__

    def get_pickcode(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str:
        "获取 pickcode"
        return self.attr(id_or_path, pid=pid).get("pickcode", "")

    @overload
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> P115Url:
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
    ) -> Awaitable[P115Url]:
        ...
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> P115Url | Awaitable[P115Url]:
        "获取下载链接"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
            if attr["is_directory"]:
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"{attr['path']!r} (id={attr['id']!r}) is a directory", 
                )
            return (yield partial(
                self.client.download_url, 
                attr["pickcode"], 
                use_web_api=attr.get("violated", False) and attr["size"] < 1024 * 1024 * 115, 
                headers=headers, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_url_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> P115Url:
        ...
    @overload
    def get_url_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[P115Url]:
        ...
    def get_url_from_pickcode(
        self, 
        /, 
        pickcode: str, 
        use_web_api: bool = False, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> P115Url | Awaitable[P115Url]:
        "由 pickcode 获取下载链接"
        return self.client.download_url(
            pickcode, 
            use_web_api=use_web_api, 
            headers=headers, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        )

    # TODO: 如果超过 5 万个文件，则需要分批进入隐藏模式
    def hide(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        show: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool:
        "把路径隐藏或显示（如果隐藏，只能在隐藏模式中看到）"
        if show is None:
            return self.attr(id_or_path, pid=pid)["hidden"]
        else:
            fid = self.get_id(id_or_path, pid=pid)
            if fid == 0:
                return False
            hidden = not show
            check_response(self.client.fs_files_hidden(
                {"hidden": int(hidden), "fid[0]": fid}, 
                request=self.request, 
            ))
            return hidden

    @property
    def hidden_mode(self, /) -> bool:
        "是否进入隐藏模式"
        return self.client.user_setting(request=self.request)["data"]["show"] == "1"

    def hidden_switch(
        self, 
        /, 
        show: None | bool = None, 
        password: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ):
        "切换隐藏模式，如果需要进入隐藏模式，需要提供密码"
        if show is None:
            show = not self.hidden_mode
        check_response(self.client.fs_hidden_switch(
            {"show": int(show), "safe_pwd": password or self.password}, 
            request=self.request, 
        ))

    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool:
        "路径是否为空文件或空目录"
        attr: AttrDict | P115Path
        if isinstance(id_or_path, P115Path):
            attr = id_or_path
        else:
            try:
                attr = self.attr(id_or_path, pid=pid)
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
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[AttrDict]:
        "获取重复文件（不含当前这个）"
        if page_size <= 0:
            page_size = 1150
        payload = {
            "file_id": self.get_id(id_or_path, pid=pid), 
            "offset": 0, 
            "limit": page_size, 
            "format": "json", 
        }
        while True:
            data = check_response(self.client.fs_get_repeat(payload, request=self.request))["data"]
            yield from data
            if len(data) < page_size:
                break
            payload["offset"] += page_size # type: ignore

    def labels(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[dict]:
        "获取路径的标签"
        return self.attr(id_or_path, pid=pid)["labels"]

    def makedirs(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        exist_ok: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "创建目录，如果上级目录不存在，则会进行创建"
        if isinstance(path, int):
            attr = self.attr(path)
            if attr["is_directory"]:
                return attr
            raise NotADirectoryError(
                errno.ENOTDIR, 
                f"{attr['path']!r} (id={attr['id']}) is not a directory", 
            )
        path_class = type(self).path_class
        if isinstance(path, (AttrDict, path_class)):
            path = path["path"]
        path = cast(str | PathLike | Sequence[str], path)
        if isinstance(path, (str, PathLike)):
            patht, parents = splits(fspath(path))
        else:
            patht = [p for i, p in enumerate(path) if not i or p]
            parents = 0
        if pid is None:
            pid = self.id
        elif patht[0] == "":
            pid = 0
        if not patht:
            if parents:
                ancestors = self.get_ancestors(pid)
                idx = min(parents-1, len(ancestors))
                pid = cast(int, ancestors[-idx]["id"])
            return self._attr(pid)
        elif patht == [""]:
            return self._attr(0)
        exists = False
        for name in patht:
            try:
                attr = self._attr_path([name], pid=pid, force_directory=True)
            except FileNotFoundError:
                exists = False
                resp = self.fs_mkdir(name, pid=pid)
                pid = int(resp["cid"])
                attr = self._attr(pid)
            else:
                exists = True
                pid = cast(int, attr["id"])
        if not exist_ok and exists:
            raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) exists")
        return attr

    def mkdir(
        self, 
        path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "创建目录"
        if isinstance(path, int):
            attr = self.attr(path)
            if attr["is_directory"]:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"{attr['path']!r} (id={attr['id']}) already exists", 
                )
            raise NotADirectoryError(
                errno.ENOTDIR, 
                f"{attr['path']!r} (id={attr['id']}) is not a directory", 
            )
        path_class = type(self).path_class
        if isinstance(path, (AttrDict, path_class)):
            path = path["path"]
        path = cast(str | PathLike | Sequence[str], path)
        if isinstance(path, (str, PathLike)):
            patht, parents = splits(fspath(path))
        else:
            patht = [p for i, p in enumerate(path) if not i or p]
            parents = 0
        if not patht or patht == [""]:
            raise OSError(errno.EINVAL, f"invalid path: {path!r}")
        if pid is None:
            pid = self.id
        elif patht[0] == "":
            pid = 0
        if parents:
            ancestors = self.get_ancestors(pid)
            idx = min(parents-1, len(ancestors))
            pid = cast(int, ancestors[-idx]["id"])
        get_attr = self._attr_path
        for i, name in enumerate(patht, 1):
            try:
                attr = get_attr([name], pid=pid, force_directory=True)
            except FileNotFoundError:
                break
            else:
                pid = cast(int, attr["id"])
        else:
            raise FileExistsError(
                errno.EEXIST, 
                f"{path!r} (in {pid!r}) already exists", 
            )
        if i < len(patht):
            raise FileNotFoundError(
                errno.ENOENT, 
                f"{path!r} (in {pid!r}) missing superior directory", 
            )
        resp = self.fs_mkdir(name, pid=pid)
        return self.attr(int(resp["cid"]))

    def move(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "重命名路径，如果目标路径是目录，则移动到其中"
        try:
            dst_attr = self.attr(dst_path, pid=pid)
        except FileNotFoundError:
            return self.rename(src_path, dst_path, pid=pid)
        src_attr = self.attr(src_path, pid=pid)
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
    # TODO: 就算删除和还原执行返回成功，后台可能依然在执行，需要等待几秒钟，前一批完成再执行下一批
    #       {'state': False, 'error': '删除[...]操作尚未执行完成，请稍后再试！', 'errno': 990009, 'errtype': 'war'}
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        recursive: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "删除文件"
        attr = self.attr(id_or_path, pid=pid)
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
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "逐级往上尝试删除空目录"
        attr = self.attr(id_or_path, pid=pid, force_directory=True)
        id = attr["id"]
        delid = 0
        parent = attr
        get_files = self.fs_files
        while id:
            files = get_files({"cid": id, "limit": 1})
            if files["count"] > 1:
                break
            delid = id
            id = int(files["path"][-1]["pid"])
            parent = {
                "id": delid, 
                "parent_id": id, 
                "is_directory": True, 
                "path": "/" + joins([p["name"] for p in files["path"][1:]]), 
            }
        if delid:
            self.fs_delete(delid)
            self._clear_cache(parent)
        return attr

    def rename(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: None | int = None, 
        replace: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "重命名路径"
        src_attr = self.attr(src_path, pid=pid)
        src_id = src_attr["id"]
        src_path = src_attr["path"]
        src_patht = self.get_patht(src_path)
        try:
            dst_attr = self.attr(dst_path, pid=pid)
        except FileNotFoundError:
            dst_patht = self.get_patht(dst_path, pid=pid)
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
            dst_parent = self.makedirs(dst_patht[:-1], exist_ok=True)
            dst_pid = dst_parent["id"]
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
            url = self.get_url(src_id)
            client = self.client
            resp = client.upload_file_init(
                dst_name, 
                filesize=src_attr["size"], 
                filesha1=src_attr["sha1"], 
                pid=dst_pid, 
                read_range_bytes_or_hash=lambda rng: client.read_bytes_range(url, bytes_range=rng, request=self.request), 
                request=self.request, 
            )
            status = resp["status"]
            statuscode = resp.get("statuscode", 0)
            if status == 2 and statuscode == 0:
                pass
            elif status == 1 and statuscode == 0:
                warn(f"wrong sha1 {src_attr['sha1']!r} found, will attempt to upload directly: {src_attr!r}")
                resp = client.upload_file_sample(
                    client.open(url=url), 
                    dst_name, 
                    pid=dst_pid, 
                    request=self.request, 
                )
            else:
                raise OSError(resp)
            self.fs_delete(src_id)
            data = resp["data"]
            if "file_id" in data:
                return self.attr(int(data["file_id"]))
            else:
                dst_name = data["file_name"]
                return self.attr([dst_name], pid=dst_pid)
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
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "重命名路径，如果文件被移动到其它目录中，则尝试从原来的上级目录逐级往上删除空目录"
        attr = self.attr(src_path, pid=pid)
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
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "替换路径"
        return self.rename(src_path, dst_path, pid=pid, replace=True)

    def rmdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "删除空目录"
        attr = self.attr(id_or_path, pid=pid, force_directory=True)
        id = attr["id"]
        if id == 0:
            raise PermissionError(
                errno.EPERM, 
                "remove the root directory is not allowed", 
            )
        elif self.dirlen(id):
            raise OSError(
                errno.ENOTEMPTY, 
                f"directory is not empty: {attr['path']!r} (id={attr['id']!r})", 
            )
        self.fs_delete(id)
        self._clear_cache(attr) 
        return attr

    def rmtree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict:
        "删除路径"
        return self.remove(id_or_path, pid, recursive=True)

    @overload
    def score(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        score: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def score(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        score: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[int]:
        ...
    def score(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        score: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> int | Awaitable[int]:
        """路径的分数
        :param star: 如果为 None，返回分数；否则，设置分数
        """
        def gen_step():
            if score is None:
                attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
                return attr.get("score", 0)
            else:
                fid = yield partial(self.get_id, id_or_path, pid=pid, async_=async_)
                if fid == 0:
                    return 0
                yield self.client.fs_score(
                    fid, 
                    score, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )
                return score
        return run_gen_step(gen_step, async_=async_)

    @overload
    def search(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        page_size: int = 1_000, 
        *, 
        async_: Literal[False] = False, 
        **payload, 
    ) -> Iterator[P115Path]:
        ...
    @overload
    def search(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        page_size: int = 1_000, 
        *, 
        async_: Literal[True], 
        **payload, 
    ) -> AsyncIterator[P115Path]:
        ...
    def search(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        page_size: int = 1_000, 
        *, 
        async_: Literal[False, True] = False, 
        **payload, 
    ) -> Iterator[P115Path] | AsyncIterator[P115Path]:
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
        if async_:
            async def request():
                attr = await self.attr(id_or_path, pid=pid, async_=True)
                payload["cid"] = attr["id"]
                payload["limit"] = page_size
                offset = int(payload.setdefault("offset", 0))
                if offset < 0:
                    payload["offset"] = 0
                if not attr["is_directory"]:
                    payload.setdefault("search_value", attr["sha1"])
                search = self.fs_search
                while True:
                    resp = await search(payload, async_=True)
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
        else:
            def request():
                attr = self.attr(id_or_path, pid=pid)
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
        return request()

    @overload
    def star(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        star: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def star(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        star: None | bool = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[bool]:
        ...
    def star(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        star: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> bool | Awaitable[bool]:
        """路径的星标
        :param star: 如果为 None，返回星标是否已设置；如果为 True，设置星标；如果为 False，取消星标
        """
        def gen_step():
            if star is None:
                attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
                return attr.get("star", False)
            else:
                fid = yield partial(self.get_id, id_or_path, pid=pid, async_=async_)
                if fid == 0:
                    return False
                check_response((yield partial(
                    self.client.fs_star, 
                    fid, 
                    star, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )))
                return star
        return run_gen_step(gen_step, async_=async_)

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
    ) -> Awaitable[stat_result]:
        ...
    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> stat_result | Awaitable[stat_result]:
        "检查路径的属性，就像 `os.stat`"
        def gen_step():
            attr = yield partial(self.attr, id_or_path, pid=pid, async_=async_)
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
        return run_gen_step(gen_step, async_=async_)

    @overload
    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        is_dir: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        is_dir: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[AttrDict]:
        ...
    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        is_dir: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        """检查路径是否存在，当不存在时，如果 is_dir 是 False 时，则创建空文件，否则创建空目录
        """
        def gen_step():
            try:
                return (yield partial(self.attr, id_or_path, pid=pid, async_=async_))
            except FileNotFoundError:
                if isinstance(id_or_path, int):
                    raise ValueError(f"no such id: {id_or_path!r}")
                elif is_dir:
                    return (yield partial(self.mkdir, id_or_path, pid=pid, async_=async_))
                else:
                    return (yield partial(self.upload, b"", id_or_path, pid=pid, async_=async_))
        return run_gen_step(gen_step, async_=async_)

    # TODO: 增加功能，返回一个 Task 对象，可以获取上传进度，可随时取消
    # TODO: 因为文件名可以重复，因此确保上传成功后再删除
    @overload
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[AttrDict]:
        ...
    def upload(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        path: IDOrPathType = "", 
        pid: None | int = None, 
        overwrite: bool = False, 
        remove_done: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        "上传文件"
        def gen_step():
            nonlocal path, pid
            path_class = type(self).path_class
            unchecked = True
            name = ""
            if isinstance(path, int):
                attr = yield partial(self.attr, path, async_=async_)
            elif isinstance(path, AttrDict):
                attr = path
            elif isinstance(path, path_class):
                attr = path.__dict__
            elif isinstance(path, (str, PathLike)):
                path = normpath(fspath(path))
                if path == "/":
                    pid = 0
                elif not path:
                    pid = self.id if pid is None else pid
                else:
                    dirname, name = split(path)
                    if name == ".." or not name:
                        attr = yield partial(self.attr, path, pid=pid, async_=async_)
                        pid = attr["pid"]
                        name = ""
                    else:
                        dattr = yield partial(self.attr, dirname, pid=pid, async_=async_)
                        pid = dattr["id"]
                unchecked = False
            else:
                patht = [*path[:1], *(p for p in path[1:] if p)]
                if not patht:
                    pid = self.id if pid is None else pid
                elif patht == [""]:
                    pid = 0
                else:
                    *dirname_t, name = patht
                    dattr = yield partial(self.attr, dirname_t, pid=pid, async_=async_)
                    pid = dattr["id"]
                unchecked = False
            if unchecked:
                if attr["is_directory"]:
                    pid = attr["id"]
                elif overwrite:
                    try:
                        yield partial(self.remove, attr["id"], async_=async_)
                    except FileNotFoundError:
                        pass
                    pid = attr["parent_id"]
                    name = attr["name"]
                else:
                    raise FileExistsError(errno.EEXIST, f"remote path {attr['path']!r} (id={attr['id']}) already exists")
            resp = yield partial(self.fs_upload, file, name, pid=pid, async_=async_)
            if remove_done and isinstance(file, (str, PathLike)):
                try:
                    remove(file)
                except OSError:
                    pass
            return resp
        return run_gen_step(gen_step, async_=async_)

    # TODO: 支持异步
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
        onerror: None | bool | Callable[[OSError], bool] = True, 
    ) -> Iterator[AttrDict]:
        "上传到路径"
        remote_path_attr_map: None | dict[str, AttrDict] = None
        try:
            attr = self.attr(path, pid=pid)
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
                    elif onerror is False or onerror is None:
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
            elif onerror is False or onerror is None:
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
                elif onerror is False or onerror is None:
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
                    elif onerror is False or onerror is None:
                        pass
                    else:
                        onerror(e)

    unlink = remove

    @overload
    def write_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def write_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[AttrDict]:
        ...
    def write_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        data: Buffer | SupportsRead[Buffer] = b"", 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        "向文件写入二进制数据，如果文件已存在则替换"
        return self.upload(data, id_or_path, pid=pid, overwrite=True, async_=async_)

    @overload
    def write_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        text: str = "", 
        pid: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> AttrDict:
        ...
    @overload
    def write_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        text: str = "", 
        pid: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Awaitable[AttrDict]:
        ...
    def write_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        text: str = "", 
        pid: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> AttrDict | Awaitable[AttrDict]:
        "向文件写入文本数据，如果文件已存在则替换"
        bio = BytesIO()
        if text:
            tio = TextIOWrapper(
                bio, 
                encoding=encoding or "utf-8", 
                errors=errors, 
                newline=newline, 
            )
            tio.write(text)
            tio.flush()
            bio.seek(0)
        return self.write_bytes(id_or_path, data=bio, pid=pid, async_=async_)

    cp = copy
    mv = move
    rm = remove

