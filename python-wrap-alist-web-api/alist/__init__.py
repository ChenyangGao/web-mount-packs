#!/usr/bin/env python3
# encoding: utf-8

"""Python alist web API wrapper.

This is a web API wrapper works with the running "alist" server, and provide some methods, which refer to `os` and `shutil` modules.

- `Alist Web API official documentation <https://alist.nn.ci/guide/api/>` 
"""

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 8)
__all__ = ["AlistClient", "AlistPath", "AlistFileReader", "AlistFileSystem"]

import errno

from asyncio import run
from datetime import datetime
from functools import cached_property, update_wrapper
from inspect import isawaitable
from io import BytesIO, TextIOWrapper, UnsupportedOperation
from os import fspath, fstat, makedirs, scandir, path as os_path, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError
from typing import (
    cast, Callable, ItemsView, Iterable, Iterator, KeysView, Literal, Mapping, Optional, Protocol, 
    TypeVar, ValuesView
)
from types import MappingProxyType
from urllib.parse import quote
from uuid import uuid4
from warnings import filterwarnings, warn

from aiohttp import ClientSession
from requests import Session

from .util.file import HTTPFileReader
from .util.iter import posix_glob_translate_iter
from .util.property import funcproperty
from .util.urlopen import urlopen


filterwarnings("ignore", category=DeprecationWarning)

_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object: ...


class SupportsRead(Protocol[_T_co]):
    def read(self, __length: int = ...) -> _T_co: ...


def _check_response(fn, /):
    def wrapper(*args, **kwds):
        resp = fn(*args, **kwds)
        code = resp["code"]
        if 200 <= code < 300:
            return resp
        fargs = (fn, args, kwds)
        if code == 403:
            raise PermissionError(errno.EACCES, fargs, resp)
        elif code == 500:
            message = resp["message"]
            if message.endswith("object not found") or message.startswith("failed get storage: storage not found"):
                raise FileNotFoundError(errno.ENOENT, fargs, resp)
            elif resp["message"].endswith("not a folder"):
                raise NotADirectoryError(errno.ENOTDIR, fargs, resp)
            elif message.endswith("file exists"):
                raise FileExistsError(errno.EEXIS, fargs, resp)
            elif message.startswith("failed get "):
                raise PermissionError(errno.EPERM, fargs, resp)
        raise OSError(errno.EREMOTE, fargs, resp)
    return update_wrapper(wrapper, fn)


class AlistClient:
    """Alist client that encapsulates web APIs

    - `Alist Web API official documentation <https://alist.nn.ci/guide/api/>` 
    """
    def __init__(self, /, origin: str = "http://localhost:5244", username: str = "", password: str = ""):
        self._origin = origin.rstrip("/")
        self._username = username
        self._password = password
        self._session = Session()
        self._async_session = ClientSession(raise_for_status=True)
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.origin == other.origin

    def __hash__(self, /) -> int:
        return hash(self.origin)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self._origin!r}, username={self._username!r}, password='******')"

    def close(self, /):
        try:
            self._session.close()
        except:
            pass
        try:
            run(self._async_session.close())
        except:
            pass

    @property
    def origin(self, /) -> str:
        return self._origin

    @property
    def username(self, /):
        return self._username

    @property
    def password(self, /):
        return self._password

    @password.setter
    def password(self, value: str, /):
        self._password = value
        self.login()

    @property
    def session(self, /) -> Session:
        return self._session

    @property
    def async_session(self, /) -> ClientSession:
        return self._async_session

    def _request(
        self, 
        api: str, 
        /, 
        method: str = "POST", 
        parse: Callable | bool = True, 
        **request_kwds, 
    ):
        if not api.startswith("/"):
            api = "/" + api
        url = self._origin + api
        request_kwds["stream"] = True
        resp = self._session.request(method, url, **request_kwds)
        resp.raise_for_status()
        if callable(parse):
            with resp:
                return parse(resp)
        elif parse:
            with resp:
                content_type = resp.headers.get("Content-Type", "")
                if content_type.startswith("application/json"):
                    return resp.json()
                elif content_type.startswith("text/"):
                    return resp.text
                return resp.content
        return resp

    def _async_request(
        self, 
        api: str, 
        /, 
        method: str = "POST", 
        parse: Callable | bool = True, 
        **request_kwds, 
    ):
        if not api.startswith("/"):
            api = "/" + api
        url = self._origin + api
        request_kwds.pop("stream", None)
        req = self._async_session.request(method, url, **request_kwds)
        if callable(parse):
            async def request():
                async with req as resp:
                    ret = parse(resp)
                    if isawaitable(ret):
                        ret = await ret
                    return ret
            return request()
        elif parse:
            async def request():
                async with req as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    if content_type.startswith("application/json"):
                        return await resp.json()
                    elif content_type.startswith("text/"):
                        return await resp.text()
                    return await resp.read()
            return request()
        return req

    def request(
        self, 
        api: str, 
        /, 
        method: str = "POST", 
        parse: Callable | bool = True, 
        async_: bool = False, 
        **request_kwds, 
    ):
        return (self._async_request if async_ else self._request)(
            api, method, parse, **request_kwds)

    def login(
        self, 
        /, 
        username: str = "", 
        password: str = "", 
        **request_kwds, 
    ):
        if username:
            self._username = username
        else:
            username = self._username
        if password:
            self._password = password
        else:
            password = self._password
        if username:
            request_kwds["async_"] = False
            resp = self.auth_login(
                {"username": username, "password": password}, 
                **request_kwds, 
            )
            if not 200 <= resp["code"] < 300:
                raise PermissionError(errno.EACCES, resp)
            self._async_session.headers["Authorization"] = self._session.headers["Authorization"] = resp["data"]["token"]
        else:
            self._session.headers.pop("Authorization", None)
            self._async_session.headers.pop("Authorization", None)

    # [auth](https://alist.nn.ci/guide/api/auth.html)

    def auth_login(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-token获取"
        return self.request(
            "/api/auth/login", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def auth_login_hash(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-token获取hash"
        return self.request(
            "/api/auth/login/hash", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def auth_2fa_generate(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-生成2fa密钥"
        return self.request(
            "/api/auth/2fa/generate", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-生成2fa密钥"
        return self.request(
            "/api/auth/2fa/verify", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def auth_me(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#get-获取当前用户信息"
        return self.request(
            "/api/me", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    # [fs](https://alist.nn.ci/guide/api/fs.html)

    def fs_mkdir(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-新建文件夹"
        return self.request(
            "/api/fs/mkdir", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_rename(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-重命名文件"
        return self.request(
            "/api/fs/rename", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_form(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        remote_path: str, 
        as_task: bool = False, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#put-表单上传文件"
        headers = request_kwds.setdefault("headers", {})
        headers["File-Path"] = quote(remote_path)
        if as_task:
            headers["As-Task"] = "true"
        if hasattr(local_path_or_file, "read"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
        else:
            file = open(local_path_or_file, "rb")
        return self.request(
            "/api/fs/form", 
            "PUT", 
            files={"file": file}, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_list(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-列出文件目录"
        return self.request(
            "/api/fs/list", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_get(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-获取某个文件-目录信息"
        return self.request(
            "/api/fs/get", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_search(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-搜索文件或文件夹"
        return self.request(
            "/api/fs/search", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_dirs(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-获取目录"
        return self.request(
            "/api/fs/dirs", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_batch_rename(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-批量重命名"
        return self.request(
            "/api/fs/batch_rename", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_regex_rename(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-正则重命名"
        return self.request(
            "/api/fs/regex_rename", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_move(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-移动文件"
        return self.request(
            "/api/fs/move", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_recursive_move(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-聚合移动"
        return self.request(
            "/api/fs/recursive_move", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_copy(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-复制文件"
        return self.request(
            "/api/fs/copy", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_remove(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-删除文件或文件夹"
        return self.request(
            "/api/fs/remove", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_remove_empty_directory(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-删除空文件夹"
        return self.request(
            "/api/fs/remove_empty_directory", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_put(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        remote_path: str, 
        as_task: bool = False, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#put-流式上传文件"
        headers = request_kwds.setdefault("headers", {})
        headers["File-Path"] = quote(remote_path)
        if as_task:
            headers["As-Task"] = "true"
        if hasattr(local_path_or_file, "read"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
        else:
            file = open(local_path_or_file, "rb")
        return self.request(
            "/api/fs/put", 
            "PUT", 
            data=file, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_add_aria2(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-添加aria2下载"
        return self.request(
            "/api/fs/add_aria2", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def fs_add_qbit(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-添加qbittorrent下载"
        return self.request(
            "/api/fs/add_qbit", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    # [public](https://alist.nn.ci/guide/api/public.html)

    def public_ping(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> str:
        "https://alist.nn.ci/guide/api/public.html#get-ping检测"
        return self.request(
            "/ping", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    def public_settings(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/public.html#get-获取站点设置"
        return self.request(
            "/api/public/settings", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    # [admin](https://alist.nn.ci/guide/api/admin/)

    # [admin/user](https://alist.nn.ci/guide/api/admin/user.html)

    def admin_user_list(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#get-列出所有用户"
        return self.request(
            "/api/admin/user/list", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_user_get(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#get-列出某个用户"
        return self.request(
            "/api/admin/user/get", 
            "GET", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_user_create(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-新建用户"
        return self.request(
            "/api/admin/user/create", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_user_update(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-更新用户信息"
        return self.request(
            "/api/admin/user/update", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_user_cancel_2fa(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-取消某个用户的两步验证"
        return self.request(
            "/api/admin/user/cancel_2fa", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_user_delete(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-删除用户"
        return self.request(
            "/api/admin/user/delete", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_user_del_cache(
        self, 
        /, 
        username: str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-删除用户缓存"
        return self.request(
            "/api/admin/user/del_cache", 
            params={"username": username}, 
            async_=async_, 
            **request_kwds, 
        )

    # [admin/meta](https://alist.nn.ci/guide/api/admin/meta.html)

    def admin_meta_list(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#get-列出元信息"
        return self.request(
            "/api/admin/meta/list", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_meta_get(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#get-获取元信息"
        return self.request(
            "/api/admin/meta/get", 
            "GET", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_meta_create(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#post-新增元信息"
        return self.request(
            "/api/admin/meta/create", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_meta_update(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#post-更新元信息"
        return self.request(
            "/api/admin/meta/update", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_meta_delete(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#post-删除元信息"
        return self.request(
            "/api/admin/meta/delete", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    # [admin/driver](https://alist.nn.ci/guide/api/admin/driver.html)

    def admin_driver_list(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/driver.html#get-查询所有驱动配置模板列表"
        return self.request(
            "/api/admin/driver/list", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_driver_names(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/driver.html#get-列出驱动名列表"
        return self.request(
            "/api/admin/driver/names", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_driver_info(
        self, 
        /, 
        driver: str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/driver.html#get-列出特定驱动信息"
        return self.request(
            "/api/admin/driver/info", 
            "GET", 
            params={"driver": driver}, 
            async_=async_, 
            **request_kwds, 
        )

    # [admin/storage](https://alist.nn.ci/guide/api/admin/storage.html)

    def admin_storage_list(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#get-列出存储列表"
        return self.request(
            "/api/admin/storage/list", 
            "GET", 
            params={"page": page, "per_page": per_page}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_storage_enable(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-启用存储"
        return self.request(
            "/api/admin/storage/enable", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_storage_disable(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-禁用存储"
        return self.request(
            "/api/admin/storage/disable", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-新增存储"
        return self.request(
            "/api/admin/storage/create", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-更新存储"
        return self.request(
            "/api/admin/storage/update", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_storage_get(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#get-查询指定存储信息"
        return self.request(
            "/api/admin/storage/get", 
            "GET", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_storage_delete(
        self, 
        /, 
        id: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-删除指定存储"
        return self.request(
            "/api/admin/storage/delete", 
            params={"id": id}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_storage_load_all(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-重新加载所有存储"
        return self.request(
            "/api/admin/storage/load_all", 
            async_=async_, 
            **request_kwds, 
        )

    # [admin/setting](https://alist.nn.ci/guide/api/admin/setting.html)

    def admin_setting_list(
        self, 
        /, 
        group: int | str = "", 
        groups: int | str = "", 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#get-列出设置"
        return self.request(
            "/api/admin/setting/list", 
            "GET", 
            params={"group": group, "groups": groups}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_setting_get(
        self, 
        /, 
        key: str = "", 
        keys: str = "", 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#get-获取某项设置"
        return self.request(
            "/api/admin/setting/get", 
            "GET", 
            params={"key": key, "keys": keys}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_setting_save(
        self, 
        /, 
        payload: list[dict], 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-保存设置"
        return self.request(
            "/api/admin/setting/save", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_setting_delete(
        self, 
        /, 
        key: str = "", 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-删除设置"
        return self.request(
            "/api/admin/setting/delete", 
            params={"key": key}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_setting_reset_token(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-重置令牌"
        return self.request(
            "/api/admin/setting/reset_token", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_setting_set_aria2(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-设置aria2"
        return self.request(
            "/api/admin/setting/set_aria2", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_setting_set_qbit(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-设置qbittorrent"
        return self.request(
            "/api/admin/setting/set_qbit", 
            json=payload, 
            async_=async_, 
            **request_kwds, 
        )

    # [admin/task](https://alist.nn.ci/guide/api/admin/task.html)

    def admin_task_upload_done(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/upload/done", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_task_upload_undone(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/upload/undone", 
            "GET", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_task_upload_delete(
        self, 
        /, 
        tid: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        return self.request(
            "/api/admin/task/upload/delete", 
            params={"tid": tid}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_task_upload_cancel(
        self, 
        /, 
        tid: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        return self.request(
            "/api/admin/task/upload/cancel", 
            params={"tid": tid}, 
            async_=async_, 
            **request_kwds, 
        )

    def admin_task_upload_clear_done(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/upload/clear_done", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_task_upload_clear_succeeded(
        self, 
        /, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/upload/clear_succeeded", 
            async_=async_, 
            **request_kwds, 
        )

    def admin_task_upload_retry(
        self, 
        /, 
        tid: int | str, 
        async_: bool = False, 
        **request_kwds, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        return self.request(
            "/api/admin/task/upload/retry", 
            params={"tid": tid}, 
            async_=async_, 
            **request_kwds, 
        )

    ########## Other Encapsulations ##########

    @cached_property
    def fs(self, /):
        return AlistFileSystem(self)


class AlistPath(Mapping, PathLike[str]):
    "Alist path information."
    fs: AlistFileSystem
    path: str
    password: str

    def __init__(
        self, 
        /, 
        fs: AlistFileSystem, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        **attr, 
    ):
        super().__setattr__("__dict__", attr)
        attr["fs"] = fs
        attr["path"] = fs.abspath(path)
        attr["password"] = password
        attr["attr_last_fetched"] = None

    def __and__(self, path: str | PathLike[str], /) -> AlistPath:
        return type(self)(
            self.fs, 
            commonpath((self.path, self.fs.abspath(path))), 
            password=self.password, 
        )

    def __call__(self, /):
        "Data from API <- https://alist.nn.ci/guide/api/fs.html#post-获取某个文件-目录信息"
        self.__dict__.update(self.fs.attr(self.path, self.password, _check=False))
        self.__dict__["attr_last_fetched"] = datetime.now()
        return self

    def __contains__(self, key, /):
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return isinstance(path, AlistPath) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.attr_last_fetched:
            self()
        return self.__dict__[key]

    def __ge__(self, path, /):
        if not isinstance(path, AlistPath) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __gt__(self, path, /):
        if not isinstance(path, AlistPath) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __hash__(self, /):
        return hash((self.fs.client, self.path))

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /):
        if not isinstance(path, AlistPath) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __lt__(self, path, /):
        if not isinstance(path, AlistPath) or self.fs.client != path.fs.client or self.path == path.path:
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
        if attr == "password":
            if not isinstance(val, str):
                raise TypeError("only accept string `password`")
            self.__dict__["password"] = val
        else:
            raise TypeError("can't set attribute")

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> AlistPath:
        return self.joinpath(path)

    def keys(self) -> KeysView:
        return self.__dict__.keys()

    def values(self) -> ValuesView:
        return self.__dict__.values()

    def items(self) -> ItemsView:
        return self.__dict__.items()

    @property
    def anchor(self, /) -> str:
        return "/"

    def as_uri(self, /) -> str:
        return self.fs.client.origin + "/d" + quote(self.path, safe=":/?&=#")

    @property
    def attr(self, /) -> MappingProxyType:
        return MappingProxyType(self.__dict__)

    def copy(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: str="", 
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> Optional[AlistPath]:
        dst_path = self.fs.copy(
            self.path, 
            dst_path, 
            self.password, dst_password, 
            overwrite_or_ignore=overwrite_or_ignore, 
        )
        if dst_path:
            return type(self)(self.fs, dst_path, dst_password)

    def copytree(
        self, 
        /, 
        dst_dir: str | PathLike[str], 
        dst_password: str="", 
    ) -> AlistPath:
        dst_path = self.fs.copytree(
            src_path, 
            dst_dir, 
            dst_password, 
        )
        return type(self)(self.fs, dst_path, dst_password)

    def download(
        self, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal[""] | Literal["x"] | Literal["w"] | Literal["a"] = "w", 
        refresh: Optional[bool] = None, 
        download: Optional[Callable[str, SupportsWrite[bytes], Unpack[HeadersKeyword]], Any] = None, 
    ):
        return self.fs.download_tree(
            self.path, 
            local_dir, 
            self.password, 
            refresh=refresh, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
        )

    def exists(self, /) -> bool:
        return self.fs.exists(self.path, self.password, _check=False)

    def glob(self, /, pattern: str, ignore_case: bool = False) -> Iterator[AlistPath]:
        dirname = self.path if self.is_dir else self.parent.path
        return self.fs.glob(pattern, dirname, self.password, ignore_case=ignore_case, _check=False)

    def isdir(self, /) -> bool:
        return self.fs.isdir(self.path, self.password, _check=False)

    @property
    def is_dir(self, /):
        try:
            return self["is_dir"]
        except FileNotFoundError:
            return False

    def isfile(self, /) -> bool:
        return self.fs.isfile(self.path, self.password, _check=False)

    @property
    def is_file(self, /) -> bool:
        try:
            return not self["is_dir"]
        except FileNotFoundError:
            return False

    def iterdir(
        self, 
        /, 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
    ) -> Iterator[AlistPath]:
        return self.fs.iterdir(
            self.path, 
            self.password, 
            refresh=refresh, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            _check=False, 
        )

    def joinpath(self, *args: str | PathLike[str]) -> AlistPath:
        if not args:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *args))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new, self.password)

    def listdir(
        self, 
        /, 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
    ) -> list[str]:
        return self.fs.listdir(
            self.path, 
            self.password, 
            refresh=refresh, 
            page=page, 
            per_page=per_page, 
            _check=False, 
        )

    def listdir_attr(
        self, 
        /, 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
    ) -> list[AlistPath]:
        return self.fs.listdir_attr(
            self.path, 
            self.password, 
            refresh=refresh, 
            page=page, 
            per_page=per_page, 
            _check=False, 
        )

    def match(self, /, path_pattern: str, ignore_case: bool = False) -> bool:
        pattern = joinpath("/", *(t[0] for t in posix_glob_translate_iter(path_pattern)))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

    def mkdir(self, /):
        self.fs.mkdir(self.path, self.password, _check=False)

    def move(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        dst_path = self.fs.abspath(dst_path)
        if dst_password is None:
            dst_password = self.password
        dst_path = self.fs.move(
            self.path, 
            dst_path, 
            self.password, 
            dst_password, 
            _check=False, 
        )
        return type(self)(self.fs, dst_path, dst_password)

    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ):
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        if self.is_dir:
            raise IsADirectoryError(errno.EISDIR, self.path)
        return AlistFileReader(self).wrap(
            text_mode="b" not in mode, 
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    @cached_property
    def parent(self, /) -> AlistPath:
        path = self.path
        if path == "/":
            return self
        parent = dirname(path)
        if path == parent:
            return self
        return type(self)(self.fs, parent, self.password)

    @cached_property
    def parents(self, /) -> tuple[AlistPath, ...]:
        path = self.path
        if path == "/":
            return ()
        parents: list[AlistPath] = []
        cls, fs, password = type(self), self.fs, self.password
        parent = dirname(path)
        while path != parent:
            parents.append(cls(fs, parent, password))
        return tuple(parents)

    @cached_property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *self.path[1:].split("/"))

    def read_bytes(self, /):
        return self.open("rb").read()

    def read_bytes_range(self, /, bytes_range="0-", headers=None) -> bytes:
        if headers:
            headers = {**headers, "Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        else:
            headers = {"Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        with urlopen(self.url, headers=headers) as resp:
            return resp.read()

    def read_range(self, /, start=0, stop=None, headers=None) -> bytes:
        length = None
        if start < 0:
            length = urlopen(self.url).length
            start += length
        if start < 0:
            start = 0
        if stop is None:
            bytes_range = f"{start}-"
        else:
            if stop < 0:
                if length is None:
                    length = urlopen(self.url).length
                stop += length
            if stop <= 0 or start >= stop:
                return b""
            bytes_range = f"{start}-{stop-1}"
        return self.read_bytes_range(bytes_range, headers=headers)

    def read_text(
        self, 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
    ):
        return self.open(encoding=encoding, errors=errors).read()

    def remove(self, /, recursive: bool = False):
        return self.fs.remove(self.path, self.password, recursive=recursive, _check=False)

    def rename(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        dst_path = self.fs.abspath(dst_path)
        if dst_password is None:
            dst_password = self.password
        self.fs.rename(
            self.path, 
            dst_path, 
            self.password, 
            dst_password, 
            _check=False, 
        )
        return type(self)(self.fs, dst_path, dst_password)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        dst_path = self.fs.abspath(dst_path)
        if dst_password is None:
            dst_password = self.password
        self.fs.replace(
            self.path, 
            dst_path, 
            self.password, 
            dst_password, 
            _check=False, 
        )
        return type(self)(self.fs, dst_path, dst_password)

    def rglob(self, /, pattern: str, ignore_case: bool = False) -> Iterator[AlistPath]:
        dirname = self.path if self.is_dir else self.parent.path
        return self.fs.rglob(pattern, dirname, self.password, ignore_case=ignore_case, _check=False)

    def rmdir(self, /):
        self.fs.rmdir(self.path, self.password, _check=False)

    @property
    def root(self, /) -> AlistPath:
        return type(self)(
            self.fs, 
            self.fs.storage_of(self.path, self.password, _check=False), 
            self.password, 
        )

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if isinstance(path, AlistPath):
            return self == path
        return self.path == self.fs.abspath(path)

    def stat(self, /):
        return self.fs.stat(self.path, self.password, _check=False)

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
        self.fs.touch(self.path, self.password, _check=False)

    unlink = remove

    @funcproperty
    def url(self, /) -> str:
        url = self["raw_url"]
        if not url:
            return self.as_uri()
        if url.startswith( self.fs.client.origin):
            self.__dict__["url"] = url
        return url

    def with_name(self, name: str, /) -> AlistPath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> AlistPath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> AlistPath:
        return self.parent.joinpath(self.stem + suffix)

    def write_bytes(self, data: bytes | bytearray, /):
        bio = BytesIO(data)
        return self.fs.upload(bio, self.path, self.password, overwrite_or_ignore=True, _check=False)

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
        return self.fs.upload(bio, self.path, self.password, overwrite_or_ignore=True, _check=False)


class AlistFileReader(HTTPFileReader):
    "Open a file from the alist server."
    path: AlistPath

    def __init__(self, /, path: AlistPath):
        super().__init__(path.url)
        self.__dict__["path"] = path

    @cached_property
    def name(self, /) -> str:
        return self.path["name"]

    @property # type: ignore
    def url(self) -> str:
        return self.path.url


class AlistFileSystem:
    """Implemented some file system methods by utilizing alist's web API 
    and referencing modules such as `os` and `shutil`."""
    client: AlistClient
    path: str
    refresh: bool

    def __init__(
        self, 
        /, 
        client: AlistClient, 
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
        return self

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

    @classmethod
    def login(
        cls, 
        /, 
        origin: str = "http://localhost:5244", 
        username: str = "", 
        password: str = "", 
    ) -> AlistFileSystem:
        return cls(AlistClient(origin, username, password))

    @_check_response
    def fs_batch_rename(
        self, 
        /, 
        rename_pairs: Iterable[tuple[str, str]], 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "src_dir": src_dir, 
            "rename_objects": [{
                "src_name": src_name, 
                "new_name": new_name, 
            } for src_name, new_name in rename_pairs]
        }
        return self.client.fs_batch_rename(payload)

    @_check_response
    def fs_copy(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> dict:
        if _check:
            src_dir = self.abspath(src_dir)
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self.client.fs_copy(payload)

    @_check_response
    def fs_dirs(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        payload = {
            "path": path, 
            "password": password, 
            "refresh": refresh, 
        }
        return self.client.fs_dirs(payload)

    @_check_response
    def fs_form(
        self, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.fs_form(local_path_or_file, path, as_task=as_task)

    @_check_response
    def fs_get(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "password": password}
        return self.client.fs_get(payload)

    @_check_response
    def fs_list(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        payload = {
            "path": path, 
            "password": password, 
            "page": page, 
            "per_page": per_page, 
            "refresh": refresh, 
        }
        return self.client.fs_list(payload)

    @_check_response
    def fs_list_storage(self, /) -> dict:
        return self.client.admin_storage_list()

    @_check_response
    def fs_mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return {"code": 200}
        return self.client.fs_mkdir({"path": path})

    @_check_response
    def fs_move(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> dict:
        if not names:
            return {"code": 200}
        if _check:
            src_dir = self.abspath(src_dir)
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        if src_dir == dst_dir:
            return {"code": 200}
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self.client.fs_move(payload)

    @_check_response
    def fs_put(
        self, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.fs_put(local_path_or_file, path, as_task=as_task)

    @_check_response
    def fs_recursive_move(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        _check: bool = True, 
    ) -> dict:
        if _check:
            src_dir = self.abspath(src_dir)
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir}
        return self.client.fs_recursive_move(payload)

    @_check_response
    def fs_regex_rename(
        self, 
        /, 
        src_name_regex: str, 
        new_name_regex: str, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "src_dir": src_dir, 
            "src_name_regex": src_name_regex, 
            "new_name_regex": new_name_regex, 
        }
        return self.client.fs_regex_rename(payload)

    @_check_response
    def fs_remove(
        self, 
        /, 
        names: list[str], 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if not names:
            return {"code": 200}
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"names": names, "dir": src_dir}
        return self.client.fs_remove(payload)

    @_check_response
    def fs_remove_empty_directory(
        self, 
        /, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"src_dir": src_dir}
        return self.client.fs_remove_empty_directory(payload)

    @_check_response
    def fs_remove_storage(self, id: int | str, /) -> dict:
        return self.client.admin_storage_delete(id)

    @_check_response
    def fs_rename(
        self, 
        /, 
        path: str | PathLike[str], 
        name: str, 
        _check: bool = True, 
    ) -> dict:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "name": name}
        return self.client.fs_rename(payload)

    @_check_response
    def fs_search(
        self, 
        /, 
        keywords: str, 
        src_dir: str | PathLike[str] = "", 
        scope: Literal[0, 1, 2] = 0, 
        page: int = 1, 
        per_page: int = 0, 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "parent": src_dir, 
            "keywords": keywords, 
            "scope": scope, 
            "page": page, 
            "per_page": per_page, 
            "password": password, 
        }
        return self.client.fs_search(payload)

    def abspath(self, /, path: str | PathLike[str] = "") -> str:
        if path in ("", "."):
            return self.path
        elif isinstance(path, AlistPath):
            return path.path
        return normpath(joinpath(self.path, path))

    def as_path(self, path: str | PathLike[str] = "", password: str = "") -> AlistPath:
        return AlistPath(self, path, password)

    def attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        return self.fs_get(path, password, _check=_check)["data"]

    def chdir(
        self, 
        /, 
        path: str | PathLike[str] = "/", 
        password: str = "", 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == self.path:
            pass
        elif path == "/":
            self.__dict__["path"] = "/"
        elif self.attr(path, password, _check=False)["is_dir"]:
            self.__dict__["path"] = path
        else:
            raise NotADirectoryError(errno.ENOTDIR, path)

    def copy(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Optional[str]:
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            if overwrite_or_ignore is None:
                raise SameFileError(src_path)
            return None
        if dst_path.startswith(src_path):
            raise PermissionError(errno.EPERM, f"copy a file to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_attr = self.attr(src_path, src_password, _check=False)
        if src_attr["is_dir"]:
            raise IsADirectoryError(errno.EISDIR, f"source path {src_path!r} is a directory: {src_path!r} -> {dst_path!r}")
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            pass
        else:
            if dst_attr["is_dir"]:
                raise IsADirectoryError(errno.EISDIR, f"destination path {src_path!r} is a directory: {src_path!r} -> {dst_path!r}")
            elif overwrite_or_ignore is None:
                raise FileExistsError(errno.EEXIST, f"destination path {dst_path!r} already exists: {src_path!r} -> {dst_path!r}")
            elif not overwrite_or_ignore:
                return None
            self.fs_remove([basename(dst_path)], dirname(dst_path), _check=False)
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        if src_name == dst_name:
            self.fs_copy(src_dir, dst_dir, [src_name], _check=False)
        else:
            src_storage = self.storage_of(src_dir, src_password, _check=False)
            dst_storage = self.storage_of(dst_dir, dst_password, _check=False)
            if src_storage != dst_storage:
                raise PermissionError(errno.EPERM, f"cross storages replication does not allow renaming: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}")
            tempdirname = str(uuid4())
            tempdir = joinpath(dst_dir, tempdirname)
            self.fs_mkdir(tempdir, _check=False)
            try:
                self.fs_copy(src_dir, tempdir, [src_name], _check=False)
                self.fs_rename(joinpath(tempdir, src_name), dst_name, _check=False)
                self.fs_move(tempdir, dst_dir, [dst_name], _check=False)
            finally:
                self.fs_remove([tempdirname], dst_dir, _check=False)
        return dst_path

    def copytree(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> str:
        if _check:
            src_path = self.abspath(src_path)
            dst_dir = self.abspath(dst_dir)
        src_path = cast(str, src_path)
        dst_dir = cast(str, dst_dir)
        if dirname(src_path) == dst_dir:
            raise SameFileError(src_path)
        elif src_path == dst_dir or dst_dir.startswith(src_path):
            raise PermissionError(errno.EPERM, f"copy a directory to its subordinate path is not allowed: {src_path!r} ->> {dst_dir!r}")
        elif not self.attr(dst_dir, dst_password, _check=False)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, f"destination is not directory: {src_path!r} ->> {dst_dir!r}")
        elif self.exists(joinpath(dst_dir, basename(src_path))):
            raise FileExistsError(errno.EEXIST, f"destination already exists: {src_path!r} ->> {dst_dir!r}")
        self.fs_copy(dirname(src_path), dst_dir, [basename(src_path)], _check=False)
        return dst_dir

    def download(
        self, 
        /, 
        path: str | PathLike[str], 
        local_path_or_file: bytes | str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        password: str = "", 
        write_mode: Literal[""] | Literal["x"] | Literal["w"] | Literal["a"] = "w", 
        download: Optional[Callable[str, SupportsWrite[bytes]], Any] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.attr(path, password, _check=False)
        if attr["is_dir"]:
            raise IsADirectoryError(errno.EISDIR, path)
        if hasattr(local_path_or_file, "write"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
        else:
            local_path = fspath(local_path_or_file)
            if write_mode:
                write_mode += "b"
            elif os_path.lexists(local_path):
                return
            else:
                write_mode = "wb"
            if local_path:
                file = open(local_path, write_mode)
            else:
                file = open(basename(path), write_mode)
        url = attr["raw_url"]
        if download:
            download(url, file)
        else:
            with urlopen(url) as fsrc:
                copyfileobj(fsrc, file)

    def download_tree(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        local_dir: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        no_root: bool = False, 
        write_mode: Literal[""] | Literal["x"] | Literal["w"] | Literal["a"] = "w", 
        download: Optional[Callable[str, SupportsWrite[bytes]], Any] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
            attr = self.attr(path, password, _check=False)
            isdir = attr["is_dir"]
        else:
            isdir = True
        path = cast(str, path)
        refresh = cast(bool, refresh)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        if isdir:
            if not no_root:
                local_dir = os_path.join(local_dir, basename(path))
                makedirs(local_dir, exist_ok=True)
            for apath in self.listdir_attr(path, password, refresh=refresh, _check=False):
                if apath["is_dir"]:
                    self.download_tree(
                        apath.path, 
                        os_path.join(local_dir, apath["name"]), 
                        password, 
                        refresh=refresh, 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
                        _check=False, 
                    )
                else:
                    self.download(
                        apath.path, 
                        os_path.join(local_dir, apath["name"]), 
                        password, 
                        write_mode=write_mode, 
                        download=download, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                os_path.join(local_dir, basename(path)), 
                password, 
                write_mode=write_mode, 
                download=download, 
                _check=False, 
            )

    def exists(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            self.attr(path, password, _check=_check)
            return True
        except FileNotFoundError:
            return False

    def getcwd(self, /) -> str:
        return self.path

    def glob(
        self, 
        /, 
        pattern: str, 
        dirname: str = "", 
        password: str = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if pattern == "*":
            return self.iterdir(dirname, password, _check=_check)
        elif pattern == "**":
            return self.iterdir(dirname, password, max_depth=-1, _check=_check)
        elif not pattern:
            if _check:
                dirname = self.abspath(dirname)
            if self.exists(dirname, password, _check=False):
                return iter((AlistPath(self, dirname, password),))
            return iter(())
        elif not pattern.lstrip("/"):
            return iter((AlistPath(self, "/", password),))
        splitted_pats = tuple(posix_glob_translate_iter(pattern))
        if pattern.startswith("/"):
            dirname = "/"
        elif _check:
            dirname = self.abspath(dirname)
        i = 0
        if ignore_case:
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), *(t[0] for t in splitted_pats))
                match = re_compile("(?i:%s)" % pattern).fullmatch
                return self.iterdir(
                    dirname, 
                    password, 
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
                if self.exists(dirname, password, _check=False):
                    return iter((AlistPath(self, dirname, password),))
                return iter(())
            elif typ == "dstar" and i + 1 == len(splitted_pats):
                return self.iterdir(dirname, password, max_depth=-1, _check=False)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), *(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                return self.iterdir(
                    dirname, 
                    password, 
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
                elif subpath.is_dir:
                    yield from glob_step_match(subpath, j)
            elif typ == "star":
                if at_end:
                    yield from path.listdir_attr()
                else:
                    for subpath in path.listdir_attr():
                        if subpath.is_dir:
                            yield from glob_step_match(subpath, j)
            else:
                for subpath in path.listdir_attr():
                    try:
                        cref = cref_cache[i]
                    except KeyError:
                        if ignore_case:
                            pat = "(?i:%s)" % pat
                        cref = cref_cache[i] = re_compile(pat).fullmatch
                    if cref(subpath.name):
                        if at_end:
                            yield subpath
                        elif subpath.is_dir:
                            yield from glob_step_match(subpath, j)
        path = AlistPath(self, dirname, password)
        if not path.is_dir:
            return iter(())
        return glob_step_match(path, i)

    def isdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            return self.attr(path, password, _check=_check)["is_dir"]
        except FileNotFoundError:
            return False

    def isfile(
        self, 
        /, 
        path: str, 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            return not self.attr(path, password, _check=_check)["is_dir"]
        except FileNotFoundError:
            return False

    def is_empty(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self.attr(path, password, _check=False)
        except FileNotFoundError:
            return True
        if attr["is_dir"]:
            data = self.fs_list(path, password, per_page=1, _check=False)["data"]
            return not data or data["total"] == 0
        else:
            return attr["size"] == 0

    def is_storage(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return True
        try:
            return any(path == s["mount_path"] for s in self.list_storages())
        except PermissionError:
            try:
                return self.attr(path, password, _check=False).get("hash_info") is None
            except FileNotFoundError:
                return False

    def iterdir(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if not max_depth:
            return
        if _check:
            top = self.abspath(top)
            if refresh is None:
                refresh = self.refresh
        top = cast(str, top)
        refresh = cast(bool, refresh)
        try:
            ls = self.listdir_attr(top, password, refresh=refresh, _check=False)
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
        for path in ls:
            yield_me = min_depth <= 0
            if yield_me and predicate:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred
            if yield_me and topdown:
                yield path
            if path["is_dir"]:
                yield from self.iterdir(
                    joinpath(top, path["name"]), 
                    password, 
                    refresh=refresh, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    _check=_check, 
                )
            if yield_me and not topdown:
                yield path

    def list_storages(self, /) -> list[dict]:
        return self.fs_list_storage()["data"]["content"]

    def _listdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        if not self.attr(path, password)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        data = self.fs_list(path, password, refresh=refresh, page=page, per_page=per_page, _check=False)["data"]
        if not data or data["total"] == 0:
            return []
        return data["content"]

    def listdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> list[str]:
        ls = self._listdir(path, password, refresh, page, per_page, _check=_check)
        return [item["name"] for item in ls]

    def listdir_attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> list[AlistPath]:
        ls = self._listdir(path, password, refresh, page, per_page, _check=_check)
        return [AlistPath(self, joinpath(path, item["name"]), password, **item) for item in ls]

    def makedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        exist_ok: bool = False, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return
        if not exist_ok and self.exists(path, password, _check=False):
            raise FileExistsError(errno.EEXIST, path)
        self.fs_mkdir(path, _check=False)

    def mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "create root directory is not allowed (because it has always existed)")
        if self.is_storage(path, password, _check=False):
            raise PermissionError(errno.EPERM, f"can't directly create a storage by `mkdir`: {path!r}")
        try:
            self.attr(path, password, _check=False)
        except FileNotFoundError as e:
            dir_ = dirname(path)
            if not self.attr(dir_, password, _check=False)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, dir_) from e
            self.fs_mkdir(path, _check=False)
        else:
            raise FileExistsError(errno.EEXIST, path)

    def move(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> str:
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path or dirname(src_path) == dst_path:
            raise SameFileError(src_path)
        if dst_path.startswith(src_path):
            raise PermissionError(errno.EPERM, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_attr = self.attr(src_path, src_password, _check=False)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            self.rename(src_path, dst_path, src_password, dst_password, _check=False)
        else:
            if dst_attr["is_dir"]:
                dst_filename = basename(src_path)
                dst_filepath = joinpath(dst_path, dst_filename)
                if self.exists(dst_filepath, dst_password, _check=False):
                    raise FileExistsError(errno.EEXIST, f"destination path {dst_filepath!r} already exists")
                self.fs_move(dirname(src_path), dst_path, [dst_filename], _check=False)
                return dst_filepath
            else:
                self.rename(src_path, dst_path, src_password, dst_password, _check=False)
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
        password: str = "", 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return AlistPath(self, path, password).open(
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
        password: str = "", 
        recursive: bool = False, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            if recursive:
                try:
                    storages = self.list_storages()
                except PermissionError:
                    self.fs_remove(self.listdir("/", password, refresh=True), "/", _check=False)
                else:
                    for storage in storages:
                        self.fs_remove_storage(storage["id"])
                return
            else:
                raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        attr = self.attr(path, password, _check=False)
        if attr["is_dir"]:
            if not recursive:
                if attr.get("hash_info") is None:
                    raise PermissionError(errno.EPERM, f"remove a storage is not allowed: {path!r}")
                raise IsADirectoryError(errno.EISDIR, path)
            try:
                storages = self.list_storages()
            except PermissionError:
                if attr.get("hash_info") is None:
                    raise
            else:
                for storage in storages:
                    if commonpath((storage["mount_path"], path)) == path:
                        self.fs_remove_storage(storage["id"])
        if attr.get("hash_info") is not None:
            self.fs_remove([basename(path)], dirname(path), _check=False)

    def removedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        self.rmdir(path, password, _check=False)
        subpath = dirname(path)
        while subpath != path:
            path = subpath
            try:
                self.rmdir(path, password, _check=False)
            except OSError as e:
                break
            subpath = dirname(path)

    def rename(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
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
            raise OSError(errno.EINVAL, f"invalid argument: {src_path!r} -> {dst_path!r}")
        if dst_path.startswith(src_path):
            raise PermissionError(errno.EPERM, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        src_attr = self.attr(src_path, src_password, _check=False)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            if src_attr.get("hash_info") is None:
                for storage in self.list_storages():
                    if src_path == storage["mount_path"]:
                        storage["mount_path"] = dst_path
                        self.client.admin_storage_update(storage)
                        break
                return
            elif src_dir == dst_dir:
                self.fs_rename(src_path, dst_name, _check=False)
                return
            if not self.attr(dst_dir, dst_password, _check=False)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"{dst_dir!r} is not a directory: {src_path!r} -> {dst_path!r}")
        else:
            if replace:
                if dst_attr.get("hash_info") is None:
                    raise PermissionError(errno.EPERM, f"replace a storage {dst_path!r} is not allowed: {src_path!r} -> {dst_path!r}")
                elif src_attr["is_dir"]:
                    if dst_attr["is_dir"]:
                        data = self.fs_list(dst_path, dst_password, per_page=1, _check=False)["data"]
                        if not data or data["total"] == 0:
                            raise OSError(errno.ENOTEMPTY, f"directory {dst_path!r} is not empty: {src_path!r} -> {dst_path!r}")
                    else:
                        raise NotADirectoryError(errno.ENOTDIR, f"{dst_path!r} is not a directory: {src_path!r} -> {dst_path!r}")
                elif dst_attr["is_dir"]:
                    raise IsADirectoryError(errno.EISDIR, f"{dst_path!r} is a directory: {src_path!r} -> {dst_path!r}")
                self.fs_remove([dst_name], dst_dir, _check=False)
            else:
                raise FileExistsError(errno.EEXIST, f"{dst_path!r} already exists: {src_path!r} -> {dst_path!r}")
        src_storage = self.storage_of(src_dir, src_password, _check=False)
        dst_storage = self.storage_of(dst_dir, dst_password, _check=False)
        if src_name == dst_name:
            if src_storage != dst_storage:
                warn("cross storages movement will retain the original file: {src_path!r} |-> {dst_path!r}")
            self.fs_move(src_dir, dst_dir, [src_name], _check=False)
        elif src_dir == dst_dir:
            self.fs_rename(src_path, dst_name, _check=False)
        else:
            if src_storage != dst_storage:
                raise PermissionError(errno.EPERM, f"cross storages movement does not allow renaming: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}")
            tempname = f"{uuid4()}{splitext(src_name)[1]}"
            self.fs_rename(src_path, tempname, _check=False)
            try:
                self.fs_move(src_dir, dst_dir, [tempname], _check=False)
                try:
                    self.fs_rename(joinpath(dst_dir, tempname), dst_name, _check=False)
                except:
                    self.fs_move(dst_dir, src_dir, [tempname], _check=False)
                    raise
            except:
                self.fs_rename(joinpath(src_dir, tempname), src_name, _check=False)
                raise

    def renames(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ):
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        self.rename(src_path, dst_path, src_password, dst_password, _check=False)
        if dirname(src_path) == dirname(dst_path):
            return
        try:
            self.removedirs(dirname(src_path), src_password, _check=False)
        except OSError:
            pass

    def replace(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ):
        self.rename(src_path, dst_path, src_password, dst_password, replace=True, _check=_check)

    def rglob(
        self, 
        /, 
        pattern: str, 
        dirname: str = "", 
        password: str = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if not pattern:
            return self.iterdir(dirname, password, max_depth=-1, _check=_check)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, password, ignore_case=ignore_case, _check=_check)

    def rmdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif self.is_storage(path, password, _check=False):
            raise PermissionError(errno.EPERM, f"remove a storage by `rmdir` is not allowed: {path!r}")
        elif _check and not self.attr(path, password, _check=False)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        elif not self.is_empty(path, password, _check=False):
            raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        self.fs_remove([basename(path)], dirname(path), _check=False)

    def rmtree(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        self.remove(path, password, recursive=True, _check=_check)

    def scandir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ):
        raise UnsupportedOperation(errno.ENOSYS, 
            "`scandir()` is currently not supported, use `listdir_attr()` instead."
        )

    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ):
        raise UnsupportedOperation(errno.ENOSYS, 
            "`stat()` is currently not supported, use `attr()` instead."
        )

    def storage_of(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> str:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        try:
            storages = self.list_storages()
        except PermissionError:
            while True:
                try:
                    attr = self.attr(path, password, _check=False)
                except FileNotFoundError:
                    continue
                else:
                    if attr.get("hash_info") is None:
                        return path
                finally:
                    ppath = dirname(path)
                    if ppath == path:
                        return "/"
                    path = ppath
            return "/"
        else:
            storage = "/"
            for s in storages:
                mount_path = s["mount_path"]
                if path == mount_path:
                    return mount_path
                elif commonpath((path, mount_path)) == mount_path and len(mount_path) > len(storage):
                    storage = mount_path
            return storage

    def touch(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.exists(path, password, _check=False):
            dir_ = dirname(path)
            if not self.attr(dir_, password, _check=False)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
        self.upload(BytesIO(), path, password, _check=False)

    def upload(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        as_task: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        file: SupportsRead[bytes]
        if hasattr(local_path_or_file, "read"):
            file = cast(SupportsRead[bytes], local_path_or_file)
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if not path:
                try:
                    path = os_path.basename(file.name) # type: ignore
                except AttributeError as e:
                    raise OSError(errno.EINVAL, "Please specify the upload path") from e
        else:
            file = open(local_path_or_file, "rb")
            if not path:
                path = os_path.basename(local_path_or_file)
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self.attr(path, password, _check=False)
        except FileNotFoundError:
            pass
        else:
            if overwrite_or_ignore is None:
                raise FileExistsError(errno.EEXIST, path)
            elif attr["is_dir"]:
                raise IsADirectoryError(errno.EISDIR, path)
            elif not overwrite_or_ignore:
                return
            self.fs_remove([basename(path)], dirname(path), _check=False)
        size: int
        if hasattr(file, "getbuffer"):
            size = len(file.getbuffer()) # type: ignore
        else:
            try:
                fd = file.fileno() # type: ignore
            except (UnsupportedOperation, AttributeError):
                size = 0
            else:
                size = fstat(fd).st_size
        if size:
            self.fs_put(file, path, as_task=as_task, _check=False)
        else:
            self.fs_form(file, path, as_task=as_task, _check=False)

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str], 
        path: str | PathLike[str] = "", 
        password: str = "", 
        as_task: bool = False, 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if self.isfile(path):
            raise NotADirectoryError(errno.ENOTDIR, path)
        try:
            it = scandir(local_path)
        except NotADirectoryError:
            self.upload(
                local_path, 
                joinpath(path, os_path.basename(local_path)), 
                password, 
                as_task=as_task, 
                overwrite_or_ignore=overwrite_or_ignore, 
                _check=False, 
            )
        else:
            if not no_root:
                path = joinpath(path, os_path.basename(local_path))
            for entry in it:
                if entry.is_dir():
                    self.upload_tree(
                        entry.path, 
                        joinpath(path, entry.name), 
                        password, 
                        as_task=as_task, 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.upload(
                        entry.path, 
                        joinpath(path, entry.name), 
                        password, 
                        as_task=as_task, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )

    unlink = remove

    def walk(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
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
            data = self.fs_list(top, password, refresh=refresh, _check=False)["data"]
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        else:
            ls = data and data["content"] or []
        if not ls:
            yield top, [], []
            return
        dirs: list[str] = []
        files: list[str] = []
        for attr in ls:
            if attr["is_dir"]:
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
                password, 
                refresh=refresh, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

    def walk_attr(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        if not max_depth:
            return
        if _check:
            top = self.abspath(top)
            if refresh is None:
                refresh = self.refresh
        top = cast(str, top)
        refresh = cast(bool, refresh)
        try:
            ls = self.listdir_attr(top, password, refresh=refresh, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if not ls:
            yield top, [], []
            return
        dirs: list[AlistPath] = []
        files: list[AlistPath] = []
        for path in ls:
            if path["is_dir"]:
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
            yield from self.walk_attr(
                joinpath(top, dir_["name"]), 
                password, 
                refresh=refresh, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

    cd = chdir
    pwd = getcwd
    ls = listdir
    ll = listdir_attr
    rm = remove

# TODO: 自动根据文档 https://alist.nn.ci/guide/api 生成 AlistClient 类
# TODO: 所有类和函数都要有文档
# TODO: 所有类和函数都要有单元测试
# TODO: 支持异步IO
# TODO: 上传下载都支持进度条，下载支持多线程
