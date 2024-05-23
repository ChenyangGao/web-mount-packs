#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = "扫码获取 115 cookies"


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

    cookies: str
    if args.cookies:
        from p115.tool import login_scan_cookie

        client = P115Client(args.cookies)
        cookies = login_scan_cookie(client, app=args.app)
    else:
        client = P115Client(app=args.app)
        cookies = client.cookies
    print()
    print(cookies, file=file)


parser.add_argument("app", nargs="?", choices=("web", "android", "ios", "linux", "mac", "windows", "tv", "alipaymini", "wechatmini", "qandroid"), default="web", 
                    help="选择一个 app 进行登录，注意：这会把已经登录的相同 app 踢下线")
parser.add_argument("-o", "--output-file", help="保存到文件，未指定时输出到 stdout")
parser.add_argument("-c", "--cookies", help="115 登录 cookie，如果提供了，就可以用这个 cookies 进行自动扫码，否则需要你用手机来手动扫码")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

