#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "relogin_wrap_maker", "login_scan_cookie", "crack_captcha", "remove_receive_dir", 
    "wish_make", "wish_answer", "wish_list", "wish_aid_list", "wish_adopt", 
    "parse_export_dir_as_dict_iter", "parse_export_dir_as_path_iter", "export_dir", 
    "export_dir_parse_iter", "iterdir", "traverse_files", "iterate_over_files", 
    "traverse_stared_dirs", "dict_traverse_files", 
]

from asyncio import Lock as AsyncLock
from collections import defaultdict, deque, ChainMap
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence, Set
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from inspect import isawaitable
from io import TextIOBase, TextIOWrapper
from itertools import takewhile
from os import PathLike
from re import compile as re_compile
from sys import _getframe
from threading import Lock
from time import sleep, time
from typing import cast, Any, IO
from warnings import warn
from weakref import WeakKeyDictionary

from concurrenttools import thread_pool_batch
from dictattr import AttrDict
from httpx import HTTPStatusError, ReadTimeout
from p115.component.client import check_response, ExportDirStatus, P115Client
from p115.component.fs import normalize_attr
from posixpatht import escape


CAPTCHA_CRACK: Callable[[bytes], str]
CRE_TREE_PREFIX_match = re_compile("^(?:\| )+\|-").match


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


def login_scan_cookie(
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


def parse_export_dir_as_dict_iter(
    file: bytes | str | PathLike | IO, 
    encoding: str = "utf-16", 
) -> Iterator[dict]:
    """解析 115 导出的目录树（可通过 P115Client.fs_export_dir 提交导出任务）

    :param file: 文件路径或已经打开的文件
    :param encoding: 文件编码，默认为 "utf-16"

    :return: 把每一行解析为一个字典，迭代返回，格式为

        .. python:

            {
                "key":        int, # 序号
                "parent_key": int, # 上级目录的序号
                "depth":      int, # 深度
                "name":       str, # 名字
            }
    """
    if isinstance(file, (bytes, str, PathLike)):
        file = open(file, encoding=encoding)
    elif not isinstance(file, TextIOBase):
        file = TextIOWrapper(file, encoding=encoding)
    stack = [0]
    for i, r in enumerate(file):
        match = CRE_TREE_PREFIX_match(r)
        if match is None:
            continue
        prefix = match[0]
        prefix_length = len(prefix)
        depth = prefix_length // 2 - 1
        yield {
            "key": i, 
            "parent_key": stack[depth-1], 
            "depth": depth, 
            "name": r.removesuffix("\n")[prefix_length:], 
        }
        try:
            stack[depth] = i
        except IndexError:
            stack.append(i)


def parse_export_dir_as_path_iter(
    file: bytes | str | PathLike | IO, 
    encoding: str = "utf-16", 
) -> Iterator[str]:
    """解析 115 导出的目录树（可通过 P115Client.fs_export_dir 提交导出任务）

    :param file: 文件路径或已经打开的文件
    :param encoding: 文件编码，默认为 "utf-16"

    :return: 把每一行解析为一个相对路径（虽然左边第 1 个符号是 "/"），迭代返回
    """
    if isinstance(file, (bytes, str, PathLike)):
        file = open(file, encoding=encoding)
    elif not isinstance(file, TextIOBase):
        file = TextIOWrapper(file, encoding=encoding)
    stack = [""]
    for r in file:
        match = CRE_TREE_PREFIX_match(r)
        if match is None:
            continue
        prefix = match[0]
        prefix_length = len(prefix)
        depth = prefix_length // 2 - 1
        path = stack[depth-1] + "/" + escape(r.removesuffix("\n")[prefix_length:])
        try:
            stack[depth] = path
        except IndexError:
            stack.append(path)
        yield path


def export_dir(
    client: str | P115Client, 
    export_file_ids: int | str | Iterable[int] = 0, 
    target_pid: int | str = 0, 
) -> ExportDirStatus:
    """导出目录树

    :param client: 115 客户端或 cookies
    :param export_file_ids: 待导出的文件夹 id 或 路径
    :param target_pid: 导出到的目标文件夹 id 或 路径

    :return: 返回对象以获取进度
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    if isinstance(export_file_ids, str):
        export_file_ids = client.fs.get_id(export_file_ids, pid=0)
    elif not isinstance(export_file_ids, int):
        export_file_ids = ",".join(map(str, export_file_ids))
    if isinstance(target_pid, str):
        target_pid = client.fs.get_id(target_pid, pid=0)    
    return client.fs_export_dir_future({"file_ids": export_file_ids, "target": f"U_0_{target_pid}"})


def export_dir_parse_iter(
    client: str | P115Client, 
    export_file_ids: int | str | Iterable[int] = 0, 
    target_pid: int | str = 0, 
    parse_iter: Callable[[IO[bytes]], Iterator] = parse_export_dir_as_path_iter, 
) -> Iterator:
    """导出目录树到文件，读取文件并解析后返回生成器，关闭后自动删除导出的文件

    :param client: 115 客户端或 cookies
    :param export_file_ids: 待导出的文件夹 id 或 路径
    :param target_pid: 导出到的目标文件夹 id 或 路径
    :param parse_iter: 解析打开的二进制文件，返回可迭代对象

    :return: 解析导出文件的迭代器
    """
    if not isinstance(client, P115Client):
        client = P115Client(client)
    future = export_dir(client, export_file_ids, target_pid)
    result = future.result()
    url = client.download_url(result["pick_code"], use_web_api=True)
    try:
        with client.open(url) as file:
            yield from parse_iter(file)
    finally:
        client.fs_delete(result["file_id"])


def iterdir(
    client: str | P115Client, 
    cid: int = 0, 
    page_size: int = 10_000, 
) -> Iterator[AttrDict]:
    """迭代目录，获取文件信息

    :param client: 115 客户端或 cookies
    :param cid: 目录 id
    :param page_size: 分页大小

    :return: 迭代器，返回此目录内的文件信息（文件和目录）
    """
    if isinstance(client, str):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 10_000
    offset = 0
    payload = {"asc": 1, "cid": cid, "limit": page_size, "o": "user_ptime", "offset": offset}
    count = 0
    while True:
        resp = check_response(client.fs_files(payload))
        if int(resp["path"][-1]["cid"]) != cid:
            raise FileNotFoundError(2, cid)
        if count == 0:
            count = resp["count"]
        elif count != resp["count"]:
            raise RuntimeError(f"{cid} detected count changes during iteration")
        yield from map(normalize_attr, resp["data"])
        offset += len(resp["data"])
        if offset >= count:
            break
        payload["offset"] = offset


def traverse_files(
    client: str | P115Client, 
    cid: int = 0, 
    page_size: int = 10_000, 
) -> Iterator[AttrDict]:
    """遍历目录树，获取文件信息

    :param client: 115 客户端或 cookies
    :param cid: 目录 id
    :param page_size: 分页大小

    :return: 迭代器，返回此目录内的（仅文件）文件信息
    """
    if isinstance(client, str):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 10_000
    offset = 0
    payload = {"asc": 1, "cid": cid, "cur": 0, "limit": page_size, "o": "user_ptime", "offset": offset, "type": 99}
    count = 0
    while True:
        resp = check_response(client.fs_files(payload))
        if int(resp["path"][-1]["cid"]) != cid:
            raise FileNotFoundError(2, cid)
        if count == 0:
            count = resp["count"]
        elif count != resp["count"]:
            warn(f"{cid} detected count changes during traversing: {count} => {resp['count']}")
            count = resp["count"]
        if offset != resp["offset"]:
            break
        yield from map(normalize_attr, resp["data"])
        offset += len(resp["data"])
        if offset >= count:
            break
        payload["offset"] = offset


def iterate_over_files(
    client: str | P115Client, 
    cid: int = 0, 
    page_size: int = 10_000, 
) -> Iterator[AttrDict]:
    """遍历目录树，获取文件信息（会根据统计信息，分解任务）

    :param client: 115 客户端或 cookies
    :param cid: 目录 id
    :param page_size: 分页大小

    :return: 迭代器，返回此目录内的（仅文件）文件信息
    """
    if isinstance(client, str):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 10_000
    dq: deque[int] = deque()
    get, put = dq.pop, dq.appendleft
    put(cid)
    while dq:
        if cid := get():
            try:
                stats = client.fs_statistic(cid, timeout=5)
            except ReadTimeout:
                file_count = float("inf")
            else:
                if not stats:
                    warn(f"{cid} does not exist")
                    continue
                file_count = int(stats["count"])
            if file_count < 150_000:
                yield from traverse_files(client, cid, page_size)
                continue
        for attr in iterdir(client, cid, page_size):
            if attr["is_directory"]:
                put(attr["id"])
            else:
                yield attr


def traverse_stared_dirs(
    client: str | P115Client, 
    page_size: int = 10_000, 
    find_ids: None | Iterable[int] = None, 
) -> Iterator[AttrDict]:
    """遍历以迭代获得所有被打上星标的目录信息

    :param client: 115 客户端或 cookies
    :param page_size: 分页大小
    :param find_ids: 需要寻找的 id 集合。如果为 None 或空，则拉取所有打星标的文件夹；否则当找到所有这些 id 时就立即终止，
                     但如果从网上全部拉取完，还有一些 id 没被看到，则报错 RuntimeError

    :return: 迭代器，被打上星标的目录信息
    """
    if isinstance(client, str):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 10_000
    offset = 0
    payload = {
        "asc": 1, "cid": 0, "count_folders": 1, "cur": 0, "fc_mix": 0, "limit": page_size, 
        "o": "user_ptime", "offset": offset, "show_dir": 1, "star": 1, 
    }
    if find_ids:
        if not isinstance(find_ids, (Mapping, Set, Sequence)):
            find_ids = tuple(find_ids)
        need_to_find = set(find_ids)
    count = 0
    while True:
        resp = check_response(client.fs_files(payload))
        if count == 0:
            count = resp.get("folder_count", 0)
        elif count != resp.get("folder_count", 0):
            warn(f"detected count changes during traversing stared dirs: {count} => {resp.get('folder_count', 0)}")
            count = resp.get("folder_count", 0)
        if not count:
            break
        if offset != resp["offset"]:
            break
        for attr in map(normalize_attr, takewhile(lambda info: "fid" not in info, resp["data"])):
            yield attr
            if find_ids and attr["id"] in need_to_find:
                need_to_find.remove(attr["id"])
                if not need_to_find:
                    return
        offset += len(resp["data"])
        if offset >= count:
            break
        payload["offset"] = offset
    if find_ids and need_to_find:
        raise RuntimeError(f"unable to find these ids: {need_to_find!r}")


def dict_traverse_files(
    client: str | P115Client, 
    cid: int = 0, 
    page_size: int = 10_000, 
    with_path: bool = False, 
    escape: None | Callable[[str], str] = escape, 
    type=99, 
    suffix="", 
    **payload, 
) -> dict[int, AttrDict]:
    """获取一个目录内的所有文件信息

    :param client: 115 客户端或 cookies
    :param cid: 待被遍历的目录 id，默认为根目录
    :param page_size: 分页大小
    :param with_path: 文件信息中是否要包含 路径
    :param escape: 对文件名进行转义的函数。如果为 None，则不处理；否则，这个函数用来对文件名中某些符号进行转义，例如 "/" 等
    :param payload: 一些其它的请求参数，只介绍 2 个
        1. type: 文件类型
            - 全部: 0 # 注意：为 0 时不能遍历目录树
            - 文档: 1
            - 图片: 2
            - 音频: 3
            - 视频: 4
            - 压缩包: 5
            - 应用: 6
            - 书籍: 7
            - 仅文件: 99
        2. suffix: 后缀名

    :return: 字典，key 是 id，value 是 文件信息
    """
    if isinstance(client, str):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 10_000
    offset = 0
    payload.update(cid=cid, limit=page_size, offset=offset, suffix=suffix, type=type)
    payload.setdefault("cur", 0)
    id_to_attr: dict[int, AttrDict] = {}
    count = 0
    while True:
        resp = check_response(client.fs_files(payload))
        if int(resp["path"][-1]["cid"]) != cid:
            raise FileNotFoundError(2, cid)
        if count == 0:
            count = resp["count"]
        elif count != resp["count"]:
            warn(f"{cid} detected count changes during traversing: {count} => {resp['count']}")
            count = resp["count"]
        if offset != resp["offset"]:
            break
        id_to_attr.update((attr["id"], attr) for attr in map(normalize_attr, resp["data"]))
        offset += len(resp["data"])
        if offset >= count:
            break
        payload["offset"] = offset
    if with_path:
        if all(a["parent_id"] == cid for a in id_to_attr.values()):
            if cid == 0:
                dirname = "/"
            elif escape is None:
                dirname = "/".join(p["name"] for p in resp["path"]) + "/"
            else:
                dirname = "/".join(escape(p["name"]) for p in resp["path"]) + "/"
            for attr in id_to_attr.values():
                name = attr["name"]
                if escape is not None:
                    name = escape(name)
                attr["path"] = dirname + name
        else:
            def get_path(attr, /) -> str:
                pid = attr["parent_id"]
                name = attr["name"]
                if escape is not None:
                    name = escape(name)
                if pid == 0:
                    return "/" + name
                else:
                    pattr = id_to_dir[pid]
                    if "path" in pattr:
                        dirname = pattr["path"]
                    else:
                        dirname = pattr["path"] = get_path(pattr)
                    return dirname + "/" + name
            id_to_dir: dict[int, dict] = {}
            for p in resp["path"][1:]:
                category_id = int(p["cid"])
                id_to_dir[category_id] = {
                    "id": category_id, 
                    "parent_id": int(p["pid"]), 
                    "name": p["name"], 
                }
            for attr in id_to_attr.values():
                if attr["is_directory"]:
                    id_to_dir[category_id] = attr
            for attr in traverse_stared_dirs(client, page_size):
                id_to_dir[attr["id"]] = attr
            pids = {pid for pid in (a["parent_id"] for a in id_to_attr.values()) if pid != cid}
            while pids:
                find_ids = pids - id_to_dir.keys()
                if find_ids:
                    client.fs_star_set(",".join(map(str, find_ids)))
                    for attr in traverse_stared_dirs(client, page_size, find_ids):
                        id_to_dir[attr["id"]] = attr
                pids = {pid for pid in (id_to_dir[id]["parent_id"] for id in pids) if pid != cid}
            for attr in id_to_attr.values():
                attr["path"] = get_path(attr)
    return id_to_attr

# TODO: 为 imglist 实现 traverse_imglist 和 dict_traverse_imglist 函数
