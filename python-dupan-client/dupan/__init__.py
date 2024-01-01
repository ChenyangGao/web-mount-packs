#!/usr/bin/env python3
# encoding: utf-8

__version__ = (0, 0, 0)
__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["Error", "DuPanClient", "DuPanShareList"]

import errno

# from base64 import b64encode
from collections.abc import deque, Callable, Mapping
from functools import cached_property, partial
from itertools import count
from json import dumps, loads
from platform import system
from re import compile as re_compile, escape as re_escape, Pattern
from subprocess import run
from threading import Thread
from typing import cast, Any, AnyStr, Final, Optional, TypedDict
from urllib.parse import parse_qsl, urlencode, urlparse, unquote
from uuid import uuid4

from ddddocr import DdddOcr # type: ignore
from lxml.html import fromstring, tostring, HtmlElement
from qrcode import QRCode # type: ignore
from requests import get, Session
from requests.cookies import create_cookie

from .util.text import cookies_str_to_dict, text_within


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
        url = "https://pan.baidu.com/disk/cmsdata?clienttype=0&web=1&do=client"
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
            clienttype: int = 0
            web: int = 1
        """
        api = "https://pan.baidu.com/api/list"
        if isinstance(payload, str):
            payload = {"num": 100, "page": 1, "order": "time", "desc": 1, "clienttype": 0, "web": 1, "dir": payload}
        else:
            payload = {"num": 100, "page": 1, "order": "time", "desc": 1, "clienttype": 0, "web": 1, **payload}
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
            "clienttype": 0, 
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
            payload = {"clienttype": 0, "web": 1, "taskid": payload}
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
            "clienttype": 0, 
            **params, 
        }
        if isinstance(data, (int, str)):
            data = {"fsidlist": "[%s]" % data, "path": "/"}
        elif isinstance(data, (list, tuple)):
            data = {"fsidlist": "[%s]" % ",".join(map(str, data)), "path": "/"}
        elif isinstance(data["fsidlist"], (list, tuple)):
            data["fsidlist"] = "[%s]" % ",".join(map(str, data["fsidlist"]))
        return self.request(api, "POST", params=params, data=data, headers={"Referer": url})

    def oauth_authorize(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        scope: str = "basic,netdisk", 
    ) -> str:
        def check(etree):
            error_msg = etree.find_class("error-msg-list")
            if error_msg:
                raise OSError(tostring(error_msg[0], encoding="utf-8").decode("utf-8").strip())
        api = "https://openapi.baidu.com/oauth/2.0/authorize"
        params = {
            "response_type": "code", 
            "client_id": client_id, 
            "redirect_uri": "oob", 
            "scope": scope, 
            "display": "popup", 
        }
        resp = self.request(api, params=params)
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
        resp = self.request(
            api, 
            "POST", 
            params=params, 
            data=urlencode(payload), 
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        etree = fromstring(resp)
        return etree.get_element_by_id("Verifier").value

    def oauth_token(
        self, 
        /, 
        client_id: str = CLIENT_ID, 
        client_secret: str = CLIENT_SECRET, 
        scope: str = "basic,netdisk", 
    ) -> dict:
        api = "https://openapi.baidu.com/oauth/2.0/token"
        params = {
            "grant_type": "authorization_code", 
            "code": self.oauth_authorize(client_id, scope), 
            "client_id": client_id, 
            "client_secret": client_secret, 
            "redirect_uri": "oob", 
        }
        return self.request(api, params=params)


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

    def __iter__(self, /):
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
            shorturl = query["surl"]
        elif path.startswith("/s/1"):
            shorturl = path.removeprefix("/s/1")
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
        self.listdir_index()
        return self.__dict__["root"]

    @cached_property
    def randsk(self, /) -> str:
        self.listdir_index()
        return unquote(self.session.cookies.get("BDCLND", ""))

    @cached_property
    def share_id(self, /):
        self.listdir_index()
        return self.__dict__["share_id"]

    @cached_property
    def share_uk(self, /):
        self.listdir_index()
        return self.__dict__["share_uk"]

    @cached_property
    def yundata(self, /):
        self.listdir_index()
        return self.__dict__["yundata"]

    def verify(self, /, use_vcode: bool = False):
        api = "https://pan.baidu.com/share/verify"
        params: dict[str, int | str] = {"surl": self.shorturl, "web": 1, "clienttype": 0}
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

    def iterdir(self, /, dir="/"):
        if dir in ("", "/"):
            yield from self.listdir_index()
            return
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
            "clienttype": 0, 
            "web": 1, 
            "page": 1, 
            "num": 100, 
            "dir": dir, 
        }
        get = self.session.get
        while True:
            ls = Error.check(get(api, params=params).json())["list"]
            yield from ls
            if len(ls) < 100:
                return
            params["page"] += 1

    def listdir_index(self, /, try_times: int = 5) -> dict:
        url = self.url
        password = self.password
        session = self.session
        if try_times <= 0:
            it = count()
        else:
            it = range(try_times)
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
                    return ls_all
                params["page"] += 1
        if page > 0:
            params["page"] = page
        if num < 100:
            params["num"] = 100
        return Error.check(session.get(api, params=params).json())["list"]


# TODO: 上传下载使用百度网盘的openapi，直接使用 alist 已经授权的 token
# TODO: 百度网盘转存时，需要保持相对路径

