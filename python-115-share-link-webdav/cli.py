#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["run"]


from argparse import ArgumentParser, RawTextHelpFormatter


def _init_command_line_options():
    parser = ArgumentParser(
        description="""
    115 分享链接 webdav 挂载工具

源码地址：https://github.com/ChenyangGao/web-mount-packs/tree/main/python-115-share-link-webdav
""", 
        formatter_class=RawTextHelpFormatter, 
    )
    parser.add_argument(
        "-ck", "--cookie-path", default="cookie.txt", 
        help="""保存 cookie 的文件，如果没有，就扫码登录，缺省时则用当前工作目录下的 cookie.txt 文件，格式为

    UID=XXXX; CID=YYYY; SEID=ZZZZ; 

""")
    parser.add_argument(
        "-l", "--links-file", default="links.yml", 
        help="""包含分享链接的配置文件（必须 yaml 文件格式，UTF-8编码），
缺省时则用当前工作目录下的 links.yml 文件

配置的格式，支持如下几种形式：
1. 单个分享链接

    https://115.com/s/xxxxxxxxxxx?password=yyyy#

2. 多个分享链接，但需要有名字

    链接1: https://115.com/s/xxxxxxxxxxx?password=yyyy#
    链接2: https://115.com/s/xxxxxxxxxxx?password=yyyy#
    链接3: https://115.com/s/xxxxxxxxxxx?password=yyyy#

3. 多个分享链接，支持多层目录结构

    一级目录:
        链接1: https://115.com/s/xxxxxxxxxxx?password=yyyy#
        二级目录:
            链接2: https://115.com/s/xxxxxxxxxxx?password=yyyy#
    链接3: https://115.com/s/xxxxxxxxxxx?password=yyyy#

""")
    parser.add_argument(
        "-c", "--config", default="wsgidav.yaml", 
        help="""WsgiDav 的配置文件（必须 yaml 文件格式，UTF-8编码），
缺省时则用当前工作目录下的 wsgidav.yaml 文件，不存在时会自动创建，
命令行的 --host|-H、--port|-p|-P 和 --verbose|-v 有更高优先级""")
    parser.add_argument("-H", "--host", help="主机地址，默认 0.0.0.0，你也可以用 localhost、127.0.0.1 或者其它")
    parser.add_argument("-p", "-P", "--port", type=int, help="端口号，默认 8080")
    parser.add_argument(
        "-v", "--verbose", type=int, choices=range(6), 
        help="""输出日志信息，默认级别 3

Set verbosity level

Verbose Output:
    0 - no output
    1 - no output (excepting application exceptions)
    2 - show warnings
    3 - show single line request summaries (for HTTP logging)
    4 - show additional events
    5 - show full request/response header info (HTTP Logging)
        request body and GET response bodies not shown
""")
    parser.add_argument("-w", "--watch-config", action="store_true", help="""如果指定此参数，则会监测配置文件的变化
    针对 -ck/--cookie-path: 默认时 cookie.txt，更新cookie
    针对 -l/--links-file:   默认是 links.yml，更新分享链接
    针对 -c/--config:       默认是 wsgidav.yaml，更新配置文件，会重启服务器（慎用）

因为有些用户提到，找不到配置文件，所以我额外增加了一个挂载目录，在 webdav 服务的 /_workdir 路径，默认情况下配置文件在这个目录里面，你可以单独挂载此路径，然后修改配置文件
""")
    return parser.parse_args()


def _init_config():
    args = _init_command_line_options()

    cookie_path  = args.cookie_path
    links_file   = args.links_file
    davconf_file = args.config
    host         = args.host
    port         = args.port
    verbose      = args.verbose
    watch_config = args.watch_config

    from os import environ, path as os_path
    from util.pip_tool import ensure_install

    environ["PIP_INDEX_URL"] = "http://mirrors.aliyun.com/pypi/simple/"

    ensure_install("Crypto", "pycryptodome")
    ensure_install("yaml", "pyyaml")
    ensure_install("qrcode")
    ensure_install("requests")
    ensure_install("wsgidav", "WsgiDAV")
    ensure_install("cheroot")
    if watch_config:
        ensure_install("watchdog")

    try:
        cookie = open(cookie_path, encoding="latin-1").read().strip()
    except FileNotFoundError:
        cookie = None # type: ignore

    from util.pan115 import Pan115Client

    client = Pan115Client(cookie)
    if client.cookie != cookie:
        cookie = client.cookie
        open(cookie_path, "w", encoding="latin-1").write(cookie)

    from pkgutil import get_data

    if not os_path.exists(links_file):
        links_config_text = get_data("src", "links.yml")
        open(links_file, "wb", buffering=0).write(links_config_text) # type: ignore

    try:
        wsgidav_config_text = open(davconf_file, "rb", buffering=0).read()
    except FileNotFoundError:
        wsgidav_config_text = get_data("src", "sample_wsgidav.yaml") # type: ignore
        open(davconf_file, "wb", buffering=0).write(wsgidav_config_text)

    from yaml import load as yaml_load, Loader as yaml_Loader

    wsgidav_config = yaml_load(wsgidav_config_text, Loader=yaml_Loader)

    if wsgidav_config is None:
        wsgidav_config = {}
    if host is None:
        wsgidav_config.setdefault("host", "0.0.0.0")
    else:
        wsgidav_config["host"] = host
    if port is None:
        wsgidav_config.setdefault("port", 8080)
    else:
        wsgidav_config["port"] = port
    if verbose is None:
        wsgidav_config.setdefault("verbose", 3)
    else:
        wsgidav_config["verbose"] = verbose
    wsgidav_config.setdefault("logging", {}).setdefault("enable", True)
    wsgidav_config.setdefault("server", "cheroot")

    from util.pan115_sharelink_dav_provider import Pan115ShareLinkFilesystemProvider
    from wsgidav.fs_dav_provider import FilesystemProvider # type: ignore

    wsgidav_config["provider_mapping"] = {
        "/": Pan115ShareLinkFilesystemProvider.from_config_file(cookie_path, links_file, davconf_file, watch=watch_config), 
        "/_workdir": FilesystemProvider("."), 
    }

    return wsgidav_config


def run():
    config = _init_config()

    from wsgidav.wsgidav_app import WsgiDAVApp # type: ignore
    from wsgidav.server.server_cli import SUPPORTED_SERVERS # type: ignore
    from wsgidav.xml_tools import use_lxml # type: ignore

    app = WsgiDAVApp(config)

    server = config["server"]
    handler = SUPPORTED_SERVERS.get(server)
    if not handler:
        raise RuntimeError(
            "Unsupported server type {!r} (expected {!r})".format(
                server, "', '".join(SUPPORTED_SERVERS.keys())
            )
        )

    if not use_lxml and config["verbose"] >= 3:
        __import__("logging").getLogger("wsgidav").warning(
            "Could not import lxml: using xml instead (up to 10% slower). "
            "Consider `pip install lxml`(see https://pypi.python.org/pypi/lxml)."
        )

    print("""
    💥 Welcome to 115 share link webdav 😄
""")
    handler(app, config, server)


if __name__ == "__main__":
    run()

