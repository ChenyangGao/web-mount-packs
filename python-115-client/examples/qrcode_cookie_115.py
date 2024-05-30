#!/usr/bin/env python3
# encoding: utf-8

"扫码获取 115 cookie"

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
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
    parser.add_argument(
        "app", 
        nargs="?", 
        choices=("web", "ios", "115ios", "android", "115android", "115ipad", "tv", 
                 "qandroid", "windows", "mac", "linux", "wechatmini", "alipaymini"), 
        default="web", 
        help="选择一个 app 进行登录，默认为 'web'，注意：这会把已经登录的相同 app 踢下线", 
    )
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


AppEnum = Enum("AppEnum", {
    "web": 1, 
    "ios": 6, 
    "115ios": 8, 
    "android": 9, 
    "115android": 11, 
    "115ipad": 14, 
    "tv": 15, 
    "qandroid": 16, 
    "windows": 19, 
    "mac": 20, 
    "linux": 21, 
    "wechatmini": 22, 
    "alipaymini": 23, 
})


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
        app 至少有 23 个可用值，目前找出 13 个：
            - 'web',         1, AppEnum.web
            - 'ios',         6, AppEnum.ios
            - '115ios',      8, AppEnum['115ios']
            - 'android',     9, AppEnum.android
            - '115android', 11, AppEnum['115android']
            - '115ipad',    14, AppEnum['115ipad']
            - 'tv',         15, AppEnum.tv
            - 'qandroid',   16, AppEnum.qandroid
            - 'windows',    19, AppEnum.windows
            - 'mac',        20, AppEnum.mac
            - 'linux',      21, AppEnum.linux
            - 'wechatmini', 22, AppEnum.wechatmini
            - 'alipaymini', 23, AppEnum.alipaymini
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
        app 至少有 23 个可用值，目前找出 13 个：
            - 'web',         1, AppEnum.web
            - 'ios',         6, AppEnum.ios
            - '115ios',      8, AppEnum['115ios']
            - 'android',     9, AppEnum.android
            - '115android', 11, AppEnum['115android']
            - '115ipad',    14, AppEnum['115ipad']
            - 'tv',         15, AppEnum.tv
            - 'qandroid',   16, AppEnum.qandroid
            - 'windows',    19, AppEnum.windows
            - 'mac',        20, AppEnum.mac
            - 'linux',      21, AppEnum.linux
            - 'wechatmini', 22, AppEnum.wechatmini
            - 'alipaymini', 23, AppEnum.alipaymini
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
    :return: dict，扫码登录结果
    """
    qrcode_token = get_qrcode_token()["data"]
    qrcode = qrcode_token.pop("qrcode")
    if scan_in_console:
        try:
            from qrcode import QRCode # type: ignore 
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

