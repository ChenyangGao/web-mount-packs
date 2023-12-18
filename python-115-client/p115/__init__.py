#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = [
    "P115Client", "P115Path", "P115FileSystem", "P115SharePath", "P115ShareFileSystem", 
    "P115ZipPath", "P115ZipFileSystem", "P115Offline", "P115Recyclebin"
]

import errno

from abc import ABC, abstractmethod
from base64 import b64encode
from binascii import b2a_hex
from collections import deque
from collections.abc import (
    Callable, Iterable, Iterator, ItemsView, KeysView, Mapping, MutableMapping, 
    Sequence, ValuesView, 
)
from copy import deepcopy
from datetime import datetime
from functools import cached_property, update_wrapper
from hashlib import md5, sha1
from io import BufferedReader, BytesIO, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE
from itertools import count
from json import dumps, loads
from os import fsdecode, fspath, fstat, makedirs, scandir, stat, stat_result, PathLike
from os import path as os_path
from posixpath import join as joinpath, splitext
from re import compile as re_compile, escape as re_escape
from sys import maxsize
from stat import S_IFDIR, S_IFREG
from shutil import copyfileobj, SameFileError
from time import time
from typing import (
    cast, Any, ClassVar, Final, Generic, IO, Literal, Optional, Never, Self, TypeAlias, 
    TypedDict, TypeVar, Unpack, 
)
from types import MappingProxyType
from urllib.parse import parse_qsl, quote, urlencode, urlparse
from uuid import uuid4

from requests.cookies import create_cookie
from requests.exceptions import Timeout
from requests.models import Response
from requests.sessions import Session

# TODO: 以后会去除这个依赖，自己实现对上传接口的调用，以支持异步
import oss2 # type: ignore
# NOTE: OR use `pyqrcode` instead
import qrcode # type: ignore

from .exception import AuthenticationError, BadRequest, LoginError
from .util.cipher import P115RSACipher, P115ECDHCipher, MD5_SALT
from .util.file import get_filesize, RequestsFileReader, SupportsRead, SupportsWrite
from .util.hash import file_digest
from .util.iter import cut_iter, posix_glob_translate_iter
from .util.path import basename, commonpath, dirname, escape, joins, normpath, splits
from .util.property import funcproperty
from .util.text import cookies_str_to_dict, unicode_unescape


IDOrPathType: TypeAlias = int | str | PathLike[str] | Sequence[str]
M = TypeVar("M", bound=Mapping)
P115FSType = TypeVar("P115FSType", bound="P115FileSystemBase")
P115PathType = TypeVar("P115PathType", bound="P115PathBase")


CRE_SHARE_LINK = re_compile(r"/s/(?P<share_code>\w+)(\?password=(?P<receive_code>\w+))?")
APP_VERSION: Final = "99.99.99.99"
RSA_ENCODER: Final = P115RSACipher()
ECDH_ENCODER: Final = P115ECDHCipher()

if not hasattr(Response, "__del__"):
    Response.__del__ = Response.close # type: ignore


def check_response(fn, /):
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


def normalize_info(info, keep_raw=False, **extra_data):
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
    for k1, k2 in (("te", "etime"), ("tu", "utime"), ("tp", "ptime"), ("to", "open_time"), ("t", "time")):
        if k1 in info:
            try:
                info2[k2] = datetime.fromtimestamp(int(info[k1]))
            except ValueError:
                pass
    if "pc" in info:
        info2["pick_code"] = info["pc"]
    if "m" in info:
        info2["star"] = bool(info["m"])
    if "play_long" in info:
        info2["play_long"] = info["play_long"]
    if keep_raw:
        info2["raw"] = info
    if extra_data:
        info2.update(extra_data)
    return info2


class HeadersKeyword(TypedDict):
    headers: Optional[Mapping]


class P115Client:
    session: Session
    user_id: int
    user_key: str
    cookie: str

    def __init__(self, /, cookie=None):
        ns = self.__dict__
        session = ns["session"] = Session()
        session.headers["User-Agent"] = f"Mozilla/5.0 115disk/{APP_VERSION}"
        if not cookie:
            cookie = self.login_with_qrcode()["data"]["cookie"]
        self.set_cookie(cookie)
        resp = self.upload_info()
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

    def close(self, /) -> None:
        self.session.close()

    def set_cookie(self, cookie, /):
        if isinstance(cookie, str):
            cookie = cookies_str_to_dict(cookie)
        cookiejar = self.session.cookies
        cookiejar.clear()
        if isinstance(cookie, dict):
            for key in ("UID", "CID", "SEID"):
                cookiejar.set_cookie(
                    create_cookie(key, cookie[key], domain=".115.com", rest={'HttpOnly': True})
                )
        else:
            cookiejar.update(cookie)
        cookies = cookiejar.get_dict()
        self.__dict__["cookie"] = "; ".join(f"{key}={cookies[key]}" for key in ("UID", "CID", "SEID"))

    def login_with_qrcode(self, /, **request_kwargs) -> dict:
        """用二维码登录
        """
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
        return self.login_qrcode_result({"account": qrcode_token["uid"]}, **request_kwargs)

    def request(
        self, 
        api: str, 
        /, 
        method: str = "GET", 
        *, 
        parse: bool | Callable = False, 
        **request_kwargs, 
    ):
        """
        """
        request_kwargs["stream"] = True
        resp = self.session.request(method, api, **request_kwargs)
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

    ########## Version API ##########

    @staticmethod
    def list_app_version(**request_kwargs) -> dict:
        """获取当前各平台最新版 115 app
        GET https://appversion.115.com/1/web/1.0/api/chrome
        """
        api = "https://appversion.115.com/1/web/1.0/api/chrome"
        return Session().get(api, **request_kwargs).json()

    ########## Account API ##########

    def login_check(self, /, **request_kwargs) -> dict:
        """检查当前用户的登录状态（用处不大）
        GET http://passportapi.115.com/app/1.0/web/1.0/check/sso/
        """
        api = "http://passportapi.115.com/app/1.0/web/1.0/check/sso/"
        return self.request(api, parse=loads, **request_kwargs)

    def login_qrcode_status(self, /, payload: dict, **request_kwargs) -> dict:
        """获取二维码的状态（未扫描、已扫描、已登录、已取消、已过期等），payload 数据取自 `login_qrcode_token` 接口响应
        GET https://qrcodeapi.115.com/get/status/
        payload:
            - uid: str
            - time: int
            - sign: str
        """
        api = "https://qrcodeapi.115.com/get/status/"
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def login_qrcode_result(self, /, payload: int | str | dict, **request_kwargs) -> dict:
        """获取扫码登录的结果，包含 cookie
        POST https://passportapi.115.com/app/1.0/web/1.0/login/qrcode/
        payload:
            - account: int | str
            - app: str = "web"
        """
        api = "https://passportapi.115.com/app/1.0/web/1.0/login/qrcode/"
        if isinstance(payload, (int, str)):
            payload = {"account": payload, "app": "web"}
        else:
            payload = {"app": "web", **payload}
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def login_qrcode_token(self, /, **request_kwargs) -> dict:
        """获取登录二维码，扫码可用
        GET https://qrcodeapi.115.com/api/1.0/web/1.0/token/
        """
        api = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
        return self.request(api, parse=loads, **request_kwargs)

    def logout(self, /, **request_kwargs) -> None:
        """退出登录状态（如无必要，不要使用）
        GET https://passportapi.115.com/app/1.0/web/1.0/logout/logout/
        """
        api = "https://passportapi.115.com/app/1.0/web/1.0/logout/logout/"
        self.request(api, **request_kwargs)

    def login_status(self, /, **request_kwargs) -> dict:
        """获取登录状态
        GET https://my.115.com/?ct=guide&ac=status
        """
        api = "https://my.115.com/?ct=guide&ac=status"
        return self.request(api, parse=loads, **request_kwargs)

    def user_info(self, /, **request_kwargs) -> dict:
        """获取此用户信息
        GET https://my.115.com/?ct=ajax&ac=na
        """
        api = "https://my.115.com/?ct=ajax&ac=nav"
        return self.request(api, parse=loads, **request_kwargs)

    def user_info2(self, /, **request_kwargs) -> dict:
        """获取此用户信息（更全）
        GET https://my.115.com/?ct=ajax&ac=get_user_aq
        """
        api = "https://my.115.com/?ct=ajax&ac=get_user_aq"
        return self.request(api, parse=loads, **request_kwargs)

    def user_setting(self, payload: dict = {}, /, **request_kwargs) -> dict:
        """获取（并可修改）此账户的网页版设置（提示：较为复杂，自己抓包研究）
        POST https://115.com/?ac=setting&even=saveedit&is_wl_tpl=1
        """
        api = "https://115.com/?ac=setting&even=saveedit&is_wl_tpl=1"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    ########## File System API ##########

    def fs_batch_copy(self, /, payload: dict, **request_kwargs) -> dict:
        """复制文件或文件夹
        POST https://webapi.115.com/files/copy
        payload:
            - pid: int | str
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
        """
        api = "https://webapi.115.com/files/copy"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_batch_delete(self, payload: dict, /, **request_kwargs) -> dict:
        """删除文件或文件夹
        POST https://webapi.115.com/rb/delete
        payload:
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
        """
        api = "https://webapi.115.com/rb/delete"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_batch_move(self, payload: dict, /, **request_kwargs) -> dict:
        """移动文件或文件夹
        POST https://webapi.115.com/files/move
        payload:
            - pid: int | str
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
        """
        api = "https://webapi.115.com/files/move"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_batch_rename(self, payload: dict, /, **request_kwargs) -> dict:
        """重命名文件或文件夹
        POST https://webapi.115.com/files/batch_rename
        payload:
            - files_new_name[{file_id}]: str # 值为新的文件名（basename）
        """
        api = "https://webapi.115.com/files/batch_rename"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_copy(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
        pid: int, 
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
        return self.fs_batch_copy(payload, **request_kwargs)

    def fs_delete(
        self, 
        fids: int | str | Iterable[int | str], 
        /, 
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
        return self.fs_batch_delete(payload, **request_kwargs)

    def fs_file(
        self, 
        payload: int | str | dict, 
        /, 
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
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_files(self, payload: dict = {}, /, **request_kwargs) -> dict:
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
            - show_dir: 0 | 1 = 1 # 此参数值必须为 1

            - aid: int | str = 1
            - code: int | str = <default>
            - count_folders: 0 | 1 = <default>
            - custom_order: int | str = <default>
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - format: str = "json"
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - natsort: 0 | 1 = <default>
            - record_open_time: 0 | 1 = <default>
            - scid: int | str = <default>
            - snap: 0 | 1 = <default>
            - star: 0 | 1 = <default>
            - source: str = <default>
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
        payload = {"cid": 0, "limit": 32, "offset": 0, "asc": 1, "o": "file_name", "show_dir": 1, **payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def fs_files2(self, payload: dict = {}, /, **request_kwargs) -> dict:
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
            - show_dir: 0 | 1 = 1 # 此参数值必须为 1

            - aid: int | str = 1
            - code: int | str = <default>
            - count_folders: 0 | 1 = <default>
            - custom_order: int | str = <default>
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - format: str = "json"
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - natsort: 0 | 1 = <default>
            - record_open_time: 0 | 1 = <default>
            - scid: int | str = <default>
            - snap: 0 | 1 = <default>
            - star: 0 | 1 = <default>
            - source: str = <default>
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
        payload = {"cid": 0, "limit": 32, "offset": 0, "asc": 1, "o": "file_name", "show_dir": 1, **payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def fs_files_edit(self, /, payload: list, **request_kwargs) -> dict:
        """设置文件或文件夹的备注、标签等（提示：此接口不建议直接使用）
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
            - file_label: int | str = <default> # 标签 id，如果有多个，用逗号","隔开
        """
        api = "https://webapi.115.com/files/edit"
        return self.request(
            api, 
            "POST", 
            data=urlencode(payload), 
            parse=loads, 
            headers={"Content-Type": "application/x-www-form-urlencoded"}, 
            **request_kwargs, 
        )

    def fs_files_hidden(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
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
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_hidden_switch(self, payload: dict, **request_kwargs) -> dict:
        """切换隐藏模式
        POST https://115.com/?ct=hiddenfiles&ac=switching
        payload:
            show: 0 | 1 = 1
            safe_pwd: int | str = <default> # 密码，如果需要进入隐藏模式，请传递此参数
            valid_type: int = 1
        """
        api = "https://115.com/?ct=hiddenfiles&ac=switching"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_statistic(self, payload: int | str | dict, /, **request_kwargs) -> dict:
        """获取文件或文件夹的统计信息（提示：但得不到根目录的统计信息，所以 cid 为 0 时无意义）
        GET https://webapi.115.com/category/get
        payload:
            cid: int | str
            aid: int | str = 1
        """
        api = "https://webapi.115.com/category/get"
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def fs_get_repeat(self, payload: int | str | dict, /, **request_kwargs) -> dict:
        """文件查重
        GET https://webapi.115.com/files/get_repeat_sha
        payload:
            file_id: int | str
        """
        api = "https://webapi.115.com/files/get_repeat_sha"
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def fs_index_info(self, /, **request_kwargs) -> dict:
        """获取当前已用空间、可用空间、登录设备等信息
        GET https://webapi.115.com/files/index_info
        """
        api = "https://webapi.115.com/files/index_info"
        return self.request(api, parse=loads, **request_kwargs)

    def fs_info(self, payload: int | str | dict, /, **request_kwargs) -> dict:
        """获取文件或文件夹的基本信息
        GET https://webapi.115.com/files/get_info
        payload:
            - file_id: int | str
        """
        api = "https://webapi.115.com/files/get_info"
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def fs_mkdir(self, payload: str | dict, /, **request_kwargs) -> dict:
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
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def fs_move(
        self, 
        fids: int | str | Iterable[int | str], 
        pid: int, 
        /, 
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
        return self.fs_batch_move(payload, **request_kwargs)

    def fs_rename(self, fid_name_pairs: Iterable[tuple[int | str, str]], /, **request_kwargs) -> dict:
        """重命名文件或文件夹，此接口是对 `fs_batch_rename` 的封装
        """
        payload = {f"files_new_name[{fid}]": name for fid, name in fid_name_pairs}
        return self.fs_batch_rename(payload, **request_kwargs)

    def fs_search(self, payload: dict, /, **request_kwargs) -> dict:
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
        payload = {"aid": 1, "cid": 0, "format": "json", "limit": 32, "offset": 0, "show_dir": 1, **payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def comment_get(self, /, payload: int | str | dict, **request_kwargs) -> dict:
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
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def comment_set(
        self, 
        /, 
        fids: int | str | Iterable[int | str], 
        file_desc: str = "", 
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
        return self.fs_files_edit(payload, **request_kwargs)

    def label_add(self, *lables: str, **request_kwargs) -> dict:
        """添加标签（可以接受多个）
        POST https://webapi.115.com/label/add_multi

        可传入多个 label 描述，每个 label 的格式都是 "{label_name}\x07{color}"，例如 "tag\x07#FF0000"
        """
        api = "https://webapi.115.com/label/add_multi"
        payload = [("name[]", label) for label in lables if label]
        if not payload:
            return {"state": False, "message": "no op"}
        return self.request(
            api, 
            "POST", 
            data=urlencode(payload), 
            parse=loads, 
            headers={"Content-Type": "application/x-www-form-urlencoded"}, 
            **request_kwargs, 
        )

    # TODO: 还需要接口，获取单个标签 id 对应的信息，也就是通过 id 来获取

    def label_del(self, /, payload: int | str | dict, **request_kwargs) -> dict:
        """删除标签
        POST https://webapi.115.com/label/delete
        payload:
            - id: int | str # 标签 id
        """
        api = "https://webapi.115.com/label/delete"
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def label_edit(self, /, payload: dict, **request_kwargs) -> dict:
        """编辑标签
        POST https://webapi.115.com/label/edit
        payload:
            - id: int | str # 标签 id
            - name: str = <default>  # 标签名
            - color: str = <default> # 标签颜色，支持 css 颜色语法
        """
        api = "https://webapi.115.com/label/edit"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def label_list(self, /, payload: dict = {}, **request_kwargs) -> dict:
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
            - user_id: int | str = <default> # 有默认值，所以不用传
        """
        api = "https://webapi.115.com/label/list"
        payload = {"offset": 0, "limit": 11500, **payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def label_set(
        self, 
        /, 
        fids: int | str | Iterable[int | str], 
        file_label: int | str = "", 
        **request_kwargs, 
    ) -> dict:
        """为文件或文件夹设置标签，此接口是对 `fs_files_edit` 的封装

        :param fids: 单个或多个文件或文件夹 id
        :param file_label: 标签 id，如果有多个，用逗号","隔开
        """
        if isinstance(fids, (int, str)):
            payload = [("fid", fids)]
        else:
            payload = [("fid[]", fid) for fid in fids]
            if not payload:
                return {"state": False, "message": "no op"}
        payload.append(("file_label", file_label))
        return self.fs_files_edit(payload, **request_kwargs)

    def label_batch(self, /, payload: dict, **request_kwargs) -> dict:
        """批量设置标签
        POST https://webapi.115.com/files/batch_label
        payload:
            - action: "add" | "remove" | "reset" | "replace"
                # 操作名
                # - 添加: "add"
                # - 移除: "remove"
                # - 重设: "reset"
                # - 替换: "replace"
            - file_ids: int | str # 文件或文件夹 id，如果有多个，用逗号","隔开
            - file_label: int | str = <default> # 标签 id，如果有多个，用逗号","隔开
            - file_label[{file_label}]: int | str = <default> # action 为 replace 时使用此参数，file_label[{原标签id}]: {目标标签id}，例如 file_label[123]: 456，就是把 id 是 123 的标签替换为 id 是 456 的标签
        """
        api = "https://webapi.115.com/files/batch_label"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def star_set(self, payload: int | str | dict, **request_kwargs) -> dict:
        """为文件或文件夹设置或取消星标
        POST https://webapi.115.com/files/star
        payload:
            - file_id: int | str # 文件或文件夹 id，如果有多个，用逗号","隔开
            - star: 0 | 1 = 1
        """
        api = "https://webapi.115.com/files/star"
        if isinstance(payload, (int, str)):
            payload = {"star": 1, "file_id": payload}
        else:
            payload = {"star": 1, **payload}
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    ########## Share API ##########

    def share_send(self, payload: int | str | dict, /, **request_kwargs) -> dict:
        """创建分享
        POST https://webapi.115.com/share/send
        payload:
            - file_ids: int | str # 文件列表，有多个用逗号","隔开
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
            - user_id: int | str = <default> # 有默认值，所以不用传
        """
        api = "https://webapi.115.com/share/send"
        if isinstance(payload, (int, str)):
            payload = {"ignore_warn": 1, "is_asc": 1, "order": "file_name", "file_ids": payload}
        else:
            payload = {"ignore_warn": 1, "is_asc": 1, "order": "file_name", **payload}
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def share_info(self, payload: str | dict, /, **request_kwargs) -> dict:
        """获取分享信息
        GET https://webapi.115.com/share/shareinfo
        payload:
            - share_code: str
        """
        api = "https://webapi.115.com/share/shareinfo"
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def share_list(self, payload: dict = {}, /, **request_kwargs) -> dict:
        """罗列分享信息列表
        GET https://webapi.115.com/share/slist
        payload:
            - limit: int = 32
            - offset: int = 0
            - user_id: int | str = <default> # 有默认值，所以不用传
        """
        api = "https://webapi.115.com/share/slist"
        payload = {"offset": 0, "limit": 32, **payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def share_update(self, payload: dict, /, **request_kwargs) -> dict:
        """变更分享的配置（例如改访问密码，取消分享）
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
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def share_snap(self, payload: dict, /, **request_kwargs) -> dict:
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
            - cid: int | str = 0             # 这是你网盘的文件夹 cid
            - user_id: int | str = <default> # 有默认值，所以不用传
        """
        api = "https://webapi.115.com/share/receive"
        payload = {"cid": 0, **payload}
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def share_download_url_web(self, payload: dict, /, **request_kwargs) -> dict:
        """获取分享链接中某个文件的下载链接（网页版接口，不推荐使用）
        GET https://webapi.115.com/share/downurl
        payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
            - user_id: int | str = <default> # 有默认值，所以不用传
        """
        api = "https://webapi.115.com/share/downurl"
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def share_download_url_app(self, payload: dict, /, **request_kwargs) -> dict:
        """获取分享链接中某个文件的下载链接
        POST https://proapi.115.com/app/share/downurl
        payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
            - user_id: int | str = <default> # 有默认值，所以不用传
        """
        api = "https://proapi.115.com/app/share/downurl"
        def parse(content) -> dict:
            resp = loads(content)
            if resp["state"]:
                resp["data"] = loads(RSA_ENCODER.decode(resp["data"]))
            return resp
        data = RSA_ENCODER.encode(dumps(payload))
        return self.request(api, "POST", data={"data": data}, parse=parse, **request_kwargs)

    def share_download_url(self, payload: dict, /, **request_kwargs) -> str:
        """获取分享链接中某个文件的下载链接，此接口是对 `share_download_url_app` 的封装
        POST https://proapi.115.com/app/share/downurl
        payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
            - user_id: int | str = <default> # 有默认值，所以不用传
        """
        resp = check_response(self.share_download_url_app)(payload, **request_kwargs)
        return resp["data"]["url"]["url"]

    ########## Download API ##########

    def download_url_web(self, payload: str | dict, /, **request_kwargs) -> dict:
        """获取文件的下载链接（网页版接口，不推荐使用）
        GET https://webapi.115.com/files/download
        payload:
            - pickcode: str
        """
        api = "https://webapi.115.com/files/download"
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def download_url_app(self, payload: str | dict, /, **request_kwargs) -> dict:
        """获取文件的下载链接
        POST https://proapi.115.com/app/chrome/downurl
        payload:
            - pickcode: str
        """
        api = "https://proapi.115.com/app/chrome/downurl"
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        def parse(content) -> dict:
            resp = loads(content)
            if resp["state"]:
                resp["data"] = loads(RSA_ENCODER.decode(resp["data"]))
            return resp
        data = RSA_ENCODER.encode(dumps(payload))
        return self.request(api, "POST", data={"data": data}, parse=parse, **request_kwargs)

    def download_url(self, pick_code: str, /, **request_kwargs) -> str:
        """获取文件的下载链接，此接口是对 `download_url_app` 的封装
        """
        resp = check_response(self.download_url_app)({"pickcode": pick_code}, **request_kwargs)
        return next(iter(resp["data"].values()))["url"]["url"]

    ########## Upload API ##########

    def upload_info(self, /, **request_kwargs) -> dict:
        """获取和上传有关的各种服务信息
        GET https://proapi.115.com/app/uploadinfo
        """
        api = "https://proapi.115.com/app/uploadinfo"
        return self.request(api, parse=loads, **request_kwargs)

    def upload_url(self, /, **request_kwargs) -> dict:
        """获取用于上传的一些 http 接口，此接口具有一定幂等性，请求一次，然后把响应记下来即可
        GET https://uplb.115.com/3.0/getuploadinfo.php
        response:
            - endpoint: 此接口用于上传文件到阿里云 OSS 
            - gettokenurl: 上传前需要用此接口获取 token
        """
        api = "https://uplb.115.com/3.0/getuploadinfo.php"
        return self.request(api, parse=loads, **request_kwargs)

    def upload_sample_init(self, /, payload: dict, **request_kwargs) -> dict:
        """网页端的上传接口，并不能秒传
        POST https://uplb.115.com/3.0/sampleinitupload.php
        payload:
            - userid: int | str
            - filename: str
            - filesize: int
            - target: str = "U_1_0"
        """
        api = "https://uplb.115.com/3.0/sampleinitupload.php"
        payload = {"target": "U_1_0", **payload}
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def upload_file_sample(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int | str = 0, 
        filesize: int = -1, 
        **request_kwargs, 
    ) -> dict:
        """基于 `upload_sample_init` 的上传接口
        """
        if hasattr(file, "read"):
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if not filename:
                try:
                    filename = os_path.basename(fsdecode(file.name))
                except Exception:
                    filename = str(uuid4())
            if filesize < 0:
                filesize = get_filesize(file)
                if file.tell() != 0:
                    file.seek(0)
        else:
            if not filename:
                filename = os_path.basename(fsdecode(file))
            if filesize < 0:
                filesize = get_filesize(file)
            file = open(file, "rb", buffering=0)
        payload = {
            "filename": filename, 
            "filesize": filesize, 
            "target": f"U_1_{pid}", 
        }
        resp = self.upload_sample_init(payload, **request_kwargs)
        api = resp["host"]
        payload = {
            "name": payload["filename"], 
            "target": payload["target"], 
            "key": resp["object"], 
            "policy": resp["policy"], 
            "OSSAccessKeyId": resp["accessid"], 
            "success_action_status": 200, 
            "callback": resp["callback"], 
            "signature": resp["signature"], 
        }
        return self.request(api, "POST", data=payload, parse=loads, files={"file": file}, **request_kwargs)

    def upload_init(self, /, **request_kwargs) -> dict:
        """秒传接口，参数的构造较为复杂，所以请不要直接使用
        POST https://uplb.115.com/4.0/initupload.php
        """
        api = "https://uplb.115.com/4.0/initupload.php"
        return self.request(api, "POST", **request_kwargs)

    def upload_sha1(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str, 
        target: str, 
        sign_key: str = "", 
        sign_val: str = "", 
        **request_kwargs, 
    ) -> dict:
        """秒传接口，此接口是对 `upload_init` 的封装，但不建议直接使用
        POST https://uplb.115.com/4.0/initupload.php
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
        params = {"k_ec": encoded_token}
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
        encrypted = ECDH_ENCODER.encode(urlencode(sorted(data.items())))
        return self.upload_init(
            params=params, 
            data=encrypted, 
            parse=lambda content: loads(ECDH_ENCODER.decode(content)), 
            headers={"Content-Type": "application/x-www-form-urlencoded"}, 
            **request_kwargs, 
        )

    def upload_file_sha1_simple(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        file_sha1: str, 
        read_bytes_range: Callable[[str], bytes], 
        pid: int | str = 0, 
    ) -> dict:
        """秒传接口，此接口是对 `upload_sha1` 的封装，推荐使用
        """
        fileinfo = {"filename": filename, "filesize": filesize, "file_sha1": file_sha1.upper(), "target": f"U_1_{pid}"}
        resp = self.upload_sha1(**fileinfo) # type: ignore
        if resp["status"] == 7 and resp["statuscode"] == 701:
            sign_key = resp["sign_key"]
            sign_check = resp["sign_check"]
            data = read_bytes_range(sign_check)
            fileinfo["sign_key"] = sign_key
            fileinfo["sign_val"] = sha1(data).hexdigest().upper()
            resp = self.upload_sha1(**fileinfo) # type: ignore
            fileinfo["sign_check"] = sign_check
        resp["fileinfo"] = fileinfo
        return resp

    def upload_file_sha1(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int | str = 0, 
        filesize: int = -1, 
        file_sha1: Optional[str] = None, 
    ) -> dict:
        """秒传接口，此接口是对 `upload_sha1` 的封装，推荐使用
        """
        if hasattr(file, "read"):
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if not filename:
                try:
                    filename = os_path.basename(fsdecode(file.name))
                except Exception:
                    filename = str(uuid4())
            if not file_sha1:
                filesize, sha1obj = file_digest(file, "sha1")
                file_sha1 = sha1obj.hexdigest()
            file_sha1 = cast(str, file_sha1)
            if filesize < 0:
                filesize = get_filesize(file)
        else:
            if not filename:
                filename = os_path.basename(fsdecode(file))
            if not file_sha1:
                filesize, sha1obj = file_digest(open(file, "rb"), "sha1")
                file_sha1 = sha1obj.hexdigest()
            file_sha1 = cast(str, file_sha1)
            if filesize < 0:
                filesize = get_filesize(file)
        fileinfo = {"filename": filename, "filesize": filesize, "file_sha1": file_sha1.upper(), "target": f"U_1_{pid}"}
        resp = self.upload_sha1(**fileinfo) # type: ignore
        if resp["status"] == 7 and resp["statuscode"] == 701:
            sign_key = resp["sign_key"]
            sign_check = resp["sign_check"]
            if not hasattr(file, "read"):
                file = open(file, "rb")
            start, end = map(int, sign_check.split("-"))
            file.seek(start)
            fileinfo["sign_key"] = sign_key
            fileinfo["sign_val"] = sha1(file.read(end-start+1)).hexdigest().upper()
            resp = self.upload_sha1(**fileinfo) # type: ignore
            fileinfo["sign_check"] = sign_check
        resp["fileinfo"] = fileinfo
        return resp

    # TODO: 提供一个可断点续传的版本
    def upload_file(
        self, 
        /, 
        file, 
        filename: Optional[str] = None, 
        pid: int | str = 0, 
        filesize: int = -1, 
        file_sha1: Optional[str] = None, 
        progress_callback: Optional[Callable] = None, 
        multipart_threshold: Optional[int] = None, 
    ) -> dict:
        """基于 `upload_file_sha1` 的上传接口，是高层封装，推荐使用
        """
        resp = self.upload_file_sha1(file, filename, pid, filesize=filesize, file_sha1=file_sha1)
        if resp["status"] == 2 and resp.get("statuscode", 0) == 0:
            return resp
        elif resp["status"] == 1 and resp.get("statuscode", 0) == 0:
            bucket_name, key, callback = resp["bucket"], resp["object"], resp["callback"]
        else:
            raise ValueError(resp)
        filesize = resp["fileinfo"]["filesize"]
        if hasattr(file, "read"):
            if isinstance(file, TextIOWrapper):
                file = file.buffer
            if file.tell() != 0:
                file.seek(0)
        else:
            file = open(file, "rb")
        multipart_threshold = multipart_threshold or oss2.defaults.multipart_threshold
        if filesize <= multipart_threshold:
            upload_resp = self._oss_upload(
                bucket_name, 
                key, 
                file, 
                callback, 
                progress_callback=progress_callback, 
            )
        else:
            upload_resp = self._oss_multipart_upload(
                bucket_name, 
                key, 
                file, 
                callback, 
                progress_callback=progress_callback, 
                total_size=resp["fileinfo"]["filesize"], 
            )
        resp["upload"] = upload_resp
        return resp

    def _oss_upload(
        self, 
        /, 
        bucket_name: str, 
        key: str, 
        file, 
        callback: dict, 
        progress_callback: Optional[Callable] = None, 
    ) -> dict:
        """帮助函数：上传文件到阿里云 OSS，一次上传全部
        """
        uploadinfo = self.upload_url()
        token = self.request(uploadinfo["gettokenurl"], parse=loads)
        auth = oss2.Auth(token["AccessKeyId"], token["AccessKeySecret"])
        bucket = oss2.Bucket(auth, uploadinfo["endpoint"], bucket_name)
        headers={
            "User-Agent": "aliyun-sdk-android/2.9.1", 
            "x-oss-security-token": token["SecurityToken"], 
            "x-oss-callback": b64encode(bytes(callback["callback"], "ascii")).decode("ascii"),
            "x-oss-callback-var": b64encode(bytes(callback["callback_var"], "ascii")).decode("ascii"),
        }
        result = bucket.put_object(key, file, headers=headers, progress_callback=progress_callback)
        data = loads(result.resp.read())
        data["headers"] = result.headers
        return data

    # TODO 提供一个可迭代版本，这样便于获取断点续传信息，并且支持多线程上传
    def _oss_multipart_upload(
        self, 
        /, 
        bucket_name, 
        key, 
        file, 
        callback, 
        progress_callback=None, 
        *, 
        total_size=None, 
        part_size=None, 
    ) -> dict:
        """帮助函数：上传文件到阿里云 OSS，分块上传，支持断点续传
        """
        uploadinfo = self.upload_url()
        token = self.request(uploadinfo["gettokenurl"], parse=loads)
        auth = oss2.Auth(token["AccessKeyId"], token["AccessKeySecret"])
        bucket = oss2.Bucket(auth, uploadinfo["endpoint"], bucket_name)
        if total_size is None:
            if hasattr(file, "fileno"):
                total_size = fstat(file).st_size
            else:
                total_size = stat(file).st_size
                file = open(file, "rb")
        part_size = oss2.determine_part_size(total_size, preferred_size=part_size or oss2.defaults.part_size)
        headers={
            "User-Agent": "aliyun-sdk-android/2.9.1", 
            "x-oss-security-token": token["SecurityToken"], 
        }
        upload_id = bucket.init_multipart_upload(key, headers=headers).upload_id
        parts = []
        offset = 0
        for part_number, (start, stop) in enumerate(cut_iter(total_size, step=part_size), 1):
            result = bucket.upload_part(
                key, 
                upload_id, 
                part_number, 
                oss2.SizedFileAdapter(file, stop-start), 
                progress_callback=progress_callback, 
                headers=headers, 
            )
            parts.append(oss2.models.PartInfo(part_number, result.etag, size=stop-start, part_crc=result.crc))
        headers["x-oss-callback"] = b64encode(bytes(callback["callback"], "ascii")).decode("ascii")
        headers["x-oss-callback-var"] = b64encode(bytes(callback["callback_var"], "ascii")).decode("ascii")
        result = bucket.complete_multipart_upload(key, upload_id, parts, headers=headers)
        data = loads(result.resp.read())
        data["headers"] = result.headers
        return data

    ########## Decompress API ##########

    def extract_push(self, /, payload: dict, **request_kwargs) -> dict:
        """推送一个解压缩任务给服务器，完成后，就可以查看压缩包的文件列表了
        POST https://webapi.115.com/files/push_extract
        payload:
            - pick_code: str
            - secret: str = "" # 解压密码
        """
        api = "https://webapi.115.com/files/push_extract"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def extract_push_progress(self, /, payload: dict, **request_kwargs) -> dict:
        """查询解压缩任务的进度
        GET https://webapi.115.com/files/push_extract
        payload:
            - pick_code: str
        """
        api = "https://webapi.115.com/files/push_extract"
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def extract_info(self, /, payload: dict, **request_kwargs) -> dict:
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
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def extract_list(
        self, 
        /, 
        pick_code: str, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
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
        return self.extract_info(payload, **request_kwargs)

    def extract_add_file(
        self, 
        /, 
        payload: list[tuple[str, int | str]], 
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
        return self.request(
            api, 
            "POST", 
            data=urlencode(payload), 
            parse=loads, 
            headers={"Content-Type": "application/x-www-form-urlencoded"}, 
            **request_kwargs, 
        )

    def extract_download_url_web(self, /, payload: dict, **request_kwargs) -> dict:
        """获取压缩包中文件的下载链接
        GET https://webapi.115.com/files/extract_down_file
        payload:
            - pick_code: str
            - full_name: str
        """
        api = "https://webapi.115.com/files/extract_down_file"
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    def extract_download_url(
        self, 
        /, 
        pick_code: str, 
        path: str, 
        **request_kwargs, 
    ) -> str:
        """获取压缩包中文件的下载链接，此接口是对 `extract_download_url_web` 的封装
        """
        resp = check_response(self.extract_download_url_web)(
            {"pick_code": pick_code, "full_name": path.strip("/")}, **request_kwargs)
        return quote(resp["data"]["url"], safe=":/?&=%#")

    # TODO: 如果解压缩单个文件呢
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

    def extract_progress(self, /, payload: int | str | dict, **request_kwargs) -> dict:
        """获取 解压缩到文件夹 任务的进度
        GET https://webapi.115.com/files/add_extract_file
        payload:
            - extract_id: str
        """
        api = "https://webapi.115.com/files/add_extract_file"
        if isinstance(payload, (int, str)):
            payload = {"extract_id": payload}
        return self.request(api, params=payload, parse=loads, **request_kwargs)

    # TODO: 增加一个接口，下载压缩包中的文件

    ########## Offline Download API ##########

    # TODO: 增加一个接口，用于获取一个种子或磁力链接，里面的文件列表，这个文件并未被添加任务

    def offline_quota_package_info(self, /, **request_kwargs) -> dict:
        """获取当前离线配额信息
        GET https://115.com/web/lixian/?ct=lixian&ac=get_quota_package_info
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=get_quota_package_info"
        return self.request(api, parse=loads, **request_kwargs)

    def offline_download_path(self, /, **request_kwargs) -> dict:
        """获取当前默认的离线下载到的文件夹信息（可能有多个）
        GET https://webapi.115.com/offine/downpath
        """
        api = "https://webapi.115.com/offine/downpath"
        return self.request(api, parse=loads, **request_kwargs)

    def offline_upload_torrent_path(self, /, **request_kwargs) -> dict:
        """获取当前的种子上传到的文件夹，当你添加种子任务后，这个种子会在此文件夹中保存
        GET https://115.com/?ct=lixian&ac=get_id&torrent=1
        """
        api = "https://115.com/?ct=lixian&ac=get_id&torrent=1"
        return self.request(api, parse=loads, **request_kwargs)

    def offline_getsign(self, /, **request_kwargs) -> dict:
        """增删改查离线下载任务，需要携带签名 sign，具有一定的时效性，但不用每次都获取，失效了再用此接口获取就行了
        GET https://115.com/?ct=offline&ac=space
        """
        api = "https://115.com/?ct=offline&ac=space"
        return self.request(api, parse=loads, **request_kwargs)

    def offline_add_url(self, /, payload: dict, **request_kwargs) -> dict:
        """添加一个离线任务
        POST https://115.com/web/lixian/?ct=lixian&ac=add_task_url
        payload:
            - uid: int | str
            - sign: str
            - time: int
            - savepath: str, 
            - wp_path_id: int | str 
            - url: str
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=add_task_url"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def offline_add_urls(self, /, payload: dict, **request_kwargs) -> dict:
        """添加一组离线任务
        POST https://115.com/web/lixian/?ct=lixian&ac=add_task_urls
        payload:
            - uid: int | str
            - sign: str
            - time: int
            - savepath: str, 
            - wp_path_id: int | str 
            - url[0]: str
            - url[1]: str
            - ...
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def offline_torrent_info(self, /, payload: dict, **request_kwargs) -> dict:
        """查看离线任务的信息
        POST https://115.com/web/lixian/?ct=lixian&ac=torrent
        payload:
            - uid: int | str
            - sign: str
            - time: int
            - sha1: str
            - pickcode: str = <default>
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=torrent"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def offline_add_torrent(self, /, payload: dict, **request_kwargs) -> dict:
        """添加一个种子作为离线任务
        POST https://115.com/web/lixian/?ct=lixian&ac=add_task_bt
        payload:
            - uid: int | str
            - sign: str
            - time: int
            - savepath: str
            - info_hash: str
            - wanted: str
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=add_task_bt"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def offline_del(self, /, payload: dict, **request_kwargs) -> dict:
        """删除一组离线任务（无论是否已经完成）
        POST https://115.com/web/lixian/?ct=lixian&ac=task_del
        payload:
            - uid: int | str
            - sign: str
            - time: int
            - hash[0]: str
            - hash[1]: str
            - ...
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=task_del"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    def offline_list(self, /, payload: dict, **request_kwargs) -> dict:
        """获取当前的离线任务列表
        POST https://115.com/web/lixian/?ct=lixian&ac=task_lists
        payload:
            - page: int | str
            - uid: int | str
            - sign: str
            - time: int
        """
        api = "https://115.com/web/lixian/?ct=lixian&ac=task_lists"
        return self.request(api, "POST", data=payload, parse=loads, **request_kwargs)

    ########## Other Encapsulations ##########

    @cached_property
    def fs(self, /) -> P115FileSystem:
        """
        """
        return P115FileSystem(self)

    @cached_property
    def offline(self, /) -> P115Offline:
        """
        """
        return P115Offline(self)

    def get_share_fs(self, share_link: str, /) -> P115ShareFileSystem:
        """
        """
        return P115ShareFileSystem(self, share_link)

    def get_zip_fs(self, id: int, /) -> P115ZipFileSystem:
        """
        """
        return P115ZipFileSystem(self, id)

    def open(self, url: str, /, **request_kwargs) -> RequestsFileReader:
        """
        """
        return RequestsFileReader(url, urlopen=self.session.get)

    def read_bytes_range(
        self, 
        url: str, 
        /, 
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
        with self.session.get(url, headers=headers, **request_kwargs) as resp:
            return resp.content

    def read_range(
        self, 
        url: str, 
        /, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
        **request_kwargs, 
    ) -> bytes:
        """
        """
        length = None
        if start < 0:
            length = int(self.session.head(url).headers["Content-Length"])
            start += length
        if start < 0:
            start = 0
        if stop is None:
            bytes_range = f"{start}-"
        else:
            if stop < 0:
                if length is None:
                    length = int(self.session.head(url).headers["Content-Length"])
                stop += length
            if stop <= 0 or start >= stop:
                return b""
            bytes_range = f"{start}-{stop-1}"
        return self.read_bytes_range(url, bytes_range, headers=headers, **request_kwargs)


class P115PathBase(Generic[P115FSType], Mapping, PathLike[str]):
    fs: P115FSType
    path: str

    def __init__(
        self, 
        /, 
        fs: P115FSType, 
        path: str | PathLike[str], 
        **attr, 
    ):
        attr.update(fs=fs, path=fs.abspath(path))
        super().__setattr__("__dict__", attr)

    def __and__(self, path: str | PathLike[str], /) -> Self:
        return type(self)(self.fs, commonpath((self.path, self.fs.abspath(path))))

    def __call__(self, /) -> Self:
        self.__dict__.update(self.fs.attr(self.id))
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

    def __truediv__(self, path: str | PathLike[str], /) -> Self:
        return self.joinpath(path)

    @cached_property
    def id(self, /):
        return self.fs.get_id(self.path)

    def keys(self) -> KeysView:
        return self.__dict__.keys()

    def values(self) -> ValuesView:
        return self.__dict__.values()

    def items(self) -> ItemsView:
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
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes], Unpack[HeadersKeyword]], Any]] = None, 
    ):
        return self.fs.download_tree(
            self, 
            local_dir, 
            pid=pid, 
            no_root=no_root, 
            write_mode=write_mode, 
            download=download, 
        )

    def exists(self, /) -> bool:
        return self.fs.exists(self)

    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
    ) -> Iterator[Self]:
        return self.fs.glob(
            pattern, 
            self if self["is_directory"] else self.parent, 
            ignore_case=ignore_case, 
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
    ) -> Iterator[Self]:
        return self.fs.iter(
            self, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
        )

    def join(self, *names: str):
        if not names:
            return self
        return type(self)(self.fs, joinpath(self.path, joins(names)))

    def joinpath(self, *paths: str | PathLike[str]) -> Self:
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

    def listdir_path(self, /) -> list[Self]:
        return self.fs.listdir_path(self)

    def match(self, /, path_pattern: str, ignore_case: bool = False) -> bool:
        pattern = joinpath("/", *(t[0] for t in posix_glob_translate_iter(path_pattern)))
        if ignore_case:
            pattern = "(?i:%s)" % pattern
        return re_compile(pattern).fullmatch(self.path) is not None

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
    ) -> IO:
        return self.fs.open(
            self, 
            mode=mode, 
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    @cached_property
    def parent(self, /) -> Self:
        path = self.path
        if path == "/":
            return self
        return type(self)(self.fs, dirname(path), id=self["parent_id"])

    @cached_property
    def parents(self, /) -> tuple[Self, ...]:
        path = self.path
        if path == "/":
            return ()
        parents: list[Self] = []
        cls, fs = type(self), self.fs
        parent = dirname(path)
        while path != parent:
            parents.append(cls(fs, parent))
        return tuple(parents)

    @cached_property
    def parts(self, /) -> tuple[str, ...]:
        return ("/", *self.path[1:].split("/"))

    def read_bytes(self, /) -> bytes:
        return self.fs.read_bytes(self)

    def read_bytes_range(
        self, 
        /, 
        bytes_range: str = "0-", 
        headers: Optional[Mapping] = None, 
    ) -> bytes:
        return self.fs.read_bytes_range(self, bytes_range, headers=headers)

    def read_range(
        self, 
        /, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
    ) -> bytes:
        return self.fs.read_range(self, start, stop, headers=headers)

    def read_text(
        self, 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
    ) -> str:
        return self.fs.read_text(self, encoding=encoding, errors=errors)

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
    ) -> Iterator[Self]:
        return self.fs.rglob(
            pattern, 
            self if self["is_directory"] else self.parent, 
            ignore_case=ignore_case, 
        )

    @cached_property
    def root(self, /) -> Self:
        return type(self)(self.fs, "/", id=0)

    def samefile(self, path: str | PathLike[str], /) -> bool:
        if isinstance(path, type(self)):
            try:
                return self["id"] == path["id"]
            except FileNotFoundError:
                return False
        path = fspath(path)
        return path in ("", ".") or path.startswith("/") and self.path == normpath(path)

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


class P115FileSystemBase(Generic[M, P115PathType]):
    client: P115Client
    cid: int
    path: str
    path_class: type[P115PathType]

    def __iter__(self, /) -> Iterator[P115PathType]:
        return self.iter(max_depth=-1)

    def __itruediv__(self, id_or_path: IDOrPathType, /):
        self.chdir(id_or_path)
        return self

    @abstractmethod
    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[M]:
        ...

    @abstractmethod
    def attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> M:
        ...

    @abstractmethod
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> str:
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
        if isinstance(id_or_path, path_class):
            return id_or_path
        elif isinstance(id_or_path, int):
            return path_class(self, **self.attr(id_or_path))
        return path_class(self, self.get_path(id_or_path, pid))

    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: Optional[int] = None, 
    ) -> int:
        if isinstance(id_or_path, type(self).path_class):
            self.__dict__.update(cid=id_or_path.id, path=id_or_path.path)
            return id_or_path.id
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
            self.__dict__.update(cid=attr["id"], path=self.get_path(id_or_path, pid))
            return attr["id"]
        else:
            raise NotADirectoryError(
                errno.ENOTDIR, f"{id_or_path!r} (in {pid!r}) is not a directory")

    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        local_path_or_file: bytes | str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
        pid: Optional[int] = None, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes], Unpack[HeadersKeyword]], Any]] = None, 
    ):
        if hasattr(local_path_or_file, "write"):
            file = local_path_or_file
            if isinstance(file, TextIOWrapper):
                file = file.buffer
        else:
            local_path = fspath(local_path_or_file)
            mode: str = write_mode
            if mode:
                mode += "b"
            elif os_path.lexists(local_path):
                return
            else:
                mode = "wb"
            if local_path:
                file = open(local_path, mode)
            else:
                file = open(self.attr(id_or_path, pid)["name"], mode)
        file = cast(SupportsWrite[bytes], file)
        url = self.get_url(id_or_path, pid)
        if download:
            download(url, file, headers=self.client.session.headers)
        else:
            with self.client.open(url) as fsrc:
                copyfileobj(fsrc, file)

    def download_tree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        local_dir: bytes | str | PathLike = "", 
        pid: Optional[int] = None, 
        no_root: bool = False, 
        write_mode: Literal["", "x", "w", "a"] = "w", 
        download: Optional[Callable[[str, SupportsWrite[bytes], Unpack[HeadersKeyword]], Any]] = None, 
    ):
        local_dir = fsdecode(local_dir)
        if local_dir:
            makedirs(local_dir, exist_ok=True)
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            if not no_root:
                local_dir = os_path.join(local_dir, attr["name"])
                if local_dir:
                    makedirs(local_dir, exist_ok=True)
            for subattr in self.listdir_attr(attr["id"]):
                if subattr["is_directory"]:
                    self.download_tree(
                        subattr["id"], 
                        os_path.join(local_dir, subattr["name"]), 
                        no_root=True, 
                        write_mode=write_mode, 
                        download=download, 
                    )
                else:
                    self.download(
                        subattr["id"], 
                        os_path.join(local_dir, subattr["name"]), 
                        write_mode=write_mode, 
                        download=download, 
                    )
        else:
            self.download(
                attr["id"], 
                os_path.join(local_dir, attr["name"]), 
                write_mode=write_mode, 
                download=download, 
            )

    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> bool:
        try:
            if isinstance(id_or_path, type(self).path_class):
                id_or_path()
            else:
                self.attr(id_or_path, pid)
            return True
        except FileNotFoundError:
            return False

    def getcid(self, /) -> int:
        return self.cid

    def getcwd(self, /) -> str:
        return self.path

    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> int:
        if pid is None and (not id_or_path or id_or_path == "."):
            return self.cid
        elif isinstance(id_or_path, type(self).path_class):
            return id_or_path.id
        elif isinstance(id_or_path, int):
            return id_or_path
        if self.get_path(id_or_path, pid) == "/":
            return 0
        return self.attr(id_or_path, pid)["id"]

    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> str:
        if pid is None and (not id_or_path or id_or_path == "."):
            return self.path
        elif isinstance(id_or_path, type(self).path_class):
            return id_or_path.path
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
        if pid is None and (not id_or_path or id_or_path == "."):
            return splits(self.path)[0]
        elif isinstance(id_or_path, type(self).path_class):
            return splits(id_or_path.path)[0]
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

    # TODO: 需要优化，使用 patht
    # TODO: 允许 pattern 里面使用 \/
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
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
                return iter((path_class(self, **attr),))
        elif not pattern.lstrip("/"):
            return iter((path_class(self, **self.attr(0)),))
        splitted_pats = tuple(posix_glob_translate_iter(pattern))
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
                pattern = joinpath(re_escape(dir_), *(t[0] for t in splitted_pats))
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
                    return iter((path_class(self, **attr),))
            elif typ == "dstar" and i + 1 == len(splitted_pats):
                if dirname_as_id:
                    return self.iter(dir2, dirid, max_depth=-1)
                else:
                    return self.iter(dir_, max_depth=-1)
            if any(typ == "dstar" for _, typ, _ in splitted_pats):
                pattern = joinpath(re_escape(dir_), *(t[0] for t in splitted_pats[i:]))
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
        path = path_class(self, dir_)
        if dirname_as_id:
            path.__dict__["id"] = self.get_id(dir2, dirid)
        if not path["is_directory"]:
            return iter(())
        return glob_step_match(path, i)

    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> bool:
        if isinstance(id_or_path, type(self).path_class):
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
        if isinstance(id_or_path, type(self).path_class):
            return not id_or_path["is_directory"]
        try:
            return not self.attr(id_or_path, pid)["is_directory"]
        except FileNotFoundError:
            return False

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
    ) -> Iterator[P115PathType]:
        if not max_depth:
            return
        if min_depth > 0:
            min_depth -= 1
        if max_depth > 0:
            max_depth -= 1
        path_class = type(self).path_class
        try:
            for path in self.listdir_path(top, pid):
                path = cast(P115PathType, path)
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
                        path.path, 
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
    ) -> list[str]:
        return [attr["name"] for attr in self.iterdir(id_or_path, pid)]

    def listdir_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> list[M]:
        return list(self.iterdir(id_or_path, pid))

    def listdir_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> list[P115PathType]:
        path_class = type(self).path_class
        return [path_class(self, **attr) for attr in self.iterdir(id_or_path, pid)]

    def open(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        mode: str = "r", 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
        pid: Optional[int] = None, 
    ) -> IO:
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        url = self.get_url(id_or_path, pid)
        return self.client.open(url).wrap(
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
        pid: Optional[int] = None, 
    ):
        return self.read_bytes_range(id_or_path, pid=pid)

    def read_bytes_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        headers: Optional[Mapping] = None, 
        pid: Optional[int] = None, 
    ) -> bytes:
        return self.client.read_bytes_range(self.get_url(id_or_path, pid), bytes_range, headers=headers)

    def read_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        stop: Optional[int] = None, 
        headers: Optional[Mapping] = None, 
        pid: Optional[int] = None, 
    ) -> bytes:
        return self.client.read_range(self.get_url(id_or_path, pid), start, stop, headers=headers)

    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        pid: Optional[int] = None, 
    ):
        return self.open(id_or_path, encoding=encoding, errors=errors, pid=pid).read()

    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
    ) -> Iterator[P115PathType]:
        if not pattern:
            return self.iter(dirname, max_depth=-1)
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(pattern, dirname, ignore_case=ignore_case)

    def scandir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[P115PathType]:
        return iter(self.listdir_path(id_or_path, pid))

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
            attrs: list[M] = []
            for attr in self.listdir_attr(top, pid):
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
    ) -> Iterator[tuple[str, list[P115PathType], list[P115PathType]]]:
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
            dirs: list[P115PathType] = []
            files: list[P115PathType] = []
            for path in self.listdir_path(top, pid):
                (dirs if path["is_directory"] else files).append(path)
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
    ll  = listdir_path


class P115Path(P115PathBase):
    fs: P115FileSystem

    def copy(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> Optional[P115Path]:
        result = self.fs.copy(self, dst_path, pid=pid, overwrite_or_ignore=overwrite_or_ignore)
        if not result:
            return None
        id = result[0]
        return type(self)(self.fs, self.fs.get_path(id), id=id)

    def copytree(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        id, _ = self.fs.copytree(self, dst_path, pid=pid)
        return type(self)(self.fs, self.fs.get_path(id), id=id)

    def mkdir(self, /, exist_ok=True):
        self.fs.makedirs(self, exist_ok=exist_ok)
        return self

    def move(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        result = self.fs.move(self, dst_path, pid)
        if not result:
            return self
        id = result[0]
        return type(self)(self.fs, self.fs.get_path(id), id=id)

    def remove(self, /, recursive: bool = False):
        return self.fs.remove(self, recursive=recursive)

    def rename(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        result = self.fs.rename(self, dst_path, pid)
        if not result:
            return self
        id = result[0]
        return type(self)(self.fs, self.fs.get_path(id), id=id)

    def renames(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        result = self.fs.renames(self, dst_path, pid)
        if not result:
            return self
        id = result[0]
        return type(self)(self.fs, self.fs.get_path(id), id=id)

    def replace(
        self, 
        /, 
        dst_path: IDOrPathType, 
        pid: Optional[int] = None, 
    ) -> Self:
        result = self.fs.replace(self, dst_path, pid)
        if not result:
            return self
        id = result[0]
        return type(self)(self.fs, self.fs.get_path(id), id=id)

    def rmdir(self, /):
        return self.fs.rmdir(self)

    def touch(self, /) -> Self:
        self.fs.touch(self)
        return self

    unlink = remove

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

    def write_bytes(self, data: bytes | bytearray = b"", /):
        return self.fs.write_bytes(self, data=data)

    def write_text(
        self, 
        text: str = "", 
        /, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ):
        return self.fs.write_text(
            self, 
            text=text, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

# TODO 增加几种文件系统：普通（增删改查）、压缩包（查，解压(extract)）、分享文件夹（查，转存(transfer)）
# TODO 如果压缩包尚未解压，则使用 zipfile 之类的模块，去模拟文件系统
# TODO 实现清空已完成，清空所有失败任务，清空所有未完成，具体参考app（抓包）
# TODO 以后会支持传入作为缓存的 MutableMapping
# TODO 如果以后有缓存的话，getcwd 会获取最新的名字

class P115FileSystem(P115FileSystemBase[dict, P115Path]):
    path_to_id: MutableMapping[str, int]
    id_to_etime: MutableMapping[int, float]
    pid_to_attrs: MutableMapping[int, dict]
    path_class = P115Path

    def __init__(
        self, 
        client: P115Client, 
        /, 
    ):
        self.__dict__.update(
            client = client, 
            cid = 0, 
            path = "/", 
            path_to_id = {"/": 0}, 
            id_to_etime = {}, 
            pid_to_attrs = {}, 
        )

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}, cid={self.cid!r}, path={self.path!r}) at {hex(id(self))}>"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    @check_response
    def _copy(self, id: int, pid: int = 0, /) -> dict:
        return self.client.fs_copy(id, pid)

    @check_response
    def _delete(self, id: int, /) -> dict:
        return self.client.fs_delete(id)

    @check_response
    def _files(
        self, 
        /, 
        id: int = 0, 
        limit: int = 32, 
        offset: int = 0, 
    ) -> dict:
        return self.client.fs_files({
            "cid": id, 
            "limit": limit, 
            "offset": offset, 
            "show_dir": 1, 
        })

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

    def _upload(self, file, name, pid: int = 0) -> dict:
        if not hasattr(file, "getbuffer") or len(file.getbuffer()) > 0:
            try:
                file.seek(0, 1)
            except:
                pass
            else:
                self.client.upload_file(file, name, pid)
                return self._attr_path(name, pid)
        id = int(check_response(self.client.upload_file_sample)(
            file, name, pid, filesize=0)["data"]["cid"])
        return self._attr(id)

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[dict]:
        attr = self.attr(id_or_path, pid)
        if not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{attr['path']!r} (id={attr['id']!r}) is not a directory")
        id = attr["id"]
        etime = attr["etime"].timestamp()
        if etime > self.id_to_etime.get(id, 0.0):
            pagesize = 1 << 10
            def iterdir():
                get_files = self._files
                path_to_id = self.path_to_id
                resp = get_files(id, limit=pagesize)
                dirname = joins(("", *(a["name"] for a in resp["path"][1:])))
                path_to_id[dirname] = id
                lastest_update = datetime.now()
                count = resp["count"]
                for attr in resp["data"]:
                    attr = normalize_info(attr, lastest_update=lastest_update)
                    path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                    path_to_id[path] = attr["id"]
                    yield attr
                for offset in range(pagesize, count, 1 << 10):
                    resp = get_files(id, limit=pagesize, offset=offset)
                    lastest_update = datetime.now()
                    if resp["count"] != count:
                        raise RuntimeError("detected directory (count) changes during iteration")
                    for attr in resp["data"]:
                        attr = normalize_info(attr, lastest_update=lastest_update)
                        path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                        path_to_id[path] = attr["id"]
                        yield attr
            self.pid_to_attrs[id] = {a["id"]: a for a in iterdir()}
            self.id_to_etime[id] = etime
        return iter(self.pid_to_attrs[id].values())

    def _attr(self, id: int, /) -> dict:
        if id == 0:
            lastest_update = datetime.now()
            return {
                "id": 0, 
                "parent_id": 0, 
                "name": "", 
                "path": "/", 
                "is_directory": True, 
                "lastest_update": lastest_update, 
                "etime": lastest_update, 
                "utime": lastest_update, 
                "ptime": datetime.fromtimestamp(0), 
                "open_time": lastest_update, 
            }
        try:
            resp = self._info(id)
        except OSError as e:
            raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}") from e
        attr = normalize_info(resp["data"][0], lastest_update=datetime.now())
        pid = attr["parent_id"]
        path = attr["path"] = joins((*(a["name"] for a in self._dir_get_ancestors(pid)), attr["name"]))
        self.path_to_id[path] = id
        try:
            self.pid_to_attrs[pid][id] = attr
        except:
            pass
        return attr

    def _attr_path(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: Optional[int] = None, 
    ) -> dict:
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
            attr = self._attr(id)
            if attr["path"] == fullpath:
                return attr
            path_to_id.pop(fullpath, None)
        attr = self._attr(pid)
        for name in patht[len(self.get_patht(pid)):]:
            if not attr["is_directory"]:
                raise NotADirectoryError(
                    errno.ENOTDIR, f"`pid` does not point to a directory: {pid!r}")
            for attr in self.listdir_attr(pid):
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
    ) -> dict:
        if isinstance(id_or_path, P115Path):
            return self._attr(id_or_path.id)
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
    ) -> Optional[tuple[int, str]]:
        src_patht = self.get_patht(src_path, pid)
        dst_patht = self.get_patht(dst_path, pid)
        src_fullpath = joins(src_patht)
        dst_fullpath = joins(dst_patht)
        if src_patht == dst_patht:
            if overwrite_or_ignore is None:
                raise SameFileError(src_fullpath)
            return None
        elif dst_patht == src_patht[:len(dst_patht)]:
            if overwrite_or_ignore is None:
                raise PermissionError(
                    errno.EPERM, 
                    f"copy a path as its ancestor is not allowed: {src_fullpath!r} -> {dst_fullpath!r}", 
                )
            return None
        elif src_patht == dst_patht[:len(src_patht)]:
            if overwrite_or_ignore is None:
                raise PermissionError(
                    errno.EPERM, 
                    f"copy a path as its descendant is not allowed: {src_fullpath!r} -> {dst_fullpath!r}", 
                )
            return None
        src_attr = self.attr(src_path, pid)
        if src_attr["is_directory"]:
            raise IsADirectoryError(
                errno.EISDIR, f"source is a directory: {src_fullpath!r} -> {dst_fullpath!r}")
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
            dst_name = check_response(self.client.upload_file_sha1_simple)(
                dst_name, 
                filesize=src_attr["size"], 
                file_sha1=src_attr["sha1"], 
                read_bytes_range=lambda rng: self.read_bytes_range(src_id, rng), 
                pid=dst_pid, 
            )["fileinfo"]["filename"]
            dst_id = self.attr(dst_name, dst_pid)["id"]
        elif src_name == dst_name:
            self._copy(src_id, dst_pid)
            dst_id = self.attr(src_name, dst_pid)["id"]
        else:
            tempdir_id = int(self._mkdir(str(uuid4()))["cid"])
            try:
                self._copy(src_id, tempdir_id)
                dst_id = self.attr(src_name, tempdir_id)["id"]
                resp = self._rename(dst_id, dst_name)
                if resp["data"]:
                    dst_name = resp["data"][str(dst_id)]
                self._move(dst_id, dst_pid)
            finally:
                self._delete(tempdir_id)
        return dst_id, dst_name

    def copytree(
        self, 
        /, 
        src_path: IDOrPathType, 
        dst_dir: IDOrPathType = "", 
        pid: Optional[int] = None, 
    ) -> tuple[int, str]:
        src_attr = self.attr(src_path, pid)
        dst_attr = self.attr(dst_dir, pid)
        src_id = src_attr["id"]
        dst_id = dst_attr["id"]
        src_name = src_attr["name"]
        if src_attr["parent_id"] == dst_id:
            raise SameFileError(src_id)
        elif any(a["id"] == src_id for a in self.get_ancestors(dst_id)):
            raise PermissionError(
                errno.EPERM, 
                f"copy a directory to its subordinate path is not allowed: {src_id!r} -> {dst_id!r}", 
            )
        elif not dst_attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"destination is not directory: {src_id!r} -> {dst_id!r}")
        elif self.exists(src_name, dst_id):
            raise FileExistsError(errno.EEXIST, f"destination already exists: {src_id!r} -> {dst_id!r}")
        self._copy(src_id, dst_id)
        dst_attr = self.attr(src_name, dst_id)
        return dst_attr["id"], src_name

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

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> str:
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{id_or_path!r} (in {pid!r}) is a directory")
        return self.client.download_url(attr["pick_code"])

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
            return self._files(attr["id"], limit=1)["count"] > 0
        return attr["size"] == 0

    def makedirs(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: Optional[int] = None, 
        exist_ok: bool = False, 
    ) -> tuple[int, str]:
        if isinstance(path, (str, PathLike)):
            patht, parents = splits(fspath(path))
        else:
            patht = [p for p in path if p]
            parents = 0
        if pid is None:
            pid = self.cid
        if not patht:
            if parents:
                ancestors = self.get_ancestors(pid)
                idx = min(parents-1, len(ancestors))
                attr = ancestors[-idx]
                return attr["id"], attr["name"]
            else:
                return pid, self.attr(pid)["name"]
        elif patht == [""]:
            return 0, ""
        exists = False
        get_attr = self._attr_path
        for name in patht:
            try:
                attr = get_attr(name, pid)
            except FileNotFoundError:
                exists = False
                resp = self._mkdir(name, pid)
                pid = int(resp["cid"])
                name = unicode_unescape(resp["cname"])
            else:
                exists = True
                if not attr["is_directory"]:
                    raise NotADirectoryError(errno.ENOTDIR, f"{path!r} (in {pid!r}): there is a superior non-directory")
                pid = attr["id"]
                name = attr["name"]
        if not exist_ok and exists:
            raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) exists")
        return cast(int, pid), name

    def mkdir(
        self, 
        path: str | PathLike[str] | Sequence[str], 
        /, 
        pid: Optional[int] = None, 
    ) -> tuple[int, str]:
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
                attr = get_attr(name, pid)
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
        return int(resp["cid"]), unicode_unescape(resp["cname"])

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
            if self.exists(name, dst_id):
                raise FileExistsError(errno.EEXIST, f"destination {name!r} (in {dst_id!r}) already exists")
            self._move(src_id, dst_id)
            return self._attr(src_id)
        raise FileExistsError(errno.EEXIST, f"destination {dst_id!r} already exists")

    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
        recursive: bool = False, 
    ):
        attr = self.attr(id_or_path, pid)
        id = attr["id"]
        if attr["is_directory"]:
            if not recursive:
                raise IsADirectoryError(errno.EISDIR, f"{id_or_path!r} (in {pid!r}) is a directory")
            if id == 0:
                for subattr in self.listdir_attr(id):
                    self._delete(subattr["id"])
        self._delete(id)

    def removedirs(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ):
        attr = self.attr(id_or_path, pid)
        if not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{id_or_path!r} (in {pid!r}) is not a directory")
        del_id = 0
        id = attr["id"]
        while id != 0:
            files = self._files(id, limit=1)
            if files["count"] > 1:
                break
            del_id = id
            id = files["path"][-1]["pid"]
        if del_id != 0:
            self._delete(del_id)

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
                return self._attr(src_id)
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
                        if self._files(dst_attr["id"], limit=1)["count"]:
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
            name = check_response(self.client.upload_file_sha1_simple)(
                dst_name, 
                filesize=src_attr["size"], 
                file_sha1=src_attr["sha1"], 
                read_bytes_range=lambda rng: self.read_bytes_range(src_id, rng), 
                pid=dst_pid, 
            )["fileinfo"]["filename"]
            self._delete(src_id)
            return self.attr(name, dst_pid)
        if src_name == dst_name:
            self._move(src_id, dst_pid)
            return self._attr(src_id)
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
            self.removedirs(self.attr(result[0])["parent_id"])
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

    rm  = remove

    def rmdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ):
        attr = self.attr(id_or_path, pid)
        id = attr["id"]
        if id == 0:
            raise PermissionError(errno.EPERM, "remove the root directory is not allowed")
        elif not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{id_or_path!r} (in {pid!r}) is not a directory")
        elif self._files(id, limit=1)["count"]:
            raise OSError(errno.ENOTEMPTY, f"directory is not empty: {id_or_path!r} (in {pid!r})")
        self._delete(id)
        return id

    def rmtree(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ):
        return self.remove(id_or_path, pid, recursive=True)

    def search(
        self, 
        search_value: str, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
        page_size: int = 1_000, 
        offset: int = 0, 
        as_path: bool = False, 
        **kwargs, 
    ):
        assert page_size > 0
        payload = {
            "cid": self.get_id(id_or_path, pid), 
            "search_value": search_value, 
            "limit": page_size, 
            "offset": offset, 
            **kwargs, 
        }
        if as_path:
            def wrap(attr):
                attr = normalize_info(attr, lastest_update=lastest_update)
                return P115Path(self, **attr)
        else:
            def wrap(attr):
                return normalize_info(attr, lastest_update=lastest_update)
        search = self._search
        while True:
            resp = search(payload)
            lastest_update = datetime.now()
            if resp["offset"] != offset:
                break
            data = resp["data"]
            if not data:
                return
            yield from map(wrap, resp["data"])
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
        lastest_update = attr.get("lastest_update") or datetime.now()
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o777, 
            attr["id"], 
            attr["parent_id"], 
            1, 
            self.client.user_id, 
            1, 
            0 if is_dir else attr["size"], 
            attr.get("open_time", lastest_update).timestamp(), 
            attr.get("etime", lastest_update).timestamp(), 
            attr.get("ptime", lastest_update).timestamp(), 
        ))

    def touch(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> dict:
        try:
            return self.attr(id_or_path, pid)
        except:
            if isinstance(id_or_path, int):
                raise ValueError(f"no such id: {id_or_path!r}")
            return self.upload(BytesIO(), id_or_path, pid=pid)

    def upload(
        self, 
        /, 
        file: bytes | str | PathLike | SupportsRead[bytes] | TextIOWrapper, 
        path: IDOrPathType = "", 
        pid: Optional[int] = None, 
        overwrite_or_ignore: Optional[bool] = None, 
    ) -> dict:
        fio: SupportsRead[bytes]
        dir_: str | Sequence[str] = ""
        name: str = ""
        if not path or isinstance(path, int):
            pass
        elif isinstance(path, (str, PathLike)):
            dir_, name = os_path.split(path)
        else:
            name, *dir_ = (p for p in path if p)
        if hasattr(file, "read"):
            fio = cast(SupportsRead[bytes], file)
            if isinstance(fio, TextIOWrapper):
                fio = fio.buffer
            if not name:
                try:
                    name = os_path.basename(file.name) # type: ignore
                except:
                    pass
        else:
            file = fsdecode(file)
            fio = open(file, "rb")
            if not name:
                name = os_path.basename(file)
        if not name:
            raise ValueError(f"can't determine the upload path: {path!r} (in {pid!r})")
        if pid is None:
            pid = self.cid
        if dir_:
            pid = self.makedirs(dir_, pid=pid, exist_ok=True)[0]
        try:
            attr = self.attr(name, pid)
        except FileNotFoundError:
            pass
        else:
            if overwrite_or_ignore is None:
                raise FileExistsError(errno.EEXIST, f"{path!r} (in {pid!r}) exists")
            elif attr["is_directory"]:
                raise IsADirectoryError(errno.EISDIR, f"{path!r} (in {pid!r}) is a directory")
            elif not overwrite_or_ignore:
                return attr["id"]
            self._delete(attr["id"])
        return self._upload(fio, name, pid)

    def upload_tree(
        self, 
        /, 
        local_path: str | PathLike[str] = ".", 
        path: IDOrPathType = "", 
        pid: Optional[int] = None, 
        no_root: bool = False, 
        overwrite_or_ignore: Optional[bool] = None, 
    ):
        try:
            attr = self.attr(path, pid)
        except FileNotFoundError:
            if isinstance(path, int):
                raise ValueError(f"no such id: {path!r}")
            pid = self.makedirs(path, pid, exist_ok=True)[0]
        else:
            if not attr["is_directory"]:
                raise NotADirectoryError(errno.ENOTDIR, f"{path!r} (in {pid!r}) is not a directory")
            pid = attr["id"]
        try:
            it = scandir(local_path or ".")
        except NotADirectoryError:
            return self.upload(
                local_path, 
                path, 
                pid=pid, 
                overwrite_or_ignore=overwrite_or_ignore, 
            )
        else:
            if not no_root:
                pid = self.makedirs(os_path.basename(local_path), pid, exist_ok=True)[0]
            for entry in it:
                if entry.is_dir():
                    self.upload_tree(
                        entry.path, 
                        entry.name, 
                        pid=pid, 
                        no_root=True, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                    )
                else:
                    self.upload(
                        entry.path, 
                        entry.name, 
                        pid=pid, 
                        overwrite_or_ignore=overwrite_or_ignore, 
                    )
            return pid

    unlink = remove

    def write_bytes(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        data: bytes | bytearray | BytesIO = b"", 
        pid: Optional[int] = None, 
    ) -> dict:
        if not isinstance(data, BytesIO):
            data = BytesIO(data)
        else:
            data.seek(0)
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
            tio = TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)
            tio.write(text)
        return self.write_bytes(id_or_path, bio, pid=pid)


class P115SharePath(P115PathBase):
    fs: P115ShareFileSystem


class P115ShareFileSystem(P115FileSystemBase[MappingProxyType, P115SharePath]):
    share_link: str
    share_code: str
    receive_code: str
    user_id: int
    path_to_id: MutableMapping[str, int]
    id_to_attr: MutableMapping[int, MappingProxyType]
    pid_to_attrs: MutableMapping[int, tuple[MappingProxyType]]
    full_loaded: bool
    path_class = P115SharePath

    def __init__(self, client: P115Client, /, share_link: str):
        m = CRE_SHARE_LINK.search(share_link)
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
            pid_to_attrs={}, 
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
    def create_time(self, /):
        return datetime.fromtimestamp(int(self.shareinfo["create_time"]))

    @property
    def sharedata(self, /) -> dict:
        return self._files(limit=1)["data"]

    @property
    def shareinfo(self, /) -> dict:
        return self.sharedata["shareinfo"]

    def _attr(self, id: int = 0, /) -> MappingProxyType:
        try:
            return self.id_to_attr[id]
        except KeyError:
            pass
        if self.full_loaded:
            raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")
        if id == 0:
            attr = self.id_to_attr[0] = MappingProxyType({
                "id": 0, 
                "parent_id": 0, 
                "name": "", 
                "path": "/", 
                "is_directory": True, 
                "time": self.create_time, 
            })
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
    ) -> MappingProxyType:
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
    ) -> MappingProxyType:
        if isinstance(id_or_path, P115SharePath):
            return self._attr(id_or_path["id"])
        elif isinstance(id_or_path, int):
            return self._attr(id_or_path)
        else:
            return self._attr_path(id_or_path, pid)

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> str:
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{id_or_path!r} (in {pid!r}) is a directory")
        return self.client.share_download_url({
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
            "file_id": attr["id"], 
        })

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[MappingProxyType]:
        attr = self.attr(id_or_path, pid)
        if not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{attr['path']!r} (id={attr['id']!r}) is not a directory")
        id = attr["id"]
        try:
            return iter(self.pid_to_attrs[id])
        except KeyError:
            dirname = attr["path"]
            def iterdir():
                page_size = 1 << 10
                get_files = self._files
                path_to_id = self.path_to_id
                data = get_files(id, page_size)["data"]
                for attr in map(normalize_info, data["list"]):
                    path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                    path_to_id[path] = attr["id"]
                    yield MappingProxyType(attr)
                for offset in range(page_size, data["count"], page_size):
                    data = get_files(id, page_size, offset)["data"]
                    for attr in map(normalize_info, data["list"]):
                        path = attr["path"] = joinpath(dirname, escape(attr["name"]))
                        path_to_id[path] = attr["id"]
                        yield MappingProxyType(attr)
            t = self.pid_to_attrs[id] = tuple(iterdir())
            self.id_to_attr.update((attr["id"], attr) for attr in t)
            return iter(t)

    def receive(self, ids: int | str | Iterable[int | str], /, cid: int = 0):
        if isinstance(ids, (int, str)):
            file_id = str(ids)
        else:
            file_id = ",".join(map(str, ids))
            if not file_id:
                raise ValueError("no id (to file) to transfer")
        payload = {
            "share_code": self.share_code, 
            "receive_code": self.receive_code, 
            "file_id": file_id, 
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
        lastest_update = attr.get("lastest_update") or datetime.now()
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | 0o444, 
            attr["id"], 
            attr["parent_id"], 
            1, 
            self.user_id, 
            1, 
            0 if is_dir else attr["size"], 
            attr.get("time", lastest_update).timestamp(), 
            attr.get("time", lastest_update).timestamp(), 
            attr.get("time", lastest_update).timestamp(), 
        ))


class P115ZipPath(P115PathBase):
    fs: P115ZipFileSystem
    path: str


# TODO: 参考zipfile的接口设计
# TODO: 检查一下是不是压缩包以及解压进度
# TODO: 要么只用 pickcode，而不是 file_id?
class P115ZipFileSystem(P115FileSystemBase[MappingProxyType, P115ZipPath]):
    file_id: int
    pick_code: str
    path_to_id: MutableMapping[str, int]
    id_to_attr: MutableMapping[int, MappingProxyType]
    pid_to_attrs: MutableMapping[int, tuple[MappingProxyType]]
    full_loaded: bool
    path_class = P115ZipPath

    def __init__(self, client: P115Client, /, file_id: int):
        pick_code = client.fs.attr(file_id)["pick_code"]
        self.__dict__.update(
            client=client, 
            cid=0, 
            path="/", 
            pick_code=pick_code, 
            file_id=file_id, 
            path_to_id={"/": 0}, 
            id_to_attr={}, 
            pid_to_attrs={}, 
            full_loaded=False, 
            _nextid=count(1).__next__, 
        )

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

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
    def create_time(self, /):
        return self.client.fs.attr(self.file_id)["ptime"]

    def _attr(self, id: int = 0, /) -> MappingProxyType:
        try:
            return self.id_to_attr[id]
        except KeyError:
            pass
        if self.full_loaded:
            raise FileNotFoundError(errno.ENOENT, f"no such id: {id!r}")
        if id == 0:
            attr = self.id_to_attr[0] = MappingProxyType({
                "id": 0, 
                "parent_id": 0, 
                "file_category": 0, 
                "is_directory": True, 
                "name": "", 
                "path": "/", 
                "size": 0, 
                "time": self.create_time, 
                "timestamp": int(self.create_time.timestamp()), 
            })
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
    ) -> MappingProxyType:
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
    ) -> MappingProxyType:
        if isinstance(id_or_path, P115ZipPath):
            return self._attr(id_or_path["id"])
        elif isinstance(id_or_path, int):
            return self._attr(id_or_path)
        else:
            return self._attr_path(id_or_path, pid)

    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: Optional[int] = None, 
    ) -> str:
        attr = self.attr(id_or_path, pid)
        if attr["is_directory"]:
            raise IsADirectoryError(errno.EISDIR, f"{id_or_path!r} (in {pid!r}) is a directory")
        return self.client.extract_download_url(self.pick_code, attr["path"])

    def iterdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: Optional[int] = None, 
    ) -> Iterator[MappingProxyType]:
        def normalize_info(info):
            timestamp = info.get("time") or 0
            return {
                "name": info["file_name"], 
                "is_directory": info["file_category"] == 0, 
                "file_category": info["file_category"], 
                "size": info["size"], 
                "time": datetime.fromtimestamp(timestamp), 
                "timestamp": timestamp, 
            }
        attr = self.attr(id_or_path, pid)
        if not attr["is_directory"]:
            raise NotADirectoryError(errno.ENOTDIR, f"{attr['path']!r} (id={attr['id']!r}) is not a directory")
        id = attr["id"]
        try:
            return iter(self.pid_to_attrs[id])
        except KeyError:
            nextid = self.__dict__["_nextid"]
            dirname = attr["path"]
            def iterdir():
                get_files = self._files
                path_to_id = self.path_to_id
                data = get_files(dirname)["data"]
                for attr in map(normalize_info, data["list"]):
                    path = joinpath(dirname, escape(attr["name"]))
                    attr.update(id=nextid(), parent_id=id, path=path)
                    path_to_id[path] = attr["id"]
                    yield MappingProxyType(attr)
                next_marker = data["next_marker"]
                while next_marker:
                    data = get_files(dirname, next_marker)["data"]
                    for attr in map(normalize_info, data["list"]):
                        path = joinpath(dirname, escape(attr["name"]))
                        attr.update(id=nextid(), parent_id=id, path=path)
                        path_to_id[path] = attr["id"]
                        yield MappingProxyType(attr)
                    next_marker = data["next_marker"]
            t = self.pid_to_attrs[id] = tuple(iterdir())
            self.id_to_attr.update((attr["id"], attr) for attr in t)
            return iter(t)

    def extract(self):
        ...
    # TODO: 其它解压方法，以及针对解压事件的 event.join()，以及进度查询


# TODO 清除已完成
# TODO 用户、密码登陆，直接用app端接口，不需要验证码
class P115Offline:

    def __init__(self, client, /):
        self.client = client
        self.uid = client.userid
        self.refresh_sign()

    def refresh_sign(self, /):
        self.sign = self.client.offline_getsign()["sign"]

    def add_url(self, /, url, pid="", savepath=""):
        payload = {
            "url": url,
            "savepath": savepath, 
            "wp_path_id": pid, 
            "uid": self.uid, 
            "sign": self.sign, 
            "time": int(time()), 
        }
        return self.client.offline_add_url(payload)

    def add_urls(self, /, urls, pid="", savepath=""):
        payload = {
            "savepath": savepath, 
            "wp_path_id": pid, 
            "uid": self.uid, 
            "sign": self.sign, 
            "time": int(time()), 
        }
        payload.update((f"url[{i}]", url) for i, url in enumerate(urls))
        return self.client.offline_add_urls(payload)

    def task_list(self, page=0):
        if page > 0:
            payload = {
                "page": page, 
                "uid": self.uid, 
                "sign": self.sign, 
                "time": int(time()), 
            }
            return self.client.offline_list(payload)
        page = 1
        payload = {
            "page": page, 
            "uid": self.uid, 
            "sign": self.sign, 
            "time": int(time()), 
        }
        resp = self.client.offline_list(payload)
        resp["page"] = 0
        ls = resp['tasks']
        if not ls:
            return resp
        for page in range(2, resp["page_count"]+1):
            payload["page"] = page
            sub_resp = self.client.offline_list(payload)
            ls.extend(sub_resp["tasks"])
        return resp

    def torrent_info(self, /, sha1_or_fid):
        payload = {
            "uid": self.uid, 
            "sign": self.sign, 
            "time": int(time()), 
        }
        if isinstance(sha1_or_fid, int):
            resp = self.client.fs_file(sha1_or_fid)
            data = resp["data"][0]
            payload["pickcode"] = data["pick_code"]
            payload["sha1"] = data["sha1"]
        else:
            payload["sha1"] = sha1_or_fid
        return self.client.offline_torrent_info(payload)

    def add_torrent(self, /, sha1_or_fid, savepath="", filter_func=None):
        resp = self.torrent_info(sha1_or_fid)
        if not resp["state"]:
            raise RuntimeError(resp)
        filelist = filter(filter_func, resp["torrent_filelist_web"])
        payload = {
            "wanted": ",".join(str(info["wanted"]) for info in filelist), 
            "info_hash": resp["info_hash"], 
            "savepath": savepath or resp["torrent_name"], 
            "uid": self.uid, 
            "sign": self.sign, 
            "time": int(time()), 
        }
        return self.client.offline_add_torrent(payload)

    def del_tasks(self, /, task_hashes):
        payload = {
            "uid": self.uid, 
            "sign": self.sign, 
            "time": int(time()), 
        }
        payload.update((f"hash[{i}]", h) for i, h in enumerate(task_hashes))
        return self.client.offline_del(payload)


class P115Recyclebin:
    ...



# TODO: 对回收站的封装
# TODO: 能及时处理文件已不存在
# TODO: 为各个fs接口添加额外的请求参数
# TODO: 115中多个文件可以在同一目录下同名，如何处理？
# TODO: 是否要支持 cd2 的改名策略，也就是遇到 **.，则自动忽略后面的所有部分，改名时，改成 新名字 + **. + 原始扩展名
# TODO: 批量改名工具：如果后缀名一样，则直接改名，如果修改了后缀名，那就尝试用秒传，重新上传，上传如果失败，因为名字问题，则尝试用uuid名字，上传成功后，再进行改名，如果成功，删除原来的文件，不成功，则删掉上传的文件（如果上传了的话）
#       - file 参数支持接受一个 callable：由于上传时，给出 sha1 本身可能就能成功，为了速度，我认为，一开始就不需要打开一个文件
#       - 增加 read_range: 由于文件可以一开始就 seek 到目标位置，因此一开始就可以指定对应的位置，因此可以添加一个方法，叫 readrange，直接读取一定范围的 http 数据

# TODO: File 对象要可以获取 url，而且尽量利用 client 上的方法，ShareFile 也要有相关方法（例如转存）
# TODO: 支持异步io，用 aiohttp
# TODO 因为获取 url 是个耗时的操作，因此需要缓存

