#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["main"]
__doc__ = "\t\t🌍🚢 alist 网络代理抓包 🕷️🕸️"


def main():
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
    parser.add_argument("-P", "--port", default=5245, type=int, help="端口号，默认值：5245")
    parser.add_argument("-b", "--base-url", default="http://localhost:5244", 
                        help="被代理的 alist 服务的 base_url，默认值：'http://localhost:5244'")
    parser.add_argument("-t", "--token", default="", help="alist 的 token，用来追踪后台任务列表和更新某些 cookies")
    parser.add_argument("-u", "--db-uri", default="", help="""数据库连接的 URI，格式为 "{dbtype}://{host}:{port}/{path}"
    - dbtype: 数据库类型，目前仅支持 "sqlite"、"mongodb" 和 "redis"
    - host: （非 "sqlite"）ip 或 hostname，如果忽略，则用 "localhost"
    - port: （非 "sqlite"）端口号，如果忽略，则自动使用此数据库的默认端口号
    - path: （限 "sqlite"）文件路径，如果忽略，则为 ""（会使用一个临时文件）
如果你只输入 dbtype 的名字，则视为 "{dbtype}://"
如果你输入了值，但不能被视为 dbtype，则自动视为 path，即 "sqlite:///{path}"
""")
    parser.add_argument("-w", "--webhooks", metavar="webhook", nargs="*", help='一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}')
    parser.add_argument("-d", "--debug", action="store_true", help="启用 debug 模式（会输出更详细的信息）")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        from alist_proxy import __version__
        print(".".join(map(str, __version__)))
        return

    from alist_proxy import make_application_with_fs_event_stream

    app = make_application_with_fs_event_stream(
        alist_token=args.token, 
        base_url=args.base_url, 
        db_uri=args.db_uri, 
        webhooks=args.webhooks, 
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
        timeout_graceful_shutdown=1, 
    )


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

