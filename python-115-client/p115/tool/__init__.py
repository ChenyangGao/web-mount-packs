#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["login_scan_cookie", "crack_captcha"]

from collections import defaultdict
from collections.abc import Callable
from typing import cast

from concurrenttools import thread_pool_batch
from p115 import P115Client


CAPTCHA_CRACK: Callable[[bytes], str]


def login_scan_cookie(
    client: str | P115Client, 
    app: str = "web", 
) -> str:
    """扫码登录 115 网盘，获取绑定到特定 app 的 cookie

    app 共有 17 个可用值，目前找出 10 个：
        - web
        - ios
        - android
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
        - qios

    设备列表如下：

    | No.    | ssoent  | app        | description            |
    |-------:|:--------|:-----------|:-----------------------|
    |      1 | A1      | web        | 网页版                 |
    |      2 | A2      | ?          | 未知: android          |
    |      3 | A3      | ?          | 未知: iphone           |
    |      4 | A4      | ?          | 未知: ipad             |
    |      5 | B1      | ?          | 未知: android          |
    |      6 | D1      | ios        | 115生活(iOS端)         |
    |      7 | F1      | android    | 115生活(Android端)     |
    |      8 | H1      | ?          | 未知: ipad             |
    |      9 | I1      | tv         | 115网盘(Android电视端) |
    |     10 | M1      | qandriod   | 115管理(Android端)     |
    |     11 | N1      | qios       | 115管理(iOS端)         |
    |     12 | O1      | ?          | 未知: ipad             |
    |     13 | P1      | windows    | 115生活(Windows端)     |
    |     14 | P2      | mac        | 115生活(macOS端)       |
    |     15 | P3      | linux      | 115生活(Linux端)       |
    |     16 | R1      | wechatmini | 115生活(微信小程序)    |
    |     17 | R2      | alipaymini | 115生活(支付宝小程序)  |
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

