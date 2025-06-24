#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["DuPanClient", "DuPanShareList"]

import errno

from base64 import b64encode
from collections import deque
from collections.abc import (
    AsyncIterator, Awaitable, Buffer, Callable, Coroutine, ItemsView, Iterable, 
    Iterator, Mapping, MutableMapping, 
)
from functools import partial
from http.cookiejar import Cookie, CookieJar
from http.cookies import Morsel
from itertools import count
from os import isatty
from posixpath import join as joinpath
from re import compile as re_compile
from typing import cast, overload, Any, Final, Literal
from urllib.parse import parse_qsl, unquote, urlparse
from uuid import uuid4

from cookietools import cookies_str_to_dict, create_cookie
from ddddocr import DdddOcr # type: ignore
from ed2k import ed2k_hash, ed2k_hash_async, Ed2kHash
from hashtools import HashObj, file_digest, file_mdigest, file_digest_async, file_mdigest_async
from httpfile import HTTPFileReader, AsyncHTTPFileReader
from http_response import get_total_length
from iterutils import run_gen_step, run_gen_step_iter, Yield, YieldFrom
from lxml.html import fromstring, tostring, HtmlElement
from orjson import dumps, loads
from property import locked_cacheproperty
from qrcode import QRCode # type: ignore
from startfile import startfile, startfile_async # type: ignore
from texttools import text_within

from .exception import check_response, DuPanOSError


# 默认的请求函数
_httpx_request = None
# 百度网盘 openapi 的应用，直接使用 AList 的
# https://alist.nn.ci/guide/drivers/baidu.html
CLIENT_ID = "iYCeC9g08h5vuP9UqvPHKKSVrKFXGa1v"
CLIENT_SECRET = "jXiFMOPVPCWlO2M5CwWQzffpNPaGTRBG"
ED2K_NAME_TRANSTAB: Final = dict(zip(b"/|", ("%2F", "%7C")))


def convert_digest(digest, /):
    if isinstance(digest, str):
        if digest == "crc32":
            from binascii import crc32
            digest = lambda: crc32
        elif digest == "ed2k":
            digest = Ed2kHash()
    return digest


def items(m: Mapping, /) -> ItemsView:
    try:
        if isinstance((items := getattr(m, "items")()), ItemsView):
            return items
    except (AttributeError, TypeError):
        pass
    return ItemsView(m)


def make_ed2k_url(
    name: str, 
    size: int | str, 
    hash: str, 
    /, 
) -> str:
    return f"ed2k://|file|{name.translate(ED2K_NAME_TRANSTAB)}|{size}|{hash}|/"


def get_default_request():
    global _httpx_request
    if _httpx_request is None:
        from httpx_request import request
        _httpx_request = partial(request, timeout=(5, 60, 60, 5))
    return _httpx_request


def default_parse(resp, content: Buffer, /):
    if isinstance(content, (bytes, bytearray, memoryview)):
        return loads(content)
    else:
        return loads(memoryview(content))


class HTTPXClientMixin:

    def __del__(self, /):
        self.close()

    @locked_cacheproperty
    def session(self, /):
        """同步请求的 session 对象
        """
        import httpx_request
        from httpx import Client, HTTPTransport
        session = Client(
            transport=HTTPTransport(retries=5), 
            verify=False, 
        )
        setattr(session, "_headers", self.headers)
        setattr(session, "_cookies", self.cookies)
        return session

    @locked_cacheproperty
    def async_session(self, /):
        """异步请求的 session 对象
        """
        import httpx_request
        from httpx import AsyncClient, AsyncHTTPTransport
        session = AsyncClient(
            transport=AsyncHTTPTransport(retries=5), 
            verify=False, 
        )
        setattr(session, "_headers", self.headers)
        setattr(session, "_cookies", self.cookies)
        return session

    @property
    def cookies(self, /):
        """请求所用的 Cookies 对象（同步和异步共用）
        """
        try:
            return self.__dict__["cookies"]
        except KeyError:
            from httpx import Cookies
            cookies = self.__dict__["cookies"] = Cookies()
            return cookies

    @cookies.setter
    def cookies(
        self, 
        cookies: None | str | Mapping[str, None | str] | Iterable[Mapping | Cookie | Morsel] = None, 
        /, 
    ):
        """更新 cookies
        """
        cookiejar = self.cookiejar
        if cookies is None:
            cookiejar.clear()
            return
        if isinstance(cookies, str):
            cookies = cookies.strip().rstrip(";")
            cookies = cookies_str_to_dict(cookies)
        set_cookie = cookiejar.set_cookie
        clear_cookie = cookiejar.clear
        cookie: Mapping | Cookie | Morsel
        if isinstance(cookies, Mapping):
            if not cookies:
                return
            for key, val in items(cookies):
                if val:
                    set_cookie(create_cookie(key, val, domain=".baidu.com"))
                else:
                    for cookie in cookiejar:
                        if cookie.name == key:
                            clear_cookie(domain=cookie.domain, path=cookie.path, name=cookie.name)
                            break
        else:
            from httpx import Cookies
            if isinstance(cookies, Cookies):
                cookies = cookies.jar
            for cookie in cookies:
                set_cookie(create_cookie("", cookie))

    @property
    def cookiejar(self, /) -> CookieJar:
        """请求所用的 CookieJar 对象（同步和异步共用）
        """
        return self.cookies.jar

    @property
    def cookies_str(self, /) -> str:
        """所有 .baidu.com 域下的 cookie 值
        """
        return "; ".join(
            f"{cookie.name}={cookie.value}" 
            for cookie in self.cookiejar
            if cookie.domain == "baidu.com" or cookie.domain.endswith(".baidu.com")
        )

    @locked_cacheproperty
    def headers(self, /) -> MutableMapping:
        """请求头，无论同步还是异步请求都共用这个请求头
        """
        from multidict import CIMultiDict
        return CIMultiDict({
            "accept": "application/json, text/plain, */*", 
            "accept-encoding": "gzip, deflate", 
            "connection": "keep-alive", 
            "user-agent": "Mozilla/5.0 AppleWebKit/600 Safari/600 Chrome/124.0.0.0", 
        })

    def close(self, /) -> None:
        """删除 session 和 async_session 属性，如果它们未被引用，则应该会被自动清理
        """
        self.__dict__.pop("session", None)
        self.__dict__.pop("async_session", None)

    def request(
        self, 
        /, 
        url: str, 
        method: str = "GET", 
        request: None | Callable = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        """执行 HTTP 请求，默认为 GET 方法
        """
        if url.startswith("//"):
            url = "https:" + url
        elif not url.startswith(("http://", "https://")):
            if not url.startswith("/"):
                url = "/" + url
            url = "https://pan.baidu.com" + url
        request_kwargs.setdefault("parse", default_parse)
        if request is None:
            request_kwargs["session"] = self.async_session if async_ else self.session
            return get_default_request()(
                url=url, 
                method=method, 
                async_=async_, 
                **request_kwargs, 
            )
        else:
            if headers := request_kwargs.get("headers"):
                headers = request_kwargs["headers"] = {**self.headers, **headers}
            else:
                headers = request_kwargs["headers"] = dict(self.headers)
            headers.setdefault("Cookie", self.cookies_str)
            return request(
                url=url, 
                method=method, 
                **request_kwargs, 
            )


class DuPanClient(HTTPXClientMixin):

    def __init__(
        self, 
        /, 
        cookies: None | str | Mapping[str, None | str] | Iterable[Mapping | Cookie | Morsel] = None, 
        console_qrcode: bool = True, 
    ):
        if cookies is None:
            self.login_with_qrcode(console_qrcode=console_qrcode)
        else:
            self.cookies = cookies

    def __eq__(self, other, /) -> bool:
        try:
            return (
                type(self) is type(other) and 
                self.baiduid == other.baiduid and 
                self.bdstoken == other.bdstoken
            )
        except AttributeError:
            return False

    def __hash__(self, /) -> int:
        return id(self)

    @locked_cacheproperty
    def session(self, /):
        """同步请求的 session 对象
        """
        import httpx_request
        from httpx import Client, HTTPTransport, Limits
        session = Client(
            limits=Limits(max_connections=256, max_keepalive_connections=64, keepalive_expiry=10), 
            transport=HTTPTransport(retries=5), 
            verify=False, 
        )
        setattr(session, "_headers", self.headers)
        setattr(session, "_cookies", self.cookies)
        return session

    @locked_cacheproperty
    def async_session(self, /):
        """异步请求的 session 对象
        """
        import httpx_request
        from httpx import AsyncClient, AsyncHTTPTransport, Limits
        session = AsyncClient(
            limits=Limits(max_connections=256, max_keepalive_connections=64, keepalive_expiry=10), 
            transport=AsyncHTTPTransport(retries=5), 
            verify=False, 
        )
        setattr(session, "_headers", self.headers)
        setattr(session, "_cookies", self.cookies)
        return session

    @locked_cacheproperty
    def baiduid(self, /) -> str:
        return self.cookies["BAIDUID"]

    @locked_cacheproperty
    def bdstoken(self, /) -> str:
        resp = self.get_templatevariable("bdstoken")
        check_response(resp)
        return resp["result"]["bdstoken"]

    @locked_cacheproperty
    def logid(self, /) -> str:
        return b64encode(self.baiduid.encode("ascii")).decode("ascii")

    @locked_cacheproperty
    def sign_and_timestamp(self, /) -> dict:
        return self.get_sign_and_timestamp()

    @overload
    def login_with_qrcode(
        self, 
        /, 
        console_qrcode: bool = True, 
        check: bool = True, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_with_qrcode(
        self, 
        /, 
        console_qrcode: bool = True, 
        check: bool = True, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_with_qrcode(
        self, 
        /, 
        console_qrcode: bool = True, 
        check: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "扫描二维码登录"
        def gen_step():
            gid = str(uuid4()).upper()
            resp = yield self.login_getqrcode(gid, async_=async_, **request_kwargs)
            sign = resp["sign"]
            if console_qrcode:
                url = f"https://wappass.baidu.com/wp/?qrlogin&error=0&sign={sign}&cmd=login&lp=pc&tpl=netdisk&adapter=3&qrloginfrom=pc"
                print(url)
                from qrcode import QRCode # type: ignore
                qr = QRCode(border=1)
                qr.add_data(url)
                qr.print_ascii(tty=isatty(1))
            else:
                url = "https://" + resp["imgurl"]
                if async_:
                    yield partial(startfile_async, url)
                else:
                    startfile(url)
            while True:
                resp = yield self.login_qrcode_status(
                    {"gid": gid, "channel_id": sign}, 
                    async_=async_, 
                    **request_kwargs, 
                )
                match resp["errno"]:
                    case 0:
                        channel_v = loads(resp["channel_v"])
                        match channel_v["status"]:
                            case 0:
                                print("[status=0] qrcode: success")
                                break
                            case 1:
                                print("[status=1] qrcode: scanned")
                            case 2:
                                print("[status=2] qrcode: canceled")
                                raise OSError(errno.EIO, resp)
                    case 1:
                        pass
                    case _:
                        raise OSError(errno.EIO, resp)
            resp = yield self.request(
                f"https://passport.baidu.com/v3/login/main/qrbdusslogin?bduss={channel_v['v']}", 
                parse=lambda _, b: eval(b), 
                async_=async_, 
                **request_kwargs, 
            )
            if check and int(resp["errInfo"]["no"]):
                raise OSError(errno.EIO, resp)
            yield self.request(
                "https://pan.baidu.com/disk/main", 
                parse=..., 
                async_=async_, 
                **request_kwargs, 
            )
            return resp
        return run_gen_step(gen_step, async_=async_)

    @overload
    @staticmethod
    def app_version_list(
        request: None | Callable = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs
    ) -> dict:
        ...
    @overload
    @staticmethod
    def app_version_list(
        request: None | Callable = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs
    ) -> Coroutine[Any, Any, dict]:
        ...
    @staticmethod
    def app_version_list(
        request: None | Callable = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列最新的 app 版本的信息

        GET https://pan.baidu.com/disk/cmsdata?clienttype=0&web=1&do=client
        """
        url = "https://pan.baidu.com/disk/cmsdata?clienttype=0&web=1&do=client"
        request_kwargs.setdefault("parse", default_parse)
        if request is None:
            return get_default_request()(url=url, async_=async_, **request_kwargs)
        else:
            return request(url=url, **request_kwargs)

    @overload
    def fs_copy(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """复制

        .. note::
            这是对 `DupanClient.fs_filemanager()` 的 2 次封装

        :payload:

            .. code:: python

                {
                    filelist: [
                        {
                            "path": str      # 源文件路径
                            "newname": str   # 目标文件名
                            "dest": str = "" # 目标目录
                            "ondup": "newcopy" | "overwrite" = <default>
                        }, 
                        ...
                    ]
                }
        """
        if not params:
            params = {"opera": "copy"}
        elif params.get("opera") != "copy":
            params = {**params, "opera": "copy"}
        return self.fs_filemanager(params, payload, async_=async_, **request_kwargs)

    @overload
    def fs_delete(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_delete(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_delete(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除

        .. note::
            这是对 `DupanClient.fs_filemanager()` 的 2 次封装

        :payload:

            .. code:: python

                {
                    filelist: [
                        str, # 文件路径
                        ...
                    ]
                }
        """
        if not params:
            params = {"opera": "delete"}
        elif params.get("opera") != "delete":
            params = {**params, "opera": "delete"}
        return self.fs_filemanager(params, payload, async_=async_, **request_kwargs)

    @overload
    def fs_filemanager(
        self, 
        params: str | dict, 
        data: str | dict | Iterable[str | dict], 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_filemanager(
        self, 
        params: str | dict, 
        data: str | dict | Iterable[str | dict], 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_filemanager(
        self, 
        params: str | dict, 
        data: str | dict | Iterable[str | dict], 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """文件管理，可执行批量操作

        .. attention::
            不要直接使用此接口，而是使用其 2 次封装

        POST https://pan.baidu.com/api/filemanager

        :params:
            - opera: "copy" | "delete" | "move" | "rename"
            - async: int = 1 💡 如果值为 2，则是异步，可用 `DupanClient.fs_taskquery()` 查询进度
            - onnest: str = "fail"
            - newVerify: 0 | 1 = 1
            - ondup: "newcopy" | "overwrite" = "newcopy"

        :data:
            - filelist: str 💡 JSON array
        """
        api = "https://pan.baidu.com/api/filemanager"
        if isinstance(params, str):
            params = {"opera": params}
        params = {
            "async": 1, 
            "onnest": "fail", 
            "newVerify": 1, 
            "ondup": "newcopy", 
            "bdstoken": self.bdstoken, 
            "clienttype": 0, 
            "web": 1, 
            **params, 
        }
        if isinstance(data, str):
            data = {"filelist": dumps([data]).decode("utf-8")}
        elif isinstance(data, dict):
            if "filelist" not in data:
                data = {"filelist": dumps([data]).decode("utf-8")}
        else:
            if not isinstance(data, (list, tuple)):
                data = tuple(data)
            data = {"filelist": dumps(data).decode("utf-8")}
        return self.request(api, "POST", params=params, data=data, async_=async_, **request_kwargs)

    @overload
    def fs_filemetas(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_filemetas(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        ...
    def fs_filemetas(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件信息

        GET https://pan.baidu.com/api/filemetas

        :payload:
            - target: str 💡 路径列表，JSON array
            - dlink: 0 | 1 = 1
        """
        api = "https://pan.baidu.com/api/filemetas"
        if isinstance(payload, str):
            payload = {"clienttype": 0, "web": 1, "dlink": 1, "target": dumps([payload]).decode("utf-8")}
        elif not isinstance(payload, dict):
            if not isinstance(payload, (list, tuple)):
                payload = tuple(payload)
            payload = {"clienttype": 0, "web": 1, "dlink": 1, "target": dumps(payload).decode("utf-8")}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_list(
        self, 
        payload: str | dict = "/", 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_list(
        self, 
        payload: str | dict = "/", 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list(
        self, 
        payload: str | dict = "/", 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列目录中的文件列表

        GET https://pan.baidu.com/api/list

        .. note::
            num 和 page 与 limit 和 start 只需要任选其中一组即可，都提供时，limit 和 start 的优先级更高

        :payload:
            - dir: str = "/"  💡 目录路径
            - desc: 0 | 1 = 0 💡 是否逆序
            - order: "name" | "time" | "size" | "other" = "name" 💡 排序方式
            - num: int = 100 💡 分页大小
            - page: int = 1 💡 第几页，从 1 开始
            - limit: int = <default> 💡 最大返回数量，优先级高于 `num`
            - start: int = 0 💡 开始索引，从 0 开始
            - showempty: 0 | 1 = 0
        """
        api = "https://pan.baidu.com/api/list"
        if isinstance(payload, str):
            payload = {"num": 100, "page": 1, "order": "name", "desc": 0, "clienttype": 0, "web": 1, "dir": payload}
        else:
            payload = {"num": 100, "page": 1, "order": "name", "desc": 0, "clienttype": 0, "web": 1, "dir": "/", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """创建目录

        POST https://pan.baidu.com/api/create

        .. note::
            如果这个路径已被占用，则会创建给名字加上后缀（格式为 "_YYYYMMDD_6位数字"）

        :payload:
            - path: str
            - isdir: 0 | 1 = 1
            - block_list: str = "[]" 💡 JSON array
        """
        api = "https://pan.baidu.com/api/create"
        params = {
            "a": "commit", 
            "bdstoken": self.bdstoken, 
            "clienttype": 0, 
            "web": 1, 
        }
        if isinstance(payload, str):
            payload = {"isdir": 1, "block_list": "[]", "path": payload}
        else:
            payload = {"isdir": 1, "block_list": "[]", **payload}
        return self.request(url=api, method="POST", params=params, data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_move(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动

        .. note::
            这是对 `DupanClient.fs_filemanager()` 的 2 次封装

        :payload:

            .. code:: python

                {
                    filelist: [
                        {
                            "path": str      # 源文件路径
                            "newname": str   # 目标文件名
                            "dest": str = "" # 目标目录
                            "ondup": "newcopy" | "overwrite" = <default>
                        }, 
                        ...
                    ]
                }
        """
        if not params:
            params = {"opera": "move"}
        elif params.get("opera") != "move":
            params = {**params, "opera": "move"}
        return self.fs_filemanager(params, payload, async_=async_, **request_kwargs)

    @overload
    def fs_rename(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        params: None | dict = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重命名

        .. note::
            这是对 `DupanClient.fs_filemanager()` 的 2 次封装

        :payload:

            .. code:: python

                {
                    filelist: [
                        {
                            "id": int,      # 文件 id，可以不传
                            "path": str,    # 源文件路径
                            "newname": str, # 目标文件名
                        }, 
                        ...
                    ]
                }
        """
        if not params:
            params = {"opera": "rename"}
        elif params.get("opera") != "rename":
            params = {**params, "opera": "rename"}
        return self.fs_filemanager(params, payload, async_=async_, **request_kwargs)

    @overload
    def fs_taskquery(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_taskquery(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_taskquery(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """任务进度查询

        GET https://pan.baidu.com/share/taskquery

        :payload:
            - taskid: int | str

        .. note::
            返回值状态:
                - status: "pending"
                - status: "running"
                - status: "failed"
                - status: "success"
        """
        api = "https://pan.baidu.com/share/taskquery"
        if isinstance(payload, (int, str)):
            payload = {"clienttype": 0, "web": 1, "taskid": payload}
        else:
            payload = {"clienttype": 0, "web": 1, **payload}
        return self.request(api, params=payload, async_=async_, **request_kwargs)

    @overload
    def get_sign_and_timestamp(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def get_sign_and_timestamp(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def get_sign_and_timestamp(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取签名，用于下载
        """
        def gen_step():
            resp = yield self.get_templatevariable(
                ["sign1", "sign3", "timestamp"], 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            result = resp["result"]
            sign1 = result["sign1"].encode("ascii")
            sign3 = result["sign3"].encode("ascii")
            a = sign3 * (256 // len(sign3))
            p = bytearray(range(256))
            u = 0
            for q in range(256):
                u = (u + p[q] + a[q]) & 255
                p[q], p[u] = p[u], p[q]
            sign = bytearray(len(sign1))
            u = 0
            for q in range(len(sign1)):
                i = (q + 1) & 255
                pi = p[i]
                u = (u + p[i]) & 255
                pu = p[u]
                p[i], p[u] = pu, pi
                sign[q] = sign1[q] ^ p[(pi + pu) & 255]
            return {
                "sign": b64encode(sign).decode("utf-8"), 
                "timestamp": result["timestamp"], 
            }
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_templatevariable(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def get_templatevariable(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def get_templatevariable(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取模版变量

        GET https://pan.baidu.com/api/gettemplatevariable

        .. note::
            "sign1", "sign2", "sign3", "timestamp", "bdstoken", "isPcShareIdWhiteList", "openlogo", "pcShareIdFrom", ...

        payload:
            - fields: str # 字段列表，JSON array
        """
        api = "https://pan.baidu.com/api/gettemplatevariable"
        if isinstance(payload, str):
            payload = {"fields": dumps([payload]).decode("utf-8")}
        elif not isinstance(payload, dict):
            if not isinstance(payload, (list, tuple)):
                payload = tuple(payload)
            payload = {"fields": dumps(payload).decode("utf-8")}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def get_url(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def get_url(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def get_url(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件的下载链接
        
        GET https://pan.baidu.com/api/download

        :payload:
            - fidlist: str 💡 文件 id 列表，JSON array
            - type: str = "dlink"
        """
        api = "https://pan.baidu.com/api/download"
        payload = {"clienttype": 0, "web": 1, "type": "dlink", **self.sign_and_timestamp}
        if isinstance(fids, (int, str)):
            payload["fidlist"] = "[%s]" % fids
        else:
            payload["fidlist"] = "[%s]" % ",".join(map(str, fids))
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    # TODO: 提供自动扫码接口
    # TODO: 提供自动提取验证码，并提交通过
    @overload
    def login_getqrcode(
        self, 
        payload: str | dict = "", 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_getqrcode(
        self, 
        payload: str | dict = "", 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_getqrcode(
        self, 
        payload: str | dict = "", 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取二维码

        GET https://passport.baidu.com/v2/api/getqrcode

        :payload:
            - gid: str 💡 一个 UUID4 的字符串表示
        """
        api = "https://passport.baidu.com/v2/api/getqrcode"
        if not payload:
            payload = str(uuid4()).upper()
        if isinstance(payload, str):
            payload = {
                "apiver": "v3", 
                "tpl": "netdisk", 
                "lp": "pc", 
                "qrloginfrom": "pc", 
                "gid": payload, 
            }
        else:
            payload = {
                "apiver": "v3", 
                "tpl": "netdisk", 
                "lp": "pc", 
                "qrloginfrom": "pc", 
                **payload, 
            }
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def login_qrcode_status(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_status(
        self, 
        payload: dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_status(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取扫码状态

        GET https://passport.baidu.com/channel/unicast

        :payload:
            - gid: str
            - channel_id: str
        """
        api = "https://passport.baidu.com/channel/unicast"
        payload = {"apiver": "v3", "tpl": "netdisk", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def oauth_authorize(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        scope: str = "basic,netdisk", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def oauth_authorize(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        scope: str = "basic,netdisk", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def oauth_authorize(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        scope: str = "basic,netdisk", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        """OAuth 授权

        POST https://openapi.baidu.com/oauth/2.0/authorize
        """
        def gen_step():
            api = "https://openapi.baidu.com/oauth/2.0/authorize"
            params = {
                "response_type": "code", 
                "client_id": client_id, 
                "redirect_uri": "oob", 
                "scope": scope, 
                "display": "popup", 
            }
            resp = yield self.request(api, params=params, parse=False, async_=async_, **request_kwargs)
            etree: HtmlElement = fromstring(resp)
            if error_msg := etree.find_class("error-msg-list"):
                raise OSError(tostring(error_msg[0], encoding="utf-8").decode("utf-8").strip())
            try:
                return etree.get_element_by_id("Verifier").value
            except KeyError:
                pass
            payload: list[tuple] = []
            grant_permissions: list[str] = []
            el: HtmlElement
            input_els = cast(list[HtmlElement], fromstring(resp).xpath('//form[@name="scopes"]//input'))
            for el in input_els:
                name, value = el.name, el.value
                if name == "grant_permissions_arr":
                    grant_permissions.append(value)
                    payload.append(("grant_permissions_arr[]", value))
                elif name == "grant_permissions":
                    payload.append(("grant_permissions", ",".join(grant_permissions)))
                else:
                    payload.append((name, value))
            resp = yield self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)
            etree = fromstring(resp)
            if error_msg := etree.find_class("error-msg-list"):
                raise OSError(tostring(error_msg[0], encoding="utf-8").decode("utf-8").strip())
            return etree.get_element_by_id("Verifier").value
        return run_gen_step(gen_step, async_=async_)

    @overload
    def oauth_token(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        client_secret: str = CLIENT_SECRET, 
        scope: str = "basic,netdisk", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def oauth_token(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        client_secret: str = CLIENT_SECRET, 
        scope: str = "basic,netdisk", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def oauth_token(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        client_secret: str = CLIENT_SECRET, 
        scope: str = "basic,netdisk", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 OAuth token

        GET https://openapi.baidu.com/oauth/2.0/token
        """
        def gen_step():
            api = "https://openapi.baidu.com/oauth/2.0/token"
            code = yield self.oauth_authorize(client_id, scope, async_=async_, **request_kwargs)
            params = {
                "grant_type": "authorization_code", 
                "code": code, 
                "client_id": client_id, 
                "client_secret": client_secret, 
                "redirect_uri": "oob", 
            }
            return self.request(url=api, params=params, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def share_transfer(
        self, 
        /, 
        url: str, 
        params: dict = {}, 
        data: None | str | int | Iterable[int] | dict = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_transfer(
        self, 
        /, 
        url: str, 
        params: dict = {}, 
        data: None | str | int | Iterable[int] | dict = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_transfer(
        self, 
        /, 
        url: str, 
        params: dict = {}, 
        data: None | int | str | Iterable[int] | dict = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """转存

        POST https://pan.baidu.com/share/transfer

        :params:
            - shareid: int | str 💡 分享 id
            - from: int | str    💡 分享者的用户 id
            - sekey: str = ""    💡 安全码
            - async: 0 | 1 = 1   💡 是否异步
            - bdstoken: str = <default>
            - ondup: "overwrite" | "newcopy" = <default>

        :data:
            - fsidlist: str # 文件 id 列表，JSON array
            - path: str = "/"
        """
        def gen_step():
            nonlocal params, data
            api = "https://pan.baidu.com/share/transfer"
            share_list = DuPanShareList(url)
            if data is None:
                resp = yield share_list.fs_list_root(async_=async_, **request_kwargs)
                data = {"fsidlist": "[%s]" % ",".join(str(f["fs_id"]) for f in resp["file_list"])}
            elif isinstance(data, str):
                data = {"fsidlist": data}
            elif isinstance(data, int):
                data = {"fsidlist": "[%s]" % data}
            elif not isinstance(data, dict):
                data = {"fsidlist": "[%s]" % ",".join(map(str, data))}
            elif "fsidlist" not in data:
                resp = yield share_list.fs_list_root(async_=async_, **request_kwargs)
                data["fsidlist"] = "[%s]" % ",".join(str(f["fs_id"]) for f in resp["file_list"])
            elif isinstance(data["fsidlist"], (list, tuple)):
                data["fsidlist"] = "[%s]" % ",".join(map(str, data["fsidlist"]))
            data.setdefault("path", "/")
            if frozenset(("shareid", "from")) - params.keys():
                params.update({
                    "shareid": share_list.share_id, 
                    "from": share_list.share_uk, 
                    "sekey": share_list.randsk, 
                })
            params = {
                "async": 1, 
                "bdstoken": self.bdstoken, 
                "clienttype": 0, 
                "web": 1, 
                **params, 
            }
            request_kwargs["headers"] = dict(request_kwargs.get("headers") or {}, Referer=url)
            return self.request(url=api, method="POST", params=params, data=data, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_=async_)

    @overload
    @staticmethod
    def user_info(
        payload: int | str | dict, 
        /, 
        request: None | Callable = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs
    ) -> dict:
        ...
    @overload
    @staticmethod
    def user_info(
        payload: int | str | dict, 
        /, 
        request: None | Callable = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs
    ) -> Coroutine[Any, Any, dict]:
        ...
    @staticmethod
    def user_info(
        payload: int | str | dict, 
        /, 
        request: None | Callable = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询某个用户信息

        GET https://pan.baidu.com/pcloud/user/getinfo

        :payload:
            - query_uk: int | str 💡 用户 id
            - third: 0 | 1 = 0
        """
        api = "https://pan.baidu.com/pcloud/user/getinfo"
        if isinstance(payload, (int, str)):
            payload = {"clienttype": 0, "web": 1, "query_uk": payload}
        else:
            payload = {"clienttype": 0, "web": 1, **payload}
        request_kwargs.setdefault("parse", default_parse)
        if request is None:
            return get_default_request()(url=api, params=payload, async_=async_, **request_kwargs)
        else:
            return request(url=api, params=payload, **request_kwargs)

    @overload
    def user_membership(
        self, 
        payload: str | dict = "rights", 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_membership(
        self, 
        payload: str | dict = "rights", 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_membership(
        self, 
        payload: str | dict = "rights", 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取会员相关权益

        GET https://pan.baidu.com/rest/2.0/membership/user

        :payload:
            - method: str = "rights"
        """
        api = "https://pan.baidu.com/rest/2.0/membership/user"
        if isinstance(payload, (int, str)):
            payload = {"clienttype": 0, "web": 1, "method": payload}
        else:
            payload = {"clienttype": 0, "web": 1, "method": "rights", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def user_query(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_query(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_query(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用户信息
        """
        api = "https://pan.baidu.com/workspace/userquery"
        return self.request(url=api, async_=async_, **request_kwargs)


    @overload
    def open(
        self, 
        /, 
        url: str | Callable[[], str], 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        headers: None | Mapping = None, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> HTTPFileReader:
        ...
    @overload
    def open(
        self, 
        /, 
        url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        headers: None | Mapping = None, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncHTTPFileReader:
        ...
    def open(
        self, 
        /, 
        url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        headers: None | Mapping = None, 
        http_file_reader_cls: None | type[HTTPFileReader] | type[AsyncHTTPFileReader] = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> HTTPFileReader | AsyncHTTPFileReader:
        """打开下载链接，返回文件对象

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）

            - P115Client.download_url
            - P115Client.share_download_url
            - P115Client.extract_download_url

        :param start: 开始索引
        :param seek_threshold: 当向前 seek 的偏移量不大于此值时，调用 read 来移动文件位置（可避免重新建立连接）
        :param http_file_reader_cls: 返回的文件对象的类，需要是 `httpfile.HTTPFileReader` 的子类
        :param headers: 请求头
        :param async_: 是否异步

        :return: 返回打开的文件对象，可以读取字节数据
        """
        if headers is None:
            headers = self.headers
        else:
            headers = {**self.headers, **headers}
        if async_:
            if http_file_reader_cls is None:
                from httpfile import AsyncHttpxFileReader
                http_file_reader_cls = AsyncHttpxFileReader
            return http_file_reader_cls(
                url, # type: ignore
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
            )
        else:
            if http_file_reader_cls is None:
                http_file_reader_cls = HTTPFileReader
            return http_file_reader_cls(
                url, # type: ignore
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
            )

    @overload
    def ed2k(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        name: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def ed2k(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        name: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def ed2k(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        name: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        """下载文件流并生成它的 ed2k 链接

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param headers: 请求头
        :param name: 文件名
        :param async_: 是否异步

        :return: 文件的 ed2k 链接
        """
        trantab = dict(zip(b"/|", ("%2F", "%7C")))
        if async_:
            async def request():
                async with self.open(url, headers=headers, async_=True) as file:
                    return make_ed2k_url(name or file.name, *(await ed2k_hash_async(file)))
            return request()
        else:
            with self.open(url, headers=headers) as file:
                return make_ed2k_url(name or file.name, *ed2k_hash(file))

    @overload
    def hash[T](
        self, 
        /, 
        url: str | Callable[[], str], 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> tuple[int, HashObj | T]:
        ...
    @overload
    def hash[T](
        self, 
        /, 
        url: str | Callable[[], str], 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, tuple[int, HashObj | T]]:
        ...
    def hash[T](
        self, 
        /, 
        url: str | Callable[[], str], 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> tuple[int, HashObj | T] | Coroutine[Any, Any, tuple[int, HashObj | T]]:
        """下载文件流并用一种 hash 算法求值

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param digest: hash 算法

            - 如果是 str，则可以是 `hashlib.algorithms_available` 中任一，也可以是 "ed2k" 或 "crc32"
            - 如果是 HashObj (来自 python-hashtools)，就相当于是 `_hashlib.HASH` 类型，需要有 update 和 digest 等方法
            - 如果是 Callable，则返回值必须是 HashObj，或者是一个可用于累计的函数，第 1 个参数是本次所传入的字节数据，第 2 个参数是上一次的计算结果，返回值是这一次的计算结果，第 2 个参数可省略

        :param start: 开始索引，可以为负数（从文件尾部开始）
        :param stop: 结束索引（不含），可以为负数（从文件尾部开始）
        :param headers: 请求头
        :param async_: 是否异步

        :return: 元组，包含文件的 大小 和 hash 计算结果
        """
        digest = convert_digest(digest)
        if async_:
            async def request():
                nonlocal stop
                async with self.open(url, start=start, headers=headers, async_=True) as file: # type: ignore
                    if stop is None:
                        return await file_digest_async(file, digest)
                    else:
                        if stop < 0:
                            stop += file.length
                        return await file_digest_async(file, digest, stop=max(0, stop-start)) # type: ignore
            return request()
        else:
            with self.open(url, start=start, headers=headers) as file:
                if stop is None:
                    return file_digest(file, digest) # type: ignore
                else:
                    if stop < 0:
                        stop = stop + file.length
                    return file_digest(file, digest, stop=max(0, stop-start)) # type: ignore

    @overload
    def hashes[T](
        self, 
        /, 
        url: str | Callable[[], str], 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        async_: Literal[False] = False, 
    ) -> tuple[int, list[HashObj | T]]:
        ...
    @overload
    def hashes[T](
        self, 
        /, 
        url: str | Callable[[], str], 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        ...
    def hashes[T](
        self, 
        /, 
        url: str | Callable[[], str], 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        async_: Literal[False, True] = False, 
    ) -> tuple[int, list[HashObj | T]] | Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        """下载文件流并用一组 hash 算法求值

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param digest: hash 算法

            - 如果是 str，则可以是 `hashlib.algorithms_available` 中任一，也可以是 "ed2k" 或 "crc32"
            - 如果是 HashObj (来自 python-hashtools)，就相当于是 `_hashlib.HASH` 类型，需要有 update 和 digest 等方法
            - 如果是 Callable，则返回值必须是 HashObj，或者是一个可用于累计的函数，第 1 个参数是本次所传入的字节数据，第 2 个参数是上一次的计算结果，返回值是这一次的计算结果，第 2 个参数可省略

        :param digests: 同 `digest`，但可以接受多个
        :param start: 开始索引，可以为负数（从文件尾部开始）
        :param stop: 结束索引（不含），可以为负数（从文件尾部开始）
        :param headers: 请求头
        :param async_: 是否异步

        :return: 元组，包含文件的 大小 和一组 hash 计算结果
        """
        digests = (convert_digest(digest), *map(convert_digest, digests))
        if async_:
            async def request():
                nonlocal stop
                async with self.open(url, start=start, headers=headers, async_=True) as file: # type: ignore
                    if stop is None:
                        return await file_mdigest_async(file, *digests)
                    else:
                        if stop < 0:
                            stop += file.length
                        return await file_mdigest_async(file *digests, stop=max(0, stop-start)) # type: ignore
            return request()
        else:
            with self.open(url, start=start, headers=headers) as file:
                if stop is None:
                    return file_mdigest(file, *digests) # type: ignore
                else:
                    if stop < 0:
                        stop = stop + file.length
                    return file_mdigest(file, *digests, stop=max(0, stop-start)) # type: ignore

    @overload
    def read_bytes(
        self, 
        /, 
        url: str, 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_bytes(
        self, 
        /, 
        url: str, 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes(
        self, 
        /, 
        url: str, 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """读取文件一定索引范围的数据

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param start: 开始索引，可以为负数（从文件尾部开始）
        :param stop: 结束索引（不含），可以为负数（从文件尾部开始）
        :param headers: 请求头
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        def gen_step():
            def get_bytes_range(start, stop):
                if start < 0 or (stop and stop < 0):
                    length: int = yield self.read_bytes_range(
                        url, 
                        bytes_range="-1", 
                        headers=headers, 
                        async_=async_, 
                        **{**request_kwargs, "parse": lambda resp: get_total_length(resp)}, 
                    )
                    if start < 0:
                        start += length
                    if start < 0:
                        start = 0
                    if stop is None:
                        return f"{start}-"
                    elif stop < 0:
                        stop += length
                if stop is None:
                    return f"{start}-"
                elif start >= stop:
                    return None
                return f"{start}-{stop-1}"
            bytes_range = yield from get_bytes_range(start, stop)
            if not bytes_range:
                return b""
            return self.read_bytes_range(
                url, 
                bytes_range=bytes_range, 
                headers=headers, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_bytes_range(
        self, 
        /, 
        url: str, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_bytes_range(
        self, 
        /, 
        url: str, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes_range(
        self, 
        /, 
        url: str, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """读取文件一定索引范围的数据

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param bytes_range: 索引范围，语法符合 `HTTP Range Requests <https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests>`_
        :param headers: 请求头
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        headers = dict(headers) if headers else {}
        if headers_extra := getattr(url, "headers", None):
            headers.update(headers_extra)
        headers["Accept-Encoding"] = "identity"
        headers["Range"] = f"bytes={bytes_range}"
        request_kwargs["headers"] = headers
        request_kwargs.setdefault("method", "GET")
        request_kwargs.setdefault("parse", False)
        return self.request(url, async_=async_, **request_kwargs)

    @overload
    def read_block(
        self, 
        /, 
        url: str, 
        size: int = -1, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_block(
        self, 
        /, 
        url: str, 
        size: int = -1, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_block(
        self, 
        /, 
        url: str, 
        size: int = -1, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """读取文件一定索引范围的数据

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param size: 读取字节数（最多读取这么多字节，如果遇到 EOF (end-of-file)，则会小于这个值），如果小于 0，则读取到文件末尾
        :param offset: 偏移索引，从 0 开始，可以为负数（从文件尾部开始）
        :param headers: 请求头
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        def gen_step():
            if size == 0:
                return b""
            elif size > 0:
                stop: int | None = offset + size
            else:
                stop = None
            return self.read_bytes(
                url, 
                start=offset, 
                stop=stop, 
                headers=headers, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)


class DuPanShareList(HTTPXClientMixin):

    def __init__(self, url: str, password: str = ""):
        if url.startswith(("http://", "https://")):
            shorturl, _password = self._extract_from_url(url)
            if not password:
                password = _password
            # NOTE: Or use the following format, return 404 when the link is cancelled or disabled
            #   url = f"https://pan.baidu.com/share/init?surl={shorturl}"
            if shorturl:
                url = f"https://pan.baidu.com/s/1{shorturl}"
        else:
            shorturl = url
            url = f"https://pan.baidu.com/s/1{shorturl}"
        self.url = url
        self.shorturl = shorturl
        self.password = password
        self.headers["Referer"] = url

    async def __aiter__(self, /) -> AsyncIterator[dict]:
        dq: deque[str] = deque()
        get, put = dq.popleft, dq.append
        put("/")
        while dq:
            async for item in self.iterdir(get(), async_=True):
                yield item
                if item["isdir"]:
                    put(item["path"])

    def __iter__(self, /) -> Iterator[dict]:
        dq: deque[str] = deque()
        get, put = dq.popleft, dq.append
        put("/")
        while dq:
            for item in self.iterdir(get()):
                yield item
                if item["isdir"]:
                    put(item["path"])

    @staticmethod
    def _extract_from_url(url: str, /) -> tuple[str, str]:
        urlp = urlparse(url)
        if urlp.scheme and urlp.scheme not in ("http", "https"):
            raise ValueError(f"url 协议只接受 'http' 和 'https'，收到 {urlp.scheme!r}，")
        if urlp.netloc and urlp.netloc != "pan.baidu.com":
            raise ValueError(f"url 的域名必须是 'pan.baidu.com'，收到 {urlp.netloc!r}")
        path = urlp.path
        query = dict(parse_qsl(urlp.query))
        if path == "/share/link":
            shorturl = ""
        elif path == "/share/init":
            try:
                shorturl = query["surl"]
            except KeyError:
                shorturl = ""
        elif path.startswith("/s/1"):
            shorturl = path.removeprefix("/s/1")
            idx = shorturl.find("&")
            if idx > -1:
                shorturl = shorturl[:idx]
        elif "/" not in path:
            shorturl = path
        else:
            raise ValueError(f"invalid share url: {url!r}")
        return shorturl, query.get("pwd", "")

    @staticmethod
    def _extract_indexdata(content: bytes, /) -> dict:
        match = text_within(content, b"locals.mset(", b");")
        if not match:
            raise OSError("没有提取到页面相关数据，可能是页面加载失败、被服务器限制访问、链接失效、分享被取消等原因")
        return loads(match)

    @staticmethod
    def _extract_yundata(
        content: bytes, 
        /, 
        _sub=partial(re_compile(r"\w+(?=:)").sub, r'"\g<0>"'), 
    ) -> None | dict:
        "从分享链接的主页中提取分享者相关的信息"
        try:
            return eval(_sub(text_within(content, b"window.yunData=", b";").decode("utf-8")))
        except:
            return None

    @locked_cacheproperty
    def root(self, /):
        self.fs_list_root()
        return self.__dict__["root"]

    @locked_cacheproperty
    def root2(self, /):
        self.fs_list_root()
        return self.__dict__["root2"]

    @locked_cacheproperty
    def randsk(self, /) -> str:
        self.fs_list_root()
        return unquote(self.cookies.get("BDCLND", ""))

    @locked_cacheproperty
    def share_id(self, /):
        self.fs_list_root()
        return self.__dict__["share_id"]

    @locked_cacheproperty
    def share_uk(self, /):
        self.fs_list_root()
        return self.__dict__["share_uk"]

    @locked_cacheproperty
    def yundata(self, /):
        self.fs_list_root()
        return self.__dict__["yundata"]

    # TODO: 增加并发，以大量获得图片，以快速得出识别结果
    @overload
    def decaptcha(
        self, 
        /, 
        min_confirm: int = 2, 
        ocr: Callable[[bytes], str] = DdddOcr(beta=True, show_ad=False).classification, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs
    ) -> dict:
        ...
    @overload
    def decaptcha(
        self, 
        /, 
        min_confirm: int = 2, 
        ocr: Callable[[bytes], str] = DdddOcr(beta=True, show_ad=False).classification, 
        *, 
        async_: Literal[True], 
        **request_kwargs
    ) -> Coroutine[Any, Any, dict]:
        ...
    def decaptcha(
        self, 
        /, 
        min_confirm: int = 2, 
        ocr: Callable[[bytes], str] = DdddOcr(beta=True, show_ad=False).classification, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs
    ) -> dict | Coroutine[Any, Any, dict]:
        """识别百度网盘的验证码

        :param min_confirm: 最小确认次数，仅当识别为相同结果达到指定次数才予以返回
        :param ocr: 调用以执行 ocr
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 字典，{"vcode": "验证码的识别结果", "vcode_str": "验证码的 key"}
        """
        def gen_step():
            url = "https://pan.baidu.com/api/getcaptcha?prod=shareverify&web=1&clienttype=0"
            data: dict = yield self.request(url=url, async_=async_, **request_kwargs)
            vcode_img: str = data["vcode_img"]
            vcode_str: str = data["vcode_str"]
            counter: dict[str, int] = {}
            while True:
                try:
                    image = yield self.request(vcode_img, timeout=5, parse=False, async_=async_, **request_kwargs)
                except:
                    continue
                res = ocr(image)
                if len(res) != 4 or not res.isalnum():
                    continue
                if min_confirm <= 1:
                    return {"vcode": res, "vcode_str": vcode_str}
                m = counter.get(res, 0) + 1
                if m >= min_confirm:
                    return {"vcode": res, "vcode_str": vcode_str}
                counter[res] = m
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_list(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_list(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件列表

        GET https://pan.baidu.com/share/list

        :payload:
            - dir: str 💡 目录路径（⚠️ 不能是根目录）
            - uk: int | str = <default> 💡 分享用户的 id
            - shareid: int | str = <default> 💡 分享 id
            - order: "name" | "time" | "size" | "other" = "name" 💡 排序方式
            - desc: 0 | 1 = 0 💡 是否逆序
            - showempty: 0 | 1 = 0
            - page: int = 1 💡 第几页，从 1 开始
            - num: int = 100 💡 分页大小
        """
        api = "https://pan.baidu.com/share/list"
        if isinstance(payload, str):
            dir_ = payload
            if not dir_.startswith("/"):
                dir_ = self.root + "/" + dir_
            payload = {"dir": dir_}
        params = {
            "uk": self.share_uk, 
            "shareid": self.share_id, 
            "order": "other", 
            "desc": 0, 
            "showempty": 0, 
            "clienttype": 0, 
            "web": 1, 
            "page": 1, 
            "num": 100, 
            **payload, 
        }
        return self.request(api, params=params, async_=async_, **request_kwargs)

    @overload
    def fs_list_root(
        self, 
        /, 
        try_times: int = 5, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_list_root(
        self, 
        /, 
        try_times: int = 5, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list_root(
        self, 
        /, 
        try_times: int = 5, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        def gen_step():
            if try_times <= 0:
                counter: Iterator[int] = count(0)
            else:
                counter = iter(range(try_times))
            url = self.url
            for _ in counter:
                content = yield self.request(url, parse=False, async_=async_, **request_kwargs)
                data = self._extract_indexdata(content)
                if b'"verify-form"' in content:
                    yield self.verify(b'"change-code"' in content, async_=async_, **request_kwargs)
                else:
                    check_response(data)
                    file_list = data.get("file_list")
                    if file_list is None:
                        raise DuPanOSError(
                            errno.ENOENT, 
                            "无下载文件，可能是链接失效、分享被取消、删除了所有分享文件等原因", 
                        )
                    self.yundata = self._extract_yundata(content)
                    if file_list:
                        for file in file_list:
                            file["relpath"] = file["server_filename"]
                        root = root2 = file_list[0]["path"].rsplit("/", 1)[0]
                        if len(file_list) > 1:
                            root2 = file_list[1]["path"].rsplit("/", 1)[0]
                    else:
                        root = root2 = "/"
                    self.__dict__.update(
                        root = root, 
                        root2 = root2, 
                        share_uk = data["share_uk"], 
                        share_id = data["shareid"], 
                    )
                    return data
            raise RuntimeError("too many attempts")
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iterdir(
        self, 
        /, 
        dir: str = "/", 
        page: int = 1, 
        num: int = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iterdir(
        self, 
        /, 
        dir: str = "/", 
        page: int = 1, 
        num: int = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iterdir(
        self, 
        /, 
        dir: str = "/", 
        page: int = 1, 
        num: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        def gen_step():
            nonlocal dir, num
            reldir = dir.strip("/")
            if reldir:
                if not dir.startswith("/"):
                    dir = self.root + "/" + dir
                params = {
                    "uk": self.share_uk, 
                    "shareid": self.share_id, 
                    "order": "other", 
                    "desc": 1, 
                    "showempty": 0, 
                    "clienttype": 0, 
                    "web": 1, 
                    "page": 1, 
                    "num": 100, 
                    "dir": dir, 
                }
                if num <= 0 or page <= 0:
                    if num > 0:
                        params["num"] = num
                    else:
                        num = params["num"]
                    while True:
                        resp = yield self.fs_list(params, async_=async_, **request_kwargs)
                        data = resp["list"]
                        for item in data:
                            item["relpath"] = joinpath(reldir, item["server_filename"])
                            yield Yield(item)
                        if len(data) < num:
                            break
                        params["page"] += 1
                else:
                    params["page"] = page
                    params["num"] = num
                    resp = yield self.fs_list(params, async_=async_, **request_kwargs)
                    for item in resp["list"]:
                        item["relpath"] = joinpath(reldir, item["server_filename"])
                        yield Yield(item)
            else:
                resp = yield self.fs_list_root(async_=async_, **request_kwargs)
                data = resp["file_list"]
                if num <= 0 or page <= 0:
                    yield YieldFrom(data)
                else:
                    yield YieldFrom(data[(page-1)*num:page*num])
        return run_gen_step_iter(gen_step, async_=async_)

    def verify(
        self, 
        /, 
        has_vcode: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        """提交验证

        :param has_vcode: 是否有验证码
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        def gen_step():
            api = "https://pan.baidu.com/share/verify"
            if self.shorturl:
                params: dict = {"surl": self.shorturl, "web": 1, "clienttype": 0}
            else:
                params = {"web": 1, "clienttype": 0}
                params.update(parse_qsl(urlparse(self.url).query))
            data = {"pwd": self.password}
            if has_vcode:
                vcode = yield self.decaptcha(async_=async_, **request_kwargs)
                data.update(vcode)
            while True:
                resp = yield self.request(url=api, method="POST", params=params, data=data, async_=async_, **request_kwargs)
                errno = resp["errno"]
                if not errno:
                    break
                if errno == -62:
                    vcode = yield self.decaptcha(async_=async_, **request_kwargs)
                    data.update(vcode)
                else:
                    check_response(resp)
        return run_gen_step(gen_step, async_=async_)

# TODO: 回收站
# TODO: 分享
# TODO: 离线下载
# TODO: 快捷访问
# TODO: 同步空间
# TODO: 开放接口
