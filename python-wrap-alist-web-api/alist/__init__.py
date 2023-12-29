#!/usr/bin/env python3
# encoding: utf-8

"""Python AList web api wrapper.

This is a web api wrapper works with the running "alist" server, and provide some methods, 
which refer to `os`, `posixpath`, `pathlib.Path` and `shutil` modules.

- AList web api official documentation: https://alist.nn.ci/guide/api/
- AList web api online tool: https://alist-v3.apifox.cn
"""

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 9)
__all__ = ["AlistClient", "AlistPath", "AlistFileSystem"]

import errno

from asyncio import run
from collections.abc import Callable, ItemsView, Iterable, Iterator, KeysView, Mapping, ValuesView
from datetime import datetime
from functools import cached_property, partial, update_wrapper
from inspect import isawaitable
from io import BytesIO, TextIOWrapper, UnsupportedOperation
from json import loads
from os import fsdecode, fspath, fstat, makedirs, scandir, stat_result, path as ospath, PathLike
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError
from stat import S_IFDIR, S_IFREG
from typing import cast, Any, IO, Literal, Never, Optional
from types import MappingProxyType, MethodType
from urllib.parse import quote
from uuid import uuid4
from warnings import filterwarnings, warn

from aiohttp import ClientSession
from dateutil.parser import parse as parse_datetime
from requests import Session

from .util.file import HTTPFileReader, SupportsRead, SupportsWrite
from .util.response import get_content_length
from .util.text import complete_base_url, posix_glob_translate_iter
from .util.urlopen import urlopen


filterwarnings("ignore", category=DeprecationWarning)


class method:

    def __init__(self, func: Callable, /):
        self.__func__ = func

    def __get__(self, instance, type=None, /):
        if instance is None:
            return self
        return MethodType(self.__func__, instance)

    def __set__(self, instance, value, /):
        raise TypeError("can't set value")


def check_response(func, /):
    def wrapper(*args, **kwds):
        resp = func(*args, **kwds)
        fargs = (func, args, kwds)
        code = resp["code"]
        if 200 <= code < 300:
            return resp
        elif code == 403:
            raise PermissionError(errno.EACCES, resp, fargs)
        elif code == 500:
            message = resp["message"]
            if (message.endswith("object not found") 
                or message.startswith("failed get storage: storage not found")
            ):
                raise FileNotFoundError(errno.ENOENT, resp, fargs)
            elif resp["message"].endswith("not a folder"):
                raise NotADirectoryError(errno.ENOTDIR, resp, fargs)
            elif message.endswith("file exists"):
                raise FileExistsError(errno.EEXIST, resp, fargs)
            elif message.startswith("failed get "):
                raise PermissionError(errno.EPERM, resp, fargs)
        raise OSError(errno.EIO, resp, fargs)
    return update_wrapper(wrapper, func)


class AlistClient:
    """AList client that encapsulates web APIs

    - AList web api official documentation: https://alist.nn.ci/guide/api/
    - AList web api online tool: https://alist-v3.apifox.cn
    """
    origin: str
    username: str
    password: str
    session: Session
    async_session: ClientSession

    def __init__(self, /, origin: str = "http://localhost:5244", username: str = "", password: str = ""):
        self.__dict__.update(
            origin=complete_base_url(origin), 
            username=username, 
            password=password, 
            session=Session(), 
            async_session=ClientSession(raise_for_status=True), 
        )
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.origin == other.origin and self.username == other.username

    def __hash__(self, /) -> int:
        return hash((self.origin, self.username))

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self.origin!r}, username={self.username!r}, password='******')"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def close(self, /):
        try:
            self.session.close()
        except:
            pass
        try:
            run(self.async_session.close())
        except:
            pass

    def set_password(self, value, /):
        self.__dict__["password"] = str(value)
        self.login()

    def _request(
        self, 
        api: str, 
        /, 
        method: str = "POST", 
        parse: bool | Callable = False, 
        **request_kwargs, 
    ):
        if not api.startswith("/"):
            api = "/" + api
        url = self.origin + api
        request_kwargs["stream"] = True
        resp = self.session.request(method, url, **request_kwargs)
        resp.raise_for_status()
        if callable(parse):
            with resp:
                return parse(resp.content)
        elif parse:
            with resp:
                content_type = resp.headers.get("Content-Type", "")
                if content_type == "application/json":
                    return resp.json()
                elif content_type.startswith("application/json;"):
                    return loads(resp.text)
                elif content_type.startswith("text/"):
                    return resp.text
                return resp.content
        return resp

    def _async_request(
        self, 
        api: str, 
        /, 
        method: str = "POST", 
        parse: bool | Callable = False, 
        **request_kwargs, 
    ):
        if not api.startswith("/"):
            api = "/" + api
        url = self.origin + api
        request_kwargs.pop("stream", None)
        req = self.async_session.request(method, url, **request_kwargs)
        if callable(parse):
            async def request():
                async with req as resp:
                    ret = parse(await resp.read())
                    if isawaitable(ret):
                        ret = await ret
                    return ret
            return request()
        elif parse:
            async def request():
                async with req as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    if content_type == "application/json":
                        return await resp.json()
                    elif content_type.startswith("application/json;"):
                        return loads(await resp.text())
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
        parse: bool | Callable = True, 
        async_: bool = False, 
        **request_kwargs, 
    ):
        return (self._async_request if async_ else self._request)(
            api, method, parse=parse, **request_kwargs)

    def login(
        self, 
        /, 
        username: str = "", 
        password: str = "", 
        **request_kwargs, 
    ):
        ns = self.__dict__
        if username:
            ns["username"] = username
        else:
            username = ns["username"]
        if password:
            ns["password"] = password
        else:
            password = ns["password"]
        if username:
            request_kwargs["async_"] = False
            resp = self.auth_login(
                {"username": username, "password": password}, 
                **request_kwargs, 
            )
            if not 200 <= resp["code"] < 300:
                raise PermissionError(errno.EACCES, resp)
            self.async_session.headers["Authorization"] = self.session.headers["Authorization"] = resp["data"]["token"]
        else:
            self.session.headers.pop("Authorization", None)
            self.async_session.headers.pop("Authorization", None)

    # [auth](https://alist.nn.ci/guide/api/auth.html)

    def auth_login(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-token获取"
        return self.request(
            "/api/auth/login", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def auth_login_hash(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-token获取hash"
        return self.request(
            "/api/auth/login/hash", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def auth_2fa_generate(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-生成2fa密钥"
        return self.request(
            "/api/auth/2fa/generate", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#post-生成2fa密钥"
        return self.request(
            "/api/auth/2fa/verify", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def auth_me(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/auth.html#get-获取当前用户信息"
        return self.request(
            "/api/me", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    # [fs](https://alist.nn.ci/guide/api/fs.html)

    def fs_list(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-列出文件目录"
        return self.request(
            "/api/fs/list", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_get(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-获取某个文件-目录信息"
        return self.request(
            "/api/fs/get", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_dirs(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-获取目录"
        return self.request(
            "/api/fs/dirs", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_search(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-搜索文件或文件夹"
        return self.request(
            "/api/fs/search", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_mkdir(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-新建文件夹"
        return self.request(
            "/api/fs/mkdir", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # NOTE: AList 改名的限制：
    #   1. 受到网盘的改名限制，例如如果挂载的是 115，就不能包含特殊符号 " < > ，也不能改扩展名，各个网盘限制不同
    #   2. 可以包含斜杠  \，但是改名后，这个文件不能被删改了，因为只能被罗列，但不能单独找到
    #   3. 名字里（basename）中包含 /，会被替换为 |
    def fs_rename(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-重命名文件"
        return self.request(
            "/api/fs/rename", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_batch_rename(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-批量重命名"
        return self.request(
            "/api/fs/batch_rename", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_regex_rename(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-正则重命名"
        return self.request(
            "/api/fs/regex_rename", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_form(
        self, 
        /, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        remote_path: str, 
        as_task: bool = False, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#put-表单上传文件"
        headers = request_kwargs.setdefault("headers", {})
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
            **request_kwargs, 
        )

    def fs_move(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-移动文件"
        return self.request(
            "/api/fs/move", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_copy(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-复制文件"
        return self.request(
            "/api/fs/copy", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_remove(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-删除文件或文件夹"
        return self.request(
            "/api/fs/remove", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_remove_empty_directory(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-删除空文件夹"
        return self.request(
            "/api/fs/remove_empty_directory", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_recursive_move(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-聚合移动"
        return self.request(
            "/api/fs/recursive_move", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # NOTE: AList 上传时的问题：
    #   1. 上传文件成功不会更新缓存，但新增文件夹会更新缓存
    #   2. 上传时路径中包含斜杠 \，视为路径分隔符 /
    #   3. put 接口是流式上传，但是不支持 chunked，目前用 requests 上传空文件为处理为 chunked，会报错，这是 requests 的问题
    def fs_put(
        self, 
        /, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        remote_path: str, 
        as_task: bool = False, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#put-流式上传文件"
        headers = request_kwargs.setdefault("headers", {})
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
            **request_kwargs, 
        )

    def fs_add_aria2(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-添加aria2下载"
        return self.request(
            "/api/fs/add_aria2", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_add_qbit(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/fs.html#post-添加qbittorrent下载"
        return self.request(
            "/api/fs/add_qbit", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [public](https://alist.nn.ci/guide/api/public.html)

    def public_settings(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/public.html#get-获取站点设置"
        return self.request(
            "/api/public/settings", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    def public_ping(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> str:
        "https://alist.nn.ci/guide/api/public.html#get-ping检测"
        return self.request(
            "/ping", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin](https://alist.nn.ci/guide/api/admin/)

    # [admin/meta](https://alist.nn.ci/guide/api/admin/meta.html)

    def admin_meta_list(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#get-列出元信息"
        return self.request(
            "/api/admin/meta/list", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_meta_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#get-获取元信息"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/meta/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_meta_create(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#post-新增元信息"
        return self.request(
            "/api/admin/meta/create", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_meta_update(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#post-更新元信息"
        return self.request(
            "/api/admin/meta/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_meta_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/meta.html#post-删除元信息"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/meta/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/user](https://alist.nn.ci/guide/api/admin/user.html)

    def admin_user_list(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#get-列出所有用户"
        return self.request(
            "/api/admin/user/list", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_user_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#get-列出某个用户"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/user/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_user_create(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-新建用户"
        return self.request(
            "/api/admin/user/create", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_user_update(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-更新用户信息"
        return self.request(
            "/api/admin/user/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_user_cancel_2fa(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-取消某个用户的两步验证"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/user/cancel_2fa", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_user_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-删除用户"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/user/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_user_del_cache(
        self, 
        /, 
        payload: str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/user.html#post-删除用户缓存"
        if isinstance(payload, str):
            payload = {"username": payload}
        return self.request(
            "/api/admin/user/del_cache", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/storage](https://alist.nn.ci/guide/api/admin/storage.html)

    def admin_storage_list(
        self, 
        /, 
        payload: dict = {"page": 1, "per_page": 0}, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#get-列出存储列表"
        return self.request(
            "/api/admin/storage/list", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_storage_enable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-启用存储"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/enable", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_storage_disable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-禁用存储"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/disable", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-新增存储"
        return self.request(
            "/api/admin/storage/create", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-更新存储"
        return self.request(
            "/api/admin/storage/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_storage_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#get-查询指定存储信息"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_storage_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-删除指定存储"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_storage_load_all(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/storage.html#post-重新加载所有存储"
        return self.request(
            "/api/admin/storage/load_all", 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/driver](https://alist.nn.ci/guide/api/admin/driver.html)

    def admin_driver_list(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/driver.html#get-查询所有驱动配置模板列表"
        return self.request(
            "/api/admin/driver/list", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_driver_names(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/driver.html#get-列出驱动名列表"
        return self.request(
            "/api/admin/driver/names", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_driver_info(
        self, 
        /, 
        payload: str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/driver.html#get-列出特定驱动信息"
        if isinstance(payload, str):
            payload = {"driver": payload}
        return self.request(
            "/api/admin/driver/info", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/setting](https://alist.nn.ci/guide/api/admin/setting.html)

    def admin_setting_list(
        self, 
        /, 
        payload: dict = {}, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#get-列出设置"
        return self.request(
            "/api/admin/setting/list", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_setting_get(
        self, 
        /, 
        payload: dict = {}, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#get-获取某项设置"
        return self.request(
            "/api/admin/setting/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_setting_save(
        self, 
        /, 
        payload: list[dict], 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-保存设置"
        return self.request(
            "/api/admin/setting/save", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_setting_delete(
        self, 
        /, 
        payload: str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-删除设置"
        if isinstance(payload, str):
            payload = {"key": payload}
        return self.request(
            "/api/admin/setting/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_setting_reset_token(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-重置令牌"
        return self.request(
            "/api/admin/setting/reset_token", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_setting_set_aria2(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-设置aria2"
        return self.request(
            "/api/admin/setting/set_aria2", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_setting_set_qbit(
        self, 
        /, 
        payload: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/setting.html#post-设置qbittorrent"
        return self.request(
            "/api/admin/setting/set_qbit", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/task](https://alist.nn.ci/guide/api/admin/task.html)

    def admin_task_upload_done(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/upload/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_task_upload_undone(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/upload/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_task_upload_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/upload/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_task_upload_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/upload/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_task_upload_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/upload/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_task_upload_clear_done(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/upload/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    def admin_task_upload_clear_succeeded(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/upload/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    ########## Other Encapsulations ##########

    @cached_property
    def fs(self, /) -> AlistFileSystem:
        return AlistFileSystem(self)

    def get_url(self, /, path: str) -> str:
        return self.origin + "/d" + quote(path, safe=":/?&=#")

    @staticmethod
    def open(
        url: str | Callable[[], str], 
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        **request_kwargs, 
    ) -> HTTPFileReader:
        """
        """
        _urlopen = urlopen
        if request_kwargs:
            _urlopen = partial(urlopen, **request_kwargs)
        return HTTPFileReader(
            url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
            urlopen=_urlopen, 
        )

    @staticmethod
    def read_bytes(
        url: str, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
        **request_kwargs, 
    ) -> bytes:
        """
        """
        length = None
        if start < 0:
            with urlopen(url) as resp:
                length = get_content_length(urlopen(url))
            if length is None:
                raise OSError(errno.ESPIPE, "can't determine content length")
            start += length
        if start < 0:
            start = 0
        if stop is None:
            bytes_range = f"{start}-"
        else:
            if stop < 0:
                if length is None:
                    with urlopen(url) as resp:
                        length = get_content_length(urlopen(url))
                if length is None:
                    raise OSError(errno.ESPIPE, "can't determine content length")
                stop += length
            if stop <= 0 or start >= stop:
                return b""
            bytes_range = f"{start}-{stop-1}"
        return __class__.read_bytes_range(url, bytes_range, headers=headers, **request_kwargs) # type: ignore

    @staticmethod
    def read_bytes_range(
        url: str, 
        bytes_range: str = "0-", 
        headers: Optional[Mapping] = None, 
        **request_kwargs, 
    ) -> bytes:
        """
        """
        if headers:
            headers = {**headers, "Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        else:
            headers = {"Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        with urlopen(url, headers=headers, **request_kwargs) as resp:
            if resp.status == 416:
                return b""
            return resp.read()

    @staticmethod
    def read_block(
        url: str, 
        size: int = 0, 
        offset: int = 0, 
        headers: Optional[Mapping] = None, 
        **request_kwargs, 
    ) -> bytes:
        """
        """
        if size <= 0:
            return b""
        return __class__.read_bytes(url, offset, offset+size, headers=headers, **request_kwargs) # type: ignore


class AlistPath(Mapping, PathLike[str]):
    "AList path information."
    fs: AlistFileSystem
    path: str
    password: str = ""

    def __init__(
        self, 
        /, 
        fs: AlistFileSystem, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        **attr, 
    ):
        attr.update(fs=fs, path=fs.abspath(path), password=password)
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> AlistPath:
        return type(self)(
            self.fs, 
            commonpath((self.path, self.fs.abspath(path))), 
            password=self.password, 
        )

    def __call__(self, /) -> AlistPath:
        self.__dict__.update(self.fs.attr(self))
        return self

    def __contains__(self, key, /) -> bool:
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.__dict__.get("lastest_update"):
            self()
        return self.__dict__[key]

    def __ge__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __gt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __hash__(self, /) -> int:
        return hash((self.fs.client, self.path))

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __lt__(self, path, /) -> bool:
        if type(self) is not type(path) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}({', '.join(f'{k}={v!r}' for k, v in self.__dict__.items())})>"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> AlistPath:
        return self.joinpath(path)

    def set_password(self, value, /):
        self.__dict__["password"] = str(value)

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

    def copy(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> Optional[AlistPath]:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.copy(
            self, 
            dst_path, 
            dst_password=dst_password, 
            overwrite_or_ignore=overwrite_or_ignore, 
        )
        if not dst:
            return None
        return type(self)(self.fs, dst, dst_password)

    def copytree(
        self, 
        /, 
        dst_dir: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.copytree(
            self, 
            dst_dir, 
            dst_password=dst_password, 
        )
        return type(self)(self.fs, dst, dst_password)

    def download(
        self, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        refresh: Optional[bool] = None, 
    ):
        return self.fs.download_tree(
            self, 
            local_dir, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
            refresh=refresh, 
        )

    def exists(self, /) -> bool:
        return self.fs.exists(self)

    def get_url(self, /) -> str:
        return self.fs.get_url(self)

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
    ) -> Iterator[AlistPath]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case
        )

    def is_absolute(self, /) -> bool:
        return True

    @method
    def is_dir(self, /) -> bool:
        try:
            return self["is_dir"]
        except FileNotFoundError:
            return False

    def is_file(self, /) -> bool:
        try:
            return not self["is_dir"]
        except FileNotFoundError:
            return False

    def is_symlink(self, /) -> bool:
        return False

    def isdir(self, /) -> bool:
        return self.fs.isdir(self)

    def isfile(self, /) -> bool:
        return self.fs.isfile(self)

    def iter(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        refresh: Optional[bool] = None, 
    ) -> Iterator[AlistPath]:
        return self.fs.iter(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def joinpath(self, *paths: str | PathLike[str]) -> AlistPath:
        if not paths:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new, self.password)

    def listdir(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        refresh: Optional[bool] = None, 
    ) -> list[str]:
        return self.fs.listdir(
            self, 
            page=page, 
            per_page=per_page, 
            refresh=refresh, 
        )

    def listdir_attr(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        refresh: Optional[bool] = None, 
    ) -> list[dict]:
        return self.fs.listdir_attr(
            self, 
            page=page, 
            per_page=per_page, 
            refresh=refresh, 
        )

    def listdir_path(
        self, 
        /, 
        page: int = 1, 
        per_page: int = 0, 
        refresh: Optional[bool] = None, 
    ) -> list[AlistPath]:
        return self.fs.listdir_path(
            self, 
            page=page, 
            per_page=per_page, 
            refresh=refresh, 
        )

    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
    ) -> bool:
        pattern = "/" + "".join(t[0] for t in posix_glob_translate_iter(path_pattern))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

    def mkdir(self, /, exist_ok: bool = True):
        self.fs.makedirs(self, exist_ok=exist_ok)

    def move(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.move(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    @cached_property
    def name(self, /) -> str:
        return basename(self.path)

    def open(
        self, 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        headers: Optional[Mapping] = None, 
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

    @cached_property
    def parent(self, /) -> AlistPath:
        path = self.path
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path), self.password)

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

    def read_bytes(self, /, start: int = 0, stop: Optional[int] = None) -> bytes:
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
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ) -> str:
        return self.fs.read_text(self, encoding=encoding, errors=errors, newline=newline)

    def remove(self, /, recursive: bool = True):
        self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.rename(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def renames(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.renames(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
        dst_password: Optional[str] = None, 
    ) -> AlistPath:
        if dst_password is None:
            dst_password = self.password
        dst = self.fs.replace(
            self, 
            dst_path, 
            dst_password=dst_password, 
        )
        if self.path == dst:
            return self
        return type(self)(self.fs, dst, dst_password)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
    ) -> Iterator[AlistPath]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def rmdir(self, /):
        self.fs.rmdir(self)

    @property
    def root(self, /) -> AlistPath:
        return type(self)(
            self.fs, 
            self.fs.storage_of(self), 
            self.password, 
        )

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if type(self) is type(path):
            return self == path
        return path in ("", ".") or self.path == self.fs.abspath(path)

    def stat(self, /) -> stat_result:
        return self.fs.stat(self)

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
        self.fs.touch(self)

    unlink = remove

    @cached_property
    def url(self, /) -> str:
        return self.fs.get_url(self)

    @property
    def raw_url(self, /) -> str:
        return self["raw_url"]

    def walk(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: Optional[bool] = None, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        return self.fs.walk(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def walk_path(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        refresh: Optional[bool] = None, 
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        return self.fs.walk_path(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            refresh=refresh, 
        )

    def with_name(self, name: str, /) -> AlistPath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> AlistPath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> AlistPath:
        return self.parent.joinpath(self.stem + suffix)

    def write_bytes(
        self, 
        /, 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
    ):
        self.fs.write_bytes(self, data)

    def write_text(
        self, 
        /, 
        text: str = "", 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ):
        self.fs.write_text(
            self, 
            text, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )


class AlistFileSystem:
    """Implemented some file system methods by utilizing AList's web api and 
    referencing modules such as `os`, `posixpath`, `pathlib.Path` and `shutil`."""
    client: AlistClient
    path: str
    refresh: bool
    request_kwargs: dict

    def __init__(
        self, 
        /, 
        client: AlistClient, 
        path: str | PathLike[str] = "/", 
        refresh: bool = False, 
        request_kwargs: Optional[dict] = None, 
    ):
        if path in ("", "/", ".", ".."):
            path = "/"
        else:
            path = "/" + normpath("/" + fspath(path)).lstrip("/")
        if request_kwargs is None:
            request_kwargs = {}
        self.__dict__.update(client=client, path=path, refresh=refresh, request_kwargs=request_kwargs)

    def __contains__(self, path: str | PathLike[str], /) -> bool:
        return self.exists(path)

    def __delitem__(self, path: str | PathLike[str], /):
        self.rmtree(path)

    def __getitem__(self, path: str | PathLike[str], /) -> AlistPath:
        return self.as_path(path)

    def __iter__(self, /) -> Iterator[AlistPath]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, path: str | PathLike[str], /) -> AlistFileSystem:
        self.chdir(path)
        return self

    def __len__(self, /) -> int:
        return self.get_directory_capacity(self.path, _check=False)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self.client!r}, path={self.path!r}, refresh={self.refresh!r}, request_kwargs={self.request_kwargs!r})"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __setitem__(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        file: None | str | bytes | bytearray | memoryview | PathLike = None, 
    ):
        if file is None:
            return self.touch(path)
        elif isinstance(file, PathLike):
            if ospath.isdir(file):
                return self.upload_tree(file, path, no_root=True, overwrite_or_ignore=True)
            else:
                return self.upload(file, path, overwrite_or_ignore=True)
        elif isinstance(file, str):
            return self.write_text(path, file)
        else:
            return self.write_bytes(path, file)

    @classmethod
    def login(
        cls, 
        /, 
        origin: str = "http://localhost:5244", 
        username: str = "", 
        password: str = "", 
    ) -> AlistFileSystem:
        return cls(AlistClient(origin, username, password))

    def set_refresh(self, value: bool, /):
        self.__dict__["refresh"] = value

    @check_response
    def fs_batch_rename(
        self, 
        /, 
        rename_pairs: Iterable[tuple[str, str]], 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "src_dir": src_dir, 
            "rename_objects": [{
                "src_name": src_name, 
                "new_name": new_name, 
            } for src_name, new_name in rename_pairs]
        }
        return self.client.fs_batch_rename(payload, **self.request_kwargs)

    @check_response
    def fs_copy(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        names: list[str], 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, AlistPath):
            dst_dir = dst_dir.path
        elif _check:
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self.client.fs_copy(payload, **self.request_kwargs)

    @check_response
    def fs_dirs(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
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
        return self.client.fs_dirs(payload, **self.request_kwargs)

    @check_response
    def fs_form(
        self, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.fs_form(local_path_or_file, path, as_task=as_task, **self.request_kwargs)

    @check_response
    def fs_get(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "password": password}
        return self.client.fs_get(payload, **self.request_kwargs)

    @check_response
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
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
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
        return self.client.fs_list(payload, **self.request_kwargs)

    @check_response
    def fs_list_storage(self, /) -> dict:
        return self.client.admin_storage_list(**self.request_kwargs)

    @check_response
    def fs_mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return {"code": 200}
        return self.client.fs_mkdir({"path": path}, **self.request_kwargs)

    @check_response
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
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, AlistPath):
            dst_dir = dst_dir.path
        elif _check:
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        if src_dir == dst_dir:
            return {"code": 200}
        payload = {"src_dir": src_dir, "dst_dir": dst_dir, "names": names}
        return self.client.fs_move(payload, **self.request_kwargs)

    @check_response
    def fs_put(
        self, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        /, 
        path: str | PathLike[str], 
        as_task: bool = False, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.fs_put(local_path_or_file, path, as_task=as_task, **self.request_kwargs)

    @check_response
    def fs_recursive_move(
        self, 
        /, 
        src_dir: str | PathLike[str], 
        dst_dir: str | PathLike[str], 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        if isinstance(dst_dir, AlistPath):
            dst_dir = dst_dir.path
        elif _check:
            dst_dir = self.abspath(dst_dir)
        src_dir = cast(str, src_dir)
        dst_dir = cast(str, dst_dir)
        payload = {"src_dir": src_dir, "dst_dir": dst_dir}
        return self.client.fs_recursive_move(payload, **self.request_kwargs)

    @check_response
    def fs_regex_rename(
        self, 
        /, 
        src_name_regex: str, 
        new_name_regex: str, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {
            "src_dir": src_dir, 
            "src_name_regex": src_name_regex, 
            "new_name_regex": new_name_regex, 
        }
        return self.client.fs_regex_rename(payload, **self.request_kwargs)

    @check_response
    def fs_remove(
        self, 
        /, 
        names: list[str], 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if not names:
            return {"code": 200}
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"names": names, "dir": src_dir}
        return self.client.fs_remove(payload, **self.request_kwargs)

    @check_response
    def fs_remove_empty_directory(
        self, 
        /, 
        src_dir: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(src_dir, AlistPath):
            src_dir = src_dir.path
        elif _check:
            src_dir = self.abspath(src_dir)
        src_dir = cast(str, src_dir)
        payload = {"src_dir": src_dir}
        return self.client.fs_remove_empty_directory(payload, **self.request_kwargs)

    @check_response
    def fs_remove_storage(self, id: int | str, /) -> dict:
        return self.client.admin_storage_delete(id, **self.request_kwargs)

    @check_response
    def fs_rename(
        self, 
        /, 
        path: str | PathLike[str], 
        name: str, 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        payload = {"path": path, "name": name}
        return self.client.fs_rename(payload, **self.request_kwargs)

    @check_response
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
        if isinstance(src_dir, AlistPath):
            if not password:
                password = src_dir.password
            src_dir = src_dir.path
        elif _check:
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
        return self.client.fs_search(payload, **self.request_kwargs)

    def abspath(self, /, path: str | PathLike[str] = "") -> str:
        if path == "/":
            return "/"
        elif path in ("", "."):
            return self.path
        elif isinstance(path, AlistPath):
            return path.path
        path = fspath(path)
        if path.startswith("/"):
            return "/" + normpath(path).lstrip("/")
        return normpath(joinpath(self.path, path))

    def as_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        fetch_attr: bool = False, 
        _check: bool = True, 
    ) -> AlistPath:
        if not isinstance(path, AlistPath):
            if _check:
                path = self.abspath(path)
            path = AlistPath(self, path, password)
        elif password:
            path = AlistPath(self, path.path, password)
        if fetch_attr:
            path()
        return path

    def attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.fs_get(path, password, _check=False)["data"]
        attr["path"] = path
        attr["lastest_update"] = datetime.now()
        return attr

    def chdir(
        self, 
        /, 
        path: str | PathLike[str] = "/", 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
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
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            if overwrite_or_ignore is None:
                raise SameFileError(src_path)
            return None
        if commonpath((src_path, dst_path)) == dst_path:
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
        if isinstance(src_path, AlistPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_dir, AlistPath):
            if not dst_password:
                dst_password = dst_dir.password
            dst_dir = dst_dir.path
        elif _check:
            dst_dir = self.abspath(dst_dir)
        src_path = cast(str, src_path)
        dst_dir = cast(str, dst_dir)
        if dirname(src_path) == dst_dir:
            raise SameFileError(src_path)
        elif src_path == dst_dir or commonpath((src_path, dst_dir)) == dst_dir:
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
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
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
            mode: str = write_mode
            if mode:
                mode += "b"
            elif ospath.lexists(local_path):
                return
            else:
                mode = "wb"
            if local_path:
                file = open(local_path, mode)
            else:
                file = open(basename(path), mode)
        file = cast(SupportsWrite[bytes], file)
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
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ):
        is_dir: bool
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            is_dir = path.is_dir()
            path = path.path
        elif _check:
            path = self.abspath(path)
            attr = self.attr(path, password, _check=False)
            is_dir = attr["is_dir"]
        else:
            is_dir = True
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        local_dir = fsdecode(local_dir)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        if is_dir:
            if not no_root:
                local_dir = ospath.join(local_dir, basename(path))
                if local_dir:
                    makedirs(local_dir, exist_ok=True)
            for pathobj in self.listdir_path(path, password, refresh=refresh, _check=False):
                name = pathobj.name
                if pathobj.is_dir():
                    self.download_tree(
                        pathobj.path, 
                        ospath.join(local_dir, name), 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
                        password=password, 
                        refresh=refresh, 
                        _check=False, 
                    )
                else:
                    self.download(
                        pathobj.path, 
                        ospath.join(local_dir, name), 
                        write_mode=write_mode, 
                        download=download, 
                        password=password, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                ospath.join(local_dir, basename(path)), 
                write_mode=write_mode, 
                download=download, 
                password=password, 
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

    def get_directory_capacity(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> int:
        return self.fs_list(path, per_page=1, password=password, refresh=refresh, _check=_check)["data"]["total"]

    def get_url(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        return self.client.get_url(path)

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if pattern == "*":
            return self.iter(dirname, password=password, _check=_check)
        elif pattern == "**":
            return self.iter(dirname, password=password, max_depth=-1, _check=_check)
        elif not pattern:
            dirname = self.as_path(dirname, password, _check=_check)
            if dirname.exists():
                return iter((dirname,))
            return iter(())
        elif not pattern.lstrip("/"):
            return iter((AlistPath(self, "/", password),))
        splitted_pats = tuple(posix_glob_translate_iter(pattern))
        if pattern.startswith("/"):
            dirname = "/"
        elif isinstance(dirname, AlistPath):
            if not password:
                password = dirname.password
            dirname = dirname.path
        elif _check:
            dirname = self.abspath(dirname)
        dirname = cast(str, dirname)
        i = 0
        if ignore_case:
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), "".join(t[0] for t in splitted_pats))
                match = re_compile("(?i:%s)" % pattern).fullmatch
                return self.iter(
                    dirname, 
                    password=password, 
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
                return self.iter(dirname, password=password, max_depth=-1, _check=False)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), "".join(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                return self.iter(
                    dirname, 
                    password=password, 
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
                elif subpath.is_dir():
                    yield from glob_step_match(subpath, j)
            elif typ == "star":
                if at_end:
                    yield from path.listdir_path()
                else:
                    for subpath in path.listdir_path():
                        if subpath.is_dir():
                            yield from glob_step_match(subpath, j)
            else:
                for subpath in path.listdir_path():
                    try:
                        cref = cref_cache[i]
                    except KeyError:
                        if ignore_case:
                            pat = "(?i:%s)" % pat
                        cref = cref_cache[i] = re_compile(pat).fullmatch
                    if cref(subpath.name):
                        if at_end:
                            yield subpath
                        elif subpath.is_dir():
                            yield from glob_step_match(subpath, j)
        path = AlistPath(self, dirname, password)
        if not path.is_dir():
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
        path: str | PathLike[str], 
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
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self.attr(path, password, _check=False)
        except FileNotFoundError:
            return True
        if attr["is_dir"]:
            return self.get_directory_capacity(path, password, _check=False) == 0
        else:
            return attr["size"] == 0

    def is_storage(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> bool:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return True
        try:
            return any(path == s["mount_path"] for s in self.list_storage())
        except PermissionError:
            try:
                return self.attr(path, password, _check=False).get("hash_info") is None
            except FileNotFoundError:
                return False

    def iter(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[AlistPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        refresh: Optional[bool] = None, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if not max_depth:
            return
        if isinstance(top, AlistPath):
            if not password:
                password = top.password
            top = top.path
        elif _check:
            top = self.abspath(top)
        if refresh is None:
            refresh = self.refresh
        top = cast(str, top)
        refresh = cast(bool, refresh)
        try:
            ls = self.listdir_path(top, password, refresh=refresh, _check=False)
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
                yield from self.iter(
                    joinpath(top, path["name"]), 
                    password=password, 
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

    def iterdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> Iterator[dict]:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        if not self.attr(path, password, _check=False)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        page = 1
        total = 0
        download_count = 0
        while not total or download_count < total:
            data = self.fs_list(path, password, refresh=refresh, page=page, per_page=per_page, _check=False)["data"]
            lastest_update = datetime.now()
            if total == 0:
                total = data["total"]
                if total == 0:
                    return
            elif data["total"] != total:
                raise RuntimeError("detected directory (count) changes during iteration")
            for attr in data["content"]:
                attr["lastest_update"] = lastest_update
                yield attr
            download_count += len(data["content"])
            page += 1

    def list_storage(self, /) -> list[dict]:
        return self.fs_list_storage()["data"]["content"]

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
        ls = self.listdir_attr(path, password, refresh, page, per_page, _check=_check)
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
    ) -> list[dict]:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        if refresh is None:
            refresh = self.refresh
        path = cast(str, path)
        refresh = cast(bool, refresh)
        if not self.attr(path, password, _check=False)["is_dir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        data = self.fs_list(path, password, refresh=refresh, page=page, per_page=per_page, _check=False)["data"]
        if data["total"] == 0:
            return []
        lastest_update = datetime.now()
        content = data["content"]
        for attr in content:
            attr["path"] = joinpath(path, attr["name"])
            attr["lastest_update"] = lastest_update
        return content

    def listdir_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        refresh: Optional[bool] = None, 
        page: int = 1, 
        per_page: int = 0, 
        _check: bool = True, 
    ) -> list[AlistPath]:
        return [
            AlistPath(self, password=password, **item)
            for item in self.listdir_attr(path, password, refresh, page, per_page, _check=_check)
        ]

    def makedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        exist_ok: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        if not exist_ok and self.exists(path, password, _check=False):
            raise FileExistsError(errno.EEXIST, path)
        self.fs_mkdir(path, _check=False)
        return path

    def mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
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
            return path
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
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path or dirname(src_path) == dst_path:
            raise SameFileError(src_path)
        if commonpath((src_path, dst_path)) == dst_path:
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
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        password: str = "", 
        _check: bool = True, 
    ) -> HTTPFileReader | IO:
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.open(
            path.url, 
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
        /, 
        path: str | PathLike[str], 
        start: int = 0, 
        stop: Optional[int] = None, 
        password: str = "", 
        _check: bool = True, 
    ) -> bytes:
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_bytes(path.url, start, stop)

    def read_bytes_range(
        self, 
        /, 
        path: str | PathLike[str], 
        bytes_range: str = "0-", 
        password: str = "", 
        _check: bool = True, 
    ) -> bytes:
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_bytes_range(path.url, bytes_range)

    def read_block(
        self, 
        /, 
        path: str | PathLike[str], 
        size: int = 0, 
        offset: int = 0, 
        password: str = "", 
        _check: bool = True, 
    ) -> bytes:
        if size <= 0:
            return b""
        path = self.as_path(path, password, _check=_check)
        if path.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"{path.path!r} is a directory")
        return self.client.read_block(path.url, size, offset)

    def read_text(
        self, 
        /, 
        path: str | PathLike[str], 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        password: str = "", 
        _check: bool = True, 
    ):
        return self.open(
            path, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            password=password, 
            _check=_check, 
        ).read()

    def remove(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        recursive: bool = False, 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            if recursive:
                try:
                    storages = self.list_storage()
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
                storages = self.list_storage()
            except PermissionError:
                if attr.get("hash_info") is None:
                    raise
            else:
                for storage in storages:
                    if commonpath((storage["mount_path"], path)) == path:
                        self.fs_remove_storage(storage["id"])
                        return
        self.fs_remove([basename(path)], dirname(path), _check=False)

    def removedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        get_directory_capacity = self.get_directory_capacity
        remove_storage = self.fs_remove_storage
        if get_directory_capacity(path, password, _check=False):
            raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        try:
            storages = self.list_storage()
        except PermissionError:
            if self.attr(path, password, _check=False)["hash_info"] is None:
                raise
            storages = []
        else:
            for storage in storages:
                if storage["mount_path"] == path:
                    remove_storage(storage["id"])
                    break
        parent_dir = dirname(path)
        del_dir = ""
        try:
            while get_directory_capacity(parent_dir, password, _check=False) <= 1:
                for storage in storages:
                    if storage["mount_path"] == parent_dir:
                        remove_storage(storage["id"])
                        del_dir = ""
                        break
                else:
                    del_dir = parent_dir
                parent_dir = dirname(parent_dir)
            if del_dir:
                self.fs_remove([basename(del_dir)], parent_dir, _check=False)
        except OSError as e:
            pass

    def rename(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        replace: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            return dst_path
        if src_path == "/" or dst_path == "/":
            raise OSError(errno.EINVAL, f"invalid argument: {src_path!r} -> {dst_path!r}")
        if commonpath((src_path, dst_path)) == dst_path:
            raise PermissionError(errno.EPERM, f"move a path to its subordinate path is not allowed: {src_path!r} -> {dst_path!r}")
        src_dir, src_name = split(src_path)
        dst_dir, dst_name = split(dst_path)
        src_attr = self.attr(src_path, src_password, _check=False)
        try:
            dst_attr = self.attr(dst_path, dst_password, _check=False)
        except FileNotFoundError:
            if src_attr.get("hash_info") is None:
                for storage in self.list_storage():
                    if src_path == storage["mount_path"]:
                        storage["mount_path"] = dst_path
                        self.client.admin_storage_update(storage)
                        break
                return dst_path
            elif src_dir == dst_dir:
                self.fs_rename(src_path, dst_name, _check=False)
                return dst_path
            if not self.attr(dst_dir, dst_password, _check=False)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"{dst_dir!r} is not a directory: {src_path!r} -> {dst_path!r}")
        else:
            if replace:
                if dst_attr.get("hash_info") is None:
                    raise PermissionError(errno.EPERM, f"replace a storage {dst_path!r} is not allowed: {src_path!r} -> {dst_path!r}")
                elif src_attr["is_dir"]:
                    if dst_attr["is_dir"]:
                        if self.get_directory_capacity(dst_path, dst_password, _check=False):
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
        return dst_path

    def renames(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, AlistPath):
            if not src_password:
                src_password = src_path.password
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, AlistPath):
            if not dst_password:
                dst_password = dst_path.password
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        dst = self.rename(src_path, dst_path, src_password, dst_password, _check=False)
        if dirname(src_path) != dirname(dst_path):
            try:
                self.removedirs(dirname(src_path), src_password, _check=False)
            except OSError:
                pass
        return dst

    def replace(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        src_password: str = "", 
        dst_password: str = "", 
        _check: bool = True, 
    ) -> str:
        return self.rename(src_path, dst_path, src_password, dst_password, replace=True, _check=_check)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        password: str = "", 
        _check: bool = True, 
    ) -> Iterator[AlistPath]:
        if not pattern:
            return self.iter(dirname, password=password, max_depth=-1, _check=_check)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, password=password, ignore_case=ignore_case, _check=_check)

    def rmdir(
        self, 
        /, 
        path: str | PathLike[str], 
        password: str = "", 
        _check: bool = True, 
    ):
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif self.is_storage(path, password, _check=False):
            raise PermissionError(errno.EPERM, f"remove a storage by `rmdir` is not allowed: {path!r}")
        elif not self.attr(path, password, _check=False)["is_dir"]:
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
    ) -> Iterator[AlistPath]:
        return iter(self.listdir_path(path, password, refresh=refresh, _check=_check))

    # TODO: 需要进一步实现，更准确的 st_mode
    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> stat_result:
        attr = self.attr(path, password, _check=_check)
        is_dir = attr.get("is_dir", False)
        lastest_update = attr["lastest_update"]
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o777, 
            0, 
            0, 
            1, 
            0, 
            0, 
            0 if is_dir else attr["size"], 
            lastest_update.timestamp(), 
            parse_datetime(attr["modified"]).timestamp(), 
            parse_datetime(attr["created"]).timestamp(), 
        ))

    def storage_of(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        try:
            storages = self.list_storage()
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
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.exists(path, password, _check=False):
            dir_ = dirname(path)
            if not self.attr(dir_, password, _check=False)["is_dir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
        return self.upload(BytesIO(), path, password, _check=False)

    def upload(
        self, 
        /, 
        local_path_or_file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        password: str = "", 
        as_task: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        file: SupportsRead[bytes]
        if hasattr(local_path_or_file, "read"):
            if isinstance(local_path_or_file, TextIOWrapper):
                file = local_path_or_file.buffer
            else:
                file = cast(SupportsRead[bytes], local_path_or_file)
            if not fspath(path):
                try:
                    path = ospath.basename(local_path_or_file.name) # type: ignore
                except AttributeError as e:
                    raise OSError(errno.EINVAL, "Please specify the upload path") from e
        else:
            local_path = fsdecode(local_path_or_file)
            file = open(local_path, "rb")
            if not fspath(path):
                path = ospath.basename(local_path)
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
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
                return path
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
            # NOTE: Because I previously found that AList does not support chunked transfer.
            #   - https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Transfer-Encoding
            self.fs_form(file, path, as_task=as_task, _check=False)
        return path

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
    ) -> str:
        if isinstance(path, AlistPath):
            if not password:
                password = path.password
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if self.isfile(path):
            raise NotADirectoryError(errno.ENOTDIR, path)
        try:
            it = scandir(local_path)
        except NotADirectoryError:
            return self.upload(
                local_path, 
                joinpath(path, ospath.basename(local_path)), 
                password, 
                as_task=as_task, 
                overwrite_or_ignore=overwrite_or_ignore, 
                _check=False, 
            )
        else:
            if not no_root:
                path = joinpath(path, ospath.basename(local_path))
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
            return path

    unlink = remove

    def walk(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        if not max_depth:
            return
        if isinstance(top, AlistPath):
            if not password:
                password = top.password
            top = top.path
        elif _check:
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
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                _check=False, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

    def walk_path(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        password: str = "", 
        refresh: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[AlistPath], list[AlistPath]]]:
        if not max_depth:
            return
        if isinstance(top, AlistPath):
            if not password:
                password = top.password
            top = top.path
        elif _check:
            top = self.abspath(top)
        if refresh is None:
            refresh = self.refresh
        top = cast(str, top)
        refresh = cast(bool, refresh)
        try:
            ls = self.listdir_path(top, password, refresh=refresh, _check=False)
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
            yield from self.walk_path(
                joinpath(top, dir_["name"]), 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                password=password, 
                refresh=refresh, 
                _check=False, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

    def write_bytes(
        self, 
        /, 
        path: str | PathLike[str], 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
        password: str = "", 
        as_task: bool = False, 
        _check: bool = True, 
    ):
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = BytesIO(data)
        return self.upload(data, path, password=password, as_task=as_task, overwrite_or_ignore=True, _check=_check)

    def write_text(
        self, 
        /, 
        path: str | PathLike[str], 
        text: str = "", 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        password: str = "", 
        as_task: bool = False, 
        _check: bool = True, 
    ):
        bio = BytesIO()
        if text:
            if encoding is None:
                encoding = "utf-8"
            tio = TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)
            tio.write(text)
            tio.flush()
            bio.seek(0)
        return self.write_bytes(path, bio, password=password, as_task=as_task, _check=_check)

    cd  = chdir
    pwd = getcwd
    ls  = listdir
    ll  = listdir_path
    rm  = remove

# TODO: 自动根据文档 https://alist.nn.ci/guide/api 生成 AlistClient 类
# TODO: 所有类和函数都要有文档
# TODO: 所有类和函数都要有单元测试
# TODO: 支持异步IO
# TODO: 上传下载都支持进度条，下载支持多线程（返回 Future）
