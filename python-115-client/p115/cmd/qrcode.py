#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = "扫码获取 115 cookies"


if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[2])
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from argparse import RawTextHelpFormatter
    from .init import subparsers

    parser = subparsers.add_parser("qrcode", description=__doc__, formatter_class=RawTextHelpFormatter)


def main(args):
    if args.version:
        from p115 import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from os.path import expanduser, dirname, join as joinpath, realpath
    from typing import TextIO

    from p115 import P115Client

    cookies = args.cookies
    cookies_path = args.cookies_path
    if not cookies:
        if cookies_path:
            try:
                cookies = open(cookies_path).read()
            except FileNotFoundError:
                pass
        else:
            seen = set()
            for dir_ in (".", expanduser("~"), dirname(__file__)):
                dir_ = realpath(dir_)
                if dir_ in seen:
                    continue
                seen.add(dir_)
                try:
                    cookies = open(joinpath(dir_, "115-cookies.txt")).read()
                    if cookies:
                        cookies_path = joinpath(dir_, "115-cookies.txt")
                        break
                except FileNotFoundError:
                    pass

    if cookies:
        from p115 import AuthenticationError

        try:
            client = P115Client(cookies)
            client.login_another_app(app=args.app, replace=True)
        except AuthenticationError:
            client = P115Client(app=args.app)
    else:
        client = P115Client(app=args.app)
    print()
    outfile = args.output_file
    file: TextIO
    if outfile:
        try:
            file = open(outfile, "w")
        except OSError as e:
            print("Error occured:", repr(e))
            from sys import stdout as file
    else:
        from sys import stdout as file
    print(client.cookies, file=file)


from p115 import AVAILABLE_APPS

parser.add_argument(
    "app", nargs="?", default="qandroid", 
    choices=AVAILABLE_APPS,        
    help="选择一个 app 进行登录，默认值 'qandroid'，注意：这会把已经登录的相同 app 踢下线")
parser.add_argument("-o", "--output-file", help="保存到文件，未指定时输出到 stdout")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -c/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="""\
存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一: 
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录""")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

