#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 5)
__all__ = [
    "P115Client", "P115Path", "P115FileSystem", "P115SharePath", "P115ShareFileSystem", 
    "P115ZipPath", "P115ZipFileSystem", "P115Offline", "P115Recyclebin", "P115Sharing", 
]

import errno

from abc import ABC, abstractmethod
from asyncio import get_running_loop, run_coroutine_threadsafe, run, to_thread
from binascii import b2a_hex
from collections import deque, ChainMap
from collections.abc import (
    AsyncIterator, Awaitable, Callable, Iterable, Iterator, ItemsView, KeysView, Mapping, 
    MutableMapping, Sequence, ValuesView, 
)
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from contextlib import asynccontextmanager
from datetime import date, datetime
from email.utils import formatdate
from functools import cached_property, partial, update_wrapper
from hashlib import md5, sha1, file_digest
from hmac import digest as hmac_digest
from inspect import isawaitable, iscoroutinefunction
from io import (
    BufferedReader, BytesIO, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE, 
)
from itertools import count
from json import dumps, loads
from mimetypes import guess_type
from os import fsdecode, fspath, fstat, makedirs, scandir, stat, stat_result, PathLike
from os import path as ospath
from posixpath import join as joinpath, splitext
from re import compile as re_compile, escape as re_escape
from shutil import copyfileobj, SameFileError
from stat import S_IFDIR, S_IFREG
from threading import Condition, Thread
from time import sleep, time
from typing import (
    cast, overload, Any, ClassVar, Final, Generic, IO, Literal, Never, Optional, Self, 
    TypeAlias, TypeVar, Unpack, 
)
from types import MappingProxyType
from urllib.parse import parse_qsl, quote, urlencode, urlparse
from uuid import uuid4
from warnings import filterwarnings
from xml.etree.ElementTree import fromstring

from aiohttp import ClientSession
from requests.cookies import create_cookie
from requests.exceptions import Timeout
from requests.models import Response
from requests.sessions import Session
from magnet2torrent import Magnet2Torrent # type: ignore
from yarl import URL

# NOTE: OR use `pyqrcode` instead
import qrcode # type: ignore

from .exception import AuthenticationError, LoginError
from .util.args import argcount
from .util.cipher import P115RSACipher, P115ECDHCipher, MD5_SALT
from .util.download import DownloadTask
from .util.file import (
    bio_chunk_iter, bio_skip_bytes, get_filesize, HTTPFileReader, 
    RequestsFileReader, SupportsRead, SupportsWrite, SupportsGetUrl, 
)
from .util.iter import asyncify_iter
from .util.path import basename, commonpath, dirname, escape, joins, normpath, splits, unescape
from .util.property import funcproperty
from .util.response import get_content_length, get_filename, is_range_request
from .util.text import cookies_str_to_dict, posix_glob_translate_iter, to_base64
from .util.urlopen import urlopen


filterwarnings("ignore", category=DeprecationWarning)

AttrDict: TypeAlias = dict # TODO: TypedDict with extra keys
IDOrPathType: TypeAlias = int | str | PathLike[str] | Sequence[str] | AttrDict
RequestVarT = TypeVar("RequestVarT", dict, Callable)
P115FSType = TypeVar("P115FSType", bound="P115FileSystemBase")
P115PathType = TypeVar("P115PathType", bound="P115PathBase")

CRE_SHARE_LINK_search = re_compile(r"/s/(?P<share_code>\w+)(\?password=(?P<receive_code>\w+))?").search
APP_VERSION: Final = "99.99.99.99"
RSA_ENCODER: Final = P115RSACipher()
ECDH_ENCODER: Final = P115ECDHCipher()

if not hasattr(Response, "__del__"):
    Response.__del__ = Response.close # type: ignore


def check_response(fn: RequestVarT, /) -> RequestVarT:
    if isinstance(fn, dict):
        resp = fn
        if not resp.get("state", True):
            raise OSError(errno.EIO, resp)
        return fn
    elif iscoroutinefunction(fn):
        async def wrapper(*args, **kwds):
            resp = await fn(*args, **kwds)
            if not resp.get("state", True):
                raise OSError(errno.EIO, resp)
            return resp
    else:
        def wrapper(*args, **kwds):
            resp = fn(*args, **kwds)
            if not resp.get("state", True):
                raise OSError(errno.EIO, resp)
            return resp
    return update_wrapper(wrapper, fn)


def console_qrcode(text: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.print_ascii(tty=True)


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
        info2["pick_code"] = info["pc"]
    if "m" in info:
        info2["star"] = bool(info["m"])
    if "u" in info:
        info2["thumb"] = info["u"]
    if "play_long" in info:
        info2["play_long"] = info["play_long"]
    if keep_raw:
        info2["raw"] = info
    if extra_data:
        info2.update(extra_data)
    return info2


class P115Client:
    cookie: str
    session: Session
    user_id: int
    user_key: str

    def __init__(self, /, cookie=None, login_app: str = "web"):
        ns = self.__dict__
        session = ns["session"] = Session()
        session.headers["User-Agent"] = f"Mozilla/5.0 115disk/{APP_VERSION}"
        if not cookie:
            cookie = self.login_with_qrcode(login_app)["data"]["cookie"]
        self.set_cookie(cookie)
        resp = self.upload_info
        if resp["errno"]:
            raise AuthenticationError(resp)
        ns.update(user_id=resp["user_id"], user_key=resp["userkey"])

    def __del__(self, /) -> None:
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.user_id == other.user_id

    def __hash__(self, /) -> int:
        return hash((self.user_id, self.cookie))

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    @cached_property
    def async_session(self, /) -> ClientSession:
        session = ClientSession(raise_for_status=True)
        session.headers.update(self.session.headers) # type: ignore
        cookiejar = session.cookie_jar
        cookiejar.clear()
        cookiejar.update_cookies(self.session.cookies, URL("http://.115.com"))
        return session

    def close(self, /) -> None:
        ns = self.__dict__
        if "session" in ns:
            try:
                ns["session"].close()
            except:
                pass
        if "async_session" in ns:
            try:
                loop = get_running_loop()
            except RuntimeError:
                run(ns["async_session"].close())
            else:
                run_coroutine_threadsafe(ns["async_session"].close(), loop)

    def set_cookie(self, cookie, /):
        if isinstance(cookie, str):
            cookie = cookies_str_to_dict(cookie)
        cookiejar = self.session.cookies
        cookiejar.clear()
        if isinstance(cookie, Mapping):
            for key in ("UID", "CID", "SEID"):
                cookiejar.set_cookie(
                    create_cookie(key, cookie[key], domain=".115.com", rest={'HttpOnly': True})
                )
        else:
            cookiejar.update(cookie)
        if "async_session" in self.__dict__:
            cookiejar2 = self.async_session.cookie_jar
            cookiejar2.clear()
            cookiejar2.update_cookies(cookiejar, URL("http://.115.com"))
        cookies = cookiejar.get_dict()
        self.__dict__["cookie"] = "; ".join(f"{key}={cookies[key]}" for key in ("UID", "CID", "SEID"))

    @property
    def headers(self, /) -> MappingProxyType:
        return MappingProxyType(self.session.headers)

    def update_headers(self, headers, /):
        sync_request_headers = self.session.headers
        if isinstance(headers, Mapping):
            try:
                headers = headers.items()
            except (AttributeError, TypeError):
                headers = ((k, headers[k]) for k in headers)
        for k, v in headers:
            if v is None:
                try:
                    del sync_request_headers[k]
                except KeyError:
                    pass
            else:
                sync_request_headers[k] = v
        if "async_session" in self.__dict__:
            async_request_headers = self.async_session.headers
            async_request_headers.clear()
            async_request_headers.update(sync_request_headers) # type: ignore

    def login_with_qrcode(
        self, 
        /, 
        app: str = "web", 
        **request_kwargs, 
    ) -> dict:
        """用二维码登录
        app 目前发现的可用值：
            - web
            - android
            - ios
            - linux
            - mac
            - windows
            - tv
            - ipad（不可用）
        """
        qrcode_token = self.login_qrcode_token(**request_kwargs)["data"]
        qrcode = qrcode_token.pop("qrcode")
        # NOTE: OR use below url to fetch QR code image
        # qrcode = f"https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode?uid={qrcode_token['uid']}"
        console_qrcode(qrcode)
        while True:
            try:
                resp = self.login_qrcode_status(qrcode_token, **request_kwargs)
            except Timeout:
                continue
            status = resp["data"].get("status")
            if status == 0:
                print("[status=0] qrcode: waiting")
            elif status == 1:
                print("[status=1] qrcode: scanned")
            elif status == 2:
                print("[status=2] qrcode: signed in")
                break
            elif status == -1:
                raise LoginError("[status=-1] qrcode: expired")
            elif status == -2:
                raise LoginError("[status=-2] qrcode: canceled")
            else:
                raise LoginError(f"qrcode: aborted with {resp!r}")
        return self.login_qrcode_result({"account": qrcode_token["uid"], "app": app}, **request_kwargs)

    def login(
        self, 
        /, 
        app: str = "web", 
        **request_kwargs, 
    ):
        if not self.is_login(**request_kwargs):
            cookie = self.login_with_qrcode(app, **request_kwargs)["data"]["cookie"]
            self.set_cookie(cookie)

    def _request(
        self, 
        /, 
        url: str, 
        method: str = "GET", 
        parse: None | bool | Callable = False, 
        **request_kwargs, 
    ):
        """帮助函数：执行同步的网络请求
        """
        request_kwargs["stream"] = True
        resp = self.session.request(method, url, **request_kwargs)
        resp.raise_for_status()
        if parse is None:
            resp.close()
        elif callable(parse):
            ac = argcount(parse)
            with resp:
                if ac == 1:
                    return parse(resp)
                else:
                    return parse(resp, resp.content)
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
        /, 
        url: str, 
        method: str = "GET", 
        parse: None | bool | Callable = False, 
        **request_kwargs, 
    ):
        """帮助函数：执行异步的网络请求
        """
        request_kwargs.pop("stream", None)
        req = self.async_session.request(method, url, **request_kwargs)
        if parse is None:
            async def request():
                async with req as resp:
                    pass
            return request()
        elif callable(parse):
            ac = argcount(parse)
            async def request():
                async with req as resp:
                    if ac == 1:
                        ret = parse(resp)
                    else:
                        ret = parse(resp, (await resp.read()))
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
        /, 
        url: str, 
        method: str = "GET", 
        parse: None | bool | Callable = lambda resp, content: loads(content), 
        async_: bool = False, 
        **request_kwargs, 
    ):
        """帮助函数：可执行同步和异步的网络请求
        """
        return (self._async_request if async_ else self._request)(
            url, method, parse=parse, **request_kwargs)

    ########## Version API ##########

    @staticmethod
    def list_app_version(
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取当前各平台最新版 115 app 下载链接
        GET https://appversion.115.com/1/web/1.0/api/chrome
        """
        api = "https://appversion.115.com/1/web/1.0/api/chrome"
        if async_:
            async def fetch():
                async with ClientSession() as session:
                    async with session.get(api, **request_kwargs) as resp:
                        resp.raise_for_status()
                        return loads(await resp.read())
            return fetch()
        else:
            with Session() as session:
                with session.get(api, **request_kwargs) as resp:
                    resp.raise_for_status()
                    return resp.json()

    ########## Account API ##########

    def is_login(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> bool:
        """检查是否已登录
        GET https://my.115.com/?ct=guide&ac=status
        """
        api = "https://my.115.com/?ct=guide&ac=status"
        def parse(resp, content: bytes) -> bool:
            try:
                return loads(content)["state"]
            except:
                return False
        request_kwargs["parse"] = parse
        return self.request(api, **request_kwargs)

    def login_check(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """检查当前用户的登录状态
        GET http://passportapi.115.com/app/1.0/web/1.0/check/sso/
        """
        api = "http://passportapi.115.com/app/1.0/web/1.0/check/sso/"
        return self.request(api, async_=async_, **request_kwargs)

    def login_qrcode_status(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取二维码的状态（未扫描、已扫描、已登录、已取消、已过期等），payload 数据取自 `login_qrcode_token` 接口响应
        GET https://qrcodeapi.115.com/get/status/
        payload:
            - uid: str
            - time: int
            - sign: str
        """
        api = "https://qrcodeapi.115.com/get/status/"
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def login_qrcode_result(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取扫码登录的结果，包含 cookie
        POST https://passportapi.115.com/app/1.0/web/1.0/login/qrcode/
        payload:
            - account: int | str
            - app: str = "web"
        """
        if isinstance(payload, (int, str)):
            payload = {"app": "web", "account": payload}
        else:
            payload = {"app": "web", **payload}
        api = f"https://passportapi.115.com/app/1.0/{payload['app']}/1.0/login/qrcode/"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def login_qrcode_token(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取登录二维码，扫码可用
        GET https://qrcodeapi.115.com/api/1.0/web/1.0/token/
        """
        api = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
        return self.request(api, async_=async_, **request_kwargs)

    @staticmethod
    def login_qrcode(
        uid: str, 
        async_: bool = False, 
        **request_kwargs, 
    ):
        """下载登录二维码图片（PNG）
        GET https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode
        :params uid: 二维码的 uid
        :return: `requests.Response` 或 `aiohttp.ClientResponse`
        """
        api = "https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode"
        request_kwargs["params"] = {"uid": uid}
        if async_:
            @asynccontextmanager
            async def fetch():
                async with ClientSession(raise_for_status=True) as session:
                    yield await session.get(api, **request_kwargs)
            return fetch()
        else:
            with Session() as session:
                resp = session.get(api, **request_kwargs)
                resp.raise_for_status()
                return resp

    def logout(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> None:
        """退出登录状态（如无必要，不要使用）
        GET https://passportapi.115.com/app/1.0/web/1.0/logout/logout/
        """
        api = "https://passportapi.115.com/app/1.0/web/1.0/logout/logout/"
        request_kwargs["parse"] = False
        self.request(api, async_=async_, **request_kwargs)

    def login_status(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取登录状态
        GET https://my.115.com/?ct=guide&ac=status
        """
        api = "https://my.115.com/?ct=guide&ac=status"
        return self.request(api, async_=async_, **request_kwargs)

    def user_info(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取此用户信息
        GET https://my.115.com/?ct=ajax&ac=na
        """
        api = "https://my.115.com/?ct=ajax&ac=nav"
        return self.request(api, async_=async_, **request_kwargs)

    def user_info2(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取此用户信息（更全）
        GET https://my.115.com/?ct=ajax&ac=get_user_aq
        """
        api = "https://my.115.com/?ct=ajax&ac=get_user_aq"
        return self.request(api, async_=async_, **request_kwargs)

    def user_setting(
        self, 
        payload: dict = {}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取（并可修改）此账户的网页版设置（提示：较为复杂，自己抓包研究）
        POST https://115.com/?ac=setting&even=saveedit&is_wl_tpl=1
        """
        api = "https://115.com/?ac=setting&even=saveedit&is_wl_tpl=1"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    ########## File System API ##########

    def fs_space_summury(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取数据报告
        POST https://webapi.115.com/user/space_summury
        """
        api = "https://webapi.115.com/user/space_summury"
        return self.request(api, "POST", async_=async_, **request_kwargs)

    def fs_batch_copy(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """复制文件或文件夹
        POST https://webapi.115.com/files/copy
        payload:
            - pid: int | str
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
        """
        api = "https://webapi.115.com/files/copy"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_batch_delete(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """删除文件或文件夹
        POST https://webapi.115.com/rb/delete
        payload:
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
        """
        api = "https://webapi.115.com/rb/delete"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_batch_move(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """移动文件或文件夹
        POST https://webapi.115.com/files/move
        payload:
            - pid: int | str
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
        """
        api = "https://webapi.115.com/files/move"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_batch_rename(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """重命名文件或文件夹
        POST https://webapi.115.com/files/batch_rename
        payload:
            - files_new_name[{file_id}]: str # 值为新的文件名（basename）
        """
        api = "https://webapi.115.com/files/batch_rename"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_copy(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        pid: int, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """复制文件或文件夹，此接口是对 `fs_batch_copy` 的封装
        """
        if isinstance(fids, (int, str)):
            payload = {"fid[0]": fids}
        else:
            payload = {f"fid[{fid}]": fid for i, fid in enumerate(fids)}
            if not payload:
                return {"state": False, "message": "no op"}
        payload["pid"] = pid
        return self.fs_batch_copy(payload, async_=async_, **request_kwargs)

    def fs_delete(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """删除文件或文件夹，此接口是对 `fs_batch_delete` 的封装
        """
        api = "https://webapi.115.com/rb/delete"
        if isinstance(fids, (int, str)):
            payload = {"fid[0]": fids}
        else:
            payload = {f"fid[{i}]": fid for i, fid in enumerate(fids)}
            if not payload:
                return {"state": False, "message": "no op"}
        return self.fs_batch_delete(payload, async_=async_, **request_kwargs)

    def fs_file(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件或文件夹的简略信息
        GET https://webapi.115.com/files/file
        payload:
            - file_id: int | str
        """
        api = "https://webapi.115.com/files/file"
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_files(
        self, 
        payload: dict = {}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件夹的中的文件列表和基本信息
        GET https://webapi.115.com/files
        payload:
            - cid: int | str = 0 # 文件夹 id
            - limit: int = 32    # 一页大小，意思就是 page_size
            - offset: int = 0    # 索引偏移，索引从 0 开始计算
            - asc: 0 | 1 = 1     # 是否升序排列
            - o: str = "file_name"
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"

            - aid: int | str = 1
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1
            - custom_order: int | str = <default>
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - format: str = "json"
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - natsort: 0 | 1 = <default>
            - record_open_time: 0 | 1 = 1
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1
            - snap: 0 | 1 = <default>
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
        """
        api = "https://webapi.115.com/files"
        payload = {"aid": 1, "asc": 1, "cid": 0, "count_folders": 1, "limit": 32, "o": "file_name", "offset": 0, "record_open_time": 1, "show_dir": 1, **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def fs_files2(
        self, 
        payload: dict = {}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件夹的中的文件列表和基本信息
        GET https://aps.115.com/natsort/files.php
        payload:
            - cid: int | str = 0 # 文件夹 id
            - limit: int = 32    # 一页大小，意思就是 page_size
            - offset: int = 0    # 索引偏移，索引从 0 开始计算
            - asc: 0 | 1 = 1     # 是否升序排列
            - o: str = "file_name"
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"

            - aid: int | str = 1
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1
            - custom_order: int | str = <default>
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - format: str = "json"
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - natsort: 0 | 1 = <default>
            - record_open_time: 0 | 1 = 1
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1
            - snap: 0 | 1 = <default>
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
        """
        api = "https://aps.115.com/natsort/files.php"
        payload = {"aid": 1, "asc": 1, "cid": 0, "count_folders": 1, "limit": 32, "o": "file_name", "offset": 0, "record_open_time": 1, "show_dir": 1, **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def fs_files_edit(
        self, 
        payload: list | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """设置文件或文件夹（备注、标签等）
        POST https://webapi.115.com/files/edit
        payload:
            # 如果是单个文件或文件夹
            - fid: int | str
            # 如果是多个文件或文件夹
            - fid[]: int | str
            - fid[]: int | str
            - ...
            # 其它配置信息
            - file_desc: str = <default> # 可以用 html
            - file_label: int | str = <default> # 标签 id，如果有多个，用逗号 "," 隔开
            - fid_cover: int | str = <default> # 封面图片的文件 id，如果有多个，用逗号 "," 隔开，如果要删除，值设为 0 即可
        """
        api = "https://webapi.115.com/files/edit"
        if (headers := request_kwargs.get("headers")):
            headers = request_kwargs["headers"] = dict(headers)
        else:
            headers = request_kwargs["headers"] = {}
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return self.request(
            api, 
            "POST", 
            data=urlencode(payload), 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_files_batch_edit(
        self, 
        payload: list | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """批量设置文件或文件夹（显示时长等）
        payload:
            - show_play_long[{fid}]: 0 | 1 = 1 # 设置或取消显示时长
        """
        api = "https://webapi.115.com/files/batch_edit"
        if (headers := request_kwargs.get("headers")):
            headers = request_kwargs["headers"] = dict(headers)
        else:
            headers = request_kwargs["headers"] = {}
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return self.request(
            api, 
            "POST", 
            data=urlencode(payload), 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_files_hidden(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """隐藏或者取消隐藏文件或文件夹
        POST https://webapi.115.com/files/hiddenfiles
        payload:
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
            - hidden: 0 | 1 = 1
        """
        api = "https://webapi.115.com/files/hiddenfiles"
        if isinstance(payload, (int | str)):
            payload = {"hidden": 1, "fid[0]": payload}
        elif isinstance(payload, dict):
            payload = {"hidden": 1, **payload}
        else:
            payload = {f"f[{i}]": f for i, f in enumerate(payload)}
            if not payload:
                return {"state": False, "message": "no op"}
            payload["hidden"] = 1
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_hidden_switch(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """切换隐藏模式
        POST https://115.com/?ct=hiddenfiles&ac=switching
        payload:
            show: 0 | 1 = 1
            safe_pwd: int | str = <default> # 密码，如果需要进入隐藏模式，请传递此参数
            valid_type: int = 1
        """
        api = "https://115.com/?ct=hiddenfiles&ac=switching"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_statistic(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件或文件夹的统计信息（提示：但得不到根目录的统计信息，所以 cid 为 0 时无意义）
        GET https://webapi.115.com/category/get
        payload:
            cid: int | str
            aid: int | str = 1
        """
        api = "https://webapi.115.com/category/get"
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def fs_get_repeat(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """文件查重
        GET https://webapi.115.com/files/get_repeat_sha
        payload:
            file_id: int | str
        """
        api = "https://webapi.115.com/files/get_repeat_sha"
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def fs_index_info(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取当前已用空间、可用空间、登录设备等信息
        GET https://webapi.115.com/files/index_info
        """
        api = "https://webapi.115.com/files/index_info"
        return self.request(api, async_=async_, **request_kwargs)

    def fs_info(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件或文件夹的基本信息
        GET https://webapi.115.com/files/get_info
        payload:
            - file_id: int | str
        """
        api = "https://webapi.115.com/files/get_info"
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """新建文件夹
        POST https://webapi.115.com/files/add
        payload:
            - cname: str
            - pid: int | str = 0
        """
        api = "https://webapi.115.com/files/add"
        if isinstance(payload, str):
            payload = {"pid": 0, "cname": payload}
        else:
            payload = {"pid": 0, **payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_move(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        pid: int = 0, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """移动文件或文件夹，此接口是对 `fs_batch_move` 的封装
        """
        if isinstance(fids, (int, str)):
            payload = {"fid[0]": fids}
        else:
            payload = {f"fid[{i}]": fid for i, fid in enumerate(fids)}
            if not payload:
                return {"state": False, "message": "no op"}
        payload["pid"] = pid
        return self.fs_batch_move(payload, async_=async_, **request_kwargs)

    def fs_rename(
        self, 
        fid_name_pairs: Iterable[tuple[int | str, str]], 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """重命名文件或文件夹，此接口是对 `fs_batch_rename` 的封装
        """
        payload = {f"files_new_name[{fid}]": name for fid, name in fid_name_pairs}
        return self.fs_batch_rename(payload, async_=async_, **request_kwargs)

    def fs_search(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """搜索文件或文件夹（提示：好像最多只能罗列前 10,000 条数据，也就是 limit + offset <= 10_000）
        GET https://webapi.115.com/files/search
        payload:
            - aid: int | str = 1
            - asc: 0 | 1 = <default> # 是否升序排列
            - cid: int | str = 0 # 文件夹 id
            - count_folders: 0 | 1 = <default>
            - date: str = <default> # 筛选日期
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - file_label: int | str = <default> # 标签 id
            - format: str = "json" # 输出格式（不用管）
            - limit: int = 32 # 一页大小，意思就是 page_size
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
        """
        api = "https://webapi.115.com/files/search"
        if isinstance(payload, str):
            payload = {"aid": 1, "cid": 0, "format": "json", "limit": 32, "offset": 0, "show_dir": 1, "search_value": payload}
        else:
            payload = {"aid": 1, "cid": 0, "format": "json", "limit": 32, "offset": 0, "show_dir": 1, **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def comment_get(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件或文件夹的备注
        GET https://webapi.115.com/files/desc
        payload:
            - file_id: int | str
            - format: str = "json"
            - compat: 0 | 1 = 1
            - new_html: 0 | 1 = 1
        """
        api = "https://webapi.115.com/files/desc"
        if isinstance(payload, (int, str)):
            payload = {"format": "json", "compat": 1, "new_html": 1, "file_id": payload}
        else:
            payload = {"format": "json", "compat": 1, "new_html": 1, **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def comment_set(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        file_desc: str = "", 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """为文件或文件夹设置备注，此接口是对 `fs_files_edit` 的封装

        :param fids: 单个或多个文件或文件夹 id
        :param file_desc: 备注信息，可以用 html
        """
        if isinstance(fids, (int, str)):
            payload = [("fid", fids)]
        else:
            payload = [("fid[]", fid) for fid in fids]
            if not payload:
                return {"state": False, "message": "no op"}
        payload.append(("file_desc", file_desc))
        return self.fs_files_edit(payload, async_=async_, **request_kwargs)

    def label_add(
        self, 
        /, 
        *lables: str, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """添加标签（可以接受多个）
        POST https://webapi.115.com/label/add_multi

        可传入多个 label 描述，每个 label 的格式都是 "{label_name}\x07{color}"，例如 "tag\x07#FF0000"
        """
        api = "https://webapi.115.com/label/add_multi"
        payload = [("name[]", label) for label in lables if label]
        if not payload:
            return {"state": False, "message": "no op"}
        if (headers := request_kwargs.get("headers")):
            headers = request_kwargs["headers"] = dict(headers)
        else:
            headers = request_kwargs["headers"] = {}
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return self.request(
            api, 
            "POST", 
            data=urlencode(payload), 
            async_=async_, 
            **request_kwargs, 
        )

    def fs_export_dir(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """导出目录树
        POST https://webapi.115.com/files/export_dir
        payload:
            file_ids: int | str   # 有多个时，用逗号 "," 隔开
            target: str = "U_1_0" # 导出目录树到这个目录
            layer_limit: int = <default> # 层级深度，自然数
        """
        api = "https://webapi.115.com/files/export_dir"
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload, "target": "U_1_0"}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_export_dir_status(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取导出目录树的完成情况
        GET https://webapi.115.com/files/export_dir
        payload:
            export_id: int | str
        """
        api = "https://webapi.115.com/files/export_dir"
        if isinstance(payload, (int, str)):
            payload = {"export_id": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def fs_export_dir_future(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> ExportDirStatus:
        """执行导出目录树，新开启一个线程，用于检查完成状态
        payload:
            file_ids: int | str   # 有多个时，用逗号 "," 隔开
            target: str = "U_1_0" # 导出目录树到这个目录
            layer_limit: int = <default> # 层级深度，自然数
        """
        resp = check_response(self.fs_export_dir(payload, async_=async_, **request_kwargs))
        return ExportDirStatus(self, resp["data"]["export_id"])

    def fs_shortcut(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """把一个目录设置或取消为快捷入口
        POST https://webapi.115.com/category/shortcut
        payload:
            file_id: int | str # 有多个时，用逗号 "," 隔开
            op: "add" | "delete" = "add"
        """
        api = "https://webapi.115.com/category/shortcut"
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def fs_shortcut_list(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """罗列所有的快捷入口
        GET https://webapi.115.com/category/shortcut
        """
        api = "https://webapi.115.com/category/shortcut"
        return self.request(api, async_=async_, **request_kwargs)

    # TODO: 还需要接口，获取单个标签 id 对应的信息，也就是通过 id 来获取

    def label_del(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """删除标签
        POST https://webapi.115.com/label/delete
        payload:
            - id: int | str # 标签 id
        """
        api = "https://webapi.115.com/label/delete"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def label_edit(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """编辑标签
        POST https://webapi.115.com/label/edit
        payload:
            - id: int | str # 标签 id
            - name: str = <default>  # 标签名
            - color: str = <default> # 标签颜色，支持 css 颜色语法
        """
        api = "https://webapi.115.com/label/edit"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def label_list(
        self, 
        payload: dict = {}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """罗列标签列表（如果要获取做了标签的文件列表，用 `fs_search` 接口）
        GET https://webapi.115.com/label/list
        payload:
            - offset: int = 0 # 索引偏移，从 0 开始
            - limit: int = 11500 # 一页大小
            - keyword: str = <default> # 搜索关键词
            - sort: "name" | "update_time" | "create_time" = <default>
                # 排序字段：
                # - 名称: "name"
                # - 创建时间: "create_time"
                # - 更新时间: "update_time"
            - order: "asc" | "desc" = <default> # 排序顺序："asc"(升序), "desc"(降序)
            - user_id: int | str = <default>
        """
        api = "https://webapi.115.com/label/list"
        payload = {"offset": 0, "limit": 11500, **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def label_set(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        file_label: int | str = "", 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """为文件或文件夹设置标签，此接口是对 `fs_files_edit` 的封装

        :param fids: 单个或多个文件或文件夹 id
        :param file_label: 标签 id，如果有多个，用逗号 "," 隔开
        """
        if isinstance(fids, (int, str)):
            payload = [("fid", fids)]
        else:
            payload = [("fid[]", fid) for fid in fids]
            if not payload:
                return {"state": False, "message": "no op"}
        payload.append(("file_label", file_label))
        return self.fs_files_edit(payload, async_=async_, **request_kwargs)

    def label_batch(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """批量设置标签
        POST https://webapi.115.com/files/batch_label
        payload:
            - action: "add" | "remove" | "reset" | "replace"
                # 操作名
                # - 添加: "add"
                # - 移除: "remove"
                # - 重设: "reset"
                # - 替换: "replace"
            - file_ids: int | str # 文件或文件夹 id，如果有多个，用逗号 "," 隔开
            - file_label: int | str = <default> # 标签 id，如果有多个，用逗号 "," 隔开
            - file_label[{file_label}]: int | str = <default> # action 为 replace 时使用此参数，file_label[{原标签id}]: {目标标签id}，例如 file_label[123]: 456，就是把 id 是 123 的标签替换为 id 是 456 的标签
        """
        api = "https://webapi.115.com/files/batch_label"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def star_set(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """为文件或文件夹设置或取消星标
        POST https://webapi.115.com/files/star
        payload:
            - file_id: int | str # 文件或文件夹 id，如果有多个，用逗号 "," 隔开
            - star: 0 | 1 = 1
        """
        api = "https://webapi.115.com/files/star"
        if isinstance(payload, (int, str)):
            payload = {"star": 1, "file_id": payload}
        else:
            payload = {"star": 1, **payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def life_list(
        self, 
        payload: dict = {}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """罗列登录和增删改操作记录（最新几条）
        payload:
            - show_type: int | str = "1,2,3,4"
            - tab_type: int | str = 0
            - start: int = 0
            - show_note_cal: 0 | 1 = 0
            - end_time: int = <default> # 默认为次日零点前一秒
            - last_data: str = <default> # JSON object, e.g. {"last_time":1700000000,"last_count":1,"total_count":200}
        """
        api = "https://life.115.com/api/1.0/android/99.99.99/life/life_list"
        now = datetime.now()
        datetime.combine(now.date(), now.time().max)
        payload = {
            "show_type": "1,2,3,4", 
            "tab_type": 0, 
            "start": 0, 
            "show_note_cal": 0, 
            "end_time": int(datetime.combine(now.date(), now.time().max).timestamp()), 
            **payload, 
        }
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def behavior_detail(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取增删改操作记录明细
        payload:
            - type: str
                # 操作类型
                # - "new_folder":    新增文件夹
                # - "copy_folder":   复制文件夹
                # - "folder_rename": 文件夹改名
                # - "move_file":     移动文件或文件夹
                # - "delete_file":   删除文件或文件夹
                # - "upload_file":   上传文件
                # - "rename_file":   文件改名（未实现）
                # - "copy_file":     复制文件（未实现）
            - limit: int = 32
            - offset: int = 0
            - date: str = <default> # 默认为今天，格式为 yyyy-mm-dd
        """
        api = "https://proapi.115.com/android/1.0/behavior/detail"
        if isinstance(payload, str):
            payload = {"limit": 32, "offset": 0, "date": str(date.today()), "type": payload}
        else:
            payload = {"limit": 32, "offset": 0, "date": str(date.today()), **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    ########## Share API ##########

    def share_send(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """创建（自己的）分享
        POST https://webapi.115.com/share/send
        payload:
            - file_ids: int | str # 文件列表，有多个用逗号 "," 隔开
            - is_asc: 0 | 1 = 1 # 是否升序排列
            - order: str = "file_name"
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
            - ignore_warn: 0 | 1 = 1 # 忽略信息提示，传 1 就行了
            - user_id: int | str = <default>
        """
        api = "https://webapi.115.com/share/send"
        if isinstance(payload, (int, str)):
            payload = {"ignore_warn": 1, "is_asc": 1, "order": "file_name", "file_ids": payload}
        else:
            payload = {"ignore_warn": 1, "is_asc": 1, "order": "file_name", **payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def share_info(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取（自己的）分享信息
        GET https://webapi.115.com/share/shareinfo
        payload:
            - share_code: str
        """
        api = "https://webapi.115.com/share/shareinfo"
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def share_list(
        self, 
        payload: dict = {}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """罗列（自己的）分享信息列表
        GET https://webapi.115.com/share/slist
        payload:
            - limit: int = 32
            - offset: int = 0
            - user_id: int | str = <default>
        """
        api = "https://webapi.115.com/share/slist"
        payload = {"offset": 0, "limit": 32, **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def share_update(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """变更（自己的）分享的配置（例如改访问密码，取消分享）
        POST https://webapi.115.com/share/updateshare
        payload:
            - share_code: str
            - receive_code: str = <default>         # 访问密码（口令）
            - share_duration: int = <default>       # 分享天数: 1(1天), 7(7天), -1(长期)
            - is_custom_code: 0 | 1 = <default>     # 用户自定义口令（不用管）
            - auto_fill_recvcode: 0 | 1 = <default> # 分享链接自动填充口令（不用管）
            - share_channel: int = <default>        # 分享渠道代码（不用管）
            - action: str = <default>               # 操作: 取消分享 "cancel"
        """
        api = "https://webapi.115.com/share/updateshare"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def share_snap(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取分享链接的某个文件夹中的文件和子文件夹的列表（包含详细信息）
        GET https://webapi.115.com/share/snap
        payload:
            - share_code: str
            - receive_code: str
            - cid: int | str = 0
            - limit: int = 32
            - offset: int = 0
            - asc: 0 | 1 = 1 # 是否升序排列
            - o: str = "file_name"
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
        """
        api = "https://webapi.115.com/share/snap"
        payload = {"cid": 0, "limit": 32, "offset": 0, "asc": 1, "o": "file_name", **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def share_downlist(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取分享链接的某个文件夹中可下载的文件的列表（只含文件，不含文件夹，任意深度，简略信息）
        GET https://proapi.115.com/app/share/downlist
        payload:
            - share_code: str
            - receive_code: str
            - cid: int | str
        """
        api = "https://proapi.115.com/app/share/downlist"
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def share_receive(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """接收分享链接的某些文件或文件夹
        POST https://webapi.115.com/share/receive
        payload:
            - share_code: str
            - receive_code: str
            - file_id: int | str             # 有多个时，用逗号 "," 分隔
            - cid: int | str = 0             # 这是你网盘的文件夹 cid
            - user_id: int | str = <default>
        """
        api = "https://webapi.115.com/share/receive"
        payload = {"cid": 0, **payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def share_download_url_web(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取分享链接中某个文件的下载链接（网页版接口，不推荐使用）
        GET https://webapi.115.com/share/downurl
        payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
            - user_id: int | str = <default>
        """
        api = "https://webapi.115.com/share/downurl"
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def share_download_url_app(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取分享链接中某个文件的下载链接
        POST https://proapi.115.com/app/share/downurl
        payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
            - user_id: int | str = <default>
        """
        api = "https://proapi.115.com/app/share/downurl"
        def parse(resp, content: bytes) -> dict:
            resp = loads(content)
            if resp["state"]:
                resp["data"] = loads(RSA_ENCODER.decode(resp["data"]))
            return resp
        request_kwargs["parse"] = parse
        data = RSA_ENCODER.encode(dumps(payload))
        return self.request(api, "POST", data={"data": data}, async_=async_, **request_kwargs)

    def share_download_url(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> str:
        """获取分享链接中某个文件的下载链接，此接口是对 `share_download_url_app` 的封装
        POST https://proapi.115.com/app/share/downurl
        payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
            - user_id: int | str = <default>
        """
        resp = self.share_download_url_app(payload, async_=async_, **request_kwargs)
        def get_url(resp: dict) -> str:
            data = check_response(resp)["data"]
            file_id = payload.get("file_id")
            if not data:
                raise FileNotFoundError(errno.ENOENT, f"no such id: {file_id!r}")
            url = data["url"]
            if not url:
                raise IsADirectoryError(errno.EISDIR, f"this id refers to a directory: {file_id!r}")
            return url["url"]
        if async_:
            async def wrapper() -> str:
                return get_url(await resp) # type: ignore
            return wrapper() # type: ignore
        return get_url(resp)

    ########## Download API ##########

    def download_url_web(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件的下载链接（网页版接口，不推荐使用）
        GET https://webapi.115.com/files/download
        payload:
            - pickcode: str
        """
        api = "https://webapi.115.com/files/download"
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def download_url_app(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取文件的下载链接
        POST https://proapi.115.com/app/chrome/downurl
        payload:
            - pickcode: str
        """
        api = "https://proapi.115.com/app/chrome/downurl"
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        def parse(resp, content: bytes) -> dict:
            resp = loads(content)
            if resp["state"]:
                resp["data"] = loads(RSA_ENCODER.decode(resp["data"]))
            return resp
        request_kwargs["parse"] = parse
        return self.request(
            api, 
            "POST", 
            data={"data": RSA_ENCODER.encode(dumps(payload))}, 
            async_=async_, 
            **request_kwargs, 
        )

    def download_url(
        self, 
        pick_code: str, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> str:
        """获取文件的下载链接，此接口是对 `download_url_app` 的封装
        """
        resp = self.download_url_app({"pickcode": pick_code}, async_=async_, **request_kwargs)
        def get_url(resp: dict) -> str:
            data = check_response(resp)["data"]
            return next(iter(data.values()))["url"]["url"]
        if async_:
            async def wrapper() -> str:
                return get_url(await resp)  # type: ignore
            return wrapper() # type: ignore
        return get_url(resp)

    ########## Upload API ##########

    @staticmethod
    def _oss_upload_sign(
        bucket_name: str, 
        key: str, 
        token: dict, 
        method: str = "PUT", 
        params: None | str | Mapping | Sequence[tuple[Any, Any]] = "", 
        headers: None | str | dict = "", 
    ) -> dict:
        """帮助函数：计算认证信息，返回带认证信息的请求头
        """
        subresource_key_set = frozenset((
            "response-content-type", "response-content-language",
            "response-cache-control", "logging", "response-content-encoding",
            "acl", "uploadId", "uploads", "partNumber", "group", "link",
            "delete", "website", "location", "objectInfo", "objectMeta",
            "response-expires", "response-content-disposition", "cors", "lifecycle",
            "restore", "qos", "referer", "stat", "bucketInfo", "append", "position", "security-token",
            "live", "comp", "status", "vod", "startTime", "endTime", "x-oss-process",
            "symlink", "callback", "callback-var", "tagging", "encryption", "versions",
            "versioning", "versionId", "policy", "requestPayment", "x-oss-traffic-limit", "qosInfo", "asyncFetch",
            "x-oss-request-payer", "sequential", "inventory", "inventoryId", "continuation-token", "callback",
            "callback-var", "worm", "wormId", "wormExtend", "replication", "replicationLocation",
            "replicationProgress", "transferAcceleration", "cname", "metaQuery",
            "x-oss-ac-source-ip", "x-oss-ac-subnet-mask", "x-oss-ac-vpc-id", "x-oss-ac-forward-allow",
            "resourceGroup", "style", "styleName", "x-oss-async-process", "regionList"
        ))
        date = formatdate(usegmt=True)
        if params is None:
            params = ""
        else:
            if not isinstance(params, str):
                if isinstance(params, dict):
                    if params.keys() - subresource_key_set:
                        params = [(k, params[k]) for k in params.keys() & subresource_key_set]
                elif isinstance(params, Mapping):
                    params = [(k, params[k]) for k in params if k in subresource_key_set]
                else:
                    params = [(k, v) for k, v in params if k in subresource_key_set]
                params = urlencode(params)
            if params:
                params = "?" + params
        if headers is None:
            headers = ""
        elif isinstance(headers, dict):
            it = (
                (k2, v)
                for k, v in headers.items()
                if (k2 := k.lower()).startswith("x-oss-")
            )
            headers = "\n".join("%s:%s" % e for e in sorted(it))
        signature_data = f"""{method.upper()}


{date}
{headers}
/{bucket_name}/{key}{params}""".encode("utf-8")
        signature = to_base64(hmac_digest(bytes(token["AccessKeySecret"], "utf-8"), signature_data, "sha1"))
        return {
            "date": date, 
            "authorization": "OSS {0}:{1}".format(token["AccessKeyId"], signature), 
        }

    def _oss_upload_request(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        method: str = "PUT", 
        params: None | str | dict | list[tuple] = None, 
        headers: None | dict = None, 
        async_: bool = False, 
        **request_kwargs, 
    ):
        """帮助函数：上传到阿里云 OSS 对公用函数
        """
        headers2 = self._oss_upload_sign(
            bucket_name, 
            key, 
            token, 
            method=method, 
            params=params, 
            headers=headers, 
        )
        if headers:
            headers2.update(headers)
        headers2["Content-Type"] = ""
        return self.request(
            url, 
            params=params, 
            headers=headers2, 
            method=method, 
            async_=async_, 
            **request_kwargs, 
        )

    # NOTE: https://github.com/aliyun/aliyun-oss-python-sdk/blob/master/oss2/api.py#L1359-L1595
    @overload
    def _oss_multipart_upload_init(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def _oss_multipart_upload_init(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[str]:
        ...
    def _oss_multipart_upload_init(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> str | Awaitable[str]:
        """帮助函数：初始化分片上传，获取 upload_id
        """
        request_kwargs["parse"] = lambda resp, content, /: fromstring(content).find("UploadId").text # type: ignore
        request_kwargs["method"] = "POST"
        request_kwargs["params"] = "uploads"
        request_kwargs["headers"] = {"x-oss-security-token": token["SecurityToken"]}
        return self._oss_upload_request(
            bucket_name, 
            key, 
            token, 
            url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def _oss_multipart_upload_part(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        part_number: int, 
        part_size: int = 10485760, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _oss_multipart_upload_part(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        part_number: int, 
        part_size: int, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[dict]:
        ...
    def _oss_multipart_upload_part(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        part_number: int, 
        part_size: int = 10485760, # default to: 10 MB
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Awaitable[dict]:
        """帮助函数：上传分片
        """
        def parse(resp) -> dict:
            headers = resp.headers
            return {
                "PartNumber": part_number, 
                "LastModified": datetime.strptime(headers["date"], "%a, %d %b %Y %H:%M:%S GMT").strftime("%FT%X.%f")[:-3] + "Z", 
                "ETag": headers["ETag"], 
                "HashCrc64ecma": int(headers["x-oss-hash-crc64ecma"]), 
                "Size": count_in_bytes, 
            }
        count_in_bytes = 0
        def acc(length):
            nonlocal count_in_bytes
            count_in_bytes += length
        request_kwargs["parse"] = parse
        request_kwargs["params"] = {"partNumber": part_number, "uploadId": upload_id}
        request_kwargs["headers"] = {"x-oss-security-token": token["SecurityToken"]}
        if hasattr(file, "read"):
            bio_it = bio_chunk_iter(file, part_size, callback=acc)
            if async_:
                request_kwargs["data"] = asyncify_iter(bio_it, io_bound=True)
            else:
                request_kwargs["data"] = bio_it
        else:
            request_kwargs["data"] = file
        return self._oss_upload_request(
            bucket_name, 
            key, 
            token, 
            url, 
            async_=async_, 
            **request_kwargs, 
        )

    def _oss_multipart_upload_complete(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        callback: dict, 
        parts: list[dict], 
        async_: bool = False, 
        **request_kwargs, 
    ):
        """帮助函数：完成分片上传，创建文件
        """
        request_kwargs["method"] = "POST"
        request_kwargs["params"] = {"uploadId": upload_id}
        request_kwargs["headers"] = {
            "x-oss-security-token": token["SecurityToken"], 
            "x-oss-callback": to_base64(callback["callback"]), 
            "x-oss-callback-var": to_base64(callback["callback_var"]), 
        }
        request_kwargs["data"] = ("<CompleteMultipartUpload>%s</CompleteMultipartUpload>" % "".join(map(
            "<Part><PartNumber>{PartNumber}</PartNumber><ETag>{ETag}</ETag></Part>".format_map, 
            parts, 
        ))).encode("utf-8")
        return self._oss_upload_request(
            bucket_name, 
            key, 
            token, 
            url, 
            async_=async_, 
            **request_kwargs, 
        )

    def _oss_multipart_upload_cancel(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        async_: bool = False, 
        **request_kwargs, 
    ):
        """帮助函数：取消分片上传
        """
        request_kwargs["parse"] = None
        request_kwargs["method"] = "DELETE"
        request_kwargs["params"] = {"uploadId": upload_id}
        request_kwargs["headers"] = {"x-oss-security-token": token["SecurityToken"]}
        return self._oss_upload_request(
            bucket_name, 
            key, 
            token, 
            url, 
            async_=async_, 
            **request_kwargs, 
        )

    def _oss_multipart_upload_part_iter_sync(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        part_number_start: int = 1, 
        part_size: int = 10485760, # default to: 10 MB
        **request_kwargs, 
    ) -> Iterator[dict]:
        """帮助函数：迭代器，迭代一次上传一个分片
        """
        for part_number in count(part_number_start):
            part = self._oss_multipart_upload_part(
                file, 
                bucket_name, 
                key, 
                token, 
                url, 
                upload_id, 
                part_number=part_number, 
                part_size=part_size, 
                **request_kwargs, 
            )
            yield part
            if part["Size"] < part_size:
                break

    async def _oss_multipart_upload_part_iter_async(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        part_number_start: int = 1, 
        part_size: int = 10485760, # default to: 10 MB
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        """帮助函数：迭代器，迭代一次上传一个分片
        """
        for part_number in count(part_number_start):
            part = await self._oss_multipart_upload_part(
                file, 
                bucket_name, 
                key, 
                token, 
                url, 
                upload_id, 
                part_number=part_number, 
                part_size=part_size, 
                async_=True, 
                **request_kwargs, 
            )
            yield part
            if part["Size"] < part_size:
                break

    def _oss_multipart_upload_part_iter(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        part_number_start: int = 1, 
        part_size: int = 10485760, # default to: 10 MB
        async_: bool = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        """帮助函数：迭代器，迭代一次上传一个分片
        """
        if async_:
            method: Callable = self._oss_multipart_upload_part_iter_async
        else:
            method = self._oss_multipart_upload_part_iter_sync
        return method(
            file, 
            bucket_name, 
            key, 
            token, 
            url, 
            upload_id, 
            part_number_start=part_number_start, 
            part_size=part_size, 
            **request_kwargs, 
        )

    def _oss_multipart_part_iter_sync(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        """帮助函数：上传文件到阿里云 OSS，罗列已经上传的分块
        """
        to_num = lambda s: int(s) if isinstance(s, str) and s.isnumeric() else s
        request_kwargs["method"] = "GET"
        request_kwargs["headers"] = {"x-oss-security-token": token["SecurityToken"]}
        request_kwargs["params"] = params = {"uploadId": upload_id}
        request_kwargs["parse"] = lambda resp, content, /: fromstring(content)
        while True:
            etree = self._oss_upload_request(
                bucket_name, 
                key, 
                token, 
                url, 
                **request_kwargs, 
            )
            for el in etree.iterfind("Part"):
                yield {sel.tag: to_num(sel.text) for sel in el}
            if etree.find("IsTruncated").text == "false":
                break
            params["part-number-marker"] = etree.find("NextPartNumberMarker").text

    async def _oss_multipart_part_iter_async(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        """帮助函数：上传文件到阿里云 OSS，罗列已经上传的分块
        """
        to_num = lambda s: int(s) if isinstance(s, str) and s.isnumeric() else s
        request_kwargs["method"] = "GET"
        request_kwargs["headers"] = {"x-oss-security-token": token["SecurityToken"]}
        request_kwargs["params"] = params = {"uploadId": upload_id}
        request_kwargs["parse"] = lambda resp, content, /: fromstring(content)
        while True:
            etree = await self._oss_upload_request(
                bucket_name, 
                key, 
                token, 
                url, 
                async_=True, 
                **request_kwargs, 
            )
            for el in etree.iterfind("Part"):
                yield {sel.tag: to_num(sel.text) for sel in el}
            if etree.find("IsTruncated").text == "false":
                break
            params["part-number-marker"] = etree.find("NextPartNumberMarker").text

    def _oss_multipart_part_iter(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        token: dict, 
        url: str, 
        upload_id: str, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        """帮助函数：上传文件到阿里云 OSS，罗列已经上传的分块
        """
        if async_:
            method: Callable = self._oss_multipart_part_iter_async
        else:
            method = self._oss_multipart_part_iter_sync
        return method(
            bucket_name, 
            key, 
            token, 
            url, 
            upload_id, 
            **request_kwargs, 
        )

    @overload
    def _oss_upload(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        callback: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _oss_upload(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        callback: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[dict]:
        ...
    def _oss_upload(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        callback: dict, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Awaitable[dict]:
        """帮助函数：上传文件到阿里云 OSS，一次上传全部
        """
        upload_url = self.upload_url
        urlp = urlparse(upload_url["endpoint"])
        url = f"{urlp.scheme}://{bucket_name}.{urlp.netloc}/{key}"
        if async_:
            async def request():
                token = await self.request(upload_url["gettokenurl"], async_=True)
                request_kwargs["data"] = file
                request_kwargs["headers"] = {
                    "x-oss-security-token": token["SecurityToken"], 
                    "x-oss-callback": to_base64(callback["callback"]), 
                    "x-oss-callback-var": to_base64(callback["callback_var"]), 
                }
                return await self._oss_upload_request(
                    bucket_name, 
                    key, 
                    token, 
                    url, 
                    async_=True, 
                    **request_kwargs, 
                )
            return request()
        token = self.request(upload_url["gettokenurl"])
        request_kwargs["data"] = file
        request_kwargs["headers"] = {
            "x-oss-security-token": token["SecurityToken"], 
            "x-oss-callback": to_base64(callback["callback"]), 
            "x-oss-callback-var": to_base64(callback["callback_var"]), 
        }
        return self._oss_upload_request(
            bucket_name, 
            key, 
            token, 
            url, 
            **request_kwargs, 
        )

    def _oss_multipart_upload_sync(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        stash: dict, 
        part_size: int = 10485760, # default to: 10 MB
        **request_kwargs, 
    ) -> dict:
        """帮助函数：上传文件到阿里云 OSS，分块上传，支持断点续传
        """
        parts: list[dict]
        if "upload_id" in stash:
            url = stash["url"]
            token = stash["token"]
            upload_id = stash["upload_id"]
            parts = list(self._oss_multipart_part_iter_sync(
                bucket_name, key, token, url, upload_id, **request_kwargs))
            skipsze = sum(part["Size"] for part in parts)
            if skipsze:
                try:
                    file.seek(skipsze) # type: ignore
                except (AttributeError, TypeError, UnsupportedOperation):
                    bio_skip_bytes(file, skipsze)
        else:
            upload_url = self.upload_url
            urlp = urlparse(upload_url["endpoint"])
            url = stash["url"] = f"{urlp.scheme}://{bucket_name}.{urlp.netloc}/{key}"
            token = stash["token"] = self.request(upload_url["gettokenurl"], **request_kwargs)
            upload_id = stash["upload_id"] = self._oss_multipart_upload_init(
                bucket_name, key, token, url, **request_kwargs)
            parts = []

        parts.extend(self._oss_multipart_upload_part_iter_sync(
            file, 
            bucket_name, 
            key, 
            token, 
            url, 
            upload_id, 
            part_number_start=len(parts) + 1, 
            part_size=part_size, 
            **request_kwargs, 
        ))

        return self._oss_multipart_upload_complete(
            bucket_name, 
            key, 
            token, 
            url, 
            upload_id, 
            callback=stash["callback"], 
            parts=parts, 
            **request_kwargs, 
        )

    async def _oss_multipart_upload_async(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        stash: dict, 
        part_size: int = 10485760, # default to: 10 MB
        **request_kwargs, 
    ) -> dict:
        """帮助函数：上传文件到阿里云 OSS，分块上传，支持断点续传
        """
        parts: list[dict]
        if "upload_id" in stash:
            url = stash["url"]
            token = stash["token"]
            upload_id = stash["upload_id"]
            parts = [p async for p in self._oss_multipart_part_iter_async(
                bucket_name, key, token, url, upload_id, **request_kwargs
            )]
            skipsze = sum(part["Size"] for part in parts)
            if skipsze:
                try:
                    file.seek(skipsze) # type: ignore
                except (AttributeError, TypeError, UnsupportedOperation):
                    bio_skip_bytes(file, skipsze)
        else:
            upload_url = self.upload_url
            urlp = urlparse(upload_url["endpoint"])
            url = stash["url"] = f"{urlp.scheme}://{bucket_name}.{urlp.netloc}/{key}"
            token = stash["token"] = await self.request(upload_url["gettokenurl"], async_=True, **request_kwargs)
            upload_id = stash["upload_id"] = await self._oss_multipart_upload_init(
                bucket_name, key, token, url, async_=True, **request_kwargs)
            parts = []

        parts.extend([p async for p in self._oss_multipart_upload_part_iter_async(
            file, 
            bucket_name, 
            key, 
            token, 
            url, 
            upload_id, 
            part_number_start=len(parts) + 1, 
            part_size=part_size, 
            **request_kwargs, 
        )])

        return await self._oss_multipart_upload_complete(
            bucket_name, 
            key, 
            token, 
            url, 
            upload_id, 
            callback=stash["callback"], 
            parts=parts, 
            async_=True, 
            **request_kwargs, 
        )

    @overload
    def _oss_multipart_upload(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        stash: dict, 
        part_size: int = 10485760, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _oss_multipart_upload(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        stash: dict, 
        part_size: int, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[dict]:
        ...
    def _oss_multipart_upload(
        self, 
        /, 
        file: SupportsRead[bytes], 
        bucket_name: str, 
        key: str, 
        stash: dict, 
        part_size: int = 10485760, # default to: 10 MB
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Awaitable[dict]:
        if async_:
            method: Callable = self._oss_multipart_upload_async
        else:
            method = self._oss_multipart_upload_sync
        return method(
            file, 
            bucket_name, 
            key, 
            stash=stash, 
            part_size=part_size, 
            **request_kwargs, 
        )

    @cached_property
    def upload_info(self, /) -> dict:
        """获取和上传有关的各种服务信息
        GET https://proapi.115.com/app/uploadinfo
        """
        api = "https://proapi.115.com/app/uploadinfo"
        return self.request(api)

    @cached_property
    def upload_url(self, /) -> dict:
        """获取用于上传的一些 http 接口，此接口具有一定幂等性，请求一次，然后把响应记下来即可
        GET https://uplb.115.com/3.0/getuploadinfo.php
        response:
            - endpoint: 此接口用于上传文件到阿里云 OSS 
            - gettokenurl: 上传前需要用此接口获取 token
        """
        api = "https://uplb.115.com/3.0/getuploadinfo.php"
        return self.request(api)

    @overload
    def upload_sample_init(
        self, 
        /, 
        filename: str, 
        pid: int = 0, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_sample_init(
        self, 
        /, 
        filename: str, 
        pid: int, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[dict]:
        ...
    def upload_sample_init(
        self, 
        /, 
        filename: str, 
        pid: int = 0, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Awaitable[dict]:
        """网页端的上传接口，并不能秒传
        POST https://uplb.115.com/3.0/sampleinitupload.php
        """
        api = "https://uplb.115.com/3.0/sampleinitupload.php"
        payload = {"filename": filename, "target": f"U_1_{pid}"}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    # TODO: 以后或许可以接受使用 httpx 进行同步和异步请求
    # TODO: 支持读取 aiofiles 打开的文件
    @overload
    def upload_file_sample(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int = 0, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file_sample(
        self, 
        /, 
        file, 
        filename: Optional[str], 
        pid: int, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[dict]:
        ...
    def upload_file_sample(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int = 0, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Awaitable[dict]:
        """非秒传的上传接口，但也不需要文件大小和 sha1
        """
        if isinstance(file, (bytes, bytearray, memoryview)):
            if not filename:
                filename = str(uuid4())
        elif isinstance(file, (str, PathLike)):
            if not filename:
                filename = ospath.basename(fsdecode(file))
            file = open(file, "rb")
        elif hasattr(file, "read"):
            if not filename:
                try:
                    filename = ospath.basename(fsdecode(file.name))
                except Exception:
                    filename = str(uuid4())
        elif isinstance(file, URL) or hasattr(file, "geturl"):
            if isinstance(file, URL):
                url = str(file)
            else:
                url = file.geturl()
            file = urlopen(url)
            if not filename:
                filename = get_filename(file) or str(uuid4())
        else:
            if not filename:
                filename = str(uuid4())
        if async_:
            async def request():
                resp = await self.upload_sample_init(filename, pid, async_=True, **request_kwargs)
                api = resp["host"]
                request_kwargs["data"] = {
                    "key": resp["object"], 
                    "policy": resp["policy"], 
                    "OSSAccessKeyId": resp["accessid"], 
                    "success_action_status": "200", 
                    "callback": resp["callback"], 
                    "signature": resp["signature"], 
                }
                request_kwargs["files"] = {"file": file}
                # TODO: 使用 aiohttp，执行下面的代码，会报错：400，The body of your POST request is not well-formed multipart/form-data
                #       需要修复解决方案或可参考：
                #       - https://docs.aiohttp.org/en/stable/multipart.html#hacking-multipart
                #       - https://docs.aiohttp.org/en/stable/client_quickstart.html#post-a-multipart-encoded-file
                # request_kwargs["data"]["file"] = file
                # return await self.request(api, "POST", async_=True, **request_kwargs)
                return await to_thread(self.request, api, "POST", **request_kwargs)
            return request()
        resp = self.upload_sample_init(filename, pid, **request_kwargs)
        api = resp["host"]
        request_kwargs["data"] = {
            "key": resp["object"], 
            "policy": resp["policy"], 
            "OSSAccessKeyId": resp["accessid"], 
            "success_action_status": "200", 
            "callback": resp["callback"], 
            "signature": resp["signature"], 
        }
        request_kwargs["files"] = {"file": file}
        return self.request(api, "POST", **request_kwargs)

    def upload_init(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """秒传接口，参数的构造较为复杂，所以请不要直接使用
        POST https://uplb.115.com/4.0/initupload.php
        """
        api = "https://uplb.115.com/4.0/initupload.php"
        return self.request(api, "POST", async_=async_, **request_kwargs)

    @overload
    def _upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str, 
        target: str = "U_1_0", 
        sign_key: str = "", 
        sign_val: str = "", 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str, 
        target: str, 
        sign_key: str, 
        sign_val: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[dict]:
        ...
    def _upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str, 
        target: str = "U_1_0", 
        sign_key: str = "", 
        sign_val: str = "", 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Awaitable[dict]:
        """秒传接口，此接口是对 `upload_init` 的封装
        """
        def gen_sig() -> str:
            sig_sha1 = sha1()
            sig_sha1.update(bytes(userkey, "ascii"))
            sig_sha1.update(b2a_hex(sha1(bytes(f"{userid}{file_sha1}{target}0", "ascii")).digest()))
            sig_sha1.update(b"000000")
            return sig_sha1.hexdigest().upper()
        def gen_token() -> str:
            token_md5 = md5(MD5_SALT)
            token_md5.update(bytes(f"{file_sha1}{filesize}{sign_key}{sign_val}{userid}{t}", "ascii"))
            token_md5.update(b2a_hex(md5(bytes(userid, "ascii")).digest()))
            token_md5.update(bytes(APP_VERSION, "ascii"))
            return token_md5.hexdigest()
        userid = str(self.user_id)
        userkey = self.user_key
        t = int(time())
        sig = gen_sig()
        token = gen_token()
        encoded_token = ECDH_ENCODER.encode_token(t).decode("ascii")
        data = {
            "appid": 0, 
            "appversion": APP_VERSION, 
            "userid": userid, 
            "filename": filename, 
            "filesize": filesize, 
            "fileid": file_sha1, 
            "target": target, 
            "sig": sig, 
            "t": t, 
            "token": token, 
        }
        if sign_key and sign_val:
            data["sign_key"] = sign_key
            data["sign_val"] = sign_val
        if (headers := request_kwargs.get("headers")):
            request_kwargs["headers"] = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
        else:
            request_kwargs["headers"] = {"Content-Type": "application/x-www-form-urlencoded"}
        request_kwargs["parse"] = lambda resp, content: loads(ECDH_ENCODER.decode(content))
        request_kwargs["params"] = {"k_ec": encoded_token}
        request_kwargs["data"] = ECDH_ENCODER.encode(urlencode(sorted(data.items())))
        return self.upload_init(async_=async_, **request_kwargs)

    def _upload_file_init_sync(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str | Callable[[], str], 
        read_range_bytes_or_hash: Callable[[str], str | bytes | bytearray | memoryview], 
        pid: int = 0, 
        **request_kwargs, 
    ) -> dict:
        """秒传接口，此接口是对 `upload_init` 的封装，文件大小 和 sha1 是必需的
        """
        if not isinstance(file_sha1, str):
            file_sha1 = file_sha1()
        file_sha1 = file_sha1.upper()
        target = f"U_1_{pid}"
        resp = self._upload_file_init(
            filename, 
            filesize, 
            file_sha1, 
            target, 
            **request_kwargs, 
        )
        # NOTE: 这种情况意思是，需要二次检验一个范围哈希，它会给出此文件的一个范围区间，你读取对应的数据计算 sha1 后上传以供检验
        if resp["status"] == 7 and resp["statuscode"] == 701:
            sign_key = resp["sign_key"]
            sign_check = resp["sign_check"]
            data = read_range_bytes_or_hash(sign_check)
            if isinstance(data, str):
                sign_val = data.upper()
            else:
                sign_val = sha1(data).hexdigest().upper()
            resp = self._upload_file_init(
                filename, 
                filesize, 
                file_sha1, 
                target, 
                sign_key=sign_key, 
                sign_val=sign_val, 
                **request_kwargs, 
            )
        resp["state"] = True
        resp["data"] = {
            "file_name": filename, 
            "file_size": filesize, 
            "sha1": file_sha1, 
            "cid": pid, 
            "pick_code": resp["pickcode"], 
        }
        return resp

    async def _upload_file_init_async(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str | Callable[[], str], 
        read_range_bytes_or_hash: Callable[[str], str | bytes | bytearray | memoryview], 
        pid: int = 0, 
        **request_kwargs, 
    ) -> dict:
        """秒传接口，此接口是对 `upload_init` 的封装，文件大小 和 sha1 是必需的
        """
        if not isinstance(file_sha1, str):
            file_sha1 = await to_thread(file_sha1)
            if isawaitable(file_sha1):
                file_sha1 = await file_sha1
            file_sha1 = cast(str, file_sha1)
        file_sha1 = file_sha1.upper()
        target = f"U_1_{pid}"
        resp = await self._upload_file_init(
            filename, 
            filesize, 
            file_sha1, 
            target, 
            async_=True, 
            **request_kwargs, 
        )
        # NOTE: 这种情况意思是，需要二次检验一个范围哈希，它会给出此文件的一个范围区间，你读取对应的数据计算 sha1 后上传以供检验
        if resp["status"] == 7 and resp["statuscode"] == 701:
            sign_key = resp["sign_key"]
            sign_check = resp["sign_check"]
            data = await to_thread(read_range_bytes_or_hash, sign_check)
            if isawaitable(data):
                data = await data
            if isinstance(data, str):
                sign_val = data.upper()
            else:
                sign_val = sha1(data).hexdigest().upper()
            resp = await self._upload_file_init(
                filename, 
                filesize, 
                file_sha1, 
                target, 
                sign_key=sign_key, 
                sign_val=sign_val, 
                async_=True, 
                **request_kwargs, 
            )
        resp["state"] = True
        resp["data"] = {
            "file_name": filename, 
            "file_size": filesize, 
            "sha1": file_sha1, 
            "cid": pid, 
            "pick_code": resp["pickcode"], 
        }
        return resp

    def upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str | Callable[[], str], 
        read_range_bytes_or_hash: Callable[[str], str | bytes | bytearray | memoryview], 
        pid: int = 0, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """秒传接口，此接口是对 `upload_init` 的封装，文件大小 和 sha1 是必需的
        """
        if async_:
            method: Callable = self._upload_file_init_async
        else:
            method = self._upload_file_init_sync
        return method(
            filename, 
            filesize, 
            file_sha1, 
            read_range_bytes_or_hash=read_range_bytes_or_hash, 
            pid=pid, 
            **request_kwargs, 
        )

    @overload
    def upload_init_file(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        filesize: int = -1, 
        file_sha1: None | str | Callable[[], str] = None, 
        pid: int = 0, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_init_file(
        self, 
        /, 
        file, 
        filename: Optional[str], 
        filesize: int, 
        file_sha1: None | str | Callable[[], str], 
        pid: int, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Awaitable[dict]:
        ...
    def upload_init_file(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        filesize: int = -1, 
        file_sha1: None | str | Callable[[], str] = None, 
        pid: int = 0, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Awaitable[dict]:
        """秒传接口，此接口是对 `upload_file_init` 的封装
        """
        if isinstance(file, (bytes, bytearray, memoryview)):
            data = file
            if not filename:
                filename = str(uuid4())
            if filesize < 0:
                filesize = len(data)
            if not file_sha1:
                file_sha1 = sha1(data).hexdigest()
            def read_range_bytes_or_hash(sign_check):
                start, end = map(int, sign_check.split("-"))
                return sha1(data[start : end + 1]).hexdigest()
        elif isinstance(file, (str, PathLike)):
            path = fsdecode(file)
            if not filename:
                filename = ospath.basename(path)
            if filesize < 0:
                filesize = stat(path).st_size
            if not file_sha1:
                file_sha1 = lambda: file_digest(open(path, "rb"), "sha1").hexdigest()
            def read_range_bytes_or_hash(sign_check):
                start, end = map(int, sign_check.split("-"))
                with open(path, "rb") as file:
                    file.seek(start)
                    return sha1(file.read(end - start + 1)).hexdigest()
        elif hasattr(file, "read"):
            try:
                curpos = file.seek(0, 1)
                seekable = True
            except Exception:
                curpos = 0
                seekable = False
            if not filename:
                try:
                    filename = ospath.basename(fsdecode(file.name))
                except Exception:
                    filename = str(uuid4())
            if not file_sha1:
                if not seekable:
                    raise TypeError(f"not a seekable reader: {file!r}")
                def file_sha1():
                    try:
                        return file_digest(file, "sha1").hexdigest()
                    finally:
                        file.seek(curpos)
            if filesize < 0:
                try:
                    filesize = fstat(file.fileno()).st_size - curpos
                except Exception:
                    try:
                        filesize = len(file) - curpos
                    except TypeError:
                        if not seekable:
                            raise TypeError(f"unable to determine the length of file: {file!r}")
                        try:
                            filesize = file.seek(0, 2) - curpos
                        finally:
                            file.seek(curpos)
            def read_range_bytes_or_hash(sign_check):
                if not seekable:
                    raise TypeError(f"not a seekable reader: {file!r}")
                start, end = map(int, sign_check.split("-"))
                try:
                    file.seek(start)
                    return sha1(file.read(end - start + 1)).hexdigest()
                finally:
                    file.seek(curpos)
        elif isinstance(file, URL) or hasattr(file, "geturl"):
            if isinstance(file, URL):
                url = str(file)
            else:
                url = file.geturl()
            resp = urlopen(url)
            is_ranged_url = is_range_request(resp)
            if not filename:
                filename = get_filename(resp) or str(uuid4())
            if not file_sha1:
                file_sha1 = lambda: file_digest(resp, "sha1").hexdigest()
            if filesize < 0:
                length = resp.length
            def read_range_bytes_or_hash(sign_check):
                nonlocal resp
                resp.close()
                if is_ranged_url:
                    with urlopen(url, headers={"Range": "bytes=%s" % sign_check}) as resp:
                        data = resp.read()
                else:
                    start, end = map(int, sign_check.split("-"))
                    with urlopen(url) as resp:
                        bio_skip_bytes(resp, start)
                        data = resp.read(end - start + 1)
                return sha1(data).hexdigest()
        else:
            raise TypeError(f"unable to process: {file!r}")
        return self.upload_file_init(
            filename, 
            filesize, 
            file_sha1, 
            read_range_bytes_or_hash, 
            pid=pid, 
            async_=async_, 
            **request_kwargs, 
        )

    def _upload_file_sync(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int = 0, 
        filesize: int = -1, 
        file_sha1: Optional[str] = None, 
        part_size: int = 0, 
        upload_directly: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """文件上传接口，这是高层封装，推荐使用
        """
        if upload_directly:
            return self.upload_file_sample(file, filename, pid, **request_kwargs)

        if not file_sha1 and hasattr(file, "read"):
            try:
                file.seek(0, 1)
            except Exception:
                return self.upload_file_sample(file, filename, pid, **request_kwargs)

        resp = self.upload_init_file(
            file, 
            filename, 
            filesize=filesize, 
            file_sha1=file_sha1, 
            pid=pid, 
            **request_kwargs, 
        )
        status = resp["status"]
        statuscode = resp.get("statuscode", 0)
        if status == 2 and statuscode == 0:
            return resp
        elif status == 1 and statuscode == 0:
            bucket_name, key, callback = resp["bucket"], resp["object"], resp["callback"]
        else:
            raise ValueError(resp)

        if isinstance(file, (bytes, bytearray, memoryview)):
            pass
        elif isinstance(file, (str, PathLike)):
            file = open(file, "rb")
        elif hasattr(file, "read"):
            pass
        elif isinstance(file, URL) or hasattr(file, "geturl"):
            if isinstance(file, URL):
                url = str(file)
            else:
                url = file.geturl()
            file = urlopen(url)

        if part_size <= 0:
            return self._oss_upload(
                file, 
                bucket_name, 
                key, 
                callback, 
                **request_kwargs, 
            )
        else:
            return self._oss_multipart_upload(
                file, 
                bucket_name, 
                key, 
                stash={"callback": callback}, 
                **request_kwargs, 
            )

    async def _upload_file_async(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int = 0, 
        filesize: int = -1, 
        file_sha1: Optional[str] = None, 
        part_size: int = 0, 
        upload_directly: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """文件上传接口，这是高层封装，推荐使用
        """
        if upload_directly:
            return await self.upload_file_sample(file, filename, pid, async_=True, **request_kwargs)

        if not file_sha1 and hasattr(file, "read"):
            try:
                file.seek(0, 1)
            except Exception:
                return await self.upload_file_sample(file, filename, pid, async_=True, **request_kwargs)

        resp = await self.upload_init_file(
            file, 
            filename, 
            filesize=filesize, 
            file_sha1=file_sha1, 
            pid=pid, 
            async_=True, 
            **request_kwargs, 
        )
        status = resp["status"]
        statuscode = resp.get("statuscode", 0)
        if status == 2 and statuscode == 0:
            return resp
        elif status == 1 and statuscode == 0:
            bucket_name, key, callback = resp["bucket"], resp["object"], resp["callback"]
        else:
            raise ValueError(resp)

        if isinstance(file, (bytes, bytearray, memoryview)):
            pass
        elif isinstance(file, (str, PathLike)):
            file = open(file, "rb")
        elif hasattr(file, "read"):
            pass
        elif isinstance(file, URL) or hasattr(file, "geturl"):
            if isinstance(file, URL):
                url = str(file)
            else:
                url = file.geturl()
            file = urlopen(url)

        if part_size <= 0:
            return await self._oss_upload(
                file, 
                bucket_name, 
                key, 
                callback, 
                async_=True, 
                **request_kwargs, 
            )
        else:
            return await self._oss_multipart_upload(
                file, 
                bucket_name, 
                key, 
                stash={"callback": callback}, 
                async_=True, 
                **request_kwargs, 
            )

    def upload_file(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int = 0, 
        filesize: int = -1, 
        file_sha1: Optional[str] = None, 
        part_size: int = 0, 
        upload_directly: bool = False, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """文件上传接口，这是高层封装，推荐使用
        """
        if async_:
            method: Callable = self._upload_file_async
        else:
            method = self._upload_file_sync
        return method(
            file, 
            filename, 
            pid=pid, 
            filesize=filesize, 
            file_sha1=file_sha1, 
            part_size=part_size, 
            upload_directly=upload_directly, 
            **request_kwargs, 
        )

    # TODO: 提供一个可断点续传的版本
    # TODO: 支持进度条
    # TODO: 返回 future，支持 pause（暂停此任务，连接不释放）、stop（停止此任务，连接释放）、cancel（取消此任务）、resume（恢复），此时需要增加参数 wait
    def upload_file_future(self):
        ...

    ########## Decompress API ##########

    def extract_push(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """推送一个解压缩任务给服务器，完成后，就可以查看压缩包的文件列表了
        POST https://webapi.115.com/files/push_extract
        payload:
            - pick_code: str
            - secret: str = "" # 解压密码
        """
        api = "https://webapi.115.com/files/push_extract"
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def extract_push_progress(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """查询解压缩任务的进度
        GET https://webapi.115.com/files/push_extract
        payload:
            - pick_code: str
        """
        api = "https://webapi.115.com/files/push_extract"
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def extract_info(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取压缩文件的文件列表，推荐直接用封装函数 `extract_list`
        GET https://webapi.115.com/files/extract_info
        payload:
            - pick_code: str
            - file_name: str
            - paths: str
            - next_marker: str
            - page_count: int | str # NOTE: 介于 1-999
        """
        api = "https://webapi.115.com/files/extract_info"
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def extract_list(
        self, 
        /, 
        pick_code: str, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取压缩文件的文件列表，此方法是对 `extract_info` 的封装，推荐使用
        """
        if not 1 <= page_count <= 999:
            page_count = 999
        payload = {
            "pick_code": pick_code, 
            "file_name": path.strip("/"), 
            "paths": "文件", 
            "next_marker": next_marker, 
            "page_count": page_count, 
        }
        return self.extract_info(payload, async_=async_, **request_kwargs)

    def extract_add_file(
        self, 
        payload: list | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """解压缩到某个文件夹，推荐直接用封装函数 `extract_file`
        POST https://webapi.115.com/files/add_extract_file
        payload:
            - pick_code: str
            - extract_file[]: str
            - extract_file[]: str
            - ...
            - to_pid: int | str = 0
            - paths: str = "文件"
        """
        api = "https://webapi.115.com/files/add_extract_file"
        if (headers := request_kwargs.get("headers")):
            headers = request_kwargs["headers"] = dict(headers)
        else:
            headers = request_kwargs["headers"] = {}
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return self.request(
            api, 
            "POST", 
            data=urlencode(payload), 
            async_=async_, 
            **request_kwargs, 
        )

    def extract_progress(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取 解压缩到文件夹 任务的进度
        GET https://webapi.115.com/files/add_extract_file
        payload:
            - extract_id: str
        """
        api = "https://webapi.115.com/files/add_extract_file"
        if isinstance(payload, (int, str)):
            payload = {"extract_id": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def extract_file(
        self, 
        /, 
        pick_code: str, 
        paths: str | Sequence[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
        **request_kwargs, 
    ) -> dict:
        """解压缩到某个文件夹，是对 `extract_add_file` 的封装，推荐使用
        """
        dirname = dirname.strip("/")
        dir2 = f"文件/{dirname}" if dirname else "文件"
        data = [
            ("pick_code", pick_code), 
            ("paths", dir2), 
            ("to_pid", to_pid), 
        ]
        if not paths:
            resp = self.extract_list(pick_code, dirname)
            if not resp["state"]:
                return resp
            paths = [p["file_name"] if p["file_category"] else p["file_name"]+"/" for p in resp["data"]["list"]]
            while (next_marker := resp["data"].get("next_marker")):
                resp = self.extract_list(pick_code, dirname, next_marker)
                paths.extend(p["file_name"] if p["file_category"] else p["file_name"]+"/" for p in resp["data"]["list"])
        if isinstance(paths, str):
            data.append(("extract_dir[]" if paths.endswith("/") else "extract_file[]", paths.strip("/")))
        else:
            data.extend(("extract_dir[]" if path.endswith("/") else "extract_file[]", path.strip("/")) for path in paths)
        return self.extract_add_file(data, **request_kwargs)

    def extract_download_url_web(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取压缩包中文件的下载链接
        GET https://webapi.115.com/files/extract_down_file
        payload:
            - pick_code: str
            - full_name: str
        """
        api = "https://webapi.115.com/files/extract_down_file"
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def extract_download_url(
        self, 
        /, 
        pick_code: str, 
        path: str, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> str:
        """获取压缩包中文件的下载链接，此接口是对 `extract_download_url_web` 的封装
        """
        resp = self.extract_download_url_web(
            {"pick_code": pick_code, "full_name": path.strip("/")}, 
            async_=async_, 
            **request_kwargs, 
        )
        def get_url(resp: dict) -> str:
            data = check_response(resp)["data"]
            return quote(data["url"], safe=":/?&=%#")
        if async_:
            async def wrapper() -> str:
                return get_url(await resp) # type: ignore
            return wrapper() # type: ignore
        return get_url(resp)

    def extract_push_future(
        self, 
        /, 
        pick_code: str, 
        secret: str = "", 
        **request_kwargs, 
    ) -> Optional[PushExtractProgress]:
        """执行在线解压，如果早就已经完成，返回 None，否则新开启一个线程，用于检查进度
        """
        resp = check_response(self.extract_push(
            {"pick_code": pick_code, "secret": secret}, **request_kwargs
        ))
        if resp["data"]["unzip_status"] == 4:
            return None
        return PushExtractProgress(self, pick_code)

    def extract_file_future(
        self, 
        /, 
        pick_code: str, 
        paths: str | Sequence[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
        **request_kwargs, 
    ) -> ExtractProgress:
        """执行在线解压到目录，新开启一个线程，用于检查进度
        """
        resp = check_response(self.extract_file(
            pick_code, paths, dirname, to_pid, **request_kwargs
        ))
        return ExtractProgress(self, resp["data"]["extract_id"])

    ########## Offline Download API ##########

    def offline_info(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取关于离线的限制的信息
        GET https://115.com/?ct=offline&ac=space
        """
        api = "https://115.com/?ct=offline&ac=space"
        return self.request(api, async_=async_, **request_kwargs)

    def offline_quota_info(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取当前离线配额信息（简略）
        GET https://lixian.115.com/lixian/?ct=lixian&ac=get_quota_info
        """
        api = "https://lixian.115.com/lixian/?ct=lixian&ac=get_quota_info"
        return self.request(api, async_=async_, **request_kwargs)

    def offline_quota_package_info(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取当前离线配额信息（详细）
        GET https://lixian.115.com/lixian/?ct=lixian&ac=get_quota_package_info
        """
        api = "https://lixian.115.com/lixian/?ct=lixian&ac=get_quota_package_info"
        return self.request(api, async_=async_, **request_kwargs)

    def offline_download_path(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取当前默认的离线下载到的文件夹信息（可能有多个）
        GET https://webapi.115.com/offine/downpath
        """
        api = "https://webapi.115.com/offine/downpath"
        return self.request(api, async_=async_, **request_kwargs)

    def offline_upload_torrent_path(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取当前的种子上传到的文件夹，当你添加种子任务后，这个种子会在此文件夹中保存
        GET https://115.com/?ct=lixian&ac=get_id&torrent=1
        """
        api = "https://115.com/?ct=lixian&ac=get_id&torrent=1"
        return self.request(api, async_=async_, **request_kwargs)

    def offline_add_url(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """添加一个离线任务
        POST https://115.com/web/lixian/?ct=lixian&ac=add_task_url
        payload:
            - url: str
            - sign: str = <default>
            - time: int = <default>
            - savepath: str = <default>
            - wp_path_id: int | str = <default>
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=add_task_url"
        if isinstance(payload, str):
            payload = {"url": payload}
        if "sign" not in payload:
            info = self.offline_info()
            payload["sign"] = info["sign"]
            payload["time"] = info["time"]
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def offline_add_urls(
        self, 
        payload: Iterable[str] | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """添加一组离线任务
        POST https://115.com/web/lixian/?ct=lixian&ac=add_task_urls
        payload:
            - url[0]: str
            - url[1]: str
            - ...
            - sign: str = <default>
            - time: int = <default>
            - savepath: str = <default>
            - wp_path_id: int | str = <default>
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
        if not isinstance(payload, dict):
            payload = {f"url[{i}]": url for i, url in enumerate(payload)}
            if not payload:
                raise ValueError("no `url` specified")
        if "sign" not in payload:
            info = self.offline_info()
            payload["sign"] = info["sign"]
            payload["time"] = info["time"]
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def offline_add_torrent(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """添加一个种子作为离线任务
        POST https://115.com/web/lixian/?ct=lixian&ac=add_task_bt
        payload:
            - info_hash: str
            - wanted: str
            - sign: str = <default>
            - time: int = <default>
            - savepath: str = <default>
            - wp_path_id: int | str = <default>
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=add_task_bt"
        if "sign" not in payload:
            info = self.offline_info()
            payload["sign"] = info["sign"]
            payload["time"] = info["time"]
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def offline_torrent_info(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """查看种子的文件列表等信息
        POST https://lixian.115.com/lixian/?ct=lixian&ac=torrent
        payload:
            - sha1: str
        """
        api = "https://lixian.115.com/lixian/?ct=lixian&ac=torrent"
        if isinstance(payload, str):
            payload = {"sha1": payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def offline_remove(
        self, 
        payload: str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """删除一组离线任务（无论是否已经完成）
        POST https://lixian.115.com/lixian/?ct=lixian&ac=task_del
        payload:
            - hash[0]: str
            - hash[1]: str
            - ...
            - sign: str = <default>
            - time: int = <default>
            - flag: 0 | 1 = <default> # 是否删除源文件
        """
        api = "https://lixian.115.com/lixian/?ct=lixian&ac=task_del"
        if isinstance(payload, str):
            payload = {"hash[0]": payload}
        if "sign" not in payload:
            info = self.offline_info()
            payload["sign"] = info["sign"]
            payload["time"] = info["time"]
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def offline_list(
        self, 
        payload: int | dict = 1, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取当前的离线任务列表
        POST https://lixian.115.com/lixian/?ct=lixian&ac=task_lists
        payload:
            - page: int | str
        """
        api = "https://lixian.115.com/lixian/?ct=lixian&ac=task_lists"
        if isinstance(payload, int):
            payload = {"page": payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def offline_clear(
        self, 
        payload: int | dict = {"flag": 0}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """清空离线任务列表
        POST https://115.com/web/lixian/?ct=lixian&ac=task_clear
        payload:
            flag: int = 0
                - 0: 已完成
                - 1: 全部
                - 2: 已失败
                - 3: 进行中
                - 4: 已完成+删除源文件
                - 5: 全部+删除源文件
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=task_clear"
        if isinstance(payload, int):
            flag = payload
            if flag < 0:
                flag = 0
            elif flag > 5:
                flag = 5
            payload = {"flag": payload}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    ########## Recyclebin API ##########

    def recyclebin_info(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """回收站：文件信息
        POST https://webapi.115.com/rb/rb_info
        payload:
            - rid: int | str
        """
        api = "https://webapi.115.com/rb/rb_info"
        if isinstance(payload, (int, str)):
            payload = {"rid": payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def recyclebin_clean(
        self, 
        payload: int | str | Iterable[int | str] | dict = {}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """回收站：删除或清空
        POST https://webapi.115.com/rb/clean
        payload:
            - rid[0]: int | str # NOTE: 如果没有 rid，就是清空回收站
            - rid[1]: int | str
            - ...
            - password: int | str = <default>
        """
        api = "https://webapi.115.com/rb/clean"
        if isinstance(payload, (int, str)):
            payload = {"rid[0]": payload}
        elif not isinstance(payload, dict):
            payload = {f"rid[{i}]": rid for i, rid in enumerate(payload)}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    def recyclebin_list(
        self, 
        payload: dict = {"limit": 32, "offset": 0}, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """回收站：罗列
        GET https://webapi.115.com/rb
        payload:
            - aid: int | str = 7
            - cid: int | str = 0
            - limit: int = 32
            - offset: int = 0
            - format: str = "json"
            - source: str = <default>
        """ 
        api = "https://webapi.115.com/rb"
        payload = {"aid": 7, "cid": 0, "limit": 32, "offset": 0, "format": "json", **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    def recyclebin_revert(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """回收站：还原
        POST https://webapi.115.com/rb/revert
        payload:
            - rid[0]: int | str
            - rid[1]: int | str
            - ...
        """
        api = "https://webapi.115.com/rb/revert"
        if isinstance(payload, (int, str)):
            payload = {"rid[0]": payload}
        elif not isinstance(payload, dict):
            payload = {f"rid[{i}]": rid for i, rid in enumerate(payload)}
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    ########## Captcha System API ##########

    def captcha_sign(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """获取验证码的签名字符串
        GET https://captchaapi.115.com/?ac=code&t=sign
        """
        api = "https://captchaapi.115.com/?ac=code&t=sign"
        return self.request(api, async_=async_, **request_kwargs)

    def captcha_code(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> bytes:
        """更新验证码，并获取图片数据（含 4 个汉字）
        GET https://captchaapi.115.com/?ct=index&ac=code&ctype=0
        """
        api = "https://captchaapi.115.com/?ct=index&ac=code&ctype=0"
        request_kwargs["parse"] = lambda _, content: content
        return self.request(api, async_=async_, **request_kwargs)

    def captcha_all(
        self, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> bytes:
        """返回一张包含 10 个汉字的图片，包含验证码中 4 个汉字（有相应的编号，从 0 到 9，计数按照从左到右，从上到下的顺序）
        GET https://captchaapi.115.com/?ct=index&ac=code&t=all
        """
        api = "https://captchaapi.115.com/?ct=index&ac=code&t=all"
        request_kwargs["parse"] = lambda _, content: content
        return self.request(api, async_=async_, **request_kwargs)

    def captcha_single(
        self, 
        id: int, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> bytes:
        """10 个汉字单独的图片，包含验证码中 4 个汉字，编号从 0 到 9
        GET https://captchaapi.115.com/?ct=index&ac=code&t=single&id={id}
        """
        if not 0 <= id <= 9:
            raise ValueError(f"expected integer between 0 and 9, got {id}")
        api = f"https://captchaapi.115.com/?ct=index&ac=code&t=single&id={id}"
        request_kwargs["parse"] = lambda _, content: content
        return self.request(api, async_=async_, **request_kwargs)

    def captcha_verify(
        self, 
        payload: int | str | dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict:
        """提交验证码
        POST https://webapi.115.com/user/captcha
        payload:
            - code: int | str # 从 0 到 9 中选取 4 个数字的一种排列
            - sign: str = <default>
            - ac: str = "security_code"
            - type: str = "web"
        """
        if isinstance(payload, (int, str)):
            payload = {"code": payload, "ac": "security_code", "type": "web"}
        else:
            payload = {"ac": "security_code", "type": "web", **payload}
        if "sign" not in payload:
            payload["sign"] = self.captcha_sign()["sign"]
        api = "https://webapi.115.com/user/captcha"
        return self.request(api, "POST", data=payload, async_=async_, **request_kwargs)

    ########## Other Encapsulations ##########

    @cached_property
    def fs(self, /) -> P115FileSystem:
        """
        """
        return P115FileSystem(self)

    def get_fs(self, /, *args, **kwargs) -> P115FileSystem:
        """
        """
        return P115FileSystem(self, *args, **kwargs)

    def get_share_fs(self, share_link: str, /, *args, **kwargs) -> P115ShareFileSystem:
        """
        """
        return P115ShareFileSystem(self, share_link, *args, **kwargs)

    def get_zip_fs(self, id_or_pickcode: int | str, /, *args, **kwargs) -> P115ZipFileSystem:
        """
        """
        return P115ZipFileSystem(self, id_or_pickcode, *args, **kwargs)

    @cached_property
    def offline(self, /) -> P115Offline:
        """
        """
        return P115Offline(self)

    def get_offline(self, /, *args, **kwargs) -> P115Offline:
        return P115Offline(self, *args, **kwargs)

    @cached_property
    def recyclebin(self, /) -> P115Recyclebin:
        return P115Recyclebin(self)

    def get_recyclebin(self, /, *args, **kwargs) -> P115Recyclebin:
        return P115Recyclebin(self, *args, **kwargs)

    @cached_property
    def sharing(self, /) -> P115Sharing:
        return P115Sharing(self)

    def get_sharing(self, /, *args, **kwargs) -> P115Sharing:
        return P115Sharing(self, *args, **kwargs)

    def open(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        **request_kwargs, 
    ) -> RequestsFileReader:
        """
        """
        urlopen = self.session.get
        if request_kwargs:
            urlopen = partial(urlopen, **request_kwargs)
        return RequestsFileReader(
            url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
            urlopen=urlopen, 
        )

    def read_bytes(
        self, 
        /, 
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
            with self.session.get(url, stream=True, headers={"Accept-Encoding": "identity"}) as resp:
                resp.raise_for_status()
                length = get_content_length(resp)
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
                    with self.session.get(url, stream=True, headers={"Accept-Encoding": "identity"}) as resp:
                        resp.raise_for_status()
                        length = get_content_length(resp)
                if length is None:
                    raise OSError(errno.ESPIPE, "can't determine content length")
                stop += length
            if stop <= 0 or start >= stop:
                return b""
            bytes_range = f"{start}-{stop-1}"
        return self.read_bytes_range(url, bytes_range, headers=headers, **request_kwargs)

    def read_bytes_range(
        self, 
        /, 
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
        request_kwargs["stream"] = False
        with self.session.get(url, headers=headers, **request_kwargs) as resp:
            if resp.status_code == 416:
                return b""
            resp.raise_for_status()
            return resp.content

    def read_block(
        self, 
        /, 
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
        return self.read_bytes(url, offset, offset+size, headers=headers, **request_kwargs)


# TODO: 使用 id 而不是 path
class P115PathBase(Generic[P115FSType], Mapping, PathLike[str]):
    fs: P115FSType
    path: str

    def __init__(self, /, attr: AttrDict):
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> Self:
        return type(self)({"fs": self.fs, "path": commonpath((self.path, self.fs.abspath(path)))})

    def __call__(self, /) -> Self:
        attr = self.fs.attr(self)
        if self.__dict__ is not attr:
            self.__dict__.update(attr)
        return self

    def __contains__(self, key, /) -> bool:
        return key in self.__dict__

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs.client == path.fs.client and self.path == path.path

    def __fspath__(self, /) -> str:
        return self.path

    def __getitem__(self, key, /):
        if key not in self.__dict__ and not self.__dict__.get("last_update"):
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
        return f"{name}({self.__dict__})"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str | PathLike[str], /) -> Self:
        return self.joinpath(path)

    @property
    def is_attr_loaded(self, /) -> bool:
        return "last_update" in self.__dict__

    @cached_property
    def id(self, /) -> int:
        return self.fs.get_id(self.path)

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

    def download(
        self, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        pid: Optional[int] = None, 
        no_root: bool = False, 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
    ):
        return self.fs.download_tree(
            self, 
            local_dir, 
            pid=pid, 
            no_root=no_root, 
            write_mode=write_mode, 
        )

    def exists(self, /) -> bool:
        return self.fs.exists(self)

    @property
    def file_extension(self, /) -> Optional[str]:
        if not self.is_file():
            return None
        return splitext(basename(self.path))[1]

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[Self]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
        )

    def is_absolute(self, /) -> bool:
        return True

    def is_dir(self, /) -> bool:
        try:
            return self["is_directory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def is_file(self, /) -> bool:
        try:
            return not self["is_directory"]
        except FileNotFoundError:
            return False
        except KeyError:
            return True

    def is_symlink(self, /) -> bool:
        return False

    def isdir(self, /) -> bool:
        return self.fs.isdir(self)

    def isfile(self, /) -> bool:
        return self.fs.isfile(self)

    def inode(self, /) -> int:
        return self.id

    def iter(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[Self], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        **kwargs, 
    ) -> Iterator[Self]:
        return self.fs.iter(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            **kwargs, 
        )

    def join(self, *names: str) -> Self:
        if not names:
            return self
        return type(self)({"fs": self.fs, "path": joinpath(self.path, joins(names))})

    def joinpath(self, *paths: str | PathLike[str]) -> Self:
        if not paths:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)({"fs": self.fs, "path": path_new})

    def listdir(self, /, **kwargs) -> list[str]:
        return self.fs.listdir(self, **kwargs)

    def listdir_attr(self, /, **kwargs) -> list[dict]:
        return self.fs.listdir_attr(self, **kwargs)

    def listdir_path(self, /, **kwargs) -> list[Self]:
        return self.fs.listdir_path(self, **kwargs)

    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> bool:
        pattern = "/" + "/".join(
            t[0] for t in posix_glob_translate_iter(
                path_pattern, allow_escaped_slash=allow_escaped_slash))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

    @property
    def media_type(self, /) -> Optional[str]:
        if not self.is_file():
            return None
        return guess_type(self.path)[0] or "application/octet-stream"

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

    @property
    def parent(self, /) -> Self:
        path = self.path
        if path == "/":
            return self
        parent = dirname(path)
        try:
            return type(self)({"id": self.__dict__["parent_id"], "fs": self.fs, "path": parent})
        except KeyError:
            return type(self)({"fs": self.fs, "path": parent})

    @cached_property
    def parents(self, /) -> tuple[Self, ...]:
        path = self.path
        if path == "/":
            return ()
        parents: list[Self] = []
        cls, fs = type(self), self.fs
        parent = dirname(path)
        while path != parent:
            parents.append(cls({"fs": fs, "path": parent}))
            path, parent = parent, dirname(parent)
        return tuple(parents)

    @cached_property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *splits(self.path, do_unescape=False)[0][1:])

    @cached_property
    def patht(self, /) -> tuple[str, ...]:
        return tuple(splits(self.path)[0])

    def read_bytes(
        self, 
        /, 
        start: int = 0, 
        stop: Optional[int] = None, 
    ) -> bytes:
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

    def relative_to(self, other: str | Self, /) -> str:
        if type(self) is type(other):
            other = cast(Self, other)
            other = other.path
        elif not cast(str, other).startswith("/"):
            other = self.fs.abspath(other)
        other = cast(str, other)
        path = self.path
        if path == other:
            return ""
        elif path.startswith(other+"/"):
            return path[len(other)+1:]
        raise ValueError(f"{path!r} is not in the subpath of {other!r}")

    @cached_property
    def relatives(self, /) -> tuple[str]:
        patht, _ = splits(self.path)
        def it():
            path = patht[-1]
            if path:
                yield path
                for p in reversed(patht[1:-1]):
                    path = joinpath(unescape(p), path)
                    yield path
        return tuple(it())

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[Self]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
        )

    @cached_property
    def root(self, /) -> Self:
        return type(self)({"fs": self.fs, "path": "/", "id": 0})

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

    @property
    def url(self, /) -> str:
        ns = self.__dict__
        try:
            url_expire_time = ns["url_expire_time"]
            if time() + 5 * 60 < url_expire_time:
                return ns["url"]
        except KeyError:
            pass
        url = ns["url"] = self.fs.get_url(self)
        ns["url_expire_time"] = int(parse_qsl(urlparse(url).query)[0][1])
        return url

    def walk(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        return self.fs.walk(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            _top=self.path, 
        )

    def walk_path(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
    ) -> Iterator[tuple[str, list[Self], list[Self]]]:
        return self.fs.walk_path(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
            _top=self.path, 
        )

    def with_name(self, name: str, /) -> Self:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> Self:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> Self:
        return self.parent.joinpath(self.stem + suffix)


class P115FileSystemBase(Generic[P115PathType]):
    client: P115Client
    cid: int
    path: str
    path_class: type[P115PathType]

    def __contains__(self, id_or_path: IDOrPathType, /) -> bool:
        return self.exists(id_or_path)

    def __getitem__(self, id_or_path: IDOrPathType, /) -> P115PathType:
        return self.as_path(id_or_path)

    def __iter__(self, /) -> Iterator[P115PathType]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, id_or_path: IDOrPathType, /) -> Self:
        self.chdir(id_or_path)
        return self

    def __len__(self, /) -> int:
        return len(tuple(self.iterdir()))

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}, cid={self.cid!r}, path={self.path!r}) at {hex(id(self))}>"

    @abstractmethod
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    )  -> AttrDict:
        ...

    @abstractmethod
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
    ) -> str:
        ...

    @abstractmethod
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[AttrDict]:
        ...

    def abspath(self, path: str | PathLike[str] = "", /) -> str:
        return self.get_path(path, self.cid)

    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> P115PathType:
        path_class = type(self).path_class
        attr: AttrDict
        if isinstance(id_or_path, path_class):
            return id_or_path
        elif isinstance(id_or_path, dict):
            attr = cast(AttrDict, id_or_path)
        elif isinstance(id_or_path, int):
            attr = self.attr(id_or_path)
        else:
            attr = self.attr(id_or_path, pid)
        attr["fs"] = self
        return path_class(attr)

    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: Optional[int] = None, 
    ) -> int:
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            cid = id_or_path.id
            self.__dict__.update(
                cid  = cid, 
                path = id_or_path["path"], 
            )
            return cid
        elif id_or_path in (0, "/"):
            self.__dict__.update(cid=0, path="/")
            return 0
        if isinstance(id_or_path, PathLike):
            id_or_path = fspath(id_or_path)
        if not id_or_path or id_or_path == ".":
            return self.cid
        attr = self.attr(id_or_path, pid)
        if self.cid == attr["id"]:
            return self.cid
        elif attr["is_directory"]:
            self.__dict__.update(
                cid  = attr["id"], 
                path = self.get_path(id_or_path, pid), 
            )
            return attr["id"]
        else:
            raise NotADirectoryError(
                errno.ENOTDIR, f"{id_or_path!r} (in {pid!r}) is not a directory")

    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        local_path_or_file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
        pid: Optional[int] = None, 
        write_mode: Literal["a", "w", "x", "i"] = "a", 
        submit = None, 
    ) -> Optional[DownloadTask]:
        if not hasattr(local_path_or_file, "write"):
            if not local_path_or_file:
                local_path_or_file = self.attr(id_or_path, pid)["name"]
            if ospath.lexists(local_path_or_file): # type: ignore
                if write_mode == "x":
                    raise FileExistsError(
                        errno.EEXIST, 
                        f"local path already exists: {local_path_or_file!r}", 
                    )
                elif write_mode == "i":
                    return None
        kwargs = {"resume": write_mode == "a", "headers": self.client.session.headers}
        if submit is not None:
            kwargs["submit"] = submit
        task = DownloadTask.create_task(
            lambda: self.get_url(id_or_path, pid), 
            local_path_or_file, 
            **kwargs, 
        )
        if submit is None:
            task.run_wait()
        else:
            task.run()
        return task

    def download_tree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        pid: Optional[int] = None, 
        write_mode: Literal["i", "x", "w", "a"] = "a", 
        submit = None, 
        no_root: bool = False, 
        predicate: Optional[Callable[[P115PathType], bool]] = None, 
        onerror: None | bool | Callable[[BaseException], Any] = None, 
    ) -> Iterator[DownloadTask]:
        local_dir = fsdecode(local_dir)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        attr = self.attr(id_or_path, pid)
        pathes: Iterable[P115PathType]
        if attr["is_directory"]:
            if not no_root:
                local_dir = ospath.join(local_dir, attr["name"])
                if local_dir:
                    makedirs(local_dir, exist_ok=True)
            pathes = self.scandir(attr["id"])
        else:
            path_class = type(self).path_class
            attr["fs"] = self
            pathes = (path_class(attr),)
        for subpath in filter(predicate, pathes):
            if subpath["is_directory"]:
                yield from self.download_tree(
                    subpath["id"], 
                    ospath.join(local_dir, subpath["name"]), 
                    write_mode=write_mode, 
                    submit=submit, 
                    no_root=True, 
                    predicate=predicate, 
                    onerror=onerror, 
                )
            else:
                try:
                    task = self.download(
                        subpath["id"], 
                        ospath.join(local_dir, subpath["name"]), 
                        write_mode=write_mode, 
                        submit=submit, 
                    )
                except KeyboardInterrupt:
                    raise
                except BaseException as exc:
                    if onerror is None or onerror is True:
                        raise
                    elif callable(onerror):
                        onerror(exc)
                else:
                    if task is not None:
                        yield task

    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> bool:
        path_class = type(self).path_class
        try:
            if isinstance(id_or_path, path_class):
                id_or_path()
            else:
                self.attr(id_or_path, pid)
            return True
        except FileNotFoundError:
            return False

    def getcid(self, /) -> int:
        return self.cid

    def getcwd(self, /, fetch_attr: bool = False) -> str:
        if fetch_attr:
            return self.attr(self.cid)["path"]
        return self.path

    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> int:
        path_class = type(self).path_class
        if pid is None and (not id_or_path or id_or_path == "."):
            return self.cid
        elif isinstance(id_or_path, path_class):
            return id_or_path.id
        elif isinstance(id_or_path, int):
            return id_or_path
        if id_or_path == "/":
            return 0
        try:
            path_to_id = getattr(self, "path_to_id", None)
            if path_to_id is not None:
                path = self.get_path(id_or_path, pid)
                return path_to_id[path]
        except LookupError:
            pass
        return self.attr(id_or_path, pid)["id"]

    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> str:
        path_class = type(self).path_class
        if pid is None and (not id_or_path or id_or_path == "."):
            return self.path
        elif isinstance(id_or_path, path_class):
            return id_or_path.path
        elif isinstance(id_or_path, dict):
            return id_or_path["path"]
        elif isinstance(id_or_path, int):
            id = id_or_path
            if id == 0:
                return "/"
            return self.attr(id)["path"]
        if isinstance(id_or_path, (str, PathLike)):
            path = fspath(id_or_path)
            if not path.startswith("/"):
                ppath = self.path if pid is None else joins(self.get_patht(pid))
                if path in ("", "."):
                    return ppath
                path = joinpath(ppath, path)
            return normpath(path)
        else:
            path = joins(id_or_path)
            if not path.startswith("/"):
                ppath = self.path if pid is None else joins(self.get_patht(pid))
                if not path:
                    return ppath
                path = joinpath(ppath, path)
        return path

    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> list[str]:
        path_class = type(self).path_class
        if pid is None and (not id_or_path or id_or_path == "."):
            return splits(self.path)[0]
        elif isinstance(id_or_path, path_class):
            return splits(id_or_path.path)[0]
        elif isinstance(id_or_path, dict):
            return splits(id_or_path["path"])[0]
        elif isinstance(id_or_path, int):
            id = id_or_path
            if id == 0:
                return [""]
            return splits(self.attr(id)["path"])[0]
        if pid is None:
            pid = self.cid
        patht: Sequence[str]
        if isinstance(id_or_path, (str, PathLike)):
            path = fspath(id_or_path)
            if path.startswith("/"):
                return splits(path)[0]
            elif path in ("", "."):
                return self.get_patht(pid)
            patht, parents = splits(path)
        else:
            patht = id_or_path
            if not patht[0]:
                return list(id_or_path)
            parents = 0
        ppatht = self.get_patht(pid)
        if parents:
            idx = min(parents, len(ppatht) - 1)
            ppatht = ppatht[:-idx]
        if patht:
            ppatht.extend(patht)
        return ppatht

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[P115PathType]:
        if pattern == "*":
            return self.iter(dirname)
        elif pattern == "**":
            return self.iter(dirname, max_depth=-1)
        path_class = type(self).path_class
        if not pattern:
            try:
                attr = self.attr(dirname)
            except FileNotFoundError:
                return iter(())
            else:
                attr["fs"] = self
                return iter((path_class(attr),))
        elif not pattern.lstrip("/"):
            attr = self.attr(0)
            attr["fs"] = self
            return iter((path_class(attr),))
        splitted_pats = tuple(posix_glob_translate_iter(
            pattern, allow_escaped_slash=allow_escaped_slash))
        dirname_as_id = isinstance(dirname, (int, path_class))
        dirid: int
        if isinstance(dirname, path_class):
            dirid = dirname.id
        elif isinstance(dirname, int):
            dirid = dirname
        if pattern.startswith("/"):
            dir_ = "/"
        else:
            dir_ = self.get_path(dirname)
        i = 0
        dir2 = ""
        if ignore_case:
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dir_), "/".join(t[0] for t in splitted_pats))
                match = re_compile("(?i:%s)" % pattern).fullmatch
                return self.iter(
                    dirname, 
                    max_depth=-1, 
                    predicate=lambda p: match(p.path) is not None, 
                )
        else:
            typ = None
            for i, (pat, typ, orig) in enumerate(splitted_pats):
                if typ != "orig":
                    break
                dir2 = joinpath(dir2, orig)
            dir_ = joinpath(dir_, dir2)
            if typ == "orig":
                try:
                    if dirname_as_id:
                        attr = self.attr(dir2, dirid)
                    else:
                        attr = self.attr(dir_)
                except FileNotFoundError:
                    return iter(())
                else:
                    attr["fs"] = self
                    return iter((path_class(attr),))
            elif typ == "dstar" and i + 1 == len(splitted_pats):
                if dirname_as_id:
                    return self.iter(dir2, dirid, max_depth=-1)
                else:
                    return self.iter(dir_, max_depth=-1)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dir_), "/".join(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                if dirname_as_id:
                    return self.iter(
                        dir2, 
                        dirid, 
                        max_depth=-1, 
                        predicate=lambda p: match(p.path) is not None, 
                    )
                else:
                    return self.iter(
                        dir_, 
                        max_depth=-1, 
                        predicate=lambda p: match(p.path) is not None, 
                    )
        cref_cache: dict[int, Callable] = {}
        def glob_step_match(path, i):
            j = i + 1
            at_end = j == len(splitted_pats)
            pat, typ, orig = splitted_pats[i]
            if typ == "orig":
                subpath = path.joinpath(orig)
                if at_end:
                    yield subpath
                elif subpath["is_directory"]:
                    yield from glob_step_match(subpath, j)
            elif typ == "star":
                if at_end:
                    yield from path.iter()
                else:
                    for subpath in path.iter():
                        if subpath["is_directory"]:
                            yield from glob_step_match(subpath, j)
            else:
                for subpath in path.iter():
                    try:
                        cref = cref_cache[i]
                    except KeyError:
                        if ignore_case:
                            pat = "(?i:%s)" % pat
                        cref = cref_cache[i] = re_compile(pat).fullmatch
                    if cref(subpath["name"]):
                        if at_end:
                            yield subpath
                        elif subpath["is_directory"]:
                            yield from glob_step_match(subpath, j)
        if dirname_as_id:
            attr = self.attr(dir2, dirid)
        else:
            attr = self.attr(dir_)
        if not attr["is_directory"]:
            return iter(())
        attr["fs"] = self
        path = path_class(attr)
        return glob_step_match(path, i)

    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> bool:
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            return id_or_path["is_directory"]
        try:
            return self.attr(id_or_path, pid)["is_directory"]
        except FileNotFoundError:
            return False

    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> bool:
        path_class = type(self).path_class
        if isinstance(id_or_path, path_class):
            return not id_or_path["is_directory"]
        try:
            return not self.attr(id_or_path, pid)["is_directory"]
        except FileNotFoundError:
            return False

    # TODO: 支持宽度优先遍历
    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[P115PathType], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        if not max_depth:
            return
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        path_class = type(self).path_class
        try:
            for attr in self.iterdir(top, pid, **kwargs):
                path = path_class(attr)
                yield_me = min_depth <= 0
                if yield_me and predicate:
                    pred = predicate(path)
                    if pred is None:
                        continue
                    yield_me = pred 
                if yield_me and topdown:
                    yield path
                if path["is_directory"]:
                    yield from self.iter(
                        path, 
                        topdown=topdown, 
                        min_depth=min_depth, 
                        max_depth=max_depth, 
                        predicate=predicate, 
                        onerror=onerror, 
                    )
                if yield_me and not topdown:
                    yield path
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise

    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        full_path: bool = False, 
        **kwargs, 
    ) -> list[str]:
        if full_path:
            return [attr["path"] for attr in self.iterdir(id_or_path, pid, **kwargs)]
        else:
            return [attr["name"] for attr in self.iterdir(id_or_path, pid, **kwargs)]

    def listdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        **kwargs, 
    ) -> list[AttrDict]:
        return list(self.iterdir(id_or_path, pid, **kwargs))

    def listdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        **kwargs, 
    ) -> list[P115PathType]:
        path_class = type(self).path_class
        return [path_class(attr) for attr in self.iterdir(id_or_path, pid, **kwargs)]

    def dictdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        full_path: bool = False, 
        **kwargs, 
    ) -> dict[int, str]:
        if full_path:
            return {attr["id"]: attr["path"] for attr in self.iterdir(id_or_path, pid, **kwargs)}
        else:
            return {attr["id"]: attr["name"] for attr in self.iterdir(id_or_path, pid, **kwargs)}

    def dictdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        **kwargs, 
    ) -> dict[int, AttrDict]:
        return {attr["id"]: attr for attr in self.iterdir(id_or_path, pid, **kwargs)}

    def dictdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        **kwargs, 
    ) -> dict[int, P115PathType]:
        path_class = type(self).path_class
        return {attr["id"]: path_class(attr) for attr in self.iterdir(id_or_path, pid, **kwargs)}

    def open(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        pid: Optional[int] = None, 
    ) -> HTTPFileReader | IO:
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        url = self.get_url(id_or_path, pid)
        return self.client.open(
            url, 
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
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        stop: Optional[int] = None, 
        pid: Optional[int] = None, 
    ) -> bytes:
        url = self.get_url(id_or_path, pid)
        return self.client.read_bytes(url, start, stop)

    def read_bytes_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: Optional[int] = None, 
    ) -> bytes:
        url = self.get_url(id_or_path, pid)
        return self.client.read_bytes_range(url, bytes_range)

    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        size: int = 0, 
        offset: int = 0, 
        pid: Optional[int] = None, 
    ) -> bytes:
        if size <= 0:
            return b""
        url = self.get_url(id_or_path, pid)
        return self.client.read_block(url, size, offset)

    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        pid: Optional[int] = None, 
    ):
        return self.open(
            id_or_path, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            pid=pid, 
        ).read()

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
    ) -> Iterator[P115PathType]:
        if not pattern:
            return self.iter(dirname, max_depth=-1)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, ignore_case=ignore_case, allow_escaped_slash=allow_escaped_slash)

    def scandir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
        **kwargs, 
    ) -> Iterator[P115PathType]:
        return map(type(self).path_class, self.iterdir(id_or_path, pid, **kwargs))

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> stat_result:
        raise UnsupportedOperation(errno.ENOSYS, 
            "`stat()` is currently not supported, use `attr()` instead."
        )

    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _top: str = "", 
        **kwargs, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        if not max_depth:
            return
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        try:
            if not _top:
                _top = self.get_path(top, pid)
            dirs: list[str] = []
            files: list[str] = []
            attrs: list[AttrDict] = []
            for attr in self.iterdir(top, pid, **kwargs):
                if attr["is_directory"]:
                    attrs.append(attr)
                    dirs.append(attr["name"])
                else:
                    files.append(attr["name"])
            if yield_me and topdown:
                yield _top, dirs, files
            for attr in attrs:
                yield from self.walk(
                    attr["id"], 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    _top=joinpath(_top, escape(attr["name"])), 
                )
            if yield_me and not topdown:
                yield _top, dirs, files
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise

    def walk_path(
        self, 
        top: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _top: str = "", 
        **kwargs, 
    ) -> Iterator[tuple[str, list[P115PathType], list[P115PathType]]]:
        if not max_depth:
            return
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        path_class = type(self).path_class
        try:
            if not _top:
                _top = self.get_path(top, pid)
            dirs: list[P115PathType] = []
            files: list[P115PathType] = []
            for attr in self.iterdir(top, pid, **kwargs):
                (dirs if attr["is_directory"] else files).append(path_class(attr))
            if yield_me and topdown:
                yield _top, dirs, files
            for path in dirs:
                yield from self.walk_path(
                    path["id"], 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    _top=joinpath(_top, escape(path["name"])), 
                )
            if yield_me and not topdown:
                yield _top, dirs, files
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise

    cd  = chdir
    pwd = getcwd
    ls  = listdir
    la  = listdir_attr
    ll  = listdir_path


class P115Path(P115PathBase):
    fs: P115FileSystem

    def copy(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> Optional[Self]:
        attr = self.fs.copy(
            self, 
            dst_path, 
            pid=pid, 
            overwrite_or_ignore=overwrite_or_ignore, 
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
        pid: Optional[int] = None, 
    ) -> Self:
        attr = self.fs.move(self, dst_path, pid)
        if attr is None:
            return self
        return type(self)(attr)

    def remove(self, /, recursive: bool = True) -> dict:
        return self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        attr = self.fs.rename(self, dst_path, pid)
        if attr is None:
            return self
        return type(self)(attr)

    def renames(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        attr = self.fs.renames(self, dst_path, pid)
        if attr is None:
            return self
        return type(self)(attr)

    def replace(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        attr = self.fs.replace(self, dst_path, pid)
        if attr is None:
            return self
        return type(self)(attr)

    def rmdir(self, /) -> dict:
        return self.fs.rmdir(self)

    def touch(self, /) -> Self:
        self.__dict__.update(self.fs.touch(self))
        return self

    unlink = remove

    def write_bytes(
        self, 
        /, 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
    ) -> Self:
        self.__dict__.update(self.fs.write_bytes(self, data))
        return self

    def write_text(
        self, 
        /, 
        text: str = "", 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
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
        client: P115Client, 
        attr_cache: Optional[MutableMapping[int, dict]] = None, 
        path_to_id: Optional[MutableMapping[str, int]] = None, 
        get_version: Optional[Callable] = lambda attr: attr.get("mtime", 0), 
    ):
        if attr_cache is not None:
            attr_cache = {}
        if type(path_to_id) is dict:
            path_to_id["/"] = 0
        elif path_to_id is not None:
            path_to_id = ChainMap(path_to_id, {"/": 0})
        self.__dict__.update(
            client = client, 
            cid = 0, 
            path = "/", 
            path_to_id = path_to_id, 
            attr_cache = attr_cache, 
            get_version = get_version, 
        )

    def __delitem__(self, id_or_path: IDOrPathType, /):
        self.rmtree(id_or_path)

    def __len__(self, /) -> int:
        return self.get_directory_capacity(self.cid)

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def __setitem__(
        self, 
        id_or_path: IDOrPathType, 
        file: None | str | bytes | bytearray | memoryview | PathLike = None, 
        /, 
    ):
        if file is None:
            return self.touch(id_or_path)
        elif isinstance(file, PathLike):
            if ospath.isdir(file):
                return list(self.upload_tree(file, id_or_path, no_root=True, overwrite_or_ignore=True))
            else:
                return self.upload(file, id_or_path, overwrite_or_ignore=True)
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
        kwargs["client"] = P115Client(cookie, login_app=app)
        return cls(**kwargs)

    @check_response
    def _copy(self, id: int, pid: int = 0, /) -> dict:
        return self.client.fs_copy(id, pid)

    @check_response
    def _delete(self, id: int, /) -> dict:
        return self.client.fs_delete(id)

    def _files(
        self, 
        /, 
        id: int = 0, 
        limit: int = 32, 
        offset: int = 0, 
    ) -> dict:
        resp = check_response(self.client.fs_files({
            "cid": id, 
            "limit": limit, 
            "offset": offset, 
            "show_dir": 1, 
        }))
        if id and int(resp["path"][-1]["cid"]) != id:
            raise NotADirectoryError(errno.ENOTDIR, f"{id} is not a directory")
        return resp

    @check_response
    def _info(self, id: int, /) -> dict:
        return self.client.fs_info({"file_id": id})

    @check_response
    def _mkdir(self, name: str, pid: int = 0, /) -> dict:
        return self.client.fs_mkdir({"cname": name, "pid": pid})

    @check_response
    def _move(self, id: int, pid: int = 0, /) -> dict:
        return self.client.fs_move(id, pid)

    @check_response
    def _rename(self, id: int, name: str, /) -> dict:
        return self.client.fs_rename([(id, name)])

    @check_response
    def _search(self, payload: dict, /) -> dict:
        return self.client.fs_search(payload)

    @check_response
    def space_summury(self, /) -> dict:
        return self.client.fs_space_summury()

    def _upload(self, file, name, pid: int = 0) -> dict:
        if not hasattr(file, "getbuffer") or len(file.getbuffer()) > 0:
            try:
                file.seek(0, 1)
            except:
                pass
            else:
                resp = self.client.upload_file(file, name, pid)
                name = resp["data"]["file_name"]
                try:
                    return self._attr_path([name], pid)
                except FileNotFoundError:
                    self._files(pid, 1)
                    return self._attr_path([name], pid)
        resp = check_response(self.client.upload_file_sample)(file, name, pid)
        id = int(resp["data"]["file_id"])
        try:
            return self._attr(id)
        except FileNotFoundError:
            self._files(pid, 1)
            return self._attr(id)

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
                cid = get()
                try:
                    cache = attr_cache[cid]
                    del attr_cache[cid]
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
                cid = get()
                try:
                    cache = attr_cache[cid]
                    del attr_cache[cid]
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

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        refresh: bool = False, 
    ) -> Iterator[AttrDict]:
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
                    if id_or_path.is_attr_loaded:
                        id_or_path()
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
            pagesize = 1 << 10
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
                get_files = self._files
                resp = get_files(id, limit=pagesize)
                dirname = joins(("", *(a["name"] for a in resp["path"][1:])))
                if path_to_id is not None:
                    path_to_id[dirname] = id
                last_update = datetime.now()
                count = resp["count"]
                for attr in resp["data"]:
                    yield normalize_attr(attr, dirname, fs=self, last_update=last_update)
                for offset in range(pagesize, count, 1 << 10):
                    resp = get_files(id, limit=pagesize, offset=offset)
                    last_update = datetime.now()
                    if resp["count"] != count:
                        raise RuntimeError(f"{id} detected count changes during iteration")
                    for attr in resp["data"]:
                        yield normalize_attr(attr, dirname, fs=self, last_update=last_update)
            children = {a["id"]: a for a in iterdir()}
            if attr_cache is not None:
                attrs = attr_cache[id] = {"version": version, "attr": attr, "children": children}
        else:
            children = pid_attrs["children"]
        return iter(children.values())

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
                "last_update": last_update, 
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
            data = self._info(id)["data"][0]
        except OSError as e:
            raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}") from e
        attr = normalize_info(data, fs=self, last_update=datetime.now())
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
        pid: Optional[int] = None, 
    )  -> AttrDict:
        if isinstance(path, PathLike):
            path = fspath(path)
        if pid is None:
            pid = self.cid
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
    )  -> AttrDict:
        if isinstance(id_or_path, P115Path):
            return self._attr(id_or_path.id)
        elif isinstance(id_or_path, dict):
            attr = id_or_path
            if "id" in attr:
                return self._attr(attr["id"])
            return self._attr_path(attr["path"])
        elif isinstance(id_or_path, int):
            return self._attr(id_or_path)
        else:
            return self._attr_path(id_or_path, pid)

    # TODO 各种 batch_* 方法

    def copy(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
        recursive: bool = False, 
    ) -> Optional[dict]:
        src_patht = self.get_patht(src_path, pid)
        dst_patht = self.get_patht(dst_path, pid)
        src_fullpath = joins(src_patht)
        dst_fullpath = joins(dst_patht)
        src_attr = self.attr(src_path, pid)
        if src_attr["is_directory"]:
            if recursive:
                return self.copytree(
                    src_attr["id"], 
                    dst_path, 
                    pid, 
                    overwrite_or_ignore=overwrite_or_ignore, 
                )
            if overwrite_or_ignore == False:
                return None
            raise IsADirectoryError(
                errno.EISDIR, f"source is a directory: {src_fullpath!r} -> {dst_fullpath!r}")
        if src_patht == dst_patht:
            if overwrite_or_ignore is None:
                raise SameFileError(src_fullpath)
            return None
        elif dst_patht == src_patht[:len(dst_patht)]:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a path as its ancestor is not allowed: {src_fullpath!r} -> {dst_fullpath!r}", 
            )
        elif src_patht == dst_patht[:len(src_patht)]:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a path as its descendant is not allowed: {src_fullpath!r} -> {dst_fullpath!r}", 
            )
        *src_dirt, src_name = src_patht
        *dst_dirt, dst_name = dst_patht
        try:
            dst_attr = self.attr(dst_path, pid)
        except FileNotFoundError:
            if src_dirt == dst_dirt:
                dst_pid = src_attr["parent_id"]
            else:
                destdir_attr = self.attr(dst_dirt)
                if not destdir_attr["is_directory"]:
                    raise NotADirectoryError(
                        errno.ENOTDIR, 
                        f"parent path {joins(dst_dirt)!r} is not directory: {src_fullpath!r} -> {dst_fullpath!r}", 
                    )
                dst_pid = destdir_attr["id"]
        else:
            if dst_attr["is_directory"]:
                if overwrite_or_ignore == False:
                    return None
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"destination is a directory: {src_fullpath!r} -> {dst_fullpath!r}", 
                )
            elif overwrite_or_ignore is None:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"destination already exists: {src_fullpath!r} -> {dst_fullpath!r}", 
                )
            elif not overwrite_or_ignore:
                return None
            self._delete(dst_attr["id"])
            dst_pid = dst_attr["parent_id"]
        src_id = src_attr["id"]
        if splitext(src_name)[1] != splitext(dst_name)[1]:
            dst_name = check_response(self.client.upload_file_init)(
                dst_name, 
                filesize=src_attr["size"], 
                file_sha1=src_attr["sha1"], 
                read_range_bytes_or_hash=lambda rng: self.read_bytes_range(src_id, rng), 
                pid=dst_pid, 
            )["data"]["file_name"]
            return self.attr([dst_name], dst_pid)
        elif src_name == dst_name:
            self._copy(src_id, dst_pid)
            return self.attr([src_name], dst_pid)
        else:
            tempdir_id = int(self._mkdir(str(uuid4()))["cid"])
            try:
                self._copy(src_id, tempdir_id)
                dst_id = self.attr([src_name], tempdir_id)["id"]
                resp = self._rename(dst_id, dst_name)
                if resp["data"]:
                    dst_name = resp["data"][str(dst_id)]
                self._move(dst_id, dst_pid)
            finally:
                self._delete(tempdir_id)
            return self.attr(dst_id)

    def copytree(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType = "", 
        pid: Optional[int] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
        **kwargs, 
    ) -> Optional[dict]:
        src_attr = self.attr(src_path, pid)
        src_id = src_attr["id"]
        if not src_attr["is_directory"]:
            return self.copy(
                src_id, 
                dst_path, 
                pid, 
                overwrite_or_ignore=overwrite_or_ignore, 
            )
        src_name = src_attr["name"]
        src_fullpath = src_attr["path"]
        try:
            dst_attr = self.attr(dst_path, pid)
        except FileNotFoundError:
            if isinstance(dst_path, int):
                if overwrite_or_ignore == False:
                    return None
                raise
            dst_patht = self.get_patht(dst_path, pid)
            if len(dst_patht) == 1:
                dst_attr = self.attr(0)
                dst_id = 0
            else:
                dst_attr = self.makedirs(dst_patht[:-1], exist_ok=True)
                dst_id = dst_attr["id"]
                if src_name == dst_patht[-1]:
                    self._copy(src_id, dst_id)
                    return self.attr([src_name], dst_id)
                dst_attr = self.makedirs([src_name], dst_id, exist_ok=True)
                dst_id = dst_attr["id"]
        else:
            dst_id = dst_attr["id"]
            dst_fullpath = dst_attr["path"]
            if src_fullpath == dst_fullpath:
                if overwrite_or_ignore is None:
                    raise SameFileError(dst_fullpath)
                return None
            elif any(a["id"] == src_id for a in self.get_ancestors(dst_id)):
                if overwrite_or_ignore == False:
                    return None
                raise PermissionError(
                    errno.EPERM, 
                    f"copy a directory as its descendant is not allowed: {src_fullpath!r} -> {dst_fullpath!r}", 
                )
            elif not dst_attr["is_directory"]:
                if overwrite_or_ignore == False:
                    return None
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"destination is not directory: {src_fullpath!r} -> {dst_fullpath!r}", 
                )
            elif overwrite_or_ignore is None:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"destination already exists: {src_fullpath!r} -> {dst_fullpath!r}", 
                )
        for attr in self.iterdir(src_id, **kwargs):
            if attr["is_directory"]:
                self.copytree(
                    attr["id"], 
                    [attr["name"]], 
                    dst_id, 
                    overwrite_or_ignore=overwrite_or_ignore, 
                )
            else:
                self.copy(
                    attr["id"], 
                    [attr["name"]], 
                    dst_id, 
                    overwrite_or_ignore=overwrite_or_ignore, 
                )
        return self.attr(dst_attr["id"])

    def _dir_get_ancestors(self, id: int, /) -> list[dict]:
        ls = [{"name": "", "id": 0, "parent_id": 0, "is_directory": True}]
        if id:
            ls.extend(
                {"name": p["name"], "id": int(p["cid"]), "parent_id": int(p["pid"]), "is_directory": True} 
                for p in self._files(id, limit=1)["path"][1:]
            )
        return ls

    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> list[dict]:
        attr = self.attr(id_or_path, pid)
        ls = self._dir_get_ancestors(attr["parent_id"])
        ls.append({"name": attr["name"], "id": attr["id"], "parent_id": attr["parent_id"], "is_directory": attr["is_directory"]})
        return ls

    def get_directory_capacity(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> int:
        return self._files(self.get_id(id_or_path, pid), limit=1)["count"]

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
    ) -> str:
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{attr['path']!r} (id={attr['id']!r}) is a directory")
        return self.client.download_url(attr["pick_code"], headers=headers)

    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> bool:
        attr: dict | P115Path
        if isinstance(id_or_path, P115Path):
            attr = id_or_path
        else:
            try:
                attr = self.attr(id_or_path, pid)
            except FileNotFoundError:
                return True
        if attr["is_directory"]:
            return self.get_directory_capacity(attr["id"]) > 0
        return attr["size"] == 0

    def makedirs(
        self, 
        path: str | PathLike[str] | Sequence[str] | AttrDict, 
        /, 
        pid: Optional[int] = None, 
        exist_ok: bool = False, 
    ) -> dict:
        if isinstance(path, dict):
            patht, parents = splits(path["path"])
        elif isinstance(path, (str, PathLike)):
            patht, parents = splits(fspath(path))
        else:
            patht = [p for p in path if p]
            parents = 0
        if pid is None:
            pid = self.cid
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
                resp = self._mkdir(name, pid)
                pid = int(resp["cid"])
                attr = get_attr(pid)
            else:
                exists = True
                if not attr["is_directory"]:
                    raise NotADirectoryError(errno.ENOTDIR, f"{path!r} (in {pid!r}): there is a superior non-directory")
                pid = attr["id"]
        if not exist_ok and exists:
            raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) exists")
        return attr

    def mkdir(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: Optional[int] = None, 
    ) -> dict:
        if isinstance(path, (str, PathLike)):
            patht, parents = splits(fspath(path))
        else:
            patht = [p for p in path if p]
            parents = 0
        if not patht or patht == [""]:
            raise OSError(errno.EINVAL, f"invalid path: {path!r}")
        if pid is None:
            pid = self.cid
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
                    raise NotADirectoryError(errno.ENOTDIR, f"{attr['id']!r} ({name!r} in {pid!r}) not a directory")
                pid = attr["id"]
        else:
            raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) already exists")
        if i < len(patht):
            raise FileNotFoundError(errno.ENOENT, f"{path!r} (in {pid!r}) missing superior directory")
        resp = self._mkdir(name, pid)
        return self.attr(int(resp["cid"]))

    def move(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Optional[dict]:
        try:
            dst_attr = self.attr(dst_path, pid)
        except FileNotFoundError:
            return self.rename(src_path, dst_path, pid)
        src_attr = self.attr(src_path, pid)
        src_id = src_attr["id"]
        dst_id = dst_attr["id"]
        if src_id == dst_id or src_attr["parent_id"] == dst_id:
            return None
        if any(a["id"] == src_id for a in self.get_ancestors(dst_id)):
            raise PermissionError(errno.EPERM, f"move a path to its subordinate path is not allowed: {src_id!r} -> {dst_id!r}")
        if dst_attr["is_directory"]:
            name = src_attr["name"]
            if self.exists([name], dst_id):
                raise FileExistsError(errno.EEXIST, f"destination {name!r} (in {dst_id!r}) already exists")
            self._move(src_id, dst_id)
            new_attr = self.attr(src_id)
            self._update_cache_path(src_attr, new_attr)
            return new_attr
        raise FileExistsError(errno.EEXIST, f"destination {dst_id!r} already exists")

    # TODO: 由于 115 网盘不支持删除里面有超过 5 万个文件等文件夹，因此需要增加参数，支持在失败后，拆分任务，返回一个 Future 对象，可以获取已完成和未完成，并且可以随时取消
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
        recursive: bool = False, 
    ) -> dict:
        attr = self.attr(id_or_path, pid)
        id = attr["id"]
        clear_cache = self._clear_cache
        if attr["is_directory"]:
            if not recursive:
                raise IsADirectoryError(errno.EISDIR, f"{id_or_path!r} (in {pid!r}) is a directory")
            if id == 0:
                for subattr in self.iterdir(0):
                    cid = subattr["id"]
                    self._delete(cid)
                    clear_cache(subattr)
                return attr
        self._delete(id)
        clear_cache(attr)
        return attr

    def removedirs(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> Optional[dict]:
        try:
            attr = self.attr(id_or_path, pid)
        except FileNotFoundError:
            return None
        if not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{attr['path']!r} (id={attr['id']!r}) is not a directory")
        delid = 0
        pid = attr["id"]
        pattr = attr
        get_files = self._files
        while pid:
            files = get_files(pid, limit=1)
            if files["count"] > 1:
                break
            delid = pid
            pid = int(files["path"][-1]["pid"])
            pattr = {
                "id": delid, 
                "parent_id": pid, 
                "is_directory": True, 
                "path": "/" + joins([p["name"] for p in files["path"][1:]]), 
            }
        if delid == 0:
            return None
        self._delete(delid)
        self._clear_cache(pattr)
        return attr

    # TODO: 支持 dst_path 从 src_path 开始的相对路径
    def rename(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
        replace: bool = False, 
    ) -> Optional[dict]:
        src_patht = self.get_patht(src_path, pid)
        dst_patht = self.get_patht(dst_path, pid)
        src_fullpath = joins(src_patht)
        dst_fullpath = joins(dst_patht)
        if src_patht == dst_patht:
            return None
        elif dst_patht == src_patht[:len(dst_patht)]:
            raise PermissionError(errno.EPERM, f"rename a path as its ancestor is not allowed: {src_fullpath!r} -> {dst_fullpath!r}")
        elif src_patht == dst_patht[:len(src_patht)]:
            raise PermissionError(errno.EPERM, f"rename a path as its descendant is not allowed: {src_fullpath!r} -> {dst_fullpath!r}")
        *src_dirt, src_name = src_patht
        *dst_dirt, dst_name = dst_patht
        src_attr = self.attr(src_path, pid)
        src_id = src_attr["id"]
        src_id_str = str(src_id)
        src_ext = splitext(src_name)[1]
        dst_ext = splitext(dst_name)[1]
        def get_result(resp):
            if resp["data"]:
                new_attr = self._attr(src_id)
                self._update_cache_path(src_attr, new_attr)
                return new_attr
            return None
        try:
            dst_attr = self.attr(dst_path, pid)
        except FileNotFoundError:
            if src_dirt == dst_dirt and (src_attr["is_directory"] or src_ext == dst_ext):
                return get_result(self._rename(src_id, dst_name))
            destdir_attr = self.attr(dst_dirt)
            if not destdir_attr["is_directory"]:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {joins(dst_dirt)!r} is not directory: {src_fullpath!r} -> {dst_fullpath!r}")
            dst_pid = destdir_attr["id"]
        else:
            if replace:
                if src_attr["is_directory"]:
                    if dst_attr["is_directory"]:
                        if self.get_directory_capacity(dst_attr["id"]):
                            raise OSError(errno.ENOTEMPTY, f"source is directory, but destination is non-empty directory: {src_fullpath!r} -> {dst_fullpath!r}")
                    else:
                        raise NotADirectoryError(errno.ENOTDIR, f"source is directory, but destination is not a directory: {src_fullpath!r} -> {dst_fullpath!r}")
                elif dst_attr["is_directory"]:
                    raise IsADirectoryError(errno.EISDIR, f"source is file, but destination is directory: {src_fullpath!r} -> {dst_fullpath!r}")
                self._delete(dst_attr["id"])
            else:
                raise FileExistsError(errno.EEXIST, f"destination already exists: {src_fullpath!r} -> {dst_fullpath!r}")
            dst_pid = dst_attr["parent_id"]
        if not (src_attr["is_directory"] or src_ext == dst_ext):
            name = check_response(self.client.upload_file_init)(
                dst_name, 
                filesize=src_attr["size"], 
                file_sha1=src_attr["sha1"], 
                read_range_bytes_or_hash=lambda rng: self.read_bytes_range(src_id, rng), 
                pid=dst_pid, 
            )["data"]["file_name"]
            self._delete(src_id)
            new_attr = self._attr_path([name], dst_pid)
            self._update_cache_path(src_attr, new_attr)
            return new_attr
        if src_name == dst_name:
            self._move(src_id, dst_pid)
            new_attr = self._attr(src_id)
            self._update_cache_path(src_attr, new_attr)
            return new_attr
        elif src_dirt == dst_dirt:
            return get_result(self._rename(src_id, dst_name))
        else:
            self._rename(src_id, str(uuid4()))
            try:
                self._move(src_id, dst_pid)
                try:
                    return get_result(self._rename(src_id, dst_name))
                except:
                    self._move(src_id, src_attr["parent_id"])
                    raise
            except:
                self._rename(src_id, src_name)
                raise

    def renames(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Optional[dict]:
        result = self.rename(src_path, dst_path, pid=pid)
        if result:
            self.removedirs(result["parent_id"])
            return result
        return None

    def replace(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Optional[dict]:
        return self.rename(src_path, dst_path, pid=pid, replace=True)

    def rmdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> dict:
        attr = self.attr(id_or_path, pid)
        id = attr["id"]
        if id == 0:
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{id_or_path!r} (in {pid!r}) is not a directory")
        elif self._files(id, limit=1)["count"]:
            raise OSError(errno.ENOTEMPTY, f"directory is not empty: {id_or_path!r} (in {pid!r})")
        self._delete(id)
        self._clear_cache(attr) 
        return attr

    def rmtree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> dict:
        return self.remove(id_or_path, pid, recursive=True)

    def search(
        self, 
        search_value: str, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        page_size: int = 1_000, 
        offset: int = 0, 
        **kwargs, 
    ) -> Iterator[P115Path]:
        assert page_size > 0
        payload = {
            "cid": self.get_id(id_or_path, pid), 
            "search_value": search_value, 
            "limit": page_size, 
            "offset": offset, 
            **kwargs, 
        }
        def wrap(attr):
            attr = normalize_info(attr, fs=self, last_update=last_update)
            return P115Path(attr)
        search = self._search
        while True:
            resp = search(payload)
            last_update = datetime.now()
            if resp["offset"] != offset:
                break
            data = resp["data"]
            if not data:
                return
            for attr in resp["data"]:
                attr = normalize_info(attr, fs=self, last_update=last_update)
                yield P115Path(attr)
            offset = payload["offset"] = offset + resp["page_size"]
            if offset >= resp["count"]:
                break

    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> stat_result:
        attr = self.attr(id_or_path, pid)
        is_dir = attr["is_directory"]
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o777, # mode
            attr["id"], # ino
            attr["parent_id"], # dev
            1, # nlink
            self.client.user_id, # uid
            1, # gid
            0 if is_dir else attr["size"], # size
            attr.get("atime", 0), # atime
            attr.get("mtime", 0), # mtime
            attr.get("ctime", 0), # ctime
        ))

    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> dict:
        try:
            return self.attr(id_or_path, pid)
        except FileNotFoundError:
            if isinstance(id_or_path, int):
                raise ValueError(f"no such id: {id_or_path!r}")
            return self.upload(BytesIO(), id_or_path, pid=pid)

    # TODO: 增加功能，返回一个 Task 对象，可以获取上传进度，可随时取消
    def upload(
        self, 
        /, 
        file: bytes | str | PathLike | SupportsRead[bytes], 
        path: IDOrPathType = "", 
        pid: Optional[int] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> dict:
        fio: SupportsRead[bytes]
        dirname: str | Sequence[str] = ""
        name: str = ""
        if not path or isinstance(path, int):
            pass
        elif isinstance(path, (str, PathLike)):
            dirname, name = ospath.split(path)
        else:
            *dirname, name = (p for p in path if p)
        if hasattr(file, "read"):
            fio = cast(SupportsRead[bytes], file)
            if not name:
                try:
                    name = ospath.basename(file.name) # type: ignore
                except:
                    pass
        elif isinstance(file, (str, PathLike)):
            file = fsdecode(file)
            fio = open(file, "rb")
            if not name:
                name = ospath.basename(file)
        else:
            fio = BytesIO(file)
        if pid is None:
            pid = self.cid
        if dirname:
            pid = cast(int, self.makedirs(dirname, pid=pid, exist_ok=True)["id"])
        if name:
            try:
                attr = self._attr_path([name], pid)
            except FileNotFoundError:
                pass
            else:
                if overwrite_or_ignore is None:
                    raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) exists")
                elif attr["is_directory"]:
                    raise IsADirectoryError(errno.EISDIR, f"{path!r} (in {pid!r}) is a directory")
                elif not overwrite_or_ignore:
                    return attr
                self._delete(attr["id"])
        return self._upload(fio, name, pid)

    # TODO: 为了提升速度，之后会支持多线程上传，以及直接上传不做检查
    # TODO: 返回上传任务的迭代器，包含进度相关信息，以及最终的响应信息
    # TODO: 增加参数，onerror, predicate, submit 等
    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str] = ".", 
        path: IDOrPathType = "", 
        pid: Optional[int] = None, 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> Iterator[dict]:
        try:
            attr = self.attr(path, pid)
        except FileNotFoundError:
            if isinstance(path, int):
                raise ValueError(f"no such id: {path!r}")
            attr = self.makedirs(path, pid, exist_ok=True)
        else:
            if not attr["is_directory"]:
                raise NotADirectoryError(errno.ENOTDIR, f"{attr['path']!r} (id={attr['id']!r}) is not a directory")
        pid = attr["id"]
        try:
            it = scandir(local_path or ".")
        except NotADirectoryError:
            yield self.upload(
                local_path, 
                [ospath.basename(local_path)], 
                pid=pid, 
                overwrite_or_ignore=overwrite_or_ignore, 
            )
        else:
            if not no_root:
                attr = self.makedirs(ospath.basename(local_path), pid, exist_ok=True)
                pid = attr["parent_id"]
            for entry in it:
                if entry.is_dir():
                    yield from self.upload_tree(
                        entry.path, 
                        entry.name, 
                        pid=pid, 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                    )
                else:
                    yield self.upload(
                        entry.path, 
                        entry.name, 
                        pid=pid, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                    )
            return attr

    unlink = remove

    def write_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
        pid: Optional[int] = None, 
    ) -> dict:
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = BytesIO(data)
        return self.upload(data, id_or_path, pid=pid, overwrite_or_ignore=True)

    def write_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        text: str = "", 
        pid: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ) -> dict:
        bio = BytesIO()
        if text:
            if encoding is None:
                encoding = "utf-8"
            tio = TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)
            tio.write(text)
            tio.flush()
            bio.seek(0)
        return self.write_bytes(id_or_path, bio, pid=pid)

    cp  = copy
    mv  = move
    rm  = remove


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

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    @classmethod
    def login(
        cls, 
        /, 
        share_link: str, 
        cookie = None, 
        app: str = "web", 
    ) -> Self:
        return cls(P115Client(cookie, login_app=app), share_link)

    def set_receive_code(self, code: str, /):
        self.__dict__["receive_code"] = code

    @check_response
    def _files(
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
        return self._files(limit=1)["data"]

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
                "last_update": datetime.now(), 
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
                get_files = self._files
                path_to_id = self.path_to_id
                data = get_files(id, page_size)["data"]
                last_update = datetime.now()
                for attr in map(normalize_info, data["list"]):
                    attr["fs"] = self
                    attr["last_update"] = last_update
                    path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                    path_to_id[path] = attr["id"]
                    yield attr
                for offset in range(page_size, data["count"], page_size):
                    data = get_files(id, page_size, offset)["data"]
                    last_update = datetime.now()
                    for attr in map(normalize_info, data["list"]):
                        attr["fs"] = self
                        attr["last_update"] = last_update
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
        last_update = attr.get("last_update") or datetime.now()
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o444, 
            attr["id"], 
            attr["parent_id"], 
            1, 
            self.user_id, 
            1, 
            0 if is_dir else attr["size"], 
            attr.get("time", last_update).timestamp(), 
            attr.get("time", last_update).timestamp(), 
            attr.get("time", last_update).timestamp(), 
        ))


# TODO: 兼容 pathlib.Path 和 zipfile.Path 的接口
class P115ZipPath(P115PathBase):
    fs: P115ZipFileSystem
    path: str


class ExportDirStatus(Future):
    _condition: Condition
    _state: str

    def __init__(self, /, client: P115Client, export_id: int | str):
        super().__init__()
        self.status = 0
        self.set_running_or_notify_cancel()
        self._run_check(client, export_id)

    def __bool__(self, /) -> bool:
        return self.status == 1

    def __del__(self, /):
        self.stop()

    def stop(self, /):
        with self._condition:
            if self._state in ["RUNNING", "PENDING"]:
                self._state = "CANCELLED"
                self.set_exception(OSError(errno.ECANCELED, "canceled"))

    def _run_check(self, client, export_id: int | str, /):
        check = check_response(client.fs_export_dir_status)
        payload = {"export_id": export_id}
        def update_progress():
            while self.running():
                try:
                    data = check(payload)["data"]
                    if data:
                        self.status = 1
                        self.set_result(data)
                        return
                except BaseException as e:
                    self.set_exception(e)
                    return
                sleep(1)
        Thread(target=update_progress).start()


class PushExtractProgress(Future):
    _condition: Condition
    _state: str

    def __init__(self, /, client: P115Client, pick_code: str):
        super().__init__()
        self.progress = 0
        self.set_running_or_notify_cancel()
        self._run_check(client, pick_code)

    def __del__(self, /):
        self.stop()

    def __bool__(self, /) -> bool:
        return self.progress == 100

    def stop(self, /):
        with self._condition:
            if self._state in ["RUNNING", "PENDING"]:
                self._state = "CANCELLED"
                self.set_exception(OSError(errno.ECANCELED, "canceled"))

    def _run_check(self, client, pick_code: str, /):
        check = check_response(client.extract_push_progress)
        payload = {"pick_code": pick_code}
        def update_progress():
            while self.running():
                try:
                    data = check(payload)["data"]
                    extract_status = data["extract_status"]
                    progress = extract_status["progress"]
                    if progress == 100:
                        self.set_result(data)
                        return
                    match extract_status["unzip_status"]:
                        case 1 | 2 | 4:
                            self.progress = progress
                        case 0:
                            raise OSError(errno.EIO, f"bad file format: {data!r}")
                        case 6:
                            raise OSError(errno.EINVAL, f"wrong password/secret: {data!r}")
                        case _:
                            raise OSError(errno.EIO, f"undefined error: {data!r}")
                except BaseException as e:
                    self.set_exception(e)
                    return
                sleep(1)
        Thread(target=update_progress).start()


class ExtractProgress(Future):
    _condition: Condition
    _state: str

    def __init__(self, /, client: P115Client, extract_id: int | str):
        super().__init__()
        self.progress = 0
        self.set_running_or_notify_cancel()
        self._run_check(client, extract_id)

    def __del__(self, /):
        self.stop()

    def __bool__(self, /) -> bool:
        return self.progress == 100

    def stop(self, /):
        with self._condition:
            if self._state in ["RUNNING", "PENDING"]:
                self._state = "CANCELLED"
                self.set_exception(OSError(errno.ECANCELED, "canceled"))

    def _run_check(self, client, extract_id: int | str, /):
        check = check_response(client.extract_progress)
        payload = {"extract_id": extract_id}
        def update_progress():
            while self.running():
                try:
                    data = check(payload)["data"]
                    if not data:
                        raise OSError(errno.EINVAL, f"no such extract_id: {extract_id}")
                    progress = data["percent"]
                    self.progress = progress
                    if progress == 100:
                        self.set_result(data)
                        return
                except BaseException as e:
                    self.set_exception(e)
                    return
                sleep(1)
        Thread(target=update_progress).start()


# TODO: 参考 zipfile 模块的接口设计 namelist、filelist 等属性，以及其它的和 zipfile 兼容的接口
# TODO: 当文件特别多时，可以用 zipfile 等模块来读取文件列表
class P115ZipFileSystem(P115FileSystemBase[P115ZipPath]):
    file_id: Optional[int]
    pick_code: str
    path_to_id: MutableMapping[str, int]
    id_to_attr: MutableMapping[int, AttrDict]
    attr_cache: MutableMapping[int, tuple[AttrDict]]
    full_loaded: bool
    path_class = P115ZipPath

    def __init__(
        self, 
        /, 
        client: P115Client, 
        id_or_pickcode: int | str, 
    ):
        file_id: Optional[int]
        if isinstance(id_or_pickcode, int):
            file_id = id_or_pickcode
            pick_code = client.fs.attr(file_id)["pick_code"]
        else:
            file_id = None
            pick_code = id_or_pickcode
        resp = check_response(client.extract_push_progress(pick_code))
        if resp["data"]["extract_status"]["unzip_status"] != 4:
            raise OSError(errno.EIO, "file was not decompressed")
        self.__dict__.update(
            client=client, 
            cid=0, 
            path="/", 
            pick_code=pick_code, 
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
        raise TypeError("can't set attribute")

    @classmethod
    def login(
        cls, 
        /, 
        id_or_pickcode: int | str, 
        cookie = None, 
        app: str = "web", 
    ) -> Self:
        return cls(P115Client(cookie, login_app=app), id_or_pickcode)

    @check_response
    def _files(
        self, 
        /, 
        path: str = "", 
        next_marker: str = "", 
    ) -> dict:
        return self.client.extract_list(
            path=path, 
            pick_code=self.pick_code, 
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
                "last_update": datetime.now(), 
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

    def extract(
        self, 
        /, 
        paths: str | Sequence[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
    ) -> ExtractProgress:
        return self.client.extract_file_future(self.pick_code, paths, dirname, to_pid)

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
    ) -> str:
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{attr['path']!r} (id={attr['id']!r}) is a directory")
        return self.client.extract_download_url(self.pick_code, attr["path"], headers=headers)

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[AttrDict]:
        def normalize_info(info):
            timestamp = info.get("time") or 0
            return {
                "name": info["file_name"], 
                "is_directory": info["file_category"] == 0, 
                "file_category": info["file_category"], 
                "size": info["size"], 
                "time": datetime.fromtimestamp(timestamp), 
                "timestamp": timestamp, 
                "fs": self, 
            }
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
                get_files = self._files
                path_to_id = self.path_to_id
                data = get_files(dirname)["data"]
                last_update = datetime.now()
                for attr in map(normalize_info, data["list"]):
                    attr["last_update"] = last_update
                    path = joinpath(dirname, escape(attr["name"]))
                    attr.update(id=nextid(), parent_id=id, path=path)
                    path_to_id[path] = attr["id"]
                    yield attr
                next_marker = data["next_marker"]
                while next_marker:
                    data = get_files(dirname, next_marker)["data"]
                    last_update = datetime.now()
                    for attr in map(normalize_info, data["list"]):
                        attr["last_update"] = last_update
                        path = joinpath(dirname, escape(attr["name"]))
                        attr.update(id=nextid(), parent_id=id, path=path)
                        path_to_id[path] = attr["id"]
                        yield attr
                    next_marker = data["next_marker"]
            t = self.attr_cache[id] = tuple(iterdir())
            self.id_to_attr.update((attr["id"], attr) for attr in t)
            return iter(t)


class P115Offline:
    __slots__ = ("client", "_sign_time")

    client: P115Client
    _sign_time: MappingProxyType

    def __init__(self, /, client: P115Client):
        self.client = client

    def __contains__(self, hash: str, /) -> bool:
        return any(item["info_hash"] == hash for item in self)

    def __delitem__(self, hash: str, /):
        return self.remove(hash)

    def __getitem__(self, hash: str, /) -> dict:
        for item in self:
            if item["info_hash"] == hash:
                return item
        raise LookupError(f"no such hash: {hash!r}")

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        return check_response(self.client.offline_list())["count"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @property
    def sign_time(self, /) -> MappingProxyType:
        try:
            sign_time = self._sign_time
            if time() - sign_time["time"] < 30 * 60:
                return sign_time
        except AttributeError:
            pass
        info = check_response(self.client.offline_info())
        sign_time = self._sign_time = MappingProxyType({"sign": info["sign"], "time": info["time"]})
        return sign_time

    def add(
        self, 
        urls: str | Iterable[str], 
        /, 
        pid: Optional[int] = None, 
        savepath: Optional[str] = None, 
    ) -> dict:
        payload: dict
        if isinstance(urls, str):
            payload = {"url": urls}
            method = self.client.offline_add_url
        else:
            payload = {f"url[{i}]": url for i, url in enumerate(urls)}
            if not payload:
                raise ValueError("no `url` specified")
            method = self.client.offline_add_urls
        payload.update(self.sign_time)
        if pid is not None:
            payload["wp_path_id"] = pid
        if savepath:
            payload["savepath"] = savepath
        return check_response(method(payload))

    def add_torrent(
        self, 
        torrent_or_magnet_or_sha1_or_fid: int | bytes | str, 
        /, 
        pid: Optional[int] = None, 
        savepath: Optional[str] = None, 
        predicate: None | str | Callable[[dict], bool] = None, 
    ) -> dict:
        resp = check_response(self.torrent_info(torrent_or_magnet_or_sha1_or_fid))
        if predicate is None:
            wanted = ",".join(
                str(i) for i, info in enumerate(resp["torrent_filelist_web"])
                if info["wanted"]
            )
        elif isinstance(predicate, str):
            wanted = predicate
        else:
            wanted = ",".join(
                str(i) for i, info in enumerate(resp["torrent_filelist_web"]) 
                if predicate(info)
            )
        payload = {
            "info_hash": resp["info_hash"], 
            "wanted": wanted, 
            "savepath": resp["torrent_name"] if savepath is None else savepath, 
        }
        if pid is not None:
            payload["wp_path_id"] = pid
        payload.update(self.sign_time)
        return check_response(self.client.offline_add_torrent(payload))

    def clear(self, /, flag: int = 1) -> dict:
        """清空离线任务列表

        :param flag: 操作目标
            - 0: 已完成
            - 1: 全部（默认值）
            - 2: 已失败
            - 3: 进行中
            - 4: 已完成+删除源文件
            - 5: 全部+删除源文件
        """
        return check_response(self.client.offline_clear(flag))

    def get(self, hash: str, /, default=None):
        return next((item for item in self if item["info_hash"] == hash), default)

    def iter(self, /, start_page: int = 1) -> Iterator[dict]:
        if start_page < 1:
            page = 1
        else:
            page = start_page
        resp = check_response(self.client.offline_list(page))
        if not resp["tasks"]:
            return
        yield from resp["tasks"]
        page_count = resp["page_count"]
        if page_count <= page:
            return
        count = resp["count"]
        for page in range(page + 1, page_count + 1):
            resp = check_response(self.client.offline_list(page))
            if count != resp["count"]:
                raise RuntimeError("detected count changes during iteration")
            if not resp["tasks"]:
                return
            yield from resp["tasks"]

    def list(self, /, page: int = 0) -> list[dict]:
        if page <= 0:
            return list(self.iter())
        return check_response(self.client.offline_list(page))["tasks"]

    def remove(
        self, 
        hashes: str | Iterable[str], 
        /, 
        remove_files: bool = False, 
    ) -> dict:
        if isinstance(hashes, str):
            payload = {"hash[0]": hashes}
        else:
            payload = {f"hash[{i}]": h for i, h in enumerate(hashes)}
            if not payload:
                raise ValueError("no `hash` specified")
        if remove_files:
            payload["flag"] = "1"
        payload.update(self.sign_time)
        return check_response(self.client.offline_remove(payload))

    def torrent_info(self, torrent_or_magnet_or_sha1_or_fid: int | bytes | str, /) -> dict:
        torrent = None
        if isinstance(torrent_or_magnet_or_sha1_or_fid, int):
            fid = torrent_or_magnet_or_sha1_or_fid
            resp = check_response(self.client.fs_file(fid))
            sha = resp["data"][0]["sha1"]
        elif isinstance(torrent_or_magnet_or_sha1_or_fid, bytes):
            torrent = torrent_or_magnet_or_sha1_or_fid
        elif torrent_or_magnet_or_sha1_or_fid.startswith("magnet:?xt=urn:btih:"):
            m2t = Magnet2Torrent(torrent_or_magnet_or_sha1_or_fid)
            torrent = run(m2t.retrieve_torrent())[1]
        else:
            sha = torrent_or_magnet_or_sha1_or_fid
        if torrent is None:
            resp = check_response(self.client.offline_torrent_info(sha))
        else:
            sha = sha1(torrent).hexdigest()
            try:
                resp = check_response(self.client.offline_torrent_info(sha))
            except:
                name = f"{sha}.torrent"
                check_response(self.client.upload_file_sample(torrent, name, 0))
                resp = check_response(self.client.offline_torrent_info(sha))
        resp["sha1"] = sha
        return resp


class P115Recyclebin:
    __slots__ = ("client", "password")

    def __init__(
        self, 
        client: P115Client, 
        /, 
        password: int | str = "", 
    ):
        self.client = client
        self.password = password

    def __contains__(self, id: int | str, /) -> bool:
        ids = str(id)
        return any(item["id"] == ids for item in self)

    def __delitem__(self, id: int | str, /):
        return self.remove(id)

    def __getitem__(self, id: int | str, /) -> dict:
        ids = str(id)
        for item in self:
            if item["id"] == ids:
                return item
        raise LookupError(f"no such id: {id!r}")

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        return int(check_response(self.client.recyclebin_list({"limit": 1}))["count"])

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @check_response
    def clear(self, /, password: None | int | str = None) -> dict:
        if password is None:
            password = self.password
        return self.client.recyclebin_clean({"password": password})

    def get(self, id: int | str, /, default=None):
        ids = str(id)
        return next((item for item in self if item["id"] == ids), default)

    def iter(self, /, offset: int = 0, page_size: int = 1 << 10) -> Iterator[dict]:
        if offset < 0:
            offset = 0
        if page_size <= 0:
            page_size = 1 << 10
        payload = {"offset": offset, "limit": page_size}
        count = 0
        while True:
            resp = check_response(self.client.recyclebin_list(payload))
            if resp["offset"] != offset:
                return
            if count == 0:
                count = int(resp["count"])
            elif count != int(resp["count"]):
                raise RuntimeError("detected count changes during iteration")
            yield from resp["data"]
            if len(resp["data"]) < resp["page_size"]:
                return
            payload["offset"] = offset + resp["page_size"]

    def list(self, /, offset: int = 0, limit: int = 0) -> list[dict]:
        if limit <= 0:
            return list(self.iter(offset))
        resp = check_response(self.client.recyclebin_list({"offset": offset, "limit": limit}))
        if resp["offset"] != offset:
            return []
        return resp["data"]

    @check_response
    def remove(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        password: None | int | str = None, 
    ) -> dict:
        if isinstance(ids, (int, str)):
            payload = {"rid[0]": ids}
        else:
            payload = {f"rid[{i}]": id for i, id in enumerate(ids)}
        payload["password"] = self.password if password is None else password
        return self.client.recyclebin_clean(payload)

    @check_response
    def revert(self, ids: int | str | Iterable[int | str], /) -> dict:
        if isinstance(ids, (int, str)):
            payload = {"rid[0]": ids}
        else:
            payload = {f"rid[{i}]": id for i, id in enumerate(ids)}
        return self.client.recyclebin_revert(payload)


class P115Sharing:
    __slots__ = "client",

    def __init__(self, client: P115Client, /):
        self.client = client

    def __contains__(self, code_or_id: int | str, /) -> bool:
        if isinstance(code_or_id, str):
            return self.client.share_info(code_or_id)["state"]
        snap_id = str(code_or_id)
        return any(item["snap_id"] == snap_id for item in self)

    def __delitem__(self, code_or_id: int | str, /):
        return self.remove(code_or_id)

    def __getitem__(self, code_or_id: int | str, /) -> dict:
        if isinstance(code_or_id, str):
            resp = self.client.share_info(code_or_id)
            if resp["state"]:
                return resp["data"]
            raise LookupError(f"no such share_code: {code_or_id!r}, with message: {resp!r}")
        snap_id = str(code_or_id)
        for item in self:
            if item["snap_id"] == snap_id:
                return item
        raise LookupError(f"no such snap_id: {snap_id!r}")

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        return check_response(self.client.share_list({"limit": 1}))["count"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @check_response
    def add(
        self, 
        file_ids: int | str | Iterable[int | str], 
        /, 
        is_asc: Literal[0, 1] = 1, 
        order: str = "file_name", 
        ignore_warn: Literal[0, 1] = 1, 
    ) -> dict:
        if not isinstance(file_ids, (int, str)):
            file_ids = ",".join(map(str, file_ids))
            if not file_ids:
                raise ValueError("no `file_id` specified") 
        return self.client.share_send({
            "file_ids": file_ids, 
            "is_asc": is_asc, 
            "order": order, 
            "ignore_warn": ignore_warn, 
        })

    @check_response
    def clear(self, /) -> dict:
        return self.client.share_update({
            "share_code": ",".join(item["share_code"] for item in self), 
            "action": "cancel", 
        })

    def get(self, code_or_id: int | str, /, default=None):
        if isinstance(code_or_id, str):
            resp = self.client.share_info(code_or_id)
            if resp["state"]:
                return resp["data"]
            return default
        snap_id = str(code_or_id)
        return next((item for item in self if item["snap_id"] == snap_id), default)

    def iter(self, /, offset: int = 0, page_size: int = 1 << 10) -> Iterator[dict]:
        if offset < 0:
            offset = 0
        if page_size <= 0:
            page_size = 1 << 10
        payload = {"offset": offset, "limit": page_size}
        count = 0
        while True:
            resp = check_response(self.client.share_list(payload))
            if count == 0:
                count = resp["count"]
            elif count != resp["count"]:
                raise RuntimeError("detected count changes during iteration")
            yield from resp["list"]
            if len(resp["list"]) < page_size:
                break
            payload["offset"] = offset + page_size

    def list(self, /, offset: int = 0, limit: int = 0) -> list[dict]:
        if limit <= 0:
            return list(self.iter(offset))
        return check_response(self.client.share_list({"offset": offset, "limit": limit}))["list"]

    @check_response
    def remove(self, code_or_id_s: int | str | Iterable[int | str], /) -> dict:
        def share_code_of(code_or_id: int | str) -> str:
            if isinstance(code_or_id, str):
                return code_or_id
            return self[code_or_id]["share_code"]
        if isinstance(code_or_id_s, (int, str)):
            share_code = share_code_of(code_or_id_s)
        else:
            share_code = ",".join(map(share_code_of, code_or_id_s))
            if not share_code:
                raise ValueError("no `share_code` or `snap_id` specified")
        return self.client.share_update({
            "share_code": share_code, 
            "action": "cancel", 
        })

    @check_response
    def update(self, /, share_code: str, **payload) -> dict:
        return self.client.share_update({"share_code": share_code, **payload})


# TODO upload_tree 多线程和进度条，并且为每一个上传返回一个 task，可重试
# TODO 能及时处理文件已不存在
# TODO 为各个fs接口添加额外的请求参数
# TODO 115中多个文件可以在同一目录下同名，如何处理
# TODO 提供一个新的上传函数，上传如果失败，因为名字问题，则尝试用uuid名字，上传成功后，再进行改名，如果成功，删除原来的文件，不成功，则删掉上传的文件（如果上传成功了的话）
# TODO 如果压缩包尚未解压，则使用 zipfile 之类的模块，去模拟文件系统
