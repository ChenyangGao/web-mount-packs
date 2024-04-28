#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["login_scan_cookie", "crack_captcha"]

from collections.abc import Callable
from typing import cast

from p115 import P115Client


CAPTCHA_CRACK: Callable[[bytes], str]


def login_scan_cookie(
    client: str | P115Client, 
    app: str = "web", 
) -> str:
    """扫码登录 115 网盘，获取绑定到特定 app 的 cookie

    app 共有 17 个可用值，目前找出 10 个：
        - web
        - android
        - ios
        - linux
        - mac
        - windows
        - tv
        - alipaymini
        - wechatmini
        - qandroid
    """
    if isinstance(client, str):
        client = P115Client(client)
    uid = client.login_qrcode_token()["data"]["uid"]
    client.login_qrcode_scan(uid)
    client.login_qrcode_scan_confirm(uid)
    data = client.login_qrcode_result({"account": uid, "app": app})
    return "; ".join(f"{k}={v}" for k, v in data["data"]["cookie"].items())


def crack_captcha(
    client: str | P115Client, 
    sample_count: int = 16, 
    crack: None | Callable[[bytes], str] = None, 
) -> bool:
    """破解 115 的图片验证码。如果返回 True，则说明破解成功，否则失败。如果失败，就不妨多运行这个函数几次。

    :param client: 115 客户端
    :param sample_count: 单个文字的采样次数，共会执行 10 * sample_count 次识别
    :param crack: 破解验证码图片，输入图片的二进制数据，输出识别的字符串

    :return: 是否破解成功

    你可以反复尝试，直到破解成功，代码如下

        while not crack_115_captcha(client):
            pass
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
                run([executable, "-m", "pip", "install", "-U", "ddddocr"], check=True)
                from ddddocr import DdddOcr # type: ignore
            crack = CAPTCHA_CRACK = cast(Callable[[bytes], str], DdddOcr(show_ad=False).classification)
    if isinstance(client, str):
        client = P115Client(client)
    while True:
        captcha = crack(client.captcha_code())
        if len(captcha) == 4:
            break
    l: list[str] = []
    for i in range(10):
        d: dict[str, int] = {}
        for _ in range(sample_count):
            while True:
                char = crack(client.captcha_single(i))
                if len(char) == 1:
                    break
            try:
                d[char] += 1
            except KeyError:
                d[char] = 1
        l.append(max(d, key=lambda k: d[k]))
    try:
        code = "".join(str(l.index(char)) for char in captcha)
    except ValueError:
        return False
    resp = client.captcha_verify(code)
    return resp["state"]

