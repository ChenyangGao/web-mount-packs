#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["crack_captcha"]

from collections import defaultdict
from collections.abc import Callable
from time import sleep, time
from typing import cast

from concurrenttools import thread_pool_batch
from p115.component.client import P115Client


CAPTCHA_CRACK: Callable[[bytes], str]


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


# TODO: 实现一个函数，用来实现选择自定义的 request

# TODO 删除文件，如果文件数过多，会尝试拆分后再执行任务，从回收站删除
# TODO 会等待目录被删除完成，采取回收站清除它
# def remove(
#     client: str | P115Client, 
#     id: int, 
#     /, 
#     password: str = "", 
# ):
#     """删除文件或目录，如果提供密码，则会从回收站把它删除

#     :param client: 115 客户端或 cookies
#     :param id: 文件或目录的 id
#     :param password: 回收站密码（即 安全密钥，是 6 位数字）

#     :return: 返回一个 Future，可以被关停
#     """
#     if not isinstance(client, P115Client):
#         client = P115Client(client)
#     fs = client.fs
#     try:
#         attr = fs.attr("/我的接收", ensure_dir=True)
#     except FileNotFoundError:
#         return
#     now = str(int(time()))
#     fs.rmtree(attr)
#     recyclebin = client.recyclebin
#     while True:
#         for i, info in enumerate(recyclebin):
#             # NOTE: 因为删除后，并不能立即在回收站看到被删除的文件夹，所以看情况需要等一等
#             if not i and info["dtime"] < now:
#                 sleep(0.1)
#                 break
#             if info["cid"] == 0 and info["file_name"] == "我的接收":
#                 recyclebin.remove(info["id"], password)
#                 return

