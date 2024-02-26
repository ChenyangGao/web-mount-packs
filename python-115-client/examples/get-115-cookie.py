#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)

from argparse import ArgumentParser

parser = ArgumentParser(description="扫码获取 115 cookie")
parser.add_argument("app", nargs="?", choices=("web", "android", "ios", "linux", "mac", "windows", "tv"), default="web", help="选择一个 app 进行登录，注意：这会把已经登录的相同 app 踢下线")
args = parser.parse_args()

try:
    # pip install python-115
    from p115 import P115Client
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "python-115"], check=True)
    from p115 import P115Client

client = P115Client(login_app=args.app)
print()
print(client.cookie)
