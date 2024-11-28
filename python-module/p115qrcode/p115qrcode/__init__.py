#!/usr/bin/env python3
# encoding: utf-8

"扫码获取 115 cookies"

# NOTE: 目前发现扫码相关的接口，可用这些 origin
# https://qrcodeapi.115.com
# https://hnqrcodeapi.115.com
# https://passportapi.115.com

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__license__ = "GPLv3 <https://www.gnu.org/licenses/gpl-3.0.txt>"
__all__ = [
    "QrcodeStatus", "QrcodeScanFuture", "QrcodeScanAsyncFuture", "scan_qrcode", 
    "qrcode_token", "qrcode_status", "qrcode_scan", "qrcode_scan_confirm", 
    "qrcode_scan_cancel", "qrcode_result", "qrcode_url", "qrcode_token_url", 
    "qrcode_print", "qrcode_open", 
]

from asyncio import AbstractEventLoop
from asyncio.futures import Future as AsyncFuture
from collections.abc import Callable, Coroutine, Mapping
from concurrent.futures import Future
from enum import IntEnum
from errno import EIO
from functools import partial
from inspect import isawaitable
from itertools import cycle
from _thread import start_new_thread
from types import MappingProxyType
from typing import overload, Any, Literal, Self


_httpx_request = None


def get_default_request():
    global _httpx_request
    if _httpx_request is None:
        from httpx import AsyncClient, AsyncHTTPTransport
        from httpx_request import request
        _httpx_request = partial(
            request, 
            session=AsyncClient(transport=AsyncHTTPTransport(retries=5), verify=False), 
            timeout=30, 
        )
    return _httpx_request


class QrcodeStatus(IntEnum):
    """二维码的扫码状态
    """
    waiting  = 0
    scanned  = 1
    sigined  = 2
    expired  = -1
    canceled = -2
    aborted  = -99

    @classmethod
    def of(cls, val, /) -> Self:
        if isinstance(val, cls):
            return val
        elif isinstance(val, str):
            try:
                return cls[val]
            except KeyError:
                pass
        return cls(val)


class QrcodeScanFutureMixin:

    def __del__(self, /):
        self.close()

    @property
    def message(self, /) -> dict:
        return self._message # type: ignore

    @property
    def running(self, /) -> bool:
        return self._running # type: ignore

    @property
    def status(self, /) -> QrcodeStatus:
        return self._status # type: ignore

    @status.setter
    def status(self, status: QrcodeStatus, /):
        self._status = status

    @property
    def token(self, /) -> MappingProxyType:
        return self._token # type: ignore

    @property
    def token_url(self, /):
        return qrcode_token_url(self.uid)

    @property
    def uid(self, /) -> str:
        return self._token["uid"] # type: ignore

    @property
    def url(self, /):
        return qrcode_url(self.uid)

    def close(self, /):
        self._running = False

    def open(self, /):
        return qrcode_open(self.uid)

    def print(self, /):
        return qrcode_print(self.uid)


class QrcodeScanFuture(Future, QrcodeScanFutureMixin):
    """二维码手动扫码，同步版
    """
    def __init__(
        self, 
        app: str = "alipaymini", 
        /, 
        console_qrcode: None | bool = True, 
        show_message: bool | Callable = False, 
        **request_kwargs, 
    ):
        super().__init__()
        self.app = app
        self.console_qrcode = console_qrcode
        if show_message is True:
            show_message = print
        self.show_message = show_message
        self.request_kwargs = request_kwargs
        self._running = False
        self._status = QrcodeStatus(0)
        self._message = {"msg": "等待扫码中", "status": 0}
        self._token = MappingProxyType(qrcode_token(**request_kwargs))
        self.start()

    def background(self, /):
        if self._running or not (0 <= self.status < 2):
            return
        self._running = True
        console_qrcode = self.console_qrcode
        show_message = self.show_message
        request_kwargs = self.request_kwargs
        token = self._token
        uid = token["uid"]
        try:
            if console_qrcode:
                qrcode_print(uid)
            elif console_qrcode is not None:
                qrcode_open(uid)
            if show_message:
                show_message(self._message)
            while self._running:
                resp = qrcode_status(token, **request_kwargs)
                self._message = resp
                if show_message:
                    show_message(resp)
                status = self._status = QrcodeStatus(resp.get("status", -99))
                if status < 0:
                    self.set_exception(RuntimeError(status))
                    break
                elif status == 2:
                    self.set_result(qrcode_result(uid, self.app, **request_kwargs))
                    break
        except BaseException as e:
            self._message = {"msg": "扫码错误", "reason": e}
            self.set_exception(e)
            if show_message:
                show_message(self._message)
            raise
        finally:
            self._running = False

    def start(self, /):
        if self._running:
            raise RuntimeError("already running")
        elif not (0 <= self._status < 2):
            raise RuntimeError("already stopped")
        start_new_thread(self.background, ())


class QrcodeScanAsyncFuture(AsyncFuture, QrcodeScanFutureMixin):
    """二维码手动扫码，异步版
    """
    def __init__(
        self, 
        app: str = "alipaymini", 
        /, 
        console_qrcode: None | bool = True, 
        show_message: bool | Callable = False, 
        loop: None | AbstractEventLoop = None, 
        **request_kwargs, 
    ):
        self._init(
            app, 
            console_qrcode=console_qrcode, 
            show_message=show_message, 
            loop=loop, 
            request_kwargs=request_kwargs, 
        )
        self._token = qrcode_token(**request_kwargs)
        self.start()

    def _init(
        self, 
        app: str, 
        /, 
        console_qrcode: None | bool = True, 
        show_message: bool | Callable = False, 
        loop: None | AbstractEventLoop = None, 
        request_kwargs: dict = {}, 
    ):
        super().__init__(loop=loop)
        self.app = app
        self.console_qrcode = console_qrcode
        if show_message is True:
            show_message = print
        self.show_message = show_message
        self.request_kwargs = request_kwargs
        self._running = False
        self._status = QrcodeStatus(0)
        self._message = {"msg": "等待扫码中", "status": 0}

    @classmethod
    async def new(
        cls, 
        app: str = "alipaymini", 
        /, 
        console_qrcode: None | bool = True, 
        show_message: bool | Callable = False, 
        loop: None | AbstractEventLoop = None, 
        **request_kwargs, 
    ) -> Self:
        self = super().__new__(cls)
        cls._init(
            self, 
            app, 
            console_qrcode=console_qrcode, 
            show_message=show_message, 
            loop=loop, 
            request_kwargs=request_kwargs, 
        )
        self._token = await qrcode_token(async_=True, **request_kwargs)
        self.start()
        return self

    async def background(self, /):
        if self._running or not (0 <= self._status < 2):
            return
        self._running = True
        console_qrcode = self.console_qrcode
        show_message = self.show_message
        request_kwargs = self.request_kwargs
        token = self._token
        uid = token["uid"]
        try:
            if console_qrcode:
                qrcode_print(uid)
            elif console_qrcode is not None:
                qrcode_open(uid)
            if show_message:
                r = show_message(self._message)
                if isawaitable(r):
                    await r
            while self._running:
                resp = await qrcode_status(token, async_=True, **request_kwargs)
                self._message = resp
                if show_message:
                    r = show_message(resp)
                    if isawaitable(r):
                        await r
                status = self._status = QrcodeStatus(resp.get("status", -99)) 
                if status < 0:
                    self.set_exception(RuntimeError(status))
                    break
                elif status == 2:
                    self.set_result(await qrcode_result(
                        uid, self.app, async_=True, **request_kwargs))
                    break
        except BaseException as e:
            self._message = {"msg": "扫码错误", "reason": e}
            self.set_exception(e)
            if show_message:
                r = show_message(self._message)
                if isawaitable(r):
                    await r
            raise
        finally:
            self._running = False

    def close(self, /):
        self._running = False
        if task := getattr(self, "_task", None):
            task.cancel()

    def start(self, /):
        if self._running:
            raise RuntimeError("already running")
        elif not (0 <= self._status < 2):
            raise RuntimeError("already stopped")
        self._task = self._loop.create_task(self.background())


def parse(_, content: bytes, /):
    from orjson import loads
    json = loads(content)
    if not json["state"]:
        raise OSError(EIO, json)
    return json["data"]


def request(
    url: str, 
    method: str = "GET", 
    parse: Callable = parse, 
    request: None | Callable = None, 
    async_: bool = False,
    **request_kwargs, 
):
    if request is None:
        request = partial(get_default_request(), async_=async_)
    return request(url=url, method=method, parse=parse, **request_kwargs)


@overload
def scan_qrcode(
    app: str = "alipaymini", 
    /, 
    console_qrcode: None | bool = True, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> QrcodeScanFuture:
    ...
@overload
def scan_qrcode(
    app: str = "alipaymini", 
    /, 
    console_qrcode: None | bool = True, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> QrcodeScanAsyncFuture:
    ...
def scan_qrcode(
    app: str = "alipaymini", 
    /, 
    console_qrcode: None | bool = True, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> QrcodeScanFuture | QrcodeScanAsyncFuture:
    """创建一个等待手动扫码的 Future 对象

    :param app: 待绑定的设备名
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 一个 Future 对象
    """
    if async_:
        return QrcodeScanAsyncFuture(
            app, console_qrcode=console_qrcode, **request_kwargs)
    else:
        return QrcodeScanFuture(
            app, console_qrcode=console_qrcode, **request_kwargs)


@overload
def qrcode_token(
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def qrcode_token(
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def qrcode_token(
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """获取二维码 token
    """
    request_kwargs["url"] = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
    return request(async_=async_, **request_kwargs)


@overload
def qrcode_status(
    payload: Mapping, 
    /, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def qrcode_status(
    payload: Mapping, 
    /, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def qrcode_status(
    payload: Mapping, 
    /, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """获取二维码的状态（未扫描、已扫描、已登录、已取消、已过期等）

    :param payload: 请求的查询参数，取自 `qrcode_token` 接口响应，有 3 个

        - uid:  str
        - time: int
        - sign: str

    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口响应值
    """
    request_kwargs.update(
        url="https://qrcodeapi.115.com/get/status/", 
        params=payload, 
    )
    request_kwargs.setdefault("timeout", None)
    return request(async_=async_, **request_kwargs)


@overload
def qrcode_scan(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def qrcode_scan(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def qrcode_scan(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """扫描二维码

    :param uid: 二维码的 token
    :param cookies: 一个有效（在线状态）的 cookies
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口返回值
    """
    if cookies:
        if headers := request_kwargs.get("headers"):
            request_kwargs["headers"] = dict(headers, Cookie=cookies)
        else:
            request_kwargs["headers"] = {"Cookie": cookies}
    request_kwargs.update(
        url="https://qrcodeapi.115.com/api/2.0/prompt.php", 
        params={"uid": uid}, 
    )
    return request(async_=async_, **request_kwargs)


@overload
def qrcode_scan_confirm(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def qrcode_scan_confirm(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def qrcode_scan_confirm(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """确认扫描二维码

    :param uid: 二维码的 token
    :param cookies: 一个有效（在线状态）的 cookies
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口返回值
    """
    if cookies:
        if headers := request_kwargs.get("headers"):
            request_kwargs["headers"] = dict(headers, Cookie=cookies)
        else:
            request_kwargs["headers"] = {"Cookie": cookies}
    request_kwargs.update(
        url="https://qrcodeapi.115.com/api/2.0/slogin.php", 
        params={"key": uid, "uid": uid, "client": 0}, 
    )
    return request(async_=async_, **request_kwargs)


@overload
def qrcode_scan_cancel(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def qrcode_scan_cancel(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def qrcode_scan_cancel(
    uid: str, 
    cookies: str = "", 
    /, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """取消扫描二维码

    :param uid: 二维码的 token
    :param cookies: 一个有效（在线状态）的 cookies
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口返回值
    """
    if cookies:
        if headers := request_kwargs.get("headers"):
            request_kwargs["headers"] = dict(headers, Cookie=cookies)
        else:
            request_kwargs["headers"] = {"Cookie": cookies}
    request_kwargs.update(
        url="https://qrcodeapi.115.com/api/2.0/cancel.php", 
        params={"key": uid, "uid": uid, "client": 0}, 
    )
    return request(async_=async_, **request_kwargs)


@overload
def qrcode_result(
    uid: str, 
    app: str = "alipaymini", 
    /, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def qrcode_result(
    uid: str, 
    app: str = "alipaymini", 
    /, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def qrcode_result(
    uid: str, 
    app: str = "alipaymini", 
    /, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """获取扫码登录的结果，并且绑定设备，包含 cookie

    :param uid: 二维码的 token
    :param app: 待绑定的设备名
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口响应值
    """
    request_kwargs.update(
        url=f"https://qrcodeapi.115.com/app/1.0/{app}/1.0/login/qrcode/", 
        method="POST", 
        data={"account": uid}, 
    )
    return request(async_=async_, **request_kwargs)


def qrcode_url(uid: str, /) -> str:
    """获取二维码图片的下载链接

    :return: 下载链接 
    """
    return "https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode?uid=" + uid


def qrcode_token_url(uid: str, /) -> str:
    """获取二维码图片的扫码链接

    :return: 扫码链接 
    """
    return "http://115.com/scan/dg-" + uid


def qrcode_print(uid: str, /):
    """在命令行输出二维码

    :param uid: 二维码的 token
    """
    from sys import stdout
    from qrcode import QRCode # type: ignore
    qr = QRCode(border=1)
    qr.add_data(qrcode_token_url(uid))
    qr.print_ascii(tty=stdout.isatty())
    return qr


def qrcode_open(uid: str, /):
    """通过浏览器打开二维码

    :param uid: 二维码的 token
    """
    from startfile import startfile # type: ignore
    start_new_thread(startfile, (qrcode_url(uid),))

