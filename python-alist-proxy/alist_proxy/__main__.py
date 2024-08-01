#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["main"]
__doc__ = "\t\t🌍🚢 alist 网络代理抓包 🕷️🕸️"


def main():
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
    parser.add_argument("-p", "--port", default=5245, type=int, help="端口号，默认值：5245")
    parser.add_argument("-b", "--base-url", default="http://localhost:5244", 
                        help="被代理的 alist 服务的 base_url，默认值：'http://localhost:5244'")
    parser.add_argument("-t", "--token", default="", help="alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）")
    parser.add_argument("-nr", "--no-redis", action="store_true", help="不使用 redis，直接输出到控制台，主要用于调试")
    parser.add_argument("-rh", "--redis-host", default="localhost", help="redis 服务所在的主机，默认值: 'localhost'")
    parser.add_argument("-rp", "--redis-port", default=6379, type=int, help="redis 服务的端口，默认值: 6379")
    parser.add_argument("-rk", "--redis-key", default="alist:fs", help="redis streams 的键名，默认值: 'alist:fs'")
    parser.add_argument("-d", "--debug", action="store_true", help="启用 debug 模式（会输出更详细的信息）")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        from alist_proxy import __version__
        print(".".join(map(str, __version__)))
        return

    if args.no_redis:
        from alist_proxy import make_application_with_fs_events

        app = make_application_with_fs_events(
            alist_token=args.token, 
            base_url=args.base_url, 
        )
    else:
        from alist_proxy import make_application_with_fs_event_stream

        app = make_application_with_fs_event_stream(
            alist_token=args.token, 
            base_url=args.base_url, 
            redis_host=args.redis_host, 
            redis_port=args.redis_port, 
            redis_key=args.redis_key, 
        )

    from uvicorn import run

    debug = args.debug
    if debug:
        getattr(app, "logger").level = 10
        app.show_error_details = True
    run(
        app, 
        host=args.host, 
        port=args.port, 
        reload=debug, 
        proxy_headers=True, 
        forwarded_allow_ips="*", 
    )


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

