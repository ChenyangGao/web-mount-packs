#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = "115 签到"

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[2])
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from argparse import RawTextHelpFormatter
    from .init import subparsers

    parser = subparsers.add_parser("check", description=__doc__, formatter_class=RawTextHelpFormatter)


def main(args):
    from p115 import P115Client, __version__

    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from os.path import expanduser, dirname, join as joinpath
    from sys import stdout

    cookies = args.cookies
    if not cookies:
        for dir_ in (".", expanduser("~"), dirname(__file__)):
            try:
                cookies = open(joinpath(dir_, "115-cookies.txt")).read()
                if cookies:
                    break
            except FileNotFoundError:
                pass

    client = P115Client(cookies)
    if client.cookies != cookies:
        open("115-cookies.txt", "w").write(client.cookies)
    print(client.user_points_sign_post())


parser.add_argument("-c", "--cookies", help="115 登录 cookie，如果缺失，则从 115-cookies.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

