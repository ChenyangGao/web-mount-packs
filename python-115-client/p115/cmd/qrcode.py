#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["main"]
__doc__ = "扫码获取 115 cookies"

from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from pathlib import Path

if __name__ == "__main__":
    from sys import path

    path[0] = str(Path(__file__).parents[2])
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from .init import subparsers

    parser = subparsers.add_parser("qrcode", description=__doc__, formatter_class=RawTextHelpFormatter)


def parse_args(argv: None | list[str] = None, /) -> Namespace:
    args = parser.parse_args(argv)
    if args.version:
        from p115 import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args


def main(argv: None | list[str] | Namespace = None, /):
    if isinstance(argv, Namespace):
        args = argv
    else:
        args = parse_args(argv)

    from typing import TextIO
    from p115 import P115Client

    if not (cookies := args.cookies):
        try:
            if cookies_path := args.cookies_path:
                cookies = open(cookies_path).read()
            else:
                cookies = open("115-cookies.txt").read()
        except FileNotFoundError:
            cookies = None
    client = P115Client(cookies, check_for_relogin=True, ensure_cookies=True, app=args.app)
    if outfile := args.output_file:
        try:
            file: TextIO = open(outfile, "w")
        except OSError as e:
            print("Error occured:", repr(e))
            from sys import stdout as file
    else:
        from sys import stdout as file
    print(client.cookies_str, file=file)


from p115 import AVAILABLE_APPS

parser.add_argument("app", nargs="?", default="qandroid", choices=AVAILABLE_APPS,        
                    help="选择一个 app 进行登录，默认值 'qandroid'，注意：这会把已经登录的相同 app 踢下线")
parser.add_argument("-o", "--output-file", help="保存到文件，未指定时输出到 stdout")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -cp/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="cookies 文件保存路径")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    main()

