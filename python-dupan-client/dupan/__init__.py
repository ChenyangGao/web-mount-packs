#!/usr/bin/env python3
# encoding: utf-8

__version__ = (0, 0, 0)
__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["Error", "DuPanClient", "DuPanShareList"]

import errno

# from base64 import b64encode
from collections.abc import Callable, Mapping
from functools import cached_property
from json import dumps, loads
from platform import system
from re import compile as re_compile, escape as re_escape, Pattern
from subprocess import run
from threading import Thread
from typing import cast, Any, AnyStr, Final, Optional, TypedDict
from urllib.parse import parse_qsl, urlsplit, unquote
from uuid import uuid4

from ddddocr import DdddOcr # type: ignore
from qrcode import QRCode # type: ignore
from requests import Session, get
from requests.cookies import create_cookie


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


class VCodeResult(TypedDict, total=True):
    vcode: str
    vcode_str: str


def recognize_vcode(_ocr=DdddOcr(beta=True), /) -> VCodeResult:
    "识别百度网盘的验证码"
    url = "https://pan.baidu.com/api/getcaptcha?prod=shareverify&web=1&DuPanClienttype=0&bdstoken="
    while True:
        resp = get(url).json()
        for i in range(10):
            res = _ocr.classification(get(resp["vcode_img"]).content)
            if len(res) == 4 and res.isalnum():
                return {"vcode": res, "vcode_str": resp["vcode_str"]}


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


def text_to_dict(
    s: AnyStr, 
    /, 
    kv_sep: AnyStr | Pattern[AnyStr], 
    entry_sep: AnyStr | Pattern[AnyStr], 
) -> dict[AnyStr, AnyStr]:
    if isinstance(kv_sep, (str, bytes, bytearray)):
        search_kv_sep = re_compile(re_escape(kv_sep)).search
    else:
        search_kv_sep = kv_sep.search
    if isinstance(entry_sep, (str, bytes, bytearray)):
        search_entry_sep = re_compile(re_escape(entry_sep)).search
    else:
        search_entry_sep = entry_sep.search
    d: dict[AnyStr, AnyStr] = {}
    start = 0
    length = len(s)
    while start < length:
        match = search_kv_sep(s, start)
        if match is None:
            break
        l, r = match.span()
        key = s[start:l]
        match = search_entry_sep(s, r)
        if match is None:
            d[key] = s[r:]
            break
        l, start = match.span()
        d[key] = s[r:l]
    return d


def headers_str_to_dict(
    cookies: str, 
    /, 
    kv_sep: str | Pattern[str] = ": ", 
    entry_sep: str | Pattern[str] = "\n", 
) -> dict[str, str]:
    return text_to_dict(cookies.strip(), kv_sep, entry_sep)


def cookies_str_to_dict(
    cookies: str, 
    /, 
    kv_sep: str | Pattern[str] = re_compile(r"\s*=\s*"), 
    entry_sep: str | Pattern[str] = re_compile(r"\s*;\s*"), 
) -> dict[str, str]:
    return text_to_dict(cookies.strip(), kv_sep, entry_sep)


class Error(OSError):

    @classmethod
    def check(cls, resp, /):
        if resp["errno"]:
            raise cls(resp)
        return resp


class DuPanClient:

    def __init__(self, cookie: Optional[str] = None):
        session = self.session = Session()
        session.headers["User-Agent"] = "pan.baidu.com"
        if not cookie or "BDUSS=" not in cookie:
            self.login_with_qrcode()
            self.request("https://pan.baidu.com/disk/main")
        else:
            self.cookie = cookie
        resp = Error.check(self.get_gettemplatevariable("bdstoken"))
        self.bdstoken = resp["result"]["bdstoken"]
        #self.logid = b64encode(self.session.cookies["BAIDUID"].encode("ascii")).decode("ascii")

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
            url = url = f"https://wappass.baidu.com/wp/?qrlogin&error=0&sign={sign}&cmd=login&lp=pc&tpl=netdisk&adapter=3&qrloginfrom=pc"
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
    def cookie(self):
        cookies = self.session.cookies.get_dict()
        return "; ".join(f"{key}={val}" for key, val in cookies.items())

    @cookie.setter
    def cookie(self, cookie, /):
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
    def list_app_version():
        url = "https://pan.baidu.com/disk/cmsdata?DuPanClienttype=0&web=1&do=DuPanClient"
        return get(url).json()

    def get_qrcode(self, /, gid):
        return self.request(
            "https://passport.baidu.com/v2/api/getqrcode", 
            params={
                "apiver": "v3", 
                "tpl": "netdisk", 
                "lp": "pc", 
                "qrloginfrom": "pc", 
                "gid": gid, 
            }
        )

    def get_qrcode_status(self, /, gid, channel_id):
        "获取扫码状态"
        return self.request(
            "https://passport.baidu.com/channel/unicast", 
            params={
                "apiver": "v3", 
                "tpl": "netdisk", 
                "gid": gid, 
                "channel_id": channel_id, 
            }
        )

    def get_gettemplatevariable(
        self, 
        /, 
        payload: str | list | tuple | dict, 
    ) -> dict:
        api = "https://pan.baidu.com/api/gettemplatevariable"
        if isinstance(payload, str):
            payload = {"fields": dumps([payload], separators=(",", ":"))}
        elif isinstance(payload, (tuple, list)):
            payload = {"fields": dumps(payload, separators=(",", ":"))}
        return self.request(api, params=payload)

    def listdir(
        self, 
        /, 
        payload: str | dict = "/", 
    ) -> dict:
        """罗列目录中的文件列表
        payload:
            dir: str = ""
            num: int = 100
            page: int = 1
            order: str = "time"
            desc: 0 | 1 = 1
            DuPanClienttype: int = 0
            web: int = 1
        """
        api = "https://pan.baidu.com/api/list"
        if isinstance(payload, str):
            payload = {"num": 100, "page": 1, "order": "time", "desc": 1, "DuPanClienttype": 0, "web": 1, "dir": payload}
        else:
            payload = {"num": 100, "page": 1, "order": "time", "desc": 1, "DuPanClienttype": 0, "web": 1, **payload}
        return self.request(api, params=payload)

    def makedir(
        self, 
        /, 
        payload: str | dict, 
    ) -> dict:
        api = "https://pan.baidu.com/api/create"
        params = {
            "a": "commit", 
            "bdstoken": self.bdstoken, 
            "DuPanClienttype": 0, 
            "web": 1, 
        }
        if isinstance(payload, str):
            payload = {"isdir": 1, "block_list": "[]", "path": payload}
        else:
            payload = {"isdir": 1, "block_list": "[]", **payload}
        return self.request(api, "POST", params=params, data=payload)

    def filemanager(
        self, 
        /, 
        params: str | dict, 
        data: str | list | tuple | dict, 
    ) -> dict:
        api = "https://pan.baidu.com/api/filemanager"
        if isinstance(params, str):
            params = {"opera": params}
        params = {
            "async": 2, 
            "onnest": "fail", 
            "bdstoken": self.bdstoken, 
            "newVerify": 1, 
            "DuPanClienttype": 0, 
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
        return self.request(api, "POST", params=params, data=data)

    def copy(
        self, 
        /, 
        payload: list | tuple | dict, 
    ) -> dict:
        return self.filemanager("copy", payload)

    def delete(
        self, 
        /, 
        payload: str | list | tuple | dict, 
    ) -> dict:
        return self.filemanager("delete", payload)

    def move(
        self, 
        /, 
        payload: list | tuple | dict, 
    ) -> dict:
        return self.filemanager("move", payload)

    def rename(
        self, 
        /, 
        payload: list | tuple | dict, 
    ) -> dict:
        return self.filemanager("rename", payload)

    def taskquery(
        self, 
        /, 
        payload: int | str | dict, 
    ) -> dict:
        api = "https://pan.baidu.com/share/taskquery"
        if isinstance(payload, (int, str)):
            payload = {"DuPanClienttype": 0, "web": 1, "taskid": payload}
        return self.request(api, params=payload)

    def transfer(
        self, 
        /, 
        url, 
        params: dict, 
        data: int | str | list | tuple | dict, 
    ) -> dict:
        api = "https://pan.baidu.com/share/transfer"
        params = {
            "ondup": "overwrite", 
            "async": 1, 
            "bdstoken": self.bdstoken, 
            "web": 1, 
            "DuPanClienttype": 0, 
            **params, 
        }
        if isinstance(data, (int, str)):
            data = {"fsidlist": "[%s]" % data, "path": "/"}
        elif isinstance(data, (list, tuple)):
            data = {"fsidlist": "[%s]" % ",".join(map(str, data)), "path": "/"}
        elif isinstance(data["fsidlist"], (list, tuple)):
            data["fsidlist"] = "[%s]" % ",".join(map(str, data["fsidlist"]))
        return self.request(api, "POST", params=params, data=data, headers={"Referer": url})


class DuPanShareList:

    def __init__(self, url):
        if url.startswith(("http://", "https://")):
            shorturl, password = self._extract_from_url(url)
        else:
            shorturl = url
            password = ""
        url = self.url = f"https://pan.baidu.com/share/init?surl={shorturl}"
        self.shorturl = shorturl
        self.password = password
        session = self.session = Session()
        session.headers["Referer"] = url

    @staticmethod
    def _extract_from_url(url: str, /) -> tuple[str, str]:
        urlp = urlsplit(url)
        path = urlp.path
        query = dict(parse_qsl(urlp.query))
        if path == "/share/init":
            shorturl = query["surl"]
        elif path.startswith("/s/1"):
            shorturl = path.removeprefix("/s/1")
        else:
            raise ValueError("invalid share url")
        pwd = query.get("pwd", "")
        return shorturl, pwd

    @staticmethod
    def _extract_index_data(
        content: bytes, 
        _search=re_compile(br"locals\.mset\((.*?)\);").search, 
        /, 
    ) -> dict:
        match = _search(content)
        if match is None:
            raise OSError("没有提取到页面相关数据，可能是页面加载失败、被服务器限制访问、链接失效、分享被取消等原因")
        return loads(match[1])

    @cached_property
    def root(self, /):
        self.listdir_index()
        return self.__dict__["root"]

    @cached_property
    def share_id(self, /):
        self.listdir_index()
        return self.__dict__["share_id"]

    @cached_property
    def share_uk(self, /):
        self.listdir_index()
        return self.__dict__["share_uk"]

    def verify(self, /) -> str:
        api = "https://pan.baidu.com/share/verify"
        params: dict[str, int | str] = {"surl": self.shorturl, "web": 1, "DuPanClienttype": 0}
        data = {"pwd": self.password}
        session = self.session
        while True:
            with session.post(api, params=params, data=data) as resp:
                resp.raise_for_status()
                json = resp.json()
                errno = json["errno"]
                if not errno:
                    break
                if errno == -62:
                    data.update(cast(dict[str, str], recognize_vcode()))
                else:
                    raise OSError(json)
        randsk = json["randsk"]
        session.cookies.set("BDCLND", randsk, domain=".baidu.com")
        self.__dict__["randsk"] = unquote(randsk)
        return randsk

    def listdir_index(self, /) -> dict:
        url = self.url
        password = self.password
        session = self.session
        while True:
            with session.get(url) as resp:
                resp.raise_for_status()
                content = resp.content
                data = self._extract_index_data(content)
                if b'"verify-form"' in content:
                    if not password:
                        raise OSError("需要密码")
                    self.verify()
                else:
                    file_list = data["file_list"]
                    if file_list is None:
                        raise OSError("没有找到下载文件，可能是链接失效、分享被取消等原因")
                    if file_list:
                        root = file_list[0]["path"].rsplit("/", 1)[0]
                    else:
                        root = "/"
                    self.__dict__.update(
                        root = root, 
                        share_uk = data["share_uk"], 
                        share_id = data["shareid"], 
                    )
                    return file_list

    def listdir(self, dir="/", page=1, num=0):
        if dir in ("", "/"):
            data = self.listdir_index()
        if not hasattr(self, "share_uk"):
            self.listdir_index()
        if not dir.startswith("/"):
            dir = self.root + "/" + dir
        api = "https://pan.baidu.com/share/list"
        params = {
            "uk": self.share_uk, 
            "shareid": self.share_id, 
            "order": "other", 
            "desc": 1, 
            "showempty": 0, 
            "DuPanClienttype": 0, 
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
                    return ls_all
                params["page"] += 1
        if page > 0:
            params["page"] = page
        if num < 100:
            params["num"] = 100
        return Error.check(session.get(api, params=params).json())["list"]


# TODO: 上传下载使用百度网盘的openapi，直接使用 alist 已经授权的 token

