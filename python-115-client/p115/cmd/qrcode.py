#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = "扫码获取 115 cookie"


if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from .init import subparsers

    parser = subparsers.add_parser("qrcode", description=__doc__)


def main(args):
    from p115 import P115Client, __version__

    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from typing import TextIO

    outfile = args.output_file
    file: TextIO
    if outfile:
        file = open(outfile, "w")
    else:
        from sys import stdout as file

    cookie: str
    if args.cookie:
        def login_scan_cookie(
            client: P115Client, 
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
            uid = client.login_qrcode_token()["data"]["uid"]
            client.login_qrcode_scan(uid)
            client.login_qrcode_scan_confirm(uid)
            data = client.login_qrcode_result({"account": uid, "app": app})
            return "; ".join(f"{k}={v}" for k, v in data["data"]["cookie"].items())

        client = P115Client(args.cookie)
        cookie = login_scan_cookie(client, app=args.app)
    else:
        client = P115Client(login_app=args.app)
        cookie = client.cookie
    print()
    print(cookie, file=file)


parser.add_argument("app", nargs="?", choices=("web", "android", "ios", "linux", "mac", "windows", "tv", "alipaymini", "wechatmini", "qandroid"), default="web", 
                    help="选择一个 app 进行登录，注意：这会把已经登录的相同 app 踢下线")
parser.add_argument("-o", "--output-file", help="保存到文件，未指定时输出到 stdout")
parser.add_argument("-c", "--cookie", help="115 登录 cookie，如果提供了，就可以自动扫码，否则需要手动扫码")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

