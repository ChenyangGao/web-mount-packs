#!/usr/bin/env python3
# encoding: utf-8

"""This module provides some utilities for encapsulating and using Alist's web APIs.

- `Alist Web API official documentation <https://alist.nn.ci/guide/api/>` 
"""

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 5)
__all__ = [
    "AuthenticationError", "AlistOSError", "AlistClient", 
    "AlistPath", "AlistFile", "AlistFileSystem", 
]
__requirements__ = ["aiohttp", "requests"]

from asyncio import run
from functools import partial
from inspect import isawaitable
from io import BufferedReader, BytesIO, RawIOBase, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE
from os import PathLike, makedirs, scandir, path as os_path
from posixpath import basename, commonpath, dirname, join as joinpath, isabs, normpath, split, splitext
from shutil import copyfileobj, SameFileError
from typing import cast, Callable, Iterable, Iterator, Literal, Mapping, Optional, Protocol, TypeVar
from types import MappingProxyType
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4
from warnings import filterwarnings, warn

from aiohttp import ClientSession
from requests import Session


filterwarnings("ignore", category=DeprecationWarning)

_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object: ...


class SupportsRead(Protocol[_T_co]):
    def read(self, __length: int = ...) -> _T_co: ...


class AuthenticationError(ValueError):
    "Login failed, possibly due to non-existent username or incorrect password."


class AlistOSError(OSError):
    "OSError for alist."


class AlistClient:
    """Alist client that encapsulates web APIs

    - `Alist Web API official documentation <https://alist.nn.ci/guide/api/>` 
    """
    def __init__(self, /, origin: str, username: str = "", password: str = ""):
        self.__origin = origin.rstrip("/")
        self.username = username
        self.password = password
        self.__async_session = ClientSession(raise_for_status=True)
        self.__session = Session()
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /):
        if not isinstance(other, AlistClient):
            return False
        return self.origin == other.origin

    def __hash__(self, /):
        return hash(self.origin)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self.origin!r}, username={self.username!r}, password='******')"

    def close(self, /):
        self.__session.close()
        try:
            run(self.__async_session.close())
        except Exception:
            pass

    @property
    def async_session(self, /) -> ClientSession:
        return self.__async_session

    @property
    def origin(self, /) -> str:
        return self.__origin

    @property
    def session(self, /) -> Session:
        return self.__session

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
        url = self.origin + api
        request_kwds["stream"] = True
        resp = self.__session.request(method, url, **request_kwds)
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
        url = self.origin + api
        request_kwds.pop("stream", None)
        req = self.__async_session.request(method, url, **request_kwds)
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
        if not username:
            username = self.username
        if not password:
            password = self.password
        request_kwds["async_"] = False
        data = self.auth_login(
            {"username": username, "password": password}, 
            **request_kwds, 
        )
        if not 200 <= data["code"] < 300:
            raise AuthenticationError(data["message"])
        self.__async_session.headers["Authorization"] = self.__session.headers["Authorization"] = data["data"]["token"]

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
        "https://alist.nn.ci/guide/api/admin/storage.html#post-更新存储"
        return self.request(
            "/api/admin/storage/create", 
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


class AlistPath(Mapping, PathLike[str]):
    "Alist path information."
    def __init__(
        self, 
        /, 
        fs: AlistFileSystem, 
        path: str, 
        password: str = "", 
        attr_preset: Optional[dict] = None, 
    ):
        assert isabs(path), "only accept absolute path"
        if attr_preset is None:
            attr_preset = {}
        self.__fs = fs
        self.__path = path
        self.password = password
        self.__attr = attr_preset
        self.attr = MappingProxyType(attr_preset)
        self._attr_unfetched = True

    def __and__(self, path: str | PathLike[str], /):
        return type(self)(
            self.__fs, 
            commonpath((self.path, path)), 
            password=self.password, 
        )

    def __eq__(self, path, /):
        if not isinstance(path, AlistPath):
            return False
        return self.fs.client.origin == path.fs.client.origin and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.__path

    def __getattr__(self, attr, /):
        try:
            return self[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __getitem__(self, key, /):
        if self._attr_unfetched and key not in self.__attr:
            self.attr_refresh()
        return self.__attr[key]

    def __gt__(self, path, /):
        if not isinstance(path, AlistPath) or self.fs.client.origin != path.fs.client.origin or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __hash__(self, /):
        return hash(self.fs.client.origin) ^ hash(self.__path)

    def __iter__(self, /):
        return iter(self.__attr)

    def __len__(self, /) -> int:
        return len(self.__attr)

    def __lt__(self, path, /):
        if not isinstance(path, AlistPath) or self.fs.client.origin != path.fs.client.origin or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(fs={self.__fs!r}, path={self.__path!r}){self.__attr} at {hex(id(self))}>"

    def __str__(self, /) -> str:
        return self.__path

    def __truediv__(self, path: str | PathLike[str], /) -> AlistPath:
        return self.joinpath(path)

    @property
    def anchor(self, /) -> str:
        return "/"

    def as_uri(self, /) -> str:
        return quote(self.__fs.client.origin + "/d" + self.__path, safe=":/?&=")

    def attr_refresh(self, /) -> MappingProxyType:
        "Data from API <- https://alist.nn.ci/guide/api/fs.html#post-获取某个文件-目录信息"
        attr = self.__fs.attr(self.__path, self.password, _check=False)
        self._attr_unfetched = False
        self.__attr.update(attr)
        return self.attr

    def exists(self, /) -> bool:
        return self.__fs.exists(self.__path, self.password, _check=False)

    @property
    def fs(self, /) -> AlistFileSystem:
        return self.__fs

    def glob(self, /, pattern: str) -> Iterator[AlistPath]:
        raise NotImplementedError("glob")

    def isdir(self, /) -> bool:
        return self.fs.isdir(self.__path, self.password, _check=False)

    def isfile(self, /) -> bool:
        return self.fs.isfile(self.__path, self.password, _check=False)

    def is_file(self, /) -> bool:
        return not self["is_dir"]

    def iterdir(
        self, 
        /, 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
    ) -> Iterator[AlistPath]:
        return self.__fs.iterdir(
            self.__path, 
            self.password, 
            refresh=refresh, 
            topdown=topdown, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            _check=False, 
        )

    def joinpath(self, *args: str | PathLike[str]) -> AlistPath:
        if not args:
            return self
        path = normpath(joinpath(self.__path, *args))
        if path == self.__path:
            return self
        return type(self)(self.__fs, path, self.password)

    def match(self, /, path_pattern: str) -> bool:
        raise NotImplementedError("match")

    def mkdir(self, /):
        self.__fs.mkdir(self.__path, self.password, _check=False)

    def move(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        dst_path = self.joinpath(dst_path)
        if dst_password is None:
            dst_password = self.password
        dest_path = self.__fs.move(
            self.__path, 
            dst_path, 
            self.password, 
            dst_password, 
            _check=False, 
        )
        return type(self)(self.__fs, dst_path.path, dst_password)

    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ):
        orig_mode = mode
        if "b" in mode:
            mode = mode.replace("b", "", 1)
            open_text_mode = False
        else:
            mode = mode.replace("t", "", 1)
            open_text_mode = True
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise ValueError(f"invalid (or unsupported) mode: {orig_mode!r}")
        if buffering is None:
            if open_text_mode:
                buffering = DEFAULT_BUFFER_SIZE
            else:
                buffering = 0
        if buffering == 0:
            if open_text_mode:
                raise ValueError("can't have unbuffered text I/O")
            return AlistFile(self, mode)
        line_buffering = False
        buffer_size: int
        if buffering < 0:
            buffer_size = DEFAULT_BUFFER_SIZE
        elif buffering == 1:
            if not open_text_mode:
                warn("line buffering (buffering=1) isn't supported in binary mode, "
                     "the default buffer size will be used", RuntimeWarning)
            buffer_size = DEFAULT_BUFFER_SIZE
            line_buffering = True
        else:
            buffer_size = buffering
        raw = AlistFile(self, mode)
        buffer = BufferedReader(raw, buffer_size)
        if open_text_mode:
            return TextIOWrapper(
                buffer, 
                encoding=encoding, 
                errors=errors, 
                newline=newline, 
                line_buffering=line_buffering, 
            )
        else:
            return buffer

    @property
    def parent(self, /) -> AlistPath:
        path = self.__path
        if path == "/":
            return self
        parent = dirname(path)
        if path == parent:
            return self
        return type(self)(self.__fs, parent, self.password)

    @property
    def parents(self, /) -> list[AlistPath]:
        path = self.__path
        parents: list[AlistPath] = []
        if path == "/":
            return parents
        cls, fs, password = type(self), self.__fs, self.password
        parent = dirname(path)
        while path != parent:
            parents.append(cls(fs, parent, password))
        return parents

    @property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *self.__path[1:].split("/"))

    @property
    def path(self, /) -> str:
        return self.__path

    def read_bytes(self, /):
        return self.open("rb").read()

    def read_text(
        self, 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
    ):
        return self.open(encoding=encoding, errors=errors).read()

    def remove(self, /, recursive: bool = False):
        self.__fs.remove(self.__path, self.password, recursive=recursive, _check=False)

    def rename(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        dst_path = self.joinpath(dst_path)
        if dst_password is None:
            dst_password = self.password
        self.__fs.rename(
            self.__path, 
            dst_path, 
            self.password, 
            dst_password, 
            _check=False, 
        )
        return type(self)(self.__fs, dst_path.path, dst_password)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        dst_path = self.joinpath(dst_path)
        if dst_password is None:
            dst_password = self.password
        self.__fs.replace(
            self.__path, 
            dst_path, 
            self.password, 
            dst_password, 
            _check=False, 
        )
        return type(self)(self.__fs, dst_path.path, dst_password)

    def rglob(self, /, pattern: str) -> Iterator[AlistPath]:
        raise NotImplementedError("rglob")

    def rmdir(self, /):
        self.__fs.rmdir(
            self.__path, 
            self.password, 
            _check=False, 
        )

    @property
    def root(self, /):
        return self.__fs.storage_of(self.__path)

    def samefile(self, path: str | PathLike[str], /) -> bool:
        return self.__path == self.joinpath(path)

    def stat(self, /):
        return self.__fs.stat(self.__path, self.password, _check=False)

    @property
    def stem(self, /):
        return splitext(basename(self.__path))[0]

    @property
    def suffix(self, /):
        return splitext(basename(self.__path))[1]

    @property
    def suffixes(self, /):
        return ["." + part for part in basename(self.__path).split(".")[1:]]

    def touch(self, /):
        self.__fs.touch(self.__path, self.password, _check=False)

    unlink = remove

    @property
    def url(self, /) -> str:
        return self.attr_refresh()["raw_url"]

    def with_name(self, name: str, /) -> AlistPath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> AlistPath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> AlistPath:
        return self.parent.joinpath(self.stem + suffix)

    def write_bytes(self, data: bytes | bytearray, /):
        bio = BytesIO(data)
        return self.__fs.upload(bio, self.__path, self.password, overwrite_or_ignore=True, _check=False)

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
        return self.__fs.upload(bio, self.__path, self.password, overwrite_or_ignore=True, _check=False)


class AlistFile(RawIOBase):
    "Open a file from the alist server."
    def __init__(
        self, 
        /, 
        path: AlistPath, 
        mode: str = "r", 
        urlopen: Callable = partial(Session().get, stream=True), 
    ):
        if mode in ("r+", "+r", "w", "w+", "+w", "a", "a+", "+a", "x", "x+", "+x"):
            raise NotImplementedError(f"Mode not currently supported: {mode!r}")
        if mode != "r":
            raise ValueError(f"invalid mode: {mode!r}")
        self.__path = path
        self.__mode = mode
        self.__urlopen = urlopen
        self.__resp = resp = urlopen(path.url, headers={"Accept-Encoding": "identity"})
        self.__seekable = resp.headers.get("Accept-Ranges") == "bytes"
        self.__size = int(resp.headers['Content-Length'])
        self.__file = resp.raw
        self.__start = 0
        self.__readable = True
        self.__writable = False
        self.__closed = False

    def __del__(self, /):
        try:
            self.close()
        except:
            pass

    def __enter__(self, /):
        return self

    def __exit__(self, /, *exc_info):
        self.close()

    def __iter__(self, /):
        return self

    def __next__(self, /) -> bytes:
        line = self.readline()
        if line:
            return line
        else:
            raise StopIteration

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(path={self.path!r}, mode={self.mode!r})"

    def close(self, /):
        self.__resp.close()
        self.__closed = True

    @property
    def closed(self, /) -> bool:
        return self.__closed

    @property
    def fileno(self, /):
        raise self.__file.fileno()

    def flush(self, /):
        return self.__file.flush()

    def isatty(self, /):
        return False

    @property
    def mode(self, /) -> str:
        return self.__mode

    @property
    def name(self, /) -> str:
        return self.__path.name

    @property
    def path(self, /) -> AlistPath:
        return self.__path

    def read(self, size: int = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return b""
        if size < 0:
            return self.__file.read()
        # If the connection breaks while reading, retry 5 times
        curpos = self.tell()
        e = None
        for _ in range(5):
            try:
                return self.__file.read(size)
            except Exception as exc:
                if e is None:
                    e = exc
                self.reconnect(curpos)
        raise cast(BaseException, e)

    def readable(self, /) -> bool:
        return self.__readable

    def readinto(self, buffer, /) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        # If the connection breaks while reading, retry 5 times
        curpos = self.tell()
        e = None
        for _ in range(5):
            try:
                return self.__file.readinto(buffer)
            except Exception as exc:
                if e is None:
                    e = exc
                self.reconnect(curpos)
        raise cast(BaseException, e)

    def readline(self, size: Optional[int] = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return b""
        if size is None:
            size = -1
        # If the connection breaks while reading, retry 5 times
        curpos = self.tell()
        e = None
        for _ in range(5):
            try:
                return self.__file.readline(size)
            except Exception as exc:
                if e is None:
                    e = exc
                self.reconnect(curpos)
        raise cast(BaseException, e)

    def readlines(self, hint: int = -1, /) -> list[bytes]:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return self.__file.readlines(hint)

    def reconnect(self, /, start: Optional[int] = None):
        if start is None:
            start = self.tell()
        elif start < 0:
            start = self.size + start
            if start < 0:
                start = 0
        self.__resp.close()
        self.__resp = resp = self.__urlopen(
            self.url, 
            headers={"Accept-Encoding": "identity", "Range": "bytes=%d-" % start}, 
        )
        self.__file = resp.raw
        self.__start = start

    def seek(self, pos: int, whence: int = 0, /) -> int:
        if not self.__seekable:
            raise TypeError("not a seekable stream")
        if whence == 0:
            if pos < 0:
                raise ValueError(f"negative seek position: {pos!r}")
            old_pos = self.tell()
            if old_pos == pos:
                return pos
            # If only moving forward within 1MB, directly read and discard
            elif old_pos < pos <= old_pos + 1024 * 1024:
                try:
                    self.__file.read(pos - old_pos)
                    return pos
                except Exception:
                    pass
            self.__resp.close()
            self.__resp = resp = self.__urlopen(
                self.url, 
                headers={"Accept-Encoding": "identity", "Range": "bytes=%d-" % pos}, 
            )
            self.__file = resp.raw
            self.__start = pos
            return pos
        elif whence == 1:
            if pos == 0:
                return self.tell()
            return self.seek(self.tell() + pos)
        elif whence == 2:
            return self.seek(self.__size + pos)
        else:
            raise ValueError(f"whence value unsupported: {whence!r}")

    def seekable(self, /) -> bool:
        return self.__seekable

    @property
    def size(self, /) -> int:
        return self.__size

    def tell(self, /) -> int:
        return self.__file.tell() + self.__start

    def truncate(self, size: Optional[int] = None, /):
        raise UnsupportedOperation("truncate")

    @property
    def url(self) -> str:
        url = self.__path.url
        assert url, "received an empty link, possibly corresponding to a directory"
        return url

    def writable(self, /) -> bool:
        return self.__writable

    def write(self, b, /) -> int:
        raise UnsupportedOperation("write")

    def writelines(self, lines, /):
        raise UnsupportedOperation("writelines")


class AlistFileSystem:
    """Implemented some file system methods by utilizing alist's web API 
    and referencing modules such as `os` and `shutil`."""
    def __init__(
        self, 
        /, 
        client: AlistClient, 
        path: str = "/", 
        refresh: bool = False, 
    ):
        self.__client = client
        if path in ("", "/", ".", ".."):
            self.__path = "/"
        else:
            self.__path = "/" + normpath("/" + path).lstrip("/")
        self.refresh = refresh

    def __iter__(self, /):
        return self.iterdir(max_depth=-1)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self.__client!r}, path={self.__path!r})"

    def _check_get_data(self, resp: dict, /) -> Optional[dict]:
        code = resp["code"]
        if code == 403:
            raise AuthenticationError(resp)
        elif code == 500:
            message = resp["message"]
            if message.startswith("failed get storage"):
                raise PermissionError(1, resp)
            elif message == "object not found":
                raise FileNotFoundError(2, resp)
            elif message == "file exists":
                raise FileExistsError(17, resp)
            else:
                raise AlistOSError(resp)
        elif not 200 <= code < 300:
            raise AlistOSError(resp)
        return resp.get("data")

    def abspath(self, /, path: str | PathLike[str] = "") -> str:
        if path in ("", "."):
            return self.__path
        return normpath(joinpath(self.__path, path))

    def attr(
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
        resp = self.client.fs_get(payload)
        code = resp["code"]
        if 200 <= code < 300:
            data = resp["data"]
            data.setdefault("path", path)
            return data
        elif code == 500:
            raise FileNotFoundError(2, path) from AlistOSError(resp)
        elif code == 403:
            raise AuthenticationError(resp)
        else:
            raise AlistOSError(resp)

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
        attr = self.attr(path, password, _check=False)
        if attr["is_dir"]:
            self.__path = path
        else:
            raise NotADirectoryError(20, path)

    @property
    def client(self, /) -> AlistClient:
        return self.__client

    def copy(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        overwrite: bool = True, 
        _check: bool = True, 
    ):
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            raise SameFileError(src_path)
        src_attr = self.attr(src_path, src_password, _check=False)
        if src_attr["is_dir"]:
            raise IsADirectoryError(21, f"source path {src_path!r} is a directory")
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            pass
        else:
            if dst_attr["is_dir"]:
                raise IsADirectoryError(21, f"destination path {src_path!r} is a directory")
            elif not overwrite:
                raise FileExistsError(17, f"destination path {dst_path!r} already exists")
            self.fs_remove([basename(dst_path)], dirname(dst_path), _check=False)
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        if src_name == dst_name:
            self.fs_copy(src_dir, dst_dir, [src_name], _check=False)
        else:
            src_storage = self.storage_of(src_dir, _check=False)
            dst_storage = self.storage_of(dst_dir, _check=False)
            if src_storage != dst_storage:
                raise PermissionError(1, f"copying does not allow renaming when across 2 storages: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}")
            tempdirname = str(uuid4())
            tempdir = joinpath(dst_dir, tempdirname)
            self.fs_mkdir(tempdir, _check=False)
            try:
                self.fs_copy(src_dir, tempdir, [src_name], _check=False)
                self.fs_rename(joinpath(tempdir, src_name), dst_name, _check=False)
                self.fs_move(tempdir, dst_dir, [dst_name], _check=False)
            finally:
                self.fs_remove([tempdirname], dst_dir, _check=False)

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
        if src_path == dst_dir:
            raise SameFileError(src_path)
        if dst_dir.startswith(src_path):
            raise PermissionError(1, f"copying a path to its subordinate path is not allowed: {src_path!r} -> {dst_dir!r}")
        if not self.attr(dst_dir, dst_password, _check=False)["is_dir"]:
            raise NotADirectoryError(20, dst_dir)
        self.fs_copy(dirname(src_path), dst_dir, [basename(src_path)])
        return dst_dir

    def download(
        self, 
        /, 
        path: str | PathLike[str], 
        local_path_or_file: str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        password: str = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.attr(path, password, _check=False)
        if attr["is_dir"]:
            raise IsADirectoryError(21, path)
        url = attr["raw_url"]
        file: SupportsWrite
        if hasattr(local_path_or_file, "write"):
            file = cast(SupportsWrite[bytes] | TextIOWrapper, local_path_or_file)
            if isinstance(file, TextIOWrapper):
                file = file.buffer
        else:
            if overwrite_or_ignore is None:
                mode = "xb"
            elif overwrite_or_ignore:
                mode = "wb"
            else:
                if os_path.lexists(local_path_or_file):
                    return
            if local_path_or_file:
                file = open(local_path_or_file, mode)
            else:
                file = open(basename(path), mode)
        copyfileobj(urlopen(url), file)

    def download_tree(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        dir_: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
            if refresh is None:
                refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        attr = self.attr(path, password, _check=False)
        makedirs(dir_, exist_ok=True)
        if attr["is_dir"]:
            if not no_root:
                dir_ = os_path.join(dir_, basename(path))
            for apath in self.listdir_attr(path, password, refresh=refresh, _check=False):
                if apath["is_dir"]:
                    self.download_tree(
                        apath.path, 
                        os_path.join(dir_, apath.name), 
                        password, 
                        refresh=refresh, 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.download(
                        apath.path, 
                        os_path.join(dir_, apath.name), 
                        password, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                os_path.join(dir_, basename(path)), 
                password, 
                overwrite_or_ignore=overwrite_or_ignore, 
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

    def fs_batch_rename(
        self, 
        /, 
        rename_pairs: Iterable[tuple[str, str]], 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> Optional[dict]:
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
        return self._check_get_data(self.client.fs_batch_rename(payload))

    def fs_copy(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            src_dir = self.abspath(src_dir)
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self._check_get_data(self.client.fs_copy(payload))

    def fs_dirs(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Optional[dict]:
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
        resp = self.client.fs_dirs(payload)
        code = resp["code"]
        if code == 500:
            raise FileNotFoundError(2, path) from AlistOSError(resp)
        elif not 200 <= code < 300:
            raise AlistOSError(resp)
        return resp["data"]

    def fs_form(
        self, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self._check_get_data(
            self.client.fs_form(local_path_or_file, path, as_task=as_task)
        )

    def fs_get(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "password": password}
        return self._check_get_data(self.client.fs_get(payload))

    def fs_list(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> Optional[dict]:
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
        resp = self.client.fs_list(payload)
        code = resp["code"]
        if code == 500:
            message = resp["message"]
            if message.endswith("not found"):
                raise FileNotFoundError(2, path) from AlistOSError(resp)
            elif "not a folder" in resp["message"]:
                raise NotADirectoryError(20, path) from AlistOSError(resp)
            else:
                raise AlistOSError(resp)
        elif not 200 <= code < 300:
            raise AlistOSError(resp)
        return resp["data"]

    def fs_mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return None
        resp = self.client.fs_mkdir({"path": path})
        if resp["code"] == 500:
            if resp["message"] == "file exists":
                raise FileExistsError(17, path) from AlistOSError(resp)
            raise PermissionError(1, f"failed to create directory: {path!r}") from AlistOSError(resp)
        elif not 200 <= resp["code"] < 300:
            raise AlistOSError(path)
        return resp

    def fs_move(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> Optional[dict]:
        if not names:
            return None
        if _check:
            src_dir = self.abspath(src_dir)
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        if src_dir == dst_dir:
            return None
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self._check_get_data(self.client.fs_move(payload))

    def fs_put(
        self, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self._check_get_data(
            self.client.fs_put(local_path_or_file, path, as_task=as_task)
        )

    def fs_recursive_move(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            src_dir = self.abspath(src_dir)
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir}
        return self._check_get_data(self.client.fs_recursive_move(payload))

    def fs_regex_rename(
        self, 
        /, 
        src_name_regex: str, 
        new_name_regex: str, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "src_dir": src_dir, 
            "src_name_regex": src_name_regex, 
            "new_name_regex": new_name_regex, 
        }
        return self._check_get_data(self.client.fs_regex_rename(payload))

    def fs_remove(
        self, 
        /, 
        names: list[str], 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> Optional[dict]:
        if not names:
            return None
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"names": names, "dir": src_dir}
        return self._check_get_data(self.client.fs_remove(payload))

    def fs_remove_empty_directory(
        self, 
        /, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"src_dir": src_dir}
        return self._check_get_data(self.client.fs_remove_empty_directory(payload))

    def fs_rename(
        self, 
        /, 
        path: str | PathLike[str], 
        name: str, 
        _check: bool = True, 
    ) -> Optional[dict]:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "name": name}
        return self._check_get_data(self.client.fs_rename(payload))

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
    ) -> Optional[dict]:
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
        return self._check_get_data(self.client.fs_search(payload))

    def getcwd(self, /) -> str:
        return self.__path

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
        if not attr["is_dir"]:
            return attr["size"] == 0
        data = self.fs_list(path, password, per_page=1, _check=False)
        return not data or data["total"] == 0

    def is_storage(self, path, _check: bool = True):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.storage_of(path) == path

    def iterdir(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
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
        if max_depth > 0:
            max_depth -= 1
        for path in ls:
            yield_me = True
            if predicate:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred
            if topdown and yield_me:
                yield path
            if path["is_dir"]:
                yield from self.iterdir(
                    joinpath(top, path.name), 
                    password, 
                    refresh=refresh, 
                    topdown=topdown, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    _check=_check, 
                )
            if not topdown and yield_me:
                yield path

    def list_storages(self, /) -> list[dict]:
        return self._check_get_data(self.__client.admin_storage_list())["content"] # type: ignore

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
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.attr(path, password)["is_dir"]:
            raise NotADirectoryError(20, path)
        data = self.fs_list(path, password, refresh=refresh, page=page, per_page=per_page, _check=False)
        if not data or data["total"] == 0:
            return []
        return [item["name"] for item in data["content"]]

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
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.attr(path, password)["is_dir"]:
            raise NotADirectoryError(20, path)
        data = self.fs_list(path, password, refresh=refresh, page=page, per_page=per_page, _check=False)
        if not data or data["total"] == 0:
            return []
        return [AlistPath(self, joinpath(path, item["name"]), password, item) for item in data["content"]]

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
            raise FileExistsError(17, path)
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
            raise PermissionError(1, "creating root directory is not allowed (because it has always existed)")
        try:
            self.attr(path, password, _check=False)
        except FileNotFoundError as e:
            if not self.attr(dirname(path), password, _check=False)["is_dir"]:
                raise NotADirectoryError(20, dirname(path)) from e
            self.fs_mkdir(path, _check=False)
        else:
            raise FileExistsError(17, path)

    def move(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> Optional[str]:
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            raise SameFileError(src_path)
        if dst_path.startswith(src_path):
            raise PermissionError(1, f"moving a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
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
                    raise FileExistsError(17, f"destination path {dst_filepath!r} already exists")
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

    @property
    def path(self, /) -> str:
        return self.__path

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
            raise PermissionError(1, "removing the root directory is not allowed")
        attr = self.attr(path, password, _check=False)
        if attr["is_dir"]:
            if not recursive:
                raise IsADirectoryError(21, path)
            elif self.is_storage(path, _check=False):
                raise PermissionError(1, f"removing storage is not allowed: {path!r}")
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
        _check: bool = True, 
        _for_renames: bool = False, 
    ):
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            return
        if src_path == "/" or dst_path == "/":
            raise OSError(22, f"invalid argument: {src_path!r} -> {dst_path!r}")
        if dst_path.startswith(src_path):
            raise PermissionError(1, f"moving a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        if self.is_storage(src_path):
            raise PermissionError(1, f"renaming a storage is not allowed")
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        src_attr = self.attr(src_path, src_password, _check=False)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            if not _for_renames and not self.attr(dst_dir, dst_password, _check=False)["is_dir"]:
                raise NotADirectoryError(20, f"not a directory: {src_path!r} -> {dst_path!r}")
        else:
            raise FileExistsError(17, f"destination path already exists: {src_path!r} -> {dst_path!r}")
        if src_name == dst_name:
            self.fs_move(src_dir, dst_dir, [src_name], _check=False)
        elif src_dir == dst_dir:
            self.fs_rename(src_path, dst_name, _check=False)
        else:
            src_storage = self.storage_of(src_dir, _check=False)
            dst_storage = self.storage_of(dst_dir, _check=False)
            if src_storage != dst_storage:
                raise PermissionError(1, f"moving does not allow renaming when across 2 storages: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}")
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
        self.rename(src_path, dst_path, src_password, dst_password, _for_renames=True, _check=False)
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
        if _check:
            src_path = self.abspath(src_path)
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            return
        if dst_path.startswith(src_path):
            raise PermissionError(1, f"moving a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        src_attr = self.attr(src_path, src_password, _check=False)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            if not self.attr(dirname(dst_path), dst_password, _check=False)["is_dir"]:
                raise NotADirectoryError(20, f"Not a directory: {src_path!r} -> {dst_path!r}")
        else:
            if src_attr["is_dir"]:
                if dst_attr["is_dir"]:
                    if not self.is_empty(dst_path, dst_password, _check=False):
                        raise OSError(66, f"Directory not empty: {src_path!r} -> {dst_path!r}")
                else:
                    raise NotADirectoryError(20, f"Not a directory: {src_path!r} -> {dst_path!r}")
            elif dst_attr["is_dir"]:
                raise IsADirectoryError(21, f"Is a directory: {src_path!r} -> {dst_path!r}")
            self.fs_remove([dst_name], dst_dir, _check=False)
        if src_name == dst_name:
            self.fs_move(src_dir, dst_dir, [src_name], _check=False)
        elif src_dir == dst_dir:
            self.fs_rename(src_path, dst_name, _check=False)
        else:
            src_storage = self.storage_of(src_dir, _check=False)
            dst_storage = self.storage_of(dst_dir, _check=False)
            if src_storage != dst_storage:
                raise PermissionError(1, f"moving does not allow renaming when across 2 storages: [{src_storage!r}]{src_path!r} -> [{dst_storage!r}]{dst_path!r}")
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
            raise PermissionError(1, "removing the root directory is not allowed")
        if _check and not self.attr(path, password, _check=False)["is_dir"]:
            raise NotADirectoryError(20, path)
        if not self.is_empty(path, password, _check=False):
            raise OSError(66, f"directory not empty: {path!r}")
        self.fs_remove([basename(path)], dirname(path), _check=False)

    def rmtree(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(1, "removing the root directory is not allowed")
        if self.is_storage(path, _check=False):
            raise PermissionError(1, f"removing storage is not allowed: {path!r}")
        self.fs_remove([basename(path)], dirname(path), _check=False)

    def scandir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ):
        raise NotImplementedError(
            "`scandir()` is currently not supported, use `listdir_attr()` instead."
        )

    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ):
        raise NotImplementedError(
            "`stat()` is currently not supported, use `attr()` instead."
        )

    def storage_of(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if _check:
            path = self.abspath(path)
        path = cast(str, path)
        storage = "/"
        for s in self.list_storages():
            mount_path = s["mount_path"]
            if path == mount_path:
                return mount_path
            elif path.startswith(mount_path+"/") and len(mount_path) > len(storage):
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
            if not self.isdir(dirname(path), password, _check=False):
                raise FileNotFoundError(2, path)
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
        if hasattr(local_path_or_file, "read"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if not path:
                try:
                    path = os_path.basename(file.name) # type: ignore
                except AttributeError as e:
                    raise AlistOSError("Please specify the upload path") from e
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
                raise FileExistsError(17, path)
            elif attr["is_dir"]:
                raise IsADirectoryError(21, path)
            elif not overwrite_or_ignore:
                return
            self.fs_remove([basename(path)], dirname(path), _check=False)
        #self.fs_put(file, path, as_task=as_task, _check=False)
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
            raise NotADirectoryError(20, path)
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
            data = self.fs_list(top, password, refresh=refresh, _check=False)
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
        if topdown:
            yield top, dirs, files
        if max_depth > 0:
            max_depth -= 1
        for dir_ in dirs:
            yield from self.walk(
                joinpath(top, dir_), 
                password, 
                refresh=refresh, 
                topdown=topdown, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if not topdown:
            yield top, dirs, files

    def walk_attr(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        topdown: bool = True, 
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
        if topdown:
            yield top, dirs, files
        if max_depth > 0:
            max_depth -= 1
        for dir_ in dirs:
            yield from self.walk_attr(
                joinpath(top, dir_.name), 
                password, 
                refresh=refresh, 
                topdown=topdown, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if not topdown:
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
