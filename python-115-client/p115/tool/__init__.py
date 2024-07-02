#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "login_scan_cookie", "crack_captcha", "wish_make", "wish_answer", 
    "wish_list", "wish_aid_list", "wish_adopt", 
    "parse_export_dir_as_dict_iter", "parse_export_dir_as_path_iter", 
    "export_dir", "export_dir_parse_iter", 
]

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from io import TextIOBase, TextIOWrapper
from os import PathLike
from re import compile as re_compile
from typing import cast, IO

from concurrenttools import thread_pool_batch
from p115.component.client import check_response, ExportDirStatus, P115Client
from posixpatht import escape


CAPTCHA_CRACK: Callable[[bytes], str]
CRE_TREE_PREFIX_match = re_compile("^(?:\| )+\|-").match


def login_scan_cookie(
    client: str | P115Client, 
    app: str = "", 
    replace: bool = False, 
) -> str:
    """扫码登录 115 网盘，获取绑定到特定 app 的 cookies
    app 至少有 23 个可用值，目前找出 13 个：
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
    """
    if isinstance(client, str):
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
    if isinstance(client, str):
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
    if isinstance(client, str):
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
    if isinstance(client, str):
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
    """
    if isinstance(client, str):
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
    """
    if isinstance(client, str):
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
    """
    if isinstance(client, str):
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
    if isinstance(file, (bytes | str | PathLike)):
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
    if isinstance(file, (bytes | str | PathLike)):
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
    """
    if isinstance(client, str):
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
    if isinstance(client, str):
        client = P115Client(client)
    future = export_dir(client, export_file_ids, target_pid)
    result = future.result()
    url = client.download_url(result["pick_code"], use_web_api=True)
    try:
        with client.open(url) as file:
            yield from parse_iter(file)
    finally:
        client.fs_delete(result["file_id"])

