#!/usr/bin/env python3
# encoding: utf-8

"扫码获取 115 cookie"

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = [
    "AppEnum", "get_qrcode_token", "get_qrcode_status", "post_qrcode_result", 
    "get_qrcode", "login_with_qrcode", 
]

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description="""\
扫码获取 115 cookie

默认在命令行输出，需要安装 qrcode: pip install qrcode
    - https://pypi.org/project/qrcode/
可以指定 -o 或 --open-qrcode 直接打开图片扫码
""", formatter_class=RawTextHelpFormatter)
    parser.add_argument("app", nargs="?", choices=("web", "android", "ios", "linux", "mac", "windows", "tv", "alipaymini", "wechatmini", "qandroid"), default="web", help="选择一个 app 进行登录，注意：这会把已经登录的相同 app 踢下线")
    parser.add_argument("-o", "--open-qrcode", action="store_true", help="打开二维码图片，而不是在命令行输出")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

from enum import Enum
from json import loads
from urllib.parse import urlencode
from urllib.request import urlopen, Request


AppEnum = Enum("AppEnum", "web, android, ios, linux, mac, windows, tv, alipaymini, wechatmini, qandroid")


def get_enum_name(val, cls):
    if isinstance(val, cls):
        return val.name
    try:
        if isinstance(val, str):
            return cls[val].name
    except KeyError:
        pass
    return cls(val).name


def get_qrcode_token():
    """获取登录二维码，扫码可用
    GET https://qrcodeapi.115.com/api/1.0/web/1.0/token/
    :return: dict
    """
    api = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
    return loads(urlopen(api).read())


def get_qrcode_status(payload):
    """获取二维码的状态（未扫描、已扫描、已登录、已取消、已过期等）
    GET https://qrcodeapi.115.com/get/status/
    :param payload: 请求的查询参数，取自 `login_qrcode_token` 接口响应，有 3 个
        - uid:  str
        - time: int
        - sign: str
    :return: dict
    """
    api = "https://qrcodeapi.115.com/get/status/?" + urlencode(payload)
    return loads(urlopen(api).read())


def post_qrcode_result(uid, app="web"):
    """获取扫码登录的结果，并且绑定设备，包含 cookie
    POST https://passportapi.115.com/app/1.0/{app}/1.0/login/qrcode/
    :param uid: 二维码的 uid，取自 `login_qrcode_token` 接口响应
    :param app: 扫码绑定的设备，可以是 int、str 或者 AppEnum
        app 目前发现的可用值：
            - 1,  "web",        AppEnum.web
            - 2,  "android",    AppEnum.android
            - 3,  "ios",        AppEnum.ios
            - 4,  "linux",      AppEnum.linux
            - 5,  "mac",        AppEnum.mac
            - 6,  "windows",    AppEnum.windows
            - 7,  "tv",         AppEnum.tv
            - 8,  "alipaymini", AppEnum.alipaymini
            - 9,  "wechatmini", AppEnum.wechatmini
            - 10, "qandroid",   AppEnum.qandroid
    :return: dict，包含 cookie
    """
    app = get_enum_name(app, AppEnum)
    payload = {"app": app, "account": uid}
    api = "https://passportapi.115.com/app/1.0/%s/1.0/login/qrcode/" % app
    return loads(urlopen(Request(api, data=urlencode(payload).encode("utf-8"), method="POST")).read())


def get_qrcode(uid):
    """获取二维码图片（注意不是链接）
    :return: 一个文件对象，可以读取
    """
    url = "https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode?uid=%s" % uid
    return urlopen(url)


def login_with_qrcode(app="web", scan_in_console=True):
    """用二维码登录
    :param app: 扫码绑定的设备，可以是 int、str 或者 AppEnum
        app 目前发现的可用值：
            - 1,  "web",        AppEnum.web
            - 2,  "android",    AppEnum.android
            - 3,  "ios",        AppEnum.ios
            - 4,  "linux",      AppEnum.linux
            - 5,  "mac",        AppEnum.mac
            - 6,  "windows",    AppEnum.windows
            - 7,  "tv",         AppEnum.tv
            - 8,  "alipaymini", AppEnum.alipaymini
            - 9,  "wechatmini", AppEnum.wechatmini
            - 10, "qandroid",   AppEnum.qandroid
    :return: dict，扫码登录结果
    """
    qrcode_token = get_qrcode_token()["data"]
    qrcode = qrcode_token.pop("qrcode")
    if scan_in_console:
        try:
            from qrcode import QRCode
        except ModuleNotFoundError:
            from sys import executable
            from subprocess import run
            run([executable, "-m", "pip", "install", "qrcode"], check=True)
            from qrcode import QRCode # type: ignore
        qr = QRCode(border=1)
        qr.add_data(qrcode)
        qr.print_ascii(tty=True)
    else:
        from atexit import register
        from os import remove
        from threading import Thread
        from tempfile import NamedTemporaryFile
        qrcode_image = get_qrcode(qrcode_token["uid"])
        with NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(qrcode_image.read())
            f.flush()
        register(lambda: remove(f.name))
        def open_qrcode():
            platform = __import__("platform").system()
            if platform == "Windows":
                from os import startfile # type: ignore
                startfile(f.name)
            elif platform == "Darwin":
                from subprocess import run
                run(["open", f.name])
            else:
                from subprocess import run
                run(["xdg-open", f.name])
        Thread(target=open_qrcode).start()
    while True:
        try:
            resp = get_qrcode_status(qrcode_token)
        except TimeoutError:
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
            raise OSError("[status=-1] qrcode: expired")
        elif status == -2:
            raise OSError("[status=-2] qrcode: canceled")
        else:
            raise OSError("qrcode: aborted with %r" % resp)
    return post_qrcode_result(qrcode_token["uid"], app)


if __name__ == "__main__":
    resp = login_with_qrcode(args.app, scan_in_console=not args.open_qrcode)
    print()
    print("; ".join("%s=%s" % t for t in resp['data']['cookie'].items()))

