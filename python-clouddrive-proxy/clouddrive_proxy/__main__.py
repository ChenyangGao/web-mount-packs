#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["main"]
__doc__ = """\
        🌍🚢 clouddrive 反向代理和功能扩展 🕷️🕸️

目前实现的功能：
✅ 反向代理
✅ 115 的下载可用 p115nano302 代理，实现 302
"""

from argparse import ArgumentParser, Namespace, RawTextHelpFormatter

parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
parser.add_argument("-u", "--username", required=True, help="用户名")
parser.add_argument("-p", "--password", required=True, help="密码")
parser.add_argument(metavar="base-url", dest="base_url", nargs="?", default="http://localhost:19798", 
                    help="被代理的 clouddrive 服务的 base_url，默认值：'http://localhost:19798'")
parser.add_argument("-115", "--base-url-115", default="http://localhost:8000", 
                    help="115 代理下载链接，默认为 http://localhost:8000，请部署一个 https://pypi.org/project/p115nano302/")
parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
parser.add_argument("-P", "--port", default=19797, type=int, help="端口号，默认值：19797")
parser.add_argument("-db", "--dbfile", default="", 
                    help="clouddrive 的持久化缓存的数据库文件路径或者所在目录，文件名为 dir_cache.sqlite")
parser.add_argument("-d", "--debug", action="store_true", help="启用 debug 模式（会输出更详细的信息）")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.add_argument("-l", "--license", action="store_true", help="输出授权信息")


def parse_args(argv: None | list[str] = None, /) -> Namespace:
    args = parser.parse_args(argv)
    if args.version:
        from clouddrive_proxy import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    elif args.license:
        from clouddrive_proxy import __license__
        print(__license__)
        raise SystemExit(0)
    return args


def main(argv: None | list[str] | Namespace = None, /):
    if isinstance(argv, Namespace):
        args = argv
    else:
        args = parse_args(argv)

    from clouddrive_proxy import make_application

    app = make_application(
        args.username, 
        args.password, 
        base_url=args.base_url, 
        base_url_115=args.base_url_115, 
        dbfile=args.dbfile, 
        debug=args.debug, 
    )

    from uvicorn import run

    run(
        app, 
        host=args.host, 
        port=args.port, 
        proxy_headers=True, 
        forwarded_allow_ips="*", 
        timeout_graceful_shutdown=1, 
    )


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

