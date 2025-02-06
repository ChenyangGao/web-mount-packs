#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["DuPanClient", "DuPanShareList"]

import errno

from base64 import b64encode
from collections import deque
from collections.abc import Callable, Coroutine, Iterator, Mapping
from functools import cached_property, partial
from itertools import count
from os import isatty
from posixpath import join as joinpath
from re import compile as re_compile
from typing import cast, overload, Any, Final, Literal, TypedDict
from urllib.parse import parse_qsl, unquote, urlencode, urlparse
from uuid import uuid4

from cookietools import cookies_str_to_dict
from ddddocr import DdddOcr # type: ignore
from iterutils import run_gen_step
from lxml.html import fromstring, tostring, HtmlElement
from orjson import dumps, loads
from qrcode import QRCode # type: ignore
from startfile import startfile, startfile_async # type: ignore
from texttools import text_within

from exception import check_response


# 默认的请求函数
_httpx_request = None
# 百度网盘 openapi 的应用，直接使用 AList 的
# https://alist.nn.ci/guide/drivers/baidu.html
CLIENT_ID = "iYCeC9g08h5vuP9UqvPHKKSVrKFXGa1v"
CLIENT_SECRET = "jXiFMOPVPCWlO2M5CwWQzffpNPaGTRBG"
# 百度网盘 errno 对应的信息
ERRNO_TO_MESSAGE: Final[dict[int, str]] = {
    0: "成功", 
    -1: "由于您分享了违反相关法律法规的文件，分享功能已被禁用，之前分享出去的文件不受影响。", 
    -2: "用户不存在,请刷新页面后重试", 
    -3: "文件不存在,请刷新页面后重试", 
    -4: "登录信息有误，请重新登录试试", 
    -5: "host_key和user_key无效", 
    -6: "请重新登录", 
    -7: "该分享已删除或已取消", 
    -8: "该分享已经过期", 
    -9: "访问密码错误", 
    -10: "分享外链已经达到最大上限100000条，不能再次分享", 
    -11: "验证cookie无效", 
    -12: "参数错误", 
    -14: "对不起，短信分享每天限制20条，你今天已经分享完，请明天再来分享吧！", 
    -15: "对不起，邮件分享每天限制20封，你今天已经分享完，请明天再来分享吧！", 
    -16: "对不起，该文件已经限制分享！", 
    -17: "文件分享超过限制", 
    -21: "预置文件无法进行相关操作", 
    -30: "文件已存在", 
    -31: "文件保存失败", 
    -33: "一次支持操作999个，减点试试吧", 
    -32: "你的空间不足了哟", 
    -62: "需要验证码或者验证码错误", 
    -70: "你分享的文件中包含病毒或疑似病毒，为了你和他人的数据安全，换个文件分享吧", 
    2: "参数错误", 
    3: "未登录或帐号无效", 
    4: "存储好像出问题了，请稍候再试", 
    108: "文件名有敏感词，优化一下吧", 
    110: "分享次数超出限制，可以到“我的分享”中查看已分享的文件链接", 
    114: "当前任务不存在，保存失败", 
    115: "该文件禁止分享", 
    112: '页面已过期，请<a href="javascript:window.location.reload();">刷新</a>后重试', 
    9100: '你的帐号存在违规行为，已被冻结，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    9200: '你的帐号存在违规行为，已被冻结，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    9300: '你的帐号存在违规行为，该功能暂被冻结，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    9400: '你的帐号异常，需验证后才能使用该功能，<a href="/disk/appeal" target="_blank">立即验证</a>', 
    9500: '你的帐号存在安全风险，已进入保护模式，请修改密码后使用，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    90003: "暂无目录管理权限", 
}
SHARE_ERRORTYPE_TO_MESSAGE: Final[dict[int, str]] = {
    0: "啊哦，你来晚了，分享的文件已经被删除了，下次要早点哟。", 
    1: "啊哦，你来晚了，分享的文件已经被取消了，下次要早点哟。", 
    2: "此链接分享内容暂时不可访问", 
    3: "此链接分享内容可能因为涉及侵权、色情、反动、低俗等信息，无法访问！", 
    5: "啊哦！链接错误没找到文件，请打开正确的分享链接!", 
    10: "啊哦，来晚了，该分享文件已过期", 
    11: "由于访问次数过多，该分享链接已失效", 
    12: "因该分享含有自动备份目录，暂无法查看", 
    15: "系统升级，链接暂时无法查看，升级完成后恢复正常。", 
    17: "该链接访问范围受限，请使用正常的访问方式", 
    123: "该链接已超过访问人数上限，可联系分享者重新分享", 
    124: "您访问的链接已被冻结，可联系分享者进行激活", 
    -1: "分享的文件不存在。", 
}


class VCodeResult(TypedDict, total=True):
    vcode: str
    vcode_str: str


# TODO: 支持同步和异步
def decaptcha(
    ocr: Callable[[bytes], str] = DdddOcr(beta=True, show_ad=False).classification, 
    /, 
    min_confirm: int = 2, 
) -> VCodeResult:
    "识别百度网盘的验证码"
    url = "https://pan.baidu.com/api/getcaptcha?prod=shareverify&web=1&clienttype=0"
    with get(url) as resp:
        resp.raise_for_status()
        data = resp.json()
    vcode_img: str = data["vcode_img"]
    vcode_str: str = data["vcode_str"]
    counter: dict[str, int] = {}
    while True:
        try:
            with get(vcode_img, timeout=5) as resp:
                resp.raise_for_status()
                content = resp.content
        except:
            continue
        res = ocr(content)
        if len(res) != 4 or not res.isalnum():
            continue
        if min_confirm <= 1:
            return {"vcode": res, "vcode_str": vcode_str}
        m = counter.get(res, 0) + 1
        if m >= min_confirm:
            return {"vcode": res, "vcode_str": vcode_str}
        counter[res] = m







def get_default_request():
    global _httpx_request
    if _httpx_request is None:
        from httpx_request import request
        _httpx_request = partial(request, timeout=(5, 60, 60, 5))
    return _httpx_request


def default_parse(resp, content: Buffer, /):
    from orjson import loads
    if isinstance(content, (bytes, bytearray, memoryview)):
        return loads(content)
    else:
        return loads(memoryview(content))


class DuPanClient:

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

    def __del__(self, /):
        self.close()

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

    @cached_property
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

    @cached_property
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

    @cached_property
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

    @cached_property
    def baiduid(self, /) -> str:
        return self.cookies["BAIDUID"]

    @cached_property
    def bdstoken(self, /) -> str:
        resp = self.get_templatevariable("bdstoken")
        check_response(resp)
        return resp["result"]["bdstoken"]

    @cached_property
    def logid(self, /) -> str:
        return b64encode(self.baiduid.encode("ascii")).decode("ascii")

    @cached_property
    def sign_and_timestamp(self, /) -> dict:
        return self.get_sign_and_timestamp()

    def close(self, /) -> None:
        """删除 session 和 async_session 属性，如果它们未被引用，则应该会被自动清理
        """
        self.__dict__.pop("session", None)
        self.__dict__.pop("async_session", None)

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
            return get_default_request()(url=api, async_=async_, **request_kwargs)
        else:
            return request(url=api, **request_kwargs)

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
        async_: Literal[True], 
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
        return self.filemanager(params, payload, async_=async_, **request_kwargs)

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
        return self.filemanager(params, payload, async_=async_, **request_kwargs)

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
            - filelist: list 💡 JSON array
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
            - target: str 💡 JSON array
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
            - order: "name" | "time" | "size" = "name" 💡 排序方式
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
        return self.filemanager(params, payload, async_=async_, **request_kwargs)

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
        return self.filemanager(params, payload, async_=async_, **request_kwargs)

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
    def fs_transfer(
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
    def fs_transfer(
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
    def fs_transfer(
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
            - fsidlist: str # JSON array
            - path: str = "/"
        """
        def gen_step():
            api = "https://pan.baidu.com/share/transfer"
            sl = DuPanShareList(url)
            if data is None:
                flist = yield sl.list_index(async_=async_, **request_kwargs)
                data = {"fsidlist": "[%s]" % ",".join(f["fs_id"] for f in flist)}
            elif isinstance(data, str):
                data = {"fsidlist": data}
            elif isinstance(data, int):
                data = {"fsidlist": "[%s]" % data}
            elif not isinstance(data, dict):
                data = {"fsidlist": "[%s]" % ",".join(map(str, data))}
            elif "fsidlist" not in data:
                flist = yield sl.list_index(async_=async_, **request_kwargs)
                data["fsidlist"] = "[%s]" % ",".join(f["fs_id"] for f in flist)
            elif isinstance(data["fsidlist"], (list, tuple)):
                data["fsidlist"] = "[%s]" % ",".join(map(str, data["fsidlist"]))
            data.setdefault("path", "/")
            if frozenset(("shareid", "from")) - params.keys():
                params.update({
                    "shareid": sl.share_id, 
                    "from": sl.share_uk, 
                    "sekey": sl.randsk, 
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
            - fields: str # JSON array
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
            - fidlist: str 💡 JSON array
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
            for el in fromstring(resp).xpath('//form[@name="scopes"]//input'):
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


class DuPanShareList:

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
        session = self.session = Session()
        session.headers["Referer"] = url

    def __iter__(self, /) -> Iterator[dict]:
        dq: deque[tuple[str, str]] = deque()
        get, put = dq.popleft, dq.append
        put(("", ""))
        while dq:
            dir, dir_relpath = get()
            for file in self.iterdir(dir):
                relpath = file["relpath"] = joinpath(dir_relpath, file["server_filename"])
                yield file
                if file["isdir"]:
                    put((file["path"], relpath))

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

    @cached_property
    def root(self, /):
        self.list_index()
        return self.__dict__["root"]

    @cached_property
    def root2(self, /):
        self.list_index()
        return self.__dict__["root2"]

    @cached_property
    def randsk(self, /) -> str:
        self.list_index()
        return unquote(self.session.cookies.get("BDCLND", ""))

    @cached_property
    def share_id(self, /):
        self.list_index()
        return self.__dict__["share_id"]

    @cached_property
    def share_uk(self, /):
        self.list_index()
        return self.__dict__["share_uk"]

    @cached_property
    def yundata(self, /):
        self.list_index()
        return self.__dict__["yundata"]

    def verify(
        self, 
        /, 
        use_vcode: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        api = "https://pan.baidu.com/share/verify"
        params: dict[str, int | str]
        if self.shorturl:
            params = {"surl": self.shorturl, "web": 1, "clienttype": 0}
        else:
            params = {"web": 1, "clienttype": 0}
            params.update(parse_qsl(urlparse(self.url).query))

        data = {"pwd": self.password}
        if use_vcode:
            data.update(cast(dict[str, str], decaptcha()))
        post = self.session.post
        while True:
            with post(api, params=params, data=data) as resp:
                resp.raise_for_status()
                json = resp.json()
                errno = json["errno"]
                if not errno:
                    break
                if errno == -62:
                    data.update(cast(dict[str, str], decaptcha()))
                else:
                    raise OSError(json)

    def iterdir(self, /, dir: str = "/", page: int = 1, num: int = 0) -> Iterator[dict]:
        if dir in ("", "/"):
            data = self.list_index()
            if num <= 0 or page <= 0:
                yield from data
            else:
                yield from data[(page-1)*num:page*num]
            return
        if not hasattr(self, "share_uk"):
            self.list_index()
        if not dir.startswith("/"):
            dir = self.root + "/" + dir
        api = "https://pan.baidu.com/share/list"
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
        get = self.session.get
        if num <= 0 or page <= 0:
            if num > 0:
                params["num"] = num
            else:
                num = params["num"]
            while True:
                ls = check_response(get(api, params=params).json())["list"]
                yield from ls
                if len(ls) < num:
                    break
                params["page"] += 1
        else:
            params["page"] = page
            params["num"] = num
            yield from check_response(get(api, params=params).json())["list"]

    def list_index(
        self, 
        /, 
        try_times: int = 5, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        url = self.url
        password = self.password
        session = self.session
        if try_times <= 0:
            it: Iterator[int] = count(0)
        else:
            it = iter(range(try_times))
        for _ in it:
            with session.get(url) as resp:
                resp.raise_for_status()
                content = resp.content
                data = self._extract_indexdata(content)
                if b'"verify-form"' in content:
                    if not password:
                        raise OSError("需要密码")
                    self.verify(b'"change-code"' in content)
                else:
                    if data["errno"]:
                        data["errno_reason"] = ERRNO_TO_MESSAGE.get(data["errno"])
                        data["errortype_reason"] = SHARE_ERRORTYPE_TO_MESSAGE.get(data.get("errortype", -1))
                        raise OSError(data)
                    file_list = data.get("file_list")
                    if not file_list:
                        raise OSError("无下载文件，可能是链接失效、分享被取消、删除了所有分享文件等原因")
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
                    return file_list
        raise RuntimeError("too many attempts")

    def listdir(
        self, 
        /, 
        dir: str = "/", 
        page: int = 1, 
        num: int = 0, 
    ) -> list[str]:
        return [attr["server_filename"] for attr in self.iterdir(dir, page, num)]

    def listdir_attr(
        self, 
        /, 
        dir: str = "/", 
        page: int = 1, 
        num: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        return list(self.iterdir(dir, page, num))

