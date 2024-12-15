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


def main(args):
    if args.version:
        from alist import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from string import hexdigits

    from alist import AlistClient
    from alist.tool import alist_update_115_cookies
    from p115qrcode import qrcode_result, qrcode_scan, qrcode_scan_confirm, qrcode_token, scan_qrcode

    if token := args.token:
        client = AlistClient.from_auth(token, origin=args.origin)
    else:
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

    cookies: str
    if not (cookies := args.set_cookies.strip()):
        cookies = args.cookies.strip()
        app: str = args.app
        resp = {}
        try:
            if cookies:
                if len(cookies) == 40 and not cookies.strip(hexdigits):
                    uid = cookies
                elif all(k in cookies for k in ("UID=", "CID=", "SEID=")):
                    uid = qrcode_token()["uid"]
                    qrcode_scan(uid, cookies)
                    qrcode_scan_confirm(uid, cookies)
                else:
                    raise OSError
                resp = qrcode_result(uid, app)
        except OSError:
            pass
        if not resp:
            future = scan_qrcode(app, console_qrcode=not args.open_qrcode, show_message=True)
            resp = future.result()
        cookies = "; ".join("%s=%s" % t for t in resp["data"]["cookie"].items())
    alist_update_115_cookies(client, cookies)


parser.add_argument(
    "app", nargs="?", default="alipaymini", 
    choices=("web", "ios", "115ios", "android", "115android", "115ipad", "tv", "qandroid", 
             "wechatmini", "alipaymini", "harmony"), 
        help="选择一个 app 进行登录，默认为 'alipaymini'", 
)
parser.add_argument("-o", "--origin", default="http://localhost:5244", help="alist 服务器地址，默认 http://localhost:5244")
parser.add_argument("-u", "--username", default="admin", help="用户名，默认为 admin")
parser.add_argument("-p", "--password", default="", help="密码，默认为空")
parser.add_argument("-t", "--token", default="", help="alist 的 token，优先级高于 -u/--username 和 -p/--password")
parser.add_argument("-c", "--cookies", default="", help="115 登录 cookies，如果提供了，就可以用这个 cookies 进行自动扫码，否则需要你用手机来手动扫码")
parser.add_argument("-ck", "--set-cookies", default="", help="115 登录 cookies，如果指定则直接把这个 cookies 更新到 alist")
parser.add_argument("-op", "--open-qrcode", action="store_true", help="打开二维码图片，而不是在命令行输出")
parser.add_argument("-on", "--only-not-work", action="store_true", help="如果 cookies 未失效则不进行更新")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

