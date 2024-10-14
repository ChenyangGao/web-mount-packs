#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "relogin_wrap_maker", "login_scan_cookies", "crack_captcha", "remove_receive_dir", 
    "wish_make", "wish_answer", "wish_list", "wish_aid_list", "wish_adopt", 
]

from asyncio import Lock as AsyncLock
from collections import defaultdict, deque, ChainMap
from collections.abc import Callable, Collection, Hashable, Iterable, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from inspect import isawaitable
from io import TextIOBase, TextIOWrapper
from itertools import chain, islice, takewhile
from operator import itemgetter
from os import PathLike
from posixpath import splitext
from re import compile as re_compile
from sys import _getframe
from threading import Lock
from time import sleep, time
from types import MappingProxyType
from typing import cast, Any, Final, IO, Literal, NamedTuple, TypeVar
from warnings import warn
from weakref import WeakKeyDictionary

from concurrenttools import thread_pool_batch
from dictattr import AttrDict
from httpx import HTTPStatusError, ReadTimeout
from iter_collect import grouped_mapping, iter_keyed_dups, SupportsLT
from p115.component.client import check_response, ExportDirStatus, P115Client
from p115.component.fs import normalize_attr
from posixpatht import escape


K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

CAPTCHA_CRACK: Callable[[bytes], str]


def _check_for_relogin(e: BaseException) -> bool:
    status = getattr(e, "status", None) or getattr(e, "code", None) or getattr(e, "status_code", None)
    if status is None and hasattr(e, "response"):
        response = e.response
        status = getattr(response, "status", None) or getattr(response, "code", None) or getattr(response, "status_code", None)
    return status == 405


def relogin_wrap_maker(
    relogin: None | Callable[[], Any] = None, 
    client: None | P115Client = None, 
    check_for_relogin: Callable[[BaseException], bool | int] = _check_for_relogin, 
    lock: None | AbstractContextManager | AbstractAsyncContextManager = None,   
) -> Callable:
    """包装调用：执行调用，成功则返回，当遇到特定错误则重新登录后循环此流程

    :param relogin: 调用以自定义重新登录，如果为 None，则用默认的重新登录
    :param client: 115 客户端或 cookies，当 relogin 为 None 时被使用
    :param check_for_relogin: 检查以确定是否要重新登录，如果为 False，则抛出异常
        - 如果值为 bool，如果为 True，则重新登录
        - 如果值为 int，则视为返回码，当值为 405 时会重新登录
    :param lock: 如果不为 None，执行调用时加这个锁（或上下文管理器）

    :return: 返回函数，用于执行调用，必要时会重新登录再重试
    """
    if relogin is None:
        d: WeakKeyDictionary[P115Client, tuple[AbstractContextManager, AbstractAsyncContextManager]] = WeakKeyDictionary()
    def wrapper(func, /, *args, **kwargs):
        nonlocal client
        if relogin is None:
            if client is None:
                f = func
                while hasattr(f, "__wrapped__"):
                    f = f.__wrapped__
                if hasattr(f, "__self__"):
                    f = f.__self__
                if isinstance(f, P115Client):
                    client = f
                elif hasattr(f, "client"):
                    client = f.client
                else:
                    frame = _getframe(1)
                    client = ChainMap(frame.f_locals, frame.f_globals, frame.f_builtins)["client"]
            elif not isinstance(client, P115Client):
                client = P115Client(client)
            if not isinstance(client, P115Client):
                raise ValueError("no awailable client")
            try:
                relogin_lock, relogin_alock = d[client]
            except KeyError:
                relogin_lock, relogin_alock = d[client] = (Lock(), AsyncLock())
        is_cm = isinstance(lock, AbstractContextManager)
        while True:
            try:
                if is_cm:
                    with cast(AbstractContextManager, lock):
                        ret = func(*args, **kwargs)
                else:
                    ret = func(*args, **kwargs)
                if isawaitable(ret):
                    is_acm = isinstance(lock, AbstractAsyncContextManager)
                    async def wrap(ret):
                        while True:
                            try:
                                if is_cm:
                                    with cast(AbstractContextManager, lock):
                                        return await ret
                                elif is_acm:
                                    async with cast(AbstractAsyncContextManager, lock):
                                        return await ret
                                else:
                                    return await ret
                            except BaseException as e:
                                res = check_for_relogin(e)
                                if isawaitable(res):
                                    res = await res
                                if not res if isinstance(res, bool) else res != 405:
                                    raise
                                if relogin is None:
                                    client = cast(P115Client, client)
                                    cookies = client.cookies
                                    async with relogin_alock:
                                        if cookies == client.cookies:
                                            await client.login_another_app(replace=True, async_=True)
                                else:
                                    res = relogin()
                                    if isawaitable(res):
                                        await res
                                ret = func(*args, **kwargs)
                    return wrap(ret)
                else:
                    return ret
            except HTTPStatusError as e:
                res = check_for_relogin(e)
                if not res if isinstance(res, bool) else res != 405:
                    raise
                if relogin is None:
                    client = cast(P115Client, client)
                    cookies = client.cookies
                    with relogin_lock:
                        if cookies == client.cookies:
                            client.login_another_app(replace=True)
                else:
                    relogin()
    return wrapper


def login_scan_cookies(
    client: str | P115Client, 
    app: str = "", 
    replace: bool = False, 
) -> str:
    """扫码登录 115 网盘，获取绑定到特定 app 的 cookies
    app 至少有 24 个可用值，目前找出 14 个：
        - web
        - ios
        - 115ios
        - android
        - 115android
        - 115ipad
        - tv
        - qandroid
        - windows
        - mac
        - linux
        - wechatmini
        - alipaymini
        - harmony
    还有几个备选：
        - bios
        - bandroid
        - qios（登录机制有些不同，暂时未破解）

    设备列表如下：

    | No.    | ssoent  | app        | description            |
    |-------:|:--------|:-----------|:-----------------------|
    |     01 | A1      | web        | 网页版                 |
    |     02 | A2      | ?          | 未知: android          |
    |     03 | A3      | ?          | 未知: iphone           |
    |     04 | A4      | ?          | 未知: ipad             |
    |     05 | B1      | ?          | 未知: android          |
    |     06 | D1      | ios        | 115生活(iOS端)         |
    |     07 | D2      | ?          | 未知: ios              |
    |     08 | D3      | 115ios     | 115(iOS端)             |
    |     09 | F1      | android    | 115生活(Android端)     |
    |     10 | F2      | ?          | 未知: android          |
    |     11 | F3      | 115android | 115(Android端)         |
    |     12 | H1      | ipad       | 未知: ipad             |
    |     13 | H2      | ?          | 未知: ipad             |
    |     14 | H3      | 115ipad    | 115(iPad端)            |
    |     15 | I1      | tv         | 115网盘(Android电视端) |
    |     16 | M1      | qandriod   | 115管理(Android端)     |
    |     17 | N1      | qios       | 115管理(iOS端)         |
    |     18 | O1      | ?          | 未知: ipad             |
    |     19 | P1      | windows    | 115生活(Windows端)     |
    |     20 | P2      | mac        | 115生活(macOS端)       |
    |     21 | P3      | linux      | 115生活(Linux端)       |
    |     22 | R1      | wechatmini | 115生活(微信小程序)    |
    |     23 | R2      | alipaymini | 115生活(支付宝小程序)  |
    |     24 | S1      | harmony    | 115(Harmony端)         |
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    if not app:
        if (resp := client.login_device()) is None:
            raise RuntimeError("this cookies may be logged out")
        app = resp["icon"]
    return client.login_another_app(app, replace=replace).cookies


def crack_captcha(
    client: str | P115Client, 
    sample_count: int = 16, 
    crack: None | Callable[[bytes], str] = None, 
) -> bool:
    """破解 115 的图片验证码。如果返回 True，则说明破解成功，否则失败。如果失败，就不妨多运行这个函数几次。

    :param client: 115 客户端或 cookies
    :param sample_count: 单个文字的采样次数，共会执行 10 * sample_count 次识别
    :param crack: 破解验证码图片，输入图片的二进制数据，输出识别的字符串

    :return: 是否破解成功

    你可以反复尝试，直到破解成功，代码如下

        while not crack_captcha(client):
            pass

    如果你需要检测是否存在验证码，然后进行破解，代码如下

        resp = client.download_url_web("a")
        if not resp["state"] and resp["code"] == 911:
            print("出现验证码，尝试破解")
            while not crack_captcha(client):
                print("破解失败，再次尝试")
    """
    global CAPTCHA_CRACK
    if crack is None:
        try:
            crack = CAPTCHA_CRACK
        except NameError:
            try:
                # https://pypi.org/project/ddddocr/
                from ddddocr import DdddOcr
            except ImportError:
                from subprocess import run
                from sys import executable
                run([executable, "-m", "pip", "install", "-U", "ddddocr==1.4.11"], check=True)
                from ddddocr import DdddOcr # type: ignore
            crack = CAPTCHA_CRACK = cast(Callable[[bytes], str], DdddOcr(show_ad=False).classification)
    if not isinstance(client, P115Client):
        client = P115Client(client)
    while True:
        captcha = crack(client.captcha_code())
        if len(captcha) == 4 and all("\u4E00" <= char <= "\u9FFF" for char in captcha):
            break
    ls: list[defaultdict[str, int]] = [defaultdict(int) for _ in range(10)]
    def crack_single(i, submit):
        try:
            char = crack(client.captcha_single(i))
            if len(char) == 1 and "\u4E00" <= char <= "\u9FFF":
                ls[i][char] += 1
            else:
                submit(i)
        except:
            submit(i)
    thread_pool_batch(crack_single, (i for i in range(10) for _ in range(sample_count)))
    l: list[str] = [max(d, key=lambda k: d[k]) for d in ls]
    try:
        code = "".join(str(l.index(char)) for char in captcha)
    except ValueError:
        return False
    resp = client.captcha_verify(code)
    return resp["state"]


def remove_receive_dir(client: P115Client, password: str):
    """删除目录 "/我的接收"

    :param client: 115 客户端或 cookies
    :param password: 回收站密码（即 安全密钥，是 6 位数字）
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    fs = client.fs
    try:
        attr = fs.attr("/我的接收", ensure_dir=True)
    except FileNotFoundError:
        return
    now = str(int(time()))
    fs.rmtree(attr)
    recyclebin = client.recyclebin
    while True:
        for i, info in enumerate(recyclebin):
            # NOTE: 因为删除后，并不能立即在回收站看到被删除的文件夹，所以看情况需要等一等
            if not i and info["dtime"] < now:
                sleep(0.1)
                break
            if info["cid"] == 0 and info["file_name"] == "我的接收":
                recyclebin.remove(info["id"], password)
                return


def wish_make(
    client: str | P115Client, 
    content: str = "随便许个愿", 
    size: int = 5, 
) -> str:
    """许愿树活动：创建许愿（许愿创建后需要等审核）

    :param client: 115 客户端或 cookies
    :param content: 许愿内容
    :param size: 答谢空间大小，单位是 GB

    :return: 许愿 id
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    return check_response(client.act_xys_wish(
        {"rewardSpace": size, "content": content}
    ))["data"]["xys_id"]


def wish_answer(
    client: str | P115Client, 
    wish_id: str, 
    content: str = "帮你助个愿", 
    file_ids: int | str | Iterable[int | str] = "", 
) -> str:
    """许愿树活动：创建助愿（助愿创建后需要等审核）

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id
    :param content: 助愿内容
    :param file_ids: 文件在你的网盘的 id，多个用逗号 "," 隔开

    :return: 助愿 id
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    if not isinstance(file_ids, (int, str)):
        file_ids = ",".join(map(str, file_ids))
    check_response(client.act_xys_get_desire_info(wish_id))
    return check_response(
        client.act_xys_aid_desire({"id": wish_id, "content": content, "file_ids": file_ids}
    ))["data"]["aid_id"]


def wish_list(
    client: str | P115Client, 
    type: int = 0, 
) -> list[dict]:
    """许愿树活动：我的许愿列表

    :param client: 115 客户端或 cookies
    :param type: 类型
        - 0: 全部
        - 1: 进行中
        - 2: 已实现

    :return: 许愿列表
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    payload: dict = {"type": type, "limit": 1000, "page": 1}
    ls = adds = check_response(client.act_xys_my_desire(payload))["data"]["list"]
    while len(adds) == 1000:
        payload["page"] += 1
        adds = check_response(client.act_xys_my_desire(payload))["data"]["list"]
        ls.extend(adds)
    return ls


def wish_aid_list(
    client: str | P115Client, 
    wish_id: str, 
) -> list[dict]:
    """许愿树活动：许愿的助愿列表

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id

    :return: 助愿列表
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    payload: dict = {"id": wish_id, "limit": 1000, "page": 1}
    ls = adds = check_response(client.act_xys_desire_aid_list(payload))["data"]["list"]
    while len(adds) == 1000:
        payload["page"] += 1
        adds = check_response(client.act_xys_desire_aid_list(payload))["data"]["list"]
        ls.extend(adds)
    return ls


def wish_adopt(
    client: str | P115Client, 
    wish_id: str, 
    aid_id: int | str, 
    to_cid: int = 0, 
) -> dict:
    """许愿树活动：采纳助愿

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id
    :param aid_id: 助愿 id
    :param to_cid: 助愿的分享文件保存到你的网盘中目录的 id

    :return: 返回信息
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    return check_response(client.act_xys_adopt({"did": wish_id, "aid": aid_id, "to_cid": to_cid}))

