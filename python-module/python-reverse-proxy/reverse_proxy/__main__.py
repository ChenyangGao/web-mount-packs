#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["main"]
__doc__ = "\t\t🌍🚢 python 反向代理服务 🕷️🕸️"

from argparse import ArgumentParser, Namespace, RawTextHelpFormatter


parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
parser.add_argument(metavar="base-url", dest="base_url", nargs="?", default="http://localhost", 
                    help="被代理的服务的 base_url，默认值：'http://localhost'")
parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
parser.add_argument("-P", "--port", default=8888, type=int, help="端口号，默认值：8888，如果为 0 则自动确定")
parser.add_argument("-m", "--ws-mode", choices=("", "r", "w", "rw"), help="websocket 的读写模式，'r' 为可读，'w' 为可写")
parser.add_argument("-d", "--debug", action="store_true", help="启用 debug 模式（会输出更详细的信息）")
parser.add_argument("-c", "--config", help="将被作为 JSON 解析然后作为关键字参数传给 `uvicorn.run`")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")


def parse_args(argv: None | list[str] = None, /) -> Namespace:
    args = parser.parse_args(argv)
    if args.version:
        from reverse_proxy import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args


def main(argv: None | list[str] | Namespace = None, /):
    if isinstance(argv, Namespace):
        args = argv
    else:
        args = parse_args(argv)

    from reverse_proxy import make_application

    app = make_application(
        base_url=args.base_url, 
        ws_mode=args.ws_mode, 
        debug=args.debug, 
    )

    from uvicorn import run

    if args.config:
        from json import loads
        run_config = loads(args.config)
    else:
        run_config = {}
    if args.host:
        run_config["host"] = args.host
    else:
        run_config.setdefault("host", "0.0.0.0")
    if args.port:
        run_config["port"] = args.port
    elif not run_config.get("port"):
        from socket import create_connection

        def get_available_ip(start: int = 1024, stop: int = 65536) -> int:
            for port in range(start, stop):
                try:
                    with create_connection(("127.0.0.1", port), timeout=1):
                        pass
                except OSError:
                    return port
            raise RuntimeError("no available ports")
    run_config.setdefault("proxy_headers", True)
    run_config.setdefault("forwarded_allow_ips", "*")
    run_config.setdefault("timeout_graceful_shutdown", 1)

    run(app, **run_config)


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

