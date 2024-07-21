#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = """\
    alist 更新 115 cookies

你可以先把你的手机抓包得到的 cookies，保存在本地的 ~/115-cookies.txt 中，然后自动进行扫码更新 cookies，自动绑定为微信小程序的 cookies

.. code: console

    /usr/bin/env python3 -m alist 115 --origin 'http://localhost:5244' --user admin --password 123456 --cookies "$(cat ~/115-cookies.txt)" --only-not-work wechatmini

这个命令可以定期运行，比如 1 分钟跑 1 次，在 crontab 里配置
"""

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[2])
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from argparse import RawTextHelpFormatter
    from .init import subparsers

    parser = subparsers.add_parser("115", description=__doc__, formatter_class=RawTextHelpFormatter)

from enum import Enum
from http.client import HTTPResponse
from json import dumps, load, loads
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


def get_qrcode_token() -> dict:
    """获取登录二维码，扫码可用
    GET https://qrcodeapi.115.com/api/1.0/web/1.0/token/

    :return: 扫码相关的信息，比如二维码的 uid
    """
    api = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
    return load(urlopen(api))


def get_qrcode_status(payload) -> dict:
    """获取二维码的状态（未扫描、已扫描、已登录、已取消、已过期等）
    GET https://qrcodeapi.115.com/get/status/

    :param payload: 请求的查询参数，取自 `login_qrcode_token` 接口响应，有 3 个
        - uid:  str
        - time: int
        - sign: str

    :return: 二维码目前的扫码状态信息
    """
    api = "https://qrcodeapi.115.com/get/status/?" + urlencode(payload)
    return load(urlopen(api))


def post_qrcode_result(uid: str, app: str = "web") -> dict:
    """获取扫码登录的结果，并且绑定设备，包含 cookies
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

    :return: 包含 cookies 的响应
    """
    app = get_enum_name(app, AppEnum)
    payload = {"app": app, "account": uid}
    api = "https://passportapi.115.com/app/1.0/%s/1.0/login/qrcode/" % app
    return load(urlopen(Request(api, data=urlencode(payload).encode("utf-8"), method="POST")))


def get_qrcode(uid: str) -> HTTPResponse:
    """获取二维码图片（注意不是链接）
    :return: 一个文件对象，可以读取
    """
    url = "https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode?uid=%s" % uid
    return urlopen(url)


def login_with_qrcode(
    app: str = "web", 
    scan_in_console: bool = True, 
) -> dict:
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
    :param scan_in_console: 是否在命令行输出二维码，否则会在默认的图片打开程序中打开

    :return: 扫码登录结果
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


def login_with_autoscan(
    cookies: str, 
    app: str = "web", 
) -> dict:
    """自动扫码登录
    """
    headers = {"Cookie": cookies.strip()}
    token = get_qrcode_token()["data"]
    uid = token["uid"]
    # scanned
    scanned_data = load(urlopen(Request(
        "https://qrcodeapi.115.com/api/2.0/prompt.php?uid=%s" % uid, 
        headers=headers, 
    )))["data"]
    # comfirmed
    urlopen(Request(
        scanned_data["do_url"], 
        data=bytes(urlencode(scanned_data["do_params"]), "utf-8"), 
        headers=headers, 
    ))
    return post_qrcode_result(uid, app)


def main(args):
    if args.version:
        from alist import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from alist import AlistClient
    from alist.tool import alist_update_115_cookies

    client = AlistClient(args.origin, args.username, args.password)
    resp = client.admin_storage_list()
    if resp["code"] != 200:
        raise ValueError(resp)

    if args.only_not_work and all(
        storage["status"] == "work" 
        for storage in resp["data"]["content"]
        if storage["driver"] in ("115 Cloud", "115 Share")
    ):
        return

    if args.set_cookies:
        cookies = args.set_cookies
    else:
        if args.cookies:
            resp = login_with_autoscan(args.cookies, args.app)
        else:
            resp = login_with_qrcode(args.app, scan_in_console=not args.open_qrcode)
        cookies = "; ".join("%s=%s" % t for t in resp["data"]["cookie"].items())

    alist_update_115_cookies(client, cookies)


parser.add_argument(
    "app", 
    nargs="?", 
    choices=("web", "ios", "115ios", "android", "115android", "115ipad", "tv", 
             "qandroid", "windows", "mac", "linux", "wechatmini", "alipaymini"), 
    default="qandroid", 
    help="选择一个 app 进行登录，默认为 'qandroid'，注意：这会把已经登录的相同 app 踢下线", 
)
parser.add_argument("-o", "--origin", default="http://localhost:5244", help="alist 服务器地址，默认 http://localhost:5244")
parser.add_argument("-u", "--username", default="admin", help="用户名，默认为 admin")
parser.add_argument("-p", "--password", default="", help="密码，默认为空")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，如果提供了，就可以用这个 cookies 进行自动扫码，否则需要你用手机来手动扫码")
parser.add_argument("-ck", "--set-cookies", help="115 登录 cookies，如果指定则直接把这个 cookies 更新到 alist")
parser.add_argument("-op", "--open-qrcode", action="store_true", help="打开二维码图片，而不是在命令行输出")
parser.add_argument("-on", "--only-not-work", action="store_true", help="如果 cookies 未失效则不进行更新")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

