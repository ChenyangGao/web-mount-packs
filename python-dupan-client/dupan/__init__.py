#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__version__ = (0, 0, 1)
__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["Error", "DuPanClient", "DuPanShareList", "DuPanPath", "DuPanFileSystem"]

import errno

from base64 import b64encode
from collections import deque
from collections.abc import Callable, ItemsView, Iterator, KeysView, Mapping, ValuesView
from functools import cached_property, partial, update_wrapper
from io import BytesIO, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE
from itertools import count
from json import dumps, loads
from mimetypes import guess_type
from os import fsdecode, fspath, makedirs, scandir, stat_result, path as ospath, PathLike
from platform import system
from posixpath import basename, commonpath, dirname, join as joinpath, normpath, split as splitpath, splitext
from re import compile as re_compile, escape as re_escape, Pattern
from shutil import copyfileobj, SameFileError
from stat import S_IFDIR, S_IFREG
from subprocess import run
from threading import Thread
from time import time
from typing import cast, Any, Final, IO, Literal, Never, Optional, TypedDict
from types import MappingProxyType
from urllib.parse import parse_qsl, urlencode, urlparse, unquote
from uuid import uuid4

from ddddocr import DdddOcr # type: ignore
from lxml.html import fromstring, tostring, HtmlElement
from qrcode import QRCode # type: ignore
from requests import get, Session
from requests.cookies import create_cookie, RequestsCookieJar

from .util.file import HTTPFileReader, SupportsRead, SupportsWrite
from .util.response import get_content_length
from .util.text import cookies_str_to_dict, posix_glob_translate_iter, text_within
from .util.urlopen import urlopen


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
    90003: "暂无文件夹管理权限", 
}
SHARE_ERRORTYPE_TO_MESSAGE: Final[dict[int, str]] = {
    0: "啊哦，你来晚了，分享的文件已经被删除了，下次要早点哟。", 
    1: "啊哦，你来晚了，分享的文件已经被取消了，下次要早点哟。", 
    2: "此链接分享内容暂时不可访问", 
    3: "此链接分享内容可能因为涉及侵权、色情、反动、低俗等信息，无法访问！", 
    5: "啊哦！链接错误没找到文件，请打开正确的分享链接!", 
    10: "啊哦，来晚了，该分享文件已过期", 
    11: "由于访问次数过多，该分享链接已失效", 
    12: "因该分享含有自动备份文件夹，暂无法查看", 
    15: "系统升级，链接暂时无法查看，升级完成后恢复正常。", 
    17: "该链接访问范围受限，请使用正常的访问方式", 
    123: "该链接已超过访问人数上限，可联系分享者重新分享", 
    124: "您访问的链接已被冻结，可联系分享者进行激活", 
    -1: "分享的文件不存在。", 
}


class VCodeResult(TypedDict, total=True):
    vcode: str
    vcode_str: str


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


try:
    from os import startfile as _startfile # type: ignore
except ImportError:
    match system():
        case "Darwin":
            def _startfile(path):
                run(["open", path], check=True)
        case "Linux":
            def _startfile(path):
                run(["xdg-open", path], check=True)
        case _:
            _startfile = None


def startfile(path, new_thread=False):
    if _startfile is None:
        return
    if new_thread:
        Thread(target=_startfile, args=(path,)).start()
    else:
        _startfile(path)


def console_qrcode(text: str) -> None:
    qr = QRCode(border=1)
    qr.add_data(text)
    qr.print_ascii(tty=True)


class Error(OSError):

    @classmethod
    def check(cls, resp, /):
        if resp["errno"]:
            raise cls(resp)
        return resp


class DuPanClient:
    session: Session
    bdstoken: str
    baiduid: str

    def __init__(
        self, 
        /, 
        cookie: Optional[str] = None, 
        scan_in_console: bool = True, 
    ):
        self.__dict__["session"] = session = Session()
        session.headers["User-Agent"] = "Mozilla/5.0"
        for _ in range(2):
            if not cookie or "BDUSS=" not in cookie:
                self.login_with_qrcode(scan_in_console=scan_in_console)
                self.request("https://pan.baidu.com/disk/main")
                resp = Error.check(self.get_gettemplatevariable("bdstoken"))
                break
            else:
                self.set_cookie(cookie)
                try:
                    resp = Error.check(self.get_gettemplatevariable("bdstoken"))
                except:
                    cookie = None
        self.__dict__.update(
            bdstoken=resp["result"]["bdstoken"], 
            baiduid=session.cookies["BAIDUID"], 
        )

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.baiduid == other.baiduid and self.bdstoken == other.bdstoken

    def __hash__(self, /) -> int:
        return hash((self.baiduid, self.bdstoken))

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    @cached_property
    def logid(self, /) -> str:
        return b64encode(self.baiduid.encode("ascii")).decode("ascii")

    @cached_property
    def sign_and_timestamp(self, /) -> dict:
        return self.get_sign()

    def close(self, /):
        try:
            self.session.close()
        except AttributeError:
            pass

    def login_with_qrcode(
        self, 
        /, 
        scan_in_console: bool = True, 
        check: bool = True, 
    ) -> dict:
        "扫描二维码登录"
        gid = str(uuid4()).upper()
        resp = self.get_qrcode(gid)
        sign = resp["sign"]
        if scan_in_console:
            url = f"https://wappass.baidu.com/wp/?qrlogin&error=0&sign={sign}&cmd=login&lp=pc&tpl=netdisk&adapter=3&qrloginfrom=pc"
            console_qrcode(url)
        else:
            imgurl = "https://" + resp["imgurl"]
            startfile(imgurl, new_thread=True)

        while True:
            msg = self.get_qrcode_status(gid, sign)
            match msg["errno"]:
                case 0:
                    channel_v = loads(msg["channel_v"])
                    match channel_v["status"]:
                        case 0:
                            print("[status=0] qrcode: success")
                            break
                        case 1:
                            print("[status=1] qrcode: scanned")
                        case 2:
                            print("[status=2] qrcode: canceled")
                            raise OSError(msg)
                case 1:
                    pass
                case _:
                    raise OSError(msg)
        resp = self.request(
            f"https://passport.baidu.com/v3/login/main/qrbdusslogin?bduss={channel_v['v']}", 
            parse=eval, 
        )
        if check and resp["errInfo"]["no"] not in ("0", 0):
            raise OSError(resp)
        return resp

    def request(
        self, 
        /, 
        url: str, 
        method: str = "GET", 
        parse: bool | Callable[[bytes], Any] = True, 
        **request_kwargs, 
    ):
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

    @property
    def cookie(self, /) -> str:
        "获取 cookie"
        cookies = self.session.cookies.get_dict()
        return "; ".join(f"{key}={val}" for key, val in cookies.items())

    @property
    def cookiejar(self, /) -> RequestsCookieJar:
        return self.session.cookies

    def set_cookie(self, cookie, /):
        "设置 cookie"
        cookiejar = self.session.cookies
        if isinstance(cookie, str):
            cookie = cookies_str_to_dict(cookie)
        cookiejar.clear()
        if isinstance(cookie, Mapping):
            for key in cookie:
                cookiejar.set_cookie(
                    create_cookie(key, cookie[key], domain=".baidu.com", rest={'HttpOnly': True})
                )
        else:
            cookiejar.update(cookie)

    @staticmethod
    def list_app_version(**request_kwargs) -> dict:
        "罗列最新的 app 版本的信息"
        url = "https://pan.baidu.com/disk/cmsdata?clienttype=0&web=1&do=client"
        return get(url, **request_kwargs).json()

    @staticmethod
    def get_userinfo(
        payload: int | str | dict, 
        /, 
        **request_kwargs, 
    ) -> dict:
        """查询某个用户信息
        payload:
            - query_uk: int | str
        """
        api = "https://pan.baidu.com/pcloud/user/getinfo"
        if isinstance(payload, (int, str)):
            payload = {"clienttype": 0, "web": 1, "query_uk": payload}
        else:
            payload = {"clienttype": 0, "web": 1, **payload}
        request_kwargs["params"] = payload
        return get(api, **request_kwargs).json()

    def userinfo(self, /, **request_kwargs) -> dict:
        "获取用户信息"
        api = "https://pan.baidu.com/sbox/user/query?web=1&clienttype=0"
        return self.request(api, **request_kwargs)

    def membership(
        self, 
        payload: str | dict = "rights", 
        /, 
        **request_kwargs, 
    ) -> dict:
        """获取会员相关权益
        payload:
            - method: str = "rights"
        """
        api = "https://pan.baidu.com/rest/2.0/membership/user"
        if isinstance(payload, (int, str)):
            payload = {"clienttype": 0, "web": 1, "method": payload}
        else:
            payload = {"clienttype": 0, "web": 1, **payload}
        request_kwargs["params"] = payload
        return self.request(api, **request_kwargs)

    def get_qrcode(self, gid, /, **request_kwargs) -> dict:
        "获取二维码"
        api = "https://passport.baidu.com/v2/api/getqrcode"
        request_kwargs["params"] = {
            "apiver": "v3", 
            "tpl": "netdisk", 
            "lp": "pc", 
            "qrloginfrom": "pc", 
            "gid": gid, 
        }
        return self.request(api, **request_kwargs)

    def get_qrcode_status(self, gid, channel_id, /, **request_kwargs) -> dict:
        "获取扫码状态"
        api = "https://passport.baidu.com/channel/unicast"
        request_kwargs["params"] = {
            "apiver": "v3", 
            "tpl": "netdisk", 
            "gid": gid, 
            "channel_id": channel_id, 
        }
        return self.request(api, **request_kwargs)

    def get_gettemplatevariable(
        self, 
        payload: str | list[str] | tuple[str] | dict, 
        /, 
        **request_kwargs, 
    ) -> dict:
        """获取模版变量，例如 "bdstoken", "isPcShareIdWhiteList", "openlogo", "pcShareIdFrom", etc.
        payload:
            - fields: str # JSON array
        """
        api = "https://pan.baidu.com/api/gettemplatevariable"
        if isinstance(payload, str):
            payload = {"fields": dumps([payload], separators=(",", ":"))}
        elif isinstance(payload, (list, tuple)):
            payload = {"fields": dumps(payload, separators=(",", ":"))}
        request_kwargs["params"] = payload
        return self.request(api, **request_kwargs)

    def get_sign(self, /) -> dict:
        resp = Error.check(self.get_gettemplatevariable(["sign1", "sign3", "timestamp"]))
        result = resp["result"]
        sign1 = result["sign1"].encode("ascii")
        sign3 = result["sign3"].encode("ascii")
        a = sign3 * (256 // len(sign3))
        p = bytearray(range(256))
        o = bytearray()
        u = q = 0
        for q in range(256):
            u = (u + p[q] + a[q]) % 256
            t = p[q]
            p[q] = p[u]
            p[u] = t
        i = u = q = 0
        for q in range(len(sign1)):
            i = (i + 1) % 256
            u = (u + p[i]) % 256
            t = p[i]
            p[i] = p[u]
            p[u] = t
            k = p[(p[i] + p[u]) % 256]
            o.append(sign1[q] ^ k)
        return {
            "sign": b64encode(o).decode("utf-8"), 
            "timestamp": result["timestamp"], 
        }

    def get_url(
        self, 
        /, 
        fids: int | str | list[int | str] | tuple[int | str], 
        **request_kwargs, 
    ):
        "获取文件的下载链接"
        api = "https://pan.baidu.com/api/download"
        if isinstance(fids, (int, str)):
            payload = {"clienttype": 0, "web": 1, "type": "dlink", **self.sign_and_timestamp, "fidlist": "[%s]" % fids}
        else:
            payload = {"clienttype": 0, "web": 1, "type": "dlink", **self.sign_and_timestamp, "fidlist": "[%s]" % ",".join(map(str, fids))}
        request_kwargs["params"] = payload
        return self.request(api, **request_kwargs)

    def listdir(
        self, 
        payload: str | dict = "/", 
        /, 
        **request_kwargs, 
    ) -> dict:
        """罗列目录中的文件列表
        payload:
            - dir: str = "/"
            - num: int = 100
            - page: int = 1
            - order: str = "time"
            - desc: 0 | 1 = 1
            - showempty: 0 | 1 = 0
        """
        api = "https://pan.baidu.com/api/list"
        if isinstance(payload, str):
            payload = {"num": 100, "page": 1, "order": "time", "desc": 1, "clienttype": 0, "web": 1, "showempty": 0, "dir": payload}
        else:
            payload = {"num": 100, "page": 1, "order": "time", "desc": 1, "clienttype": 0, "web": 1, "showempty": 0, **payload}
        request_kwargs["params"] = payload
        return self.request(api, **request_kwargs)

    def makedir(
        self, 
        payload: str | dict, 
        /, 
        **request_kwargs, 
    ) -> dict:
        """创建文件夹
        payload:
            - path: str
            - isdir: 0 | 1 = 1
            - block_list: str = "[]" # JSON array
        """
        api = "https://pan.baidu.com/api/create"
        request_kwargs["params"] = {
            "a": "commit", 
            "bdstoken": self.bdstoken, 
            "clienttype": 0, 
            "web": 1, 
        }
        if isinstance(payload, str):
            payload = {"isdir": 1, "block_list": "[]", "path": payload}
        else:
            payload = {"isdir": 1, "block_list": "[]", **payload}
        request_kwargs["data"] = payload
        return self.request(api, "POST", **request_kwargs)

    def filemetas(
        self, 
        payload: str | list[str] | tuple[str] | dict, 
        /, 
        **request_kwargs, 
    ) -> dict:
        """获取文件信息
        payload:
            - target: str # JSON array
            - dlink: 0 | 1 = 1
        """
        api = "https://pan.baidu.com/api/filemetas"
        if isinstance(payload, str):
            payload = {"clienttype": 0, "web": 1, "dlink": 1, "target": dumps([payload], separators=(",", ":"))}
        elif isinstance(payload, (list, tuple)):
            payload = {"clienttype": 0, "web": 1, "dlink": 1, "target": dumps(payload, separators=(",", ":"))}
        request_kwargs["params"] = payload
        return self.request(api, **request_kwargs)

    def filemanager(
        self, 
        /, 
        params: str | dict, 
        data: str | list | tuple | dict, 
        **request_kwargs, 
    ) -> dict:
        """文件管理，可批量操作
        params:
            - opera: "copy" | "delete" | "move" | "rename"
            - async: int = 1 # 如果值为 2，则是异步，可用 `taskquery()` 查询进度
            - onnest: str = "fail"
            - newVerify: 0 | 1 = 1
            - ondup: "newcopy" | "overwrite" = <default>
            - bdstoken: str = <default>
        data:
            - filelist: list # 取决于具体 opera
        """
        api = "https://pan.baidu.com/api/filemanager"
        if isinstance(params, str):
            params = {"opera": params}
        params = {
            "async": 1, 
            "onnest": "fail", 
            "newVerify": 1, 
            "bdstoken": self.bdstoken, 
            "clienttype": 0, 
            "web": 1, 
            **params, 
        }
        if isinstance(data, str):
            data = {"filelist": dumps([data], separators=(",", ":"))}
        elif isinstance(data, dict):
            if "filelist" not in data:
                data = {"filelist": dumps([data], separators=(",", ":"))}
        elif isinstance(data, (list, tuple)):
            data = {"filelist": dumps(data, separators=(",", ":"))}
        return self.request(api, "POST", params=params, data=data, **request_kwargs)

    def copy(
        self, 
        payload: list | tuple | dict, 
        /, 
        params: Optional[dict] = None, 
        **request_kwargs, 
    ) -> dict:
        """复制
        payload:
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
        if params is None:
            params = {"opera": "copy"}
        elif params.get("opera") != "copy":
            params = {**params, "opera": "copy"}
        return self.filemanager(params, payload, **request_kwargs)

    def delete(
        self, 
        payload: str | list | tuple | dict, 
        /, 
        params: Optional[dict] = None, 
        **request_kwargs, 
    ) -> dict:
        """删除
        payload:
            {
                filelist: [
                    str, # 文件路径
                    ...
                ]
            }
        """
        if params is None:
            params = {"opera": "delete"}
        elif params.get("opera") != "delete":
            params = {**params, "opera": "delete"}
        return self.filemanager(params, payload, **request_kwargs)

    def move(
        self, 
        payload: list | tuple | dict, 
        /, 
        params: Optional[dict] = None, 
        **request_kwargs, 
    ) -> dict:
        """移动
        payload:
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
        if params is None:
            params = {"opera": "move"}
        elif params.get("opera") != "move":
            params = {**params, "opera": "move"}
        return self.filemanager(params, payload, **request_kwargs)

    def rename(
        self, 
        payload: list | tuple | dict, 
        /, 
        params: Optional[dict] = None, 
        **request_kwargs, 
    ) -> dict:
        """重命名
        payload:
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
        if params is None:
            params = {"opera": "rename"}
        elif params.get("opera") != "rename":
            params = {**params, "opera": "rename"}
        return self.filemanager(params, payload, **request_kwargs)

    def taskquery(
        self, 
        payload: int | str | dict, 
        /, 
        **request_kwargs, 
    ) -> dict:
        """任务进度查询
        payload:
            - taskid: int | str
        返回值状态:
            - status: "pending"
            - status: "running"
            - status: "failed"
            - status: "success"
        """
        api = "https://pan.baidu.com/share/taskquery"
        if isinstance(payload, (int, str)):
            payload = {"clienttype": 0, "web": 1, "taskid": payload}
        request_kwargs["params"] = payload
        return self.request(api, **request_kwargs)

    def transfer(
        self, 
        /, 
        url, 
        params: dict = {}, 
        data: None | str | int | list[int] | tuple[int] | dict = None, 
        **request_kwargs, 
    ) -> dict:
        """转存
        params:
            - shareid: int | str
            - from: int | str
            - sekey: str = ""
            - async: 0 | 1 = 1
            - bdstoken: str = <default>
            - ondup: "overwrite" | "newcopy" = <default>
        data:
            - fsidlist: str # JSON array
            - path: str = "/"
        """
        api = "https://pan.baidu.com/share/transfer"
        sl = DuPanShareList(url)
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
        if data is None:
            fsidlist = "[%s]" % ",".join(f["fs_id"] for f in sl.list_index())
            data = {"fsidlist": fsidlist, "path": "/"}
        elif isinstance(data, str):
            data = {"fsidlist": data, "path": "/"}
        elif isinstance(data, int):
            data = {"fsidlist": "[%s]" % data, "path": "/"}
        elif isinstance(data, (list, tuple)):
            data = {"fsidlist": "[%s]" % ",".join(map(str, data)), "path": "/"}
        else:
            if "fsidlist" not in data:
                data["fsidlist"] = "[%s]" % ",".join(f["fs_id"] for f in sl.list_index())
            elif isinstance(data["fsidlist"], (list, tuple)):
                data["fsidlist"] = "[%s]" % ",".join(map(str, data["fsidlist"]))
        request_kwargs["headers"] = {**(request_kwargs.get("headers") or {}), "Referer": url}
        return self.request(api, "POST", params=params, data=data, **request_kwargs)

    def oauth_authorize(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        scope: str = "basic,netdisk", 
        **request_kwargs, 
    ) -> str:
        """OAuth 授权
        """
        def check(etree):
            error_msg = etree.find_class("error-msg-list")
            if error_msg:
                raise OSError(tostring(error_msg[0], encoding="utf-8").decode("utf-8").strip())
        api = "https://openapi.baidu.com/oauth/2.0/authorize"
        request_kwargs["params"] = {
            "response_type": "code", 
            "client_id": client_id, 
            "redirect_uri": "oob", 
            "scope": scope, 
            "display": "popup", 
        }
        resp = self.request(api, **request_kwargs)
        etree: HtmlElement = fromstring(resp)
        check(etree)
        try:
            return etree.get_element_by_id("Verifier").value
        except KeyError:
            pass
        payload = []
        grant_permissions = []
        el: HtmlElement
        for el in fromstring(resp).cssselect('form[name="scopes"] input'):
            name, value = el.name, el.value
            if name == "grant_permissions_arr":
                grant_permissions.append(value)
                payload.append(("grant_permissions_arr[]", value))
            elif name == "grant_permissions":
                payload.append(("grant_permissions", ",".join(grant_permissions)))
            else:
                payload.append((name, value))
        request_kwargs.update(
            data=urlencode(payload), 
            headers={
                **(request_kwargs.get("headers") or {}), 
                "Content-Type": "application/x-www-form-urlencoded", 
            }, 
        )
        resp = self.request(api, "POST", **request_kwargs)
        etree = fromstring(resp)
        return etree.get_element_by_id("Verifier").value

    def oauth_token(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        client_secret: str = CLIENT_SECRET, 
        scope: str = "basic,netdisk", 
        **request_kwargs, 
    ) -> dict:
        """获取 OAuth token
        """
        api = "https://openapi.baidu.com/oauth/2.0/token"
        request_kwargs["params"] = {
            "grant_type": "authorization_code", 
            "code": self.oauth_authorize(client_id, scope, **request_kwargs), 
            "client_id": client_id, 
            "client_secret": client_secret, 
            "redirect_uri": "oob", 
        }
        return self.request(api, **request_kwargs)

    @cached_property
    def fs(self, /) -> DuPanFileSystem:
        return DuPanFileSystem(self)

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        dq = deque("/")
        get, put = dq.popleft, dq.append
        while dq:
            for file in self.iterdir(get()):
                yield file
                if file["isdir"]:
                    put(file["path"])

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
    ) -> Optional[dict]:
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

    def verify(self, /, use_vcode: bool = False):
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

    def iterdir(self, /, dir="/") -> Iterator[dict]:
        if dir in ("", "/"):
            yield from self.list_index()
            return
        if not hasattr(self, "share_uk"):
            self.list_index()
        if not dir.startswith("/"):
            dir = self.root + "/" + dir
            start_inx = len(dir) + 1
        elif dir == self.root or dir.startswith(self.root + "/"):
            start_inx = len(self.root) + 1
        elif dir == self.root2 or dir.startswith(self.root2 + "/"):
            start_inx = len(self.root2) + 1
        else:
            raise FileNotFoundError(errno.ENOENT, dir)
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
        while True:
            ls = Error.check(get(api, params=params).json())["list"]
            for file in ls:
                file["relpath"] = file["path"][start_inx:]
            yield from ls
            if len(ls) < 100:
                return
            params["page"] += 1

    def list_index(self, /, try_times: int = 5) -> list[dict]:
        url = self.url
        password = self.password
        session = self.session
        if try_times <= 0:
            it: Iterator[int] = count()
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

    def listdir(self, /, dir="/", page=1, num=0) -> list[str]:
        return [a["server_filename"] for a in self.listdir_attr(dir, page, num)]

    def listdir_attr(self, /, dir="/", page=1, num=0) -> list[dict]:
        if dir in ("", "/"):
            data = self.list_index()
            if num <= 0:
                return data
            if page < 1:
                page = 1
            return data[(page-1)*num:page*num]
        if not hasattr(self, "share_uk"):
            self.list_index()
        if not dir.startswith("/"):
            dir = self.root + "/" + dir
            start_inx = len(dir) + 1
        elif dir == self.root or dir.startswith(self.root + "/"):
            start_inx = len(self.root) + 1
        elif dir == self.root2 or dir.startswith(self.root2 + "/"):
            start_inx = len(self.root2) + 1
        else:
            raise FileNotFoundError(errno.ENOENT, dir)
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
        session = self.session
        if num <= 0:
            ls_all = []
            while True:
                ls = Error.check(session.get(api, params=params).json())["list"]
                ls_all.extend(ls)
                if len(ls) < 100:
                    for file in ls_all:
                        file["relpath"] = file["path"][start_inx:]
                    return ls_all
                params["page"] += 1
        if page > 0:
            params["page"] = page
        if num < 100:
            params["num"] = 100
        ls = Error.check(session.get(api, params=params).json())["list"]
        for file in ls:
            file["relpath"] = file["path"][start_inx:]
        return ls


class DuPanPath:
    fs: DuPanFileSystem
    path: str

    def __init__(
        self, 
        /, 
        fs: DuPanFileSystem, 
        path: str | PathLike[str], 
        **attr, 
    ):
        attr.update(fs=fs, path=fs.abspath(path))
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> DuPanPath:
        return type(self)(self.fs, commonpath((self, self.fs.abspath(path))))

    def __call__(self, /) -> DuPanPath:
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
        if not type(self) is type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __gt__(self, path, /) -> bool:
        if not type(self) is type(path) or self.fs.client != path.fs.client or self.path == path.path:
            return False
        return commonpath((self.path, path.path)) == path.path

    def __hash__(self, /) -> int:
        return hash((self.fs.client, self.path))

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /) -> int:
        return len(self.__dict__)

    def __le__(self, path, /) -> bool:
        if not type(self) is type(path) or self.fs.client != path.fs.client:
            return False
        return commonpath((self.path, path.path)) == self.path

    def __lt__(self, path, /) -> bool:
        if not type(self) is type(path) or self.fs.client != path.fs.client or self.path == path.path:
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

    def __truediv__(self, path: str | PathLike[str], /) -> DuPanPath:
        return type(self).joinpath(self, path)

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
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> Optional[DuPanPath]:
        dst = self.fs.copy(
            self, 
            dst_path, 
            overwrite_or_ignore=overwrite_or_ignore, 
            recursive=True, 
        )
        if not dst:
            return None
        return type(self)(self.fs, dst)

    def download(
        self, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
    ):
        return self.fs.download_tree(
            self, 
            local_dir, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
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
    ) -> Iterator[DuPanPath]:
        return self.fs.glob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def is_absolute(self, /) -> bool:
        return True

    def is_dir(self, /):
        try:
            return self["isdir"]
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def is_file(self, /) -> bool:
        try:
            return not self["isdir"]
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

    def iter(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[DuPanPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
    ) -> Iterator[DuPanPath]:
        return self.fs.iter(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
        )

    def joinpath(self, *paths: str | PathLike[str]) -> DuPanPath:
        if not paths:
            return self
        path = self.path
        path_new = normpath(joinpath(path, *paths))
        if path == path_new:
            return self
        return type(self)(self.fs, path_new)

    def listdir(self, /) -> list[str]:
        return self.fs.listdir(self)

    def listdir_attr(self, /) -> list[dict]:
        return self.fs.listdir_attr(self)

    def listdir_path(self, /) -> list[DuPanPath]:
        return self.fs.listdir_path(self)

    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
    ) -> bool:
        pattern = "/" + "/".join(t[0] for t in posix_glob_translate_iter(path_pattern))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

    @property
    def media_type(self, /) -> Optional[str]:
        if not self.is_file():
            return None
        return guess_type(self.path)[0] or "application/octet-stream"

    def mkdir(self, /, exist_ok: bool = True):
        self.fs.makedirs(self, exist_ok=exist_ok)

    def move(self, /, dst_path: str | PathLike[str]) -> DuPanPath:
        dst = self.fs.move(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

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
    def parent(self, /) -> DuPanPath:
        path = self.path
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path))

    @cached_property
    def parents(self, /) -> tuple[DuPanPath, ...]:
        path = self.path
        if path == "/":
            return ()
        parents: list[DuPanPath] = []
        cls, fs = type(self), self.fs
        parent = dirname(path)
        while path != parent:
            parents.append(cls(fs, parent))
            path, parent = parent, dirname(parent)
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

    def relative_to(self, other: str | DuPanPath, /) -> str:
        if isinstance(other, DuPanPath):
            other = other.path
        elif not other.startswith("/"):
            other = self.fs.abspath(other)
        path = self.path
        if path == other:
            return ""
        elif path.startswith(other+"/"):
            return path[len(other)+1:]
        raise ValueError(f"{path!r} is not in the subpath of {other!r}")

    @cached_property
    def relatives(self, /) -> tuple[str]:
        def it(path):
            stop = len(path)
            while stop:
                stop = path.rfind("/", 0, stop)
                yield path[stop+1:]
        return tuple(it(self.path))

    def remove(self, /, recursive: bool = False):
        self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> DuPanPath:
        dst = self.fs.rename(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def renames(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> DuPanPath:
        dst = self.fs.renames(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def replace(
        self, 
        /, 
        dst_path: str | PathLike[str], 
    ) -> DuPanPath:
        dst = self.fs.replace(self, dst_path)
        if self.path == dst:
            return self
        return type(self)(self.fs, dst)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
    ) -> Iterator[DuPanPath]:
        return self.fs.rglob(
            pattern, 
            self if self.is_dir() else self.parent, 
            ignore_case=ignore_case, 
        )

    def rmdir(self, /):
        self.fs.rmdir(self)

    @cached_property
    def root(self, /) -> DuPanPath:
        if dirname(self.path) == "/":
            return self
        return self.parents[-2]

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
        )

    def walk_path(
        self, 
        /, 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
    ) -> Iterator[tuple[str, list[DuPanPath], list[DuPanPath]]]:
        return self.fs.walk_path(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            onerror=onerror, 
        )

    def with_name(self, name: str, /) -> DuPanPath:
        return self.parent.joinpath(name)

    def with_stem(self, stem: str, /) -> DuPanPath:
        return self.parent.joinpath(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> DuPanPath:
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


class DuPanFileSystem:
    client: DuPanClient
    path: str

    def __init__(
        self, 
        /, 
        client: DuPanClient, 
        path: str | PathLike[str] = "/", 
    ):
        if path in ("", "/", ".", ".."):
            path = "/"
        else:
            path = "/" + normpath("/" + fspath(path)).lstrip("/")
        self.__dict__.update(client=client, path=path)

    def __contains__(self, path: str | PathLike[str], /) -> bool:
        return self.exists(path)

    def __delitem__(self, path: str | PathLike[str], /):
        self.rmtree(path)

    def __getitem__(self, path: str | PathLike[str], /) -> DuPanPath:
        return self.as_path(path)

    def __iter__(self, /) -> Iterator[DuPanPath]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, /, path: str | PathLike[str]) -> DuPanFileSystem:
        self.chdir(path)
        return self

    def __len__(self, /) -> int:
        return len(self.listdir_attr())

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self.client!r}, path={self.path!r})"

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
    def login(cls, /, cookie=None, scan_in_console: bool = True) -> DuPanFileSystem:
        return cls(DuPanClient(cookie, scan_in_console=scan_in_console))

    def abspath(self, path: str | PathLike[str] = "", /) -> str:
        if path == "/":
            return "/"
        elif path in ("", "."):
            return self.path
        elif isinstance(path, DuPanPath):
            return path.path
        path = fspath(path)
        if path.startswith("/"):
            return "/" + normpath(path).lstrip("/")
        return normpath(joinpath(self.path, path))

    def as_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        fetch_attr: bool = False, 
        _check: bool = True, 
    ) -> DuPanPath:
        if not isinstance(path, DuPanPath):
            if _check:
                path = self.abspath(path)
            path = DuPanPath(self, path)
        if fetch_attr:
            path()
        return path

    def attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> dict:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        resp = self.client.filemetas(path)
        lastest_update = time()
        err = resp["errno"]
        if err:
            resp["path"] = path
            if err == 12:
                raise FileNotFoundError(errno.ENOENT, resp)
            raise OSError(errno.EIO, resp)
        attr = resp["info"][0]
        attr["name"] = attr["server_filename"]
        attr["ctime"] = attr["local_ctime"]
        attr["mtime"] = attr["local_mtime"]
        attr["atime"] = lastest_update
        attr["lastest_update"] = lastest_update
        return attr

    def chdir(
        self, 
        /, 
        path: str | PathLike[str] = "/", 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == self.path:
            pass
        elif path == "/":
            self.__dict__["path"] = "/"
        elif self.attr(path, _check=False)["isdir"]:
            self.__dict__["path"] = path
        else:
            raise NotADirectoryError(errno.ENOTDIR, path)

    def copy(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = None, 
        recursive: bool = False, 
        _check: bool = True, 
    ) -> Optional[str]:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if _check:
            src_attr = self.attr(src_path, _check=False)
            if src_attr["isdir"]:
                if recursive:
                    return self.copytree(
                        src_path, 
                        dst_path, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                if overwrite_or_ignore == False:
                    return None
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"source path {src_path!r} is a directory: {src_path!r} -> {dst_path!r}", 
                )
        if src_path == dst_path:
            if overwrite_or_ignore is None:
                raise SameFileError(src_path)
            return None
        cmpath = commonpath((src_path, dst_path))
        if cmpath == dst_path:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a file as its ancestor is not allowed: {src_path!r} -> {dst_path!r}", 
            )
        elif cmpath == src_path:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a file as its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
            )
        src_dir, src_name = splitpath(src_path)
        dst_dir, dst_name = splitpath(dst_path)
        try:
            dst_attr = self.attr(dst_path, _check=False)
        except FileNotFoundError:
            self.client.copy([{"path": src_path, "dest": dst_dir, "newname": dst_name}])
        else:
            if dst_attr["isdir"]:
                if overwrite_or_ignore == False:
                    return None
                raise IsADirectoryError(
                    errno.EISDIR, 
                    f"destination path {src_path!r} is a directory: {src_path!r} -> {dst_path!r}", 
                )
            elif overwrite_or_ignore is None:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"destination path {dst_path!r} already exists: {src_path!r} -> {dst_path!r}", 
                )
            elif not overwrite_or_ignore:
                return None
            self.client.copy([{"path": src_path, "dest": dst_dir, "newname": dst_name, "ondup": "overwrite"}])
        return dst_path

    def copytree(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Optional[str]:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if _check:
            src_attr = self.attr(src_path, _check=False)
            if not src_attr["isdir"]:
                return self.copy(
                    src_path, 
                    dst_path, 
                    overwrite_or_ignore=overwrite_or_ignore, 
                    _check=False, 
                )
        if src_path == dst_path:
            if overwrite_or_ignore is None:
                raise SameFileError(src_path)
            return None
        elif commonpath((src_path, dst_path)) == dst_path:
            if overwrite_or_ignore == False:
                return None
            raise PermissionError(
                errno.EPERM, 
                f"copy a directory to its subordinate path is not allowed: {src_path!r} ->> {dst_path!r}", 
            )
        src_dir, src_name = splitpath(src_path)
        dst_dir, dst_name = splitpath(dst_path)
        try:
            dst_attr = self.attr(dst_path, _check=False)
        except FileNotFoundError:
            self.client.copy([{"path": src_path, "dest": dst_dir, "newname": dst_name}])
        else:
            if not dst_attr["isdir"]:
                if overwrite_or_ignore == False:
                    return None
                raise NotADirectoryError(
                    errno.ENOTDIR, 
                    f"destination is not directory: {src_path!r} ->> {dst_path!r}", 
                )
            elif overwrite_or_ignore is None:
                raise FileExistsError(
                    errno.EEXIST, 
                    f"destination already exists: {src_path!r} ->> {dst_path!r}", 
                )
            for attr in self.listdir_attr(src_path):
                if attr["isdir"]:
                    self.copytree(
                        joinpath(src_path, attr["name"]), 
                        joinpath(dst_path, attr["name"]), 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.copy(
                        joinpath(src_path, attr["name"]), 
                        joinpath(dst_path, attr["name"]), 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
        return dst_path

    def download(
        self, 
        /, 
        path: str | PathLike[str], 
        local_path_or_file: bytes | str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        _check: bool = True, 
    ):
        raise NotImplementedError

    def download_tree(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        local_dir: bytes | str | PathLike = "", 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes]], Any]] = None, 
        _check: bool = True, 
    ):
        is_dir: bool
        if isinstance(path, DuPanPath):
            is_dir = path.is_dir()
            path = path.path
        elif _check:
            path = self.abspath(path)
            is_dir = self.attr(path)["isdir"]
        else:
            is_dir = True
        path = cast(str, path)
        local_dir = fsdecode(local_dir)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        if is_dir:
            if not no_root:
                local_dir = ospath.join(local_dir, basename(path))
                if local_dir:
                    makedirs(local_dir, exist_ok=True)
            for pathobj in self.listdir_path(path, _check=False):
                name = pathobj.name
                if pathobj.is_dir():
                    self.download_tree(
                        pathobj.name, 
                        ospath.join(local_dir, name), 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
                        _check=False, 
                    )
                else:
                    self.download(
                        pathobj.name, 
                        ospath.join(local_dir, name), 
                        write_mode=write_mode, 
                        download=download, 
                        _check=False, 
                    )
        else:
            self.download(
                path, 
                ospath.join(local_dir, basename(path)), 
                write_mode=write_mode, 
                download=download, 
                _check=False, 
            )

    def exists(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> bool:
        try:
            self.attr(path, _check=_check)
            return True
        except FileNotFoundError:
            return False

    def getcwd(self, /) -> str:
        return self.path

    def get_url(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        attr = self.attr(path)
        if attr["isdir"]:
            raise OSError(errno.EISDIR, path)
        return Error.check(self.client.get_url(attr["fs_id"]))["dlink"][0]["dlink"]

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[DuPanPath]:
        if pattern == "*":
            return self.iter(dirname, _check=_check)
        elif pattern == "**":
            return self.iter(dirname, max_depth=-1, _check=_check)
        elif not pattern:
            dirname = self.as_path(dirname, _check=_check)
            if dirname.exists():
                return iter((dirname,))
            return iter(())
        elif not pattern.lstrip("/"):
            return iter((DuPanPath(self, "/"),))
        splitted_pats = tuple(posix_glob_translate_iter(pattern))
        if pattern.startswith("/"):
            dirname = "/"
        elif isinstance(dirname, DuPanPath):
            dirname = dirname.path
        elif _check:
            dirname = self.abspath(dirname)
        dirname = cast(str, dirname)
        i = 0
        if ignore_case:
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), "/".join(t[0] for t in splitted_pats))
                match = re_compile("(?i:%s)" % pattern).fullmatch
                return self.iter(
                    dirname, 
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
                if self.exists(dirname, _check=False):
                    return iter((DuPanPath(self, dirname),))
                return iter(())
            elif typ == "dstar" and i + 1 == len(splitted_pats):
                return self.iter(dirname, max_depth=-1, _check=False)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dirname), "/".join(t[0] for t in splitted_pats[i:]))
                match = re_compile(pattern).fullmatch
                return self.iter(
                    dirname, 
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
        path = DuPanPath(self, dirname)
        if not path.is_dir():
            return iter(())
        return glob_step_match(path, i)

    def isdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        try:
            return self.attr(path, _check=_check)["isdir"] == 1
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def isfile(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        try:
            return not self.attr(path, _check=_check)["isdir"] == 0
        except FileNotFoundError:
            return False
        except KeyError:
            return True

    def is_empty(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> bool:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            attr = self.attr(path, _check=False)
        except FileNotFoundError:
            return True
        if attr["isdir"]:
            try:
                next(self.iterdir(path, page_size=1, _check=False))
                return False
            except StopIteration:
                return True
        else:
            return attr.get("size", 0)

    def iter(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[DuPanPath], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
        _check: bool = True, 
    ) -> Iterator[DuPanPath]:
        if not max_depth:
            return
        if _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_path(top, _check=False)
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
        yield_me = min_depth <= 0
        for path in ls:
            if yield_me and predicate:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred 
            if yield_me and topdown:
                yield path
            if path.is_dir():
                yield from self.iter(
                    path.path, 
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
        page_size: int = 100, 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        if page_size <= 0:
            page_size = 100
        if not self.attr(path)["isdir"]:
            raise OSError(errno.ENOTDIR, path)
        payload = {"dir": path, "num": page_size, "page": 1}
        while True:
            resp = self.client.listdir(payload)
            lastest_update = time()
            err = resp["errno"]
            if err:
                raise OSError(errno.EIO, path)
            ls = resp["list"]
            for attr in ls:
                attr["name"] = attr["server_filename"]
                attr["ctime"] = attr["local_ctime"]
                attr["mtime"] = attr["local_mtime"]
                attr["atime"] = lastest_update
                attr["lastest_update"] = lastest_update
                yield attr
            if len(ls) < page_size:
                break

    def listdir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> list[str]:
        return list(attr["server_filename"] for attr in self.iterdir(path, page_size=10_000, _check=_check))

    def listdir_attr(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> list[dict]:
        return list(self.iterdir(path, page_size=10_000, _check=_check))

    def listdir_path(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> list[DuPanPath]:
        return [DuPanPath(self, **attr) for attr in self.iterdir(path, page_size=10_000, _check=_check)]

    def makedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        exist_ok: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            return "/"
        if not exist_ok and self.exists(path, _check=False):
            raise FileExistsError(errno.EEXIST, path)
        Error.check(self.client.makedir(path))
        return path

    def mkdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "create root directory is not allowed (because it has always existed)")
        try:
            self.attr(path)
        except FileNotFoundError as e:
            dir_ = dirname(path)
            if not self.attr(dir_)["isdir"]:
                raise NotADirectoryError(errno.ENOTDIR, dir_) from e
            Error.check(self.client.makedir(path))
            return path
        else:
            raise FileExistsError(errno.EEXIST, path)

    def move(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            return src_path
        cmpath = commonpath((src_path, dst_path))
        if cmpath == dst_path:
            raise PermissionError(
                errno.EPERM, 
                f"rename a path as its ancestor is not allowed: {src_path!r} -> {dst_path!r}", 
            )
        elif cmpath == src_path:
            raise PermissionError(
                errno.EPERM, 
                f"rename a path as its descendant is not allowed: {src_path!r} -> {dst_path!r}", 
            )
        src_attr = self.attr(src_path)
        try:
            dst_attr = self.attr(dst_path)
        except FileNotFoundError:
            dest, name = splitpath(dst_path)
            Error.check(self.client.move([{
                "path": src_path, 
                "dest": dest, 
                "newname": name, 
            }]))
            return dst_path
        else:
            if dst_attr["isdir"]:
                dst_filename = basename(src_path)
                dst_filepath = joinpath(dst_path, dst_filename)
                if self.exists(dst_filepath, _check=False):
                    raise FileExistsError(errno.EEXIST, f"destination path {dst_filepath!r} already exists")
                Error.check(self.client.move([{
                    "path": src_path, 
                    "dest": dst_path, 
                    "newname": dst_filename, 
                }]))
                return dst_filepath
            raise FileExistsError(errno.EEXIST, f"destination path {dst_path!r} already exists")

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
        _check: bool = True, 
    ):
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        url = self.get_url(path, _check=_check)
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
        /, 
        path: str | PathLike[str], 
        start: int = 0, 
        stop: Optional[int] = None, 
        _check: bool = True, 
    ) -> bytes:
        url = self.get_url(path, _check=_check)
        return self.client.read_bytes(url, start, stop)

    def read_bytes_range(
        self, 
        /, 
        path: str | PathLike[str], 
        bytes_range: str = "0-", 
        _check: bool = True, 
    ) -> bytes:
        url = self.get_url(path, _check=_check)
        return self.client.read_bytes_range(url, bytes_range)

    def read_block(
        self, 
        /, 
        path: str | PathLike[str], 
        size: int = 0, 
        offset: int = 0, 
        _check: bool = True, 
    ) -> bytes:
        if size <= 0:
            return b""
        url = self.get_url(path, _check=_check)
        return self.client.read_block(url, size, offset)

    def read_text(
        self, 
        /, 
        path: str | PathLike[str], 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        _check: bool = True, 
    ):
        return self.open(
            path, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            _check=_check, 
        ).read()

    def remove(
        self, 
        /, 
        path: str | PathLike[str], 
        recursive: bool = False, 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            if recursive:
                attrs = self.listdir_attr("/")
                if attrs:
                    Error.check(self.client.delete([attr["path"] for attr in attrs]))
                return
            else:
                raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        if self.attr(path)["isdir"] and not recursive:
            raise IsADirectoryError(errno.EISDIR, path)
        Error.check(self.client.delete([path]))

    def removedirs(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        self.rmdir(path, _check=False)
        subpath = dirname(path)
        while subpath != path:
            path = subpath
            try:
                self.rmdir(path, _check=False)
            except OSError as e:
                break
            subpath = dirname(path)

    def rename(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        replace: bool = False, 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        if src_path == dst_path:
            return dst_path
        if src_path == "/" or dst_path == "/":
            raise OSError(errno.EINVAL, f"invalid argument: {src_path!r} -> {dst_path!r}")
        cmpath = commonpath((src_path, dst_path))
        if cmpath == dst_path:
            raise PermissionError(errno.EPERM, f"rename a path as its ancestor is not allowed: {src_path!r} -> {dst_path!r}")
        elif cmpath == src_path:
            raise PermissionError(errno.EPERM, f"rename a path as its descendant is not allowed: {src_path!r} -> {dst_path!r}")
        dest, name = splitpath(dst_path)
        if replace:
            Error.check(self.client.move([{
                "path": src_path, 
                "dest": dest, 
                "newname": name, 
                "ondup": "overwrite", 
            }]))
        else:
            if self.exists(dst_path, _check=False):
                raise FileExistsError(errno.EEXIST, f"{dst_path!r} already exists: {src_path!r} -> {dst_path!r}")
            Error.check(self.client.move([{
                "path": src_path, 
                "dest": dest, 
                "newname": name
            }]))
        return dst_path

    def renames(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        if isinstance(src_path, DuPanPath):
            src_path = src_path.path
        elif _check:
            src_path = self.abspath(src_path)
        if isinstance(dst_path, DuPanPath):
            dst_path = dst_path.path
        elif _check:
            dst_path = self.abspath(dst_path)
        src_path = cast(str, src_path)
        dst_path = cast(str, dst_path)
        dst = self.rename(src_path, dst_path, _check=False)
        if dirname(src_path) != dirname(dst_path):
            try:
                self.removedirs(dirname(src_path), _check=False)
            except OSError:
                pass
        return dst

    def replace(
        self, 
        /, 
        src_path: str | PathLike[str], 
        dst_path: str | PathLike[str], 
        _check: bool = True, 
    ) -> str:
        return self.rename(src_path, dst_path, replace=True, _check=_check)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: str | PathLike[str] = "", 
        ignore_case: bool = False, 
        _check: bool = True, 
    ) -> Iterator[DuPanPath]:
        if not pattern:
            return self.iter(dirname, max_depth=-1, _check=_check)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, ignore_case=ignore_case, _check=_check)

    def rmdir(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if path == "/":
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        attr = self.attr(path)
        if not attr["isdir"]:
            raise NotADirectoryError(errno.ENOTDIR, path)
        else:
            try:
                next(self.iterdir(path, page_size=1))
            except StopIteration:
                pass
            else:
                raise OSError(errno.ENOTEMPTY, f"directory not empty: {path!r}")
        Error.check(self.client.delete([path]))

    def rmtree(
        self, 
        /, 
        path: str | PathLike[str], 
        _check: bool = True, 
    ):
        self.remove(path, recursive=True, _check=_check)

    def scandir(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> Iterator[DuPanPath]:
        return iter(self.listdir_path(path, _check=_check))

    def stat(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ):
        attr = self.attr(path, _check=_check)
        return stat_result((
            (S_IFDIR if attr["isdir"] else S_IFREG) | 0o777, 
            0, # ino
            0, # dev
            1, # nlink
            0, # uid
            0, # gid
            attr["size"], # size
            attr["atime"], # atime
            attr["mtime"], # mtime
            attr["ctime"], # ctime
        ))

    def touch(
        self, 
        /, 
        path: str | PathLike[str] = "", 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        if not self.exists(path, _check=False):
            dir_ = dirname(path)
            if not self.attr(dir_, _check=False)["isdir"]:
                raise NotADirectoryError(errno.ENOTDIR, f"parent path {dir_!r} is not a directory: {path!r}")
            return self.upload(BytesIO(), path, _check=False)
        return path

    def upload(
        self, 
        /, 
        local_path_or_file: str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: str | PathLike[str] = "", 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        raise NotImplementedError

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str], 
        path: str | PathLike[str] = "", 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
        _check: bool = True, 
    ) -> str:
        if isinstance(path, DuPanPath):
            path = path.path
        elif _check:
            path = self.abspath(path)
        path = cast(str, path)
        try:
            if not self.attr(path)["isdir"]:
                raise NotADirectoryError(errno.ENOTDIR, path)
        except FileNotFoundError:
            self.makedirs(path, exist_ok=True, _check=False)
        try:
            it = scandir(local_path)
        except NotADirectoryError:
            return self.upload(
                local_path, 
                joinpath(path, ospath.basename(local_path)), 
                overwrite_or_ignore=overwrite_or_ignore, 
                _check=False, 
            )
        else:
            if not no_root:
                path = joinpath(path, ospath.basename(local_path))
                self.makedirs(path, exist_ok=True, _check=False)
            for entry in it:
                if entry.is_dir():
                    self.upload_tree(
                        entry.path, 
                        joinpath(path, entry.name), 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                        _check=False, 
                    )
                else:
                    self.upload(
                        entry.path, 
                        joinpath(path, entry.name), 
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
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        if not max_depth:
            return
        if isinstance(top, DuPanPath):
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_attr(top, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if not ls:
            yield top, [], []
            return
        dirs: list[str] = []
        files: list[str] = []
        for attr in ls:
            if attr["isdir"]:
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
                _check=False, 
            )
        if yield_me and topdown:
            yield top, dirs, files

    def walk_attr(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        if not max_depth:
            return
        if isinstance(top, DuPanPath):
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_attr(top, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if not ls:
            yield top, [], []
            return
        dirs: list[dict] = []
        files: list[dict] = []
        for attr in ls:
            if attr["isdir"]:
                dirs.append(attr)
            else:
                files.append(attr)
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        yield_me = min_depth <= 0
        if yield_me and topdown:
            yield top, dirs, files
        for dir_ in dirs:
            yield from self.walk_attr(
                dir_["path"], 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if yield_me and topdown:
            yield top, dirs, files

    def walk_path(
        self, 
        /, 
        top: str | PathLike[str] = "", 
        topdown: bool = True, 
        min_depth: int = 0, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
        _check: bool = True, 
    ) -> Iterator[tuple[str, list[DuPanPath], list[DuPanPath]]]:
        if not max_depth:
            return
        if isinstance(top, DuPanPath):
            top = top.path
        elif _check:
            top = self.abspath(top)
        top = cast(str, top)
        try:
            ls = self.listdir_path(top, _check=False)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if not ls:
            yield top, [], []
            return
        dirs: list[DuPanPath] = []
        files: list[DuPanPath] = []
        for path in ls:
            if path.is_dir():
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
                dir_.path, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                _check=False, 
            )
        if yield_me and not topdown:
            yield top, dirs, files

    def write_bytes(
        self, 
        /, 
        path: str | PathLike[str], 
        data: bytes | bytearray | memoryview | SupportsRead[bytes] = b"", 
        _check: bool = True, 
    ):
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = BytesIO(data)
        return self.upload(data, path, overwrite_or_ignore=True, _check=_check)

    def write_text(
        self, 
        /, 
        path: str | PathLike[str], 
        text: str = "", 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
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
        return self.write_bytes(path, bio, _check=_check)

    cd  = chdir
    cp  = copy
    pwd = getcwd
    ls  = listdir
    la  = listdir_attr
    ll  = listdir_path
    mv  = move
    rm  = remove


# TODO: 上传下载使用百度网盘的openapi，直接使用 alist 已经授权的 token
# TODO: 百度网盘转存时，需要保持相对路径
# TODO: 等待 filemanager 任务完成
# TODO: 分享、回收站、分享转存、群分享转存等的接口封装
