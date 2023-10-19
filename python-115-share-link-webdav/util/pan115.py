#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["LoginError", "BadRequest", "Pan115Client", "Pan115ShareLinkFileSystem", "HTTPFileReader"]
__requirements__ = ["pycryptodome", "qrcode", "requests"]

from base64 import b64decode, b64encode
from collections import deque
from copy import deepcopy
from datetime import datetime
from http.cookiejar import Cookie, CookieJar
from io import RawIOBase, BufferedReader, TextIOWrapper, DEFAULT_BUFFER_SIZE
from json import dumps, loads
from posixpath import dirname, join as joinpath, normpath
from re import compile as re_compile
from time import time
from typing import cast, Callable, Final, Iterable, Iterator, Optional
from urllib.parse import parse_qsl, urlparse
from warnings import warn

from requests.cookies import create_cookie
from requests.exceptions import Timeout
from requests.models import Response
from requests.sessions import Session
from urllib3.exceptions import ProtocolError
from Crypto import Random
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.PublicKey import RSA
from Crypto.Util.number import bytes_to_long, long_to_bytes

import qrcode # type: ignore


Response.__del__ = Response.close # type: ignore

CRE_SHARE_LINK: Final = re_compile(r"/s/(?P<share_code>\w+)(\?password=(?P<receive_code>\w+))?")
APP_VERSION: Final = "99.99.99.99"
G_key_l: Final = bytes((
    0x78, 0x06, 0xad, 0x4c, 0x33, 0x86, 0x5d, 0x18, 0x4c, 0x01, 0x3f, 0x46, 
))
G_kts: Final = bytes((
    0xf0, 0xe5, 0x69, 0xae, 0xbf, 0xdc, 0xbf, 0x8a, 0x1a, 0x45, 0xe8, 0xbe, 0x7d, 0xa6, 0x73, 0xb8, 
    0xde, 0x8f, 0xe7, 0xc4, 0x45, 0xda, 0x86, 0xc4, 0x9b, 0x64, 0x8b, 0x14, 0x6a, 0xb4, 0xf1, 0xaa, 
    0x38, 0x01, 0x35, 0x9e, 0x26, 0x69, 0x2c, 0x86, 0x00, 0x6b, 0x4f, 0xa5, 0x36, 0x34, 0x62, 0xa6, 
    0x2a, 0x96, 0x68, 0x18, 0xf2, 0x4a, 0xfd, 0xbd, 0x6b, 0x97, 0x8f, 0x4d, 0x8f, 0x89, 0x13, 0xb7, 
    0x6c, 0x8e, 0x93, 0xed, 0x0e, 0x0d, 0x48, 0x3e, 0xd7, 0x2f, 0x88, 0xd8, 0xfe, 0xfe, 0x7e, 0x86, 
    0x50, 0x95, 0x4f, 0xd1, 0xeb, 0x83, 0x26, 0x34, 0xdb, 0x66, 0x7b, 0x9c, 0x7e, 0x9d, 0x7a, 0x81, 
    0x32, 0xea, 0xb6, 0x33, 0xde, 0x3a, 0xa9, 0x59, 0x34, 0x66, 0x3b, 0xaa, 0xba, 0x81, 0x60, 0x48, 
    0xb9, 0xd5, 0x81, 0x9c, 0xf8, 0x6c, 0x84, 0x77, 0xff, 0x54, 0x78, 0x26, 0x5f, 0xbe, 0xe8, 0x1e, 
    0x36, 0x9f, 0x34, 0x80, 0x5c, 0x45, 0x2c, 0x9b, 0x76, 0xd5, 0x1b, 0x8f, 0xcc, 0xc3, 0xb8, 0xf5, 
))
RSA_PUBLIC_KEY: Final = RSA.construct((
    0x8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683, 
    0x10001, 
))


class LoginError(Exception):
    ...


class BadRequest(ValueError):
    ...


def check_get(resp: dict, exc_cls: type[BaseException] = BadRequest):
    if resp["state"]:
        return resp.get("data")
    raise exc_cls(resp)


def text_to_dict(s: str, /, entry_sep: str = "\n", kv_sep: str = "=") -> dict[str, str]:
    return dict(
        map(str.strip, e.split(kv_sep, 1)) # type: ignore
        for e in s.strip(entry_sep).split(entry_sep)
    )


def console_qrcode(text: str):
    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.print_ascii(tty=True)


def normattr(info: dict) -> dict:
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
        "is_dir": is_dir, 
        "size": info.get("s"), 
        "id": int(fid), 
        "parent_id": int(parent_id), 
        "sha1": info.get("sha"), 
    }
    if "te" in info:
        info2.update({
            "etime": datetime.fromtimestamp(int(info["te"])), 
            "utime": datetime.fromtimestamp(int(info["tu"])), 
            "ptime": datetime.fromtimestamp(int(info["tp"])), 
            "open_time": datetime.fromtimestamp(int(info["to"])), 
        })
    elif "t" in info:
        info2["time"] = datetime.fromtimestamp(int(info["t"]))
    # if "pc" in info:
    #     info2["pick_code"] = info["pc"]
    # if "m" in info:
    #     info2["star"] = bool(info["m"])
    #info2["raw"] = info
    return info2


class lazyproperty:

    def __init__(self, func):
        self.func = func
        self.name = func.__name__

    def __get__(self, instance, type):
        if instance is None:
            return self
        value = self.func(instance)
        setattr(instance, self.name, value)
        return value


class Pan115RSACipher:

    def __init__(self, /):
        rsa_key_size = 16
        self.rand_key = Random.new().read(rsa_key_size)
        self.key = __class__.gen_key(self.rand_key, 4)

    @staticmethod
    def gen_key(rand_key: bytes, sk_len: int = 4) -> bytes:
        xor = __class__.xor # type: ignore
        xor_key = bytearray()
        if rand_key and sk_len > 0:
            length = sk_len * (sk_len - 1)
            index = 0
            for i in range(sk_len):
                x = (rand_key[i] + G_kts[index]) & 0xff
                xor_key.append(G_kts[length] ^ x)
                length -= sk_len
                index += sk_len
        return xor_key

    @staticmethod
    def xor(src: bytes, key: bytes) -> bytes:
        secret = bytearray()
        pad = len(src) % 4
        if pad:
            secret.extend(c ^ k for c, k in zip(src[:pad], key[:pad]))
            src = src[pad:]
        key_len = len(key)
        secret.extend(c ^ key[i % key_len] for i, c in enumerate(src))
        return secret

    def encode(self, text: bytes | str, /) -> str:
        if isinstance(text, str):
            text = bytes(text, "utf-8")
        xor = __class__.xor # type: ignore
        rsa_block_size = 128
        rsa_encrypt_block_size = rsa_block_size - 11
        tmp = xor(text, self.key)[::-1]
        xor_text = self.rand_key + xor(tmp, G_key_l)
        encrypt = PKCS1_v1_5.new(RSA_PUBLIC_KEY).encrypt
        cipher_text = bytearray()
        for i in range(-(-len(xor_text)//rsa_encrypt_block_size)):
            cipher_text += encrypt(xor_text[i*rsa_encrypt_block_size:(i+1)*rsa_encrypt_block_size])
        return b64encode(cipher_text).decode("ascii")

    def decode(self, cipher_text: bytes | str, /) -> str:
        xor = __class__.xor # type: ignore
        rsa_key_size = 16
        rsa_block_size = 128
        cipher_text = b64decode(cipher_text)
        block_count = len(cipher_text) // rsa_block_size
        text = bytearray()
        for i in range(block_count):
            n = bytes_to_long(cipher_text[i*rsa_block_size:(i+1)*rsa_block_size])
            m = pow(n, RSA_PUBLIC_KEY.e, RSA_PUBLIC_KEY.n)
            b = long_to_bytes(m)
            text += b[b.index(0)+1:]
        rand_key = text[0:rsa_key_size]
        text = text[rsa_key_size:]
        key_l = __class__.gen_key(rand_key, 12) # type: ignore
        tmp = xor(text, key_l)[::-1]
        return xor(tmp, self.key)


class Pan115Client:

    def __init__(self, /, cookie=None):
        self.__session = session = Session()
        session.headers["User-Agent"] = f"Mozilla/5.0 115disk/{APP_VERSION}"
        need_login = True
        if cookie:
            self.cookie = cookie
            resp = self.user_info()
            need_login = not resp["state"]
        if need_login:
            cookie = self.login_with_qrcode()["data"]["cookie"]
            self.cookie = cookie
            resp = self.user_info()
            if not resp["state"]:
                raise LoginError("bad cookie")
        self.userid = str(resp["data"]["user_id"])
        self.rsa_encoder = Pan115RSACipher()

    def __del__(self, /):
        self.close()

    def close(self, /):
        self.__session.close()

    @property
    def cookie(self, /) -> str:
        return self.__cookie

    @cookie.setter
    def cookie(self, cookie: str | dict | Iterable[dict | Cookie] | CookieJar, /):
        if isinstance(cookie, str):
            cookie = text_to_dict(cookie, entry_sep=";")
        cookiejar = self.__session.cookies
        cookiejar.clear()
        if isinstance(cookie, dict):
            for key in ("UID", "CID", "SEID"):
                cookiejar.set_cookie(
                    create_cookie(key, cookie[key], domain=".115.com", rest={'HttpOnly': True})
                )
        else:
            cookiejar.update(cookie)
        cookies = cookiejar.get_dict()
        self.__cookie = "; ".join(f"{key}={cookies[key]}" for key in ("UID", "CID", "SEID"))

    @property
    def session(self, /) -> Session:
        return self.__session

    def login_with_qrcode(self, /, **request_kwargs) -> dict:
        qrcode_token = self.login_qrcode_token(**request_kwargs)["data"]
        qrcode = qrcode_token.pop("qrcode")
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
        return self.login_qrcode_result(qrcode_token["uid"], **request_kwargs)

    def request(self, api: str, /, method: str = "GET", *, parse: bool | Callable = False, **request_kwargs):
        request_kwargs["stream"] = True
        resp = self.__session.request(method, api, **request_kwargs)
        resp.raise_for_status()
        if callable(parse):
            return parse(resp.content)
        if parse:
            if request_kwargs.get("stream"):
                return resp
            else:
                content_type = resp.headers.get("Content-Type", "")
                if content_type == "application/json" or content_type.startswith("application/json;"):
                    return resp.json()
                elif content_type.startswith("text/"):
                    return resp.text
                return resp.content
        return resp

    ########## Account API ##########

    def login_check(self, /, **request_kwargs) -> dict:
        api = "https://passportapi.115.com/app/1.0/web/1.0/check/sso/"
        return self.request(api, parse=loads, **request_kwargs)

    def login_qrcode_status(self, /, payload: dict, **request_kwargs) -> dict:
        api = "https://qrcodeapi.115.com/get/status/"
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def login_qrcode_result(self, /, uid: int | str, **request_kwargs) -> dict:
        api = "https://passportapi.115.com/app/1.0/web/1.0/login/qrcode/"
        return self.request(api, "POST", data={"account": uid, "app": "web"}, parse=loads, **request_kwargs)

    def login_qrcode_token(self, /, **request_kwargs) -> dict:
        api = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
        return self.request(api, parse=loads, **request_kwargs)

    def logout(self, /, **request_kwargs) -> None:
        api = "https://passportapi.115.com/app/1.0/web/1.0/logout/logout/"
        self.request(api, **request_kwargs)

    def login_status(self, /, **request_kwargs) -> dict:
        api = "https://my.115.com/?ct=guide&ac=status"
        return self.request(api, parse=loads, **request_kwargs)

    def user_info(self, /, **request_kwargs) -> dict:
        api = "https://my.115.com/?ct=ajax&ac=nav"
        return self.request(api, parse=loads, **request_kwargs)

    def user_info2(self, /, **request_kwargs) -> dict:
        api = "https://my.115.com/?ct=ajax&ac=get_user_aq"
        return self.request(api, parse=loads, **request_kwargs)

    ########## Share API ##########

    def share_snap(self, payload: dict, /, **request_kwargs) -> dict:
        """获取分享链接的某个文件夹中的文件和子文件夹的列表（包含详细信息）
        GET https://webapi.115.com/share/snap
        payload:
            - share_code: str
            - receive_code: str
            - offset int = 0
            - limit: int = 100
            - cid: int | str = 0 
        }
        """
        api = "https://webapi.115.com/share/snap"
        payload = {"offset": 0, "limit": 100, "cid": 0, **payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def share_downlist(self, payload: dict, /, **request_kwargs) -> dict:
        """获取分享链接的某个文件夹中可下载的文件的列表（只含文件，不含文件夹，任意深度，简略信息）
        GET https://proapi.115.com/app/share/downlist
        payload:
            - share_code: str
            - receive_code: str
            - cid: int | str
        """
        api = "https://proapi.115.com/app/share/downlist"
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def share_receive(self, payload: dict, /, **request_kwargs) -> dict:
        """接收分享链接的某些文件或文件夹
        POST https://webapi.115.com/share/receive
        payload:
            - share_code: str
            - receive_code: str
            - file_id: int | str             # 有多个时，用逗号,分隔
            - user_id: int | str = <default> # 有默认值，可以不传
            - cid: int | str = 0             # 这是你网盘的文件夹 cid
        """
        api = "https://webapi.115.com/share/receive"
        payload = {"cid": 0, "uid": self.userid, **payload}
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def share_download_url(self, payload: dict, /, **request_kwargs) -> dict:
        """获取分享链接中某个文件的下载链接
        POST https://proapi.115.com/app/share/downurl
        payload:
            - share_code: str
            - receive_code: str
            - file_id: int | str
        """
        api = "https://proapi.115.com/app/share/downurl"
        def parse(content):
            resp = loads(content)
            if resp["state"]:
                resp["data"] = loads(encoder.decode(resp["data"]))
            return resp
        encoder = self.rsa_encoder
        data = encoder.encode(dumps(payload))
        return self.request(api, "POST", data={"data": data}, parse=parse, **request_kwargs)

    ...


class Pan115ShareLinkFileSystem:

    def __init__(self, client: Pan115Client, /, share_link: str, path: str = "/"):
        self._client = client
        m = CRE_SHARE_LINK.search(share_link)
        if m is None:
            raise ValueError("not a valid 115 share link")
        self._share_link = share_link
        self._params = {"share_code": m["share_code"], "receive_code": m["receive_code"] or ""}
        self._path_to_id = {"/": 0}
        self._id_to_path = {0: "/"}
        self._id_to_attr: dict[int, dict] = {}
        self._id_to_url: dict[int, dict] = {}
        self._pid_to_attrs: dict[int, list[dict]]  = {}
        self._full_loaded = False
        self._path = "/" + normpath(path).rstrip("/")

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(client={self._client!r}, share_link={self._share_link!r}, path={self._path!r})"

    def _attr(self, id_or_path: int | str, /) -> dict:
        if isinstance(id_or_path, str):
            return self._attr_path(id_or_path)
        else:
            return self._attr(id_or_path)

    def _attr_id(self, id: int, /) -> dict:
        if id == 0:
            raise PermissionError(1, "the attributes of the root are not readable")
        if id in self._id_to_attr:
            return self._id_to_attr[id]
        if self._full_loaded:
            raise FileNotFoundError(2, f"no such cid/file_id: {id!r}")
        dq = deque((0,))
        while dq:
            pid = dq.popleft()
            for attr in self._listdir(pid):
                if attr["id"] == id:
                    return attr
                if attr["is_dir"]:
                    dq.append(attr["id"])
        self._full_loaded = True
        raise FileNotFoundError(2, f"no such cid/file_id: {id!r}")

    def _attr_path(self, path: str, /) -> dict:
        path = self.abspath(path)
        if path == "/":
            raise PermissionError(1, "the attributes of the root are not readable")
        if path in self._path_to_id:
            id = self._path_to_id[path]
            return self._id_to_attr[id]
        if self._full_loaded:
            raise FileNotFoundError(2, f"no such path: {path!r}")
        ppath = dirname(path)
        ls_ppath = [ppath]
        while ppath not in self._path_to_id:
            ppath = dirname(ppath)
            ls_ppath.append(ppath)
        try:
            for ppath in reversed(ls_ppath):
                pid = self._path_to_id[ppath]
                attrs = self._listdir(pid)
                if not attrs or attrs[0]["id"] in self._id_to_path:
                    raise FileNotFoundError(2, f"no such path: {path!r}")
                for attr in attrs:
                    psid = attr["id"]
                    pspath = joinpath(ppath, attr["name"])
                    self._path_to_id[pspath] = psid
                    self._id_to_path[psid] = pspath
            id = self._path_to_id[path]
            return self._id_to_attr[id]
        except KeyError:
            raise FileNotFoundError(2, f"no such path: {path!r}")

    def _listdir(self, id_or_path: int | str = "", /) -> list[dict]:
        if isinstance(id_or_path, str):
            if id_or_path == "":
                id = self._path_to_id[self._path]
            elif self.abspath(id_or_path) == "/":
                id = 0
            else:
                id = self._attr_path(id_or_path)["id"]
        else:
            id = id_or_path
        if id in self._pid_to_attrs:
            return self._pid_to_attrs[id]
        if self._full_loaded:
            raise FileNotFoundError(2, f"no such cid/file_id: {id!r}")
        params = {**self._params, "cid": id, "offset": 0, "limit": 100}
        data = check_get(self.client.share_snap(params))
        ls = list(map(normattr, data["list"]))
        count = data["count"]
        if count > 100:
            for offset in range(100, count, 100):
                params["offset"] = offset
                data = check_get(self.client.share_snap(params))
                ls.extend(map(normattr, data["list"]))
        self._id_to_attr.update((attr["id"], attr) for attr in ls)
        self._pid_to_attrs[id] = ls
        return ls

    def abspath(self, path: str, /) -> str:
        return normpath(joinpath(self._path, path))

    def attr(self, id_or_path: int | str) -> dict:
        return deepcopy(self._attr(id_or_path))

    def chdir(self, path: str = "/", /):
        if path == "":
            return
        path = self.abspath(path)
        if path == "/":
            self._path = "/"
        else:
            if self._attr_path(path)["is_dir"]:
                self._path = path

    @property
    def client(self, /) -> Pan115Client:
        return self._client

    def exists(self, id_or_path: int | str = 0, /):
        try:
            self._attr(id_or_path)
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            return True

    def getcwd(self, /) -> str:
        return self._path

    def get_download_url(self, id_or_path: int | str = 0, /) -> str:
        id: int
        if isinstance(id_or_path, str):
            id = self._attr_path(id_or_path)["id"]
        else:
            id = id_or_path
        if id in self._id_to_url and time() + 60 * 30 < self._id_to_url[id]["expire"]:
            return self._id_to_url[id]["url"]
        payload = {**self._params, "file_id": id}
        url = self.client.share_download_url(payload)["data"]["url"]["url"]
        self._id_to_url[id] = {"url": url, "expire": int(parse_qsl(urlparse(url).query)[0][1])}
        return url

    def isdir(self, id_or_path: int | str = 0, /) -> bool:
        try:
            return self._attr(id_or_path)["is_dir"]
        except FileNotFoundError:
            return False
        except PermissionError:
            return True

    def isfile(self, id_or_path: int | str = 0, /) -> bool:
        try:
            return not self._attr(id_or_path)["is_dir"]
        except FileNotFoundError:
            return False
        except PermissionError:
            return False

    def iterdir(
        self, 
        id_or_path: int | str = "", 
        /, 
        topdown: bool = True, 
        max_depth: int = 1, 
        predicate: Optional[Callable[[str, dict], Optional[bool]]] = None, 
        onerror: Optional[bool] = None, 
    ) -> Iterator[tuple[str, dict]]:
        if not max_depth:
            return
        try:
            ls = self._listdir(id_or_path)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if isinstance(id_or_path, str):
            top = self.abspath(id_or_path)
        else:
            top = self._id_to_path[id_or_path]
        if max_depth > 0:
            max_depth -= 1
        for attr in ls:
            path = joinpath(top, attr["name"])
            yield_me = True
            if predicate:
                pred = predicate(path, attr)
                if pred is None:
                    continue
                yield_me = pred
            if topdown and yield_me:
                yield path, attr
            if attr["is_dir"]:
                yield from self.iterdir(
                    path, 
                    topdown=topdown, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                )
            if not topdown and yield_me:
                yield path, attr

    def listdir(self, id_or_path: int | str = 0, /) -> list[str]:
        return [attr["name"] for attr in self._listdir(id_or_path)]

    def listdir_attr(self, id_or_path: int | str = 0, /) -> list[dict]:
        return deepcopy(self._listdir(id_or_path))

    def open(
        self, 
        id_or_path: int | str, 
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
        if mode not in ("r", "rt", "tr"):
            raise ValueError(f"invalid (or unsupported) mode: {orig_mode!r}")
        url = self.get_download_url(id_or_path)
        if buffering is None:
            if open_text_mode:
                buffering = DEFAULT_BUFFER_SIZE
            else:
                buffering = 0
        if buffering == 0:
            if open_text_mode:
                raise ValueError("can't have unbuffered text I/O")
            return HTTPFileReader(url, self.client.request)
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
        raw = HTTPFileReader(url, self.client.request)
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

    path = property(getcwd, chdir)

    def receive(self, ids: int | str | Iterable[int | str], cid=0):
        if isinstance(ids, (int, str)):
            file_id = str(ids)
        else:
            file_id = ",".join(map(str, ids))
            if not file_id:
                raise ValueError("no id (to file) to transfer")
        payload = {**self._params, "file_id": file_id, "cid": cid}
        check_get(self.client.share_receive(payload))

    @lazyproperty
    def shareinfo(self, /) -> dict:
        return check_get(self.client.share_snap({**self._params, "limit": 1}))["shareinfo"]

    @property
    def share_link(self, /) -> str:
        return self._share_link

    def walk(
        self, 
        id_or_path: int | str = "", 
        /, 
        topdown: bool = True, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        if not max_depth:
            return
        try:
            ls = self._listdir(id_or_path)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if isinstance(id_or_path, str):
            top = self.abspath(id_or_path)
        else:
            top = self._id_to_path[id_or_path]
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
                topdown=topdown, 
                max_depth=max_depth, 
                onerror=onerror, 
            )
        if not topdown:
            yield top, dirs, files

    def walk_attr(
        self, 
        id_or_path: int | str = "", 
        /, 
        topdown: bool = True, 
        max_depth: int = -1, 
        onerror: None | bool | Callable = None, 
    ) -> Iterator[tuple[str, list[dict], list[dict]]]:
        if not max_depth:
            return
        try:
            ls = self._listdir(id_or_path)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        if isinstance(id_or_path, str):
            top = self.abspath(id_or_path)
        else:
            top = self._id_to_path[id_or_path]
        if not ls:
            yield top, [], []
            return
        dirs: list[dict] = []
        files: list[dict] = []
        for attr in ls:
            if attr["is_dir"]:
                dirs.append(attr)
            else:
                files.append(attr)
        if topdown:
            yield top, dirs, files
        if max_depth > 0:
            max_depth -= 1
        for dir_ in dirs:
            yield from self.walk_attr(
                joinpath(top, dir_["name"]), 
                topdown=topdown, 
                max_depth=max_depth, 
                onerror=onerror, 
            )
        if not topdown:
            yield top, dirs, files

    cd = chdir
    pwd = getcwd
    ls = listdir
    ll = listdir_attr


class HTTPFileReader(RawIOBase):

    def __init__(self, /, url: str, urlopen: Callable = Session().get):
        self.__resp = resp = urlopen(url, headers={"Accept-Encoding": "identity"}, stream=True)
        self.__seekable = resp.headers.get("Accept-Ranges") == "bytes"
        self.__size = int(resp.headers['Content-Length'])
        self.__file = resp.raw
        self.__url = url
        self.__urlopen: Callable = urlopen
        self.__start = 0
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
        return f"<{name}(url={self.url!r}) at {hex(id(self))}>"

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

    def isatty(self, /) -> bool:
        return False

    @property
    def mode(self, /) -> str:
        return "r"

    @property
    def name(self, /) -> str:
        return self.__url

    def read(self, size: int = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return b""
        elif size < 0:
            return self.__file.read()
        # If the connection breaks while reading, retry 5 times
        curpos = self.tell()
        e = None
        for _ in range(5):
            try:
                return self.__file.read(size)
            except ProtocolError as exc:
                if e is None:
                    e = exc
                self.reconnect(curpos)
        raise cast(BaseException, e)

    def readable(self, /) -> bool:
        return True

    def readinto(self, buffer, /) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        # If the connection breaks while reading, retry 5 times
        curpos = self.tell()
        e = None
        for _ in range(5):
            try:
                return self.__file.readinto(buffer)
            except ProtocolError as exc:
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
            except ProtocolError as exc:
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
            self.__url, 
            headers={"Accept-Encoding": "identity", "Range": "bytes=%d-" % start}, 
            stream=True, 
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
                except ProtocolError:
                    pass
            self.__resp.close()
            self.__resp = resp = self.__urlopen(
                self.__url, 
                headers={"Accept-Encoding": "identity", "Range": "bytes=%d-" % pos}, 
                stream=True, 
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

    @property
    def url(self) -> str:
        return self.__url

    def writable(self, /) -> bool:
        return False

