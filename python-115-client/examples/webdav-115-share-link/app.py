#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__doc__ = """\
        🛸 115 share link webdav 🌌

源码地址：https://github.com/ChenyangGao/web-mount-packs/tree/main/python-115-client/examples/webdav-115-share-link
"""
__all__ = ["run"]

from argparse import ArgumentParser, RawTextHelpFormatter


def _init_command_line_options():
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument("-cp", "--cookies-path", default="115-cookies.txt", help="""\
存储 115 登录 cookies 的文本文件的路径，默认为当前工作目录下的 '115-cookies.txt'，文本格式为

    UID=XXXX; CID=YYYY; SEID=ZZZZ
""")
    parser.add_argument(
        "-l", "--links-file", default="links.yml", 
        help="""包含分享链接的配置文件（必须 yaml 文件格式，utf-8 编码），
缺省时则用当前工作目录下的 links.yml 文件

配置的格式，支持如下几种形式：
1. 单个分享链接

    link

2. 多个分享链接，但需要有名字

    链接1: link1
    链接2: link2
    链接3: link3

3. 多个分享链接，支持多层目录结构

    一级目录:
        链接1: link1
        二级目录:
            链接2: link2
    链接3: link3

支持以下几种格式的链接（括号内的字符表示可有可无）：
    - http(s)://115.com/s/{share_code}?password={receive_code}(#)
    - http(s)://share.115.com/{share_code}?password={receive_code}(#)
    - (/){share_code}-{receive_code}(/)
""")
    parser.add_argument(
        "-c", "--config", default="wsgidav.yaml", 
        help="""WsgiDav 的配置文件（必须 yaml 文件格式，UTF-8编码），
缺省时则用当前工作目录下的 wsgidav.yaml 文件，不存在时会自动创建，
命令行的 --host|-H、--port|-p|-P 和 --verbose|-v 有更高优先级""")
    parser.add_argument("-H", "--host", help="主机地址，默认值：'0.0.0.0'，你也可以用 'localhost'、'127.0.0.1' 或者其它")
    parser.add_argument("-p", "-P", "--port", type=int, help="端口号，默认值：80")
    parser.add_argument(
        "-v", "--verbose", type=int, choices=range(6), help="""\
输出日志信息，默认级别 3

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
    针对 -cp/--cookies-path: 默认是 115-cookies.txt，更新cookie
    针对 -l/--links-file:    默认是 links.yml，更新分享链接
    针对 -c/--config:        默认是 wsgidav.yaml，更新配置文件，会重启服务器（慎用）

因为有些用户提到，找不到配置文件，所以我额外增加了一个挂载目录，在 webdav 服务的 /_workdir 路径，默认情况下配置文件在这个目录里面，你可以单独挂载此路径，然后修改配置文件""")
    return parser.parse_args()


def _init_config():
    args = _init_command_line_options()

    cookies_path  = args.cookies_path
    links_file    = args.links_file
    davconf_file  = args.config
    host          = args.host
    port          = args.port
    verbose       = args.verbose
    watch_config  = args.watch_config

    from os import environ, path as os_path
    from pkgutil import get_data

    environ["PIP_INDEX_URL"] = "http://mirrors.aliyun.com/pypi/simple/"

    try:
        import wsgidav # type: ignore
        import cheroot, p115, watchdog, yaml
    except ImportError:
        from sys import executable
        from subprocess import run
        run([executable, "-m", "pip", "install", "-U", "cheroot", "python-115", "PyYAML", "watchdog", "WsgiDAV"], check=True)

    cookies: None | str
    try:
        cookies = open(cookies_path, encoding="latin-1").read().strip()
    except FileNotFoundError:
        cookies = None

    from p115 import P115Client

    client = P115Client(cookies)
    if client.cookies != cookies:
        open(cookies_path, "w", encoding="latin-1").write(client.cookies)

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
        wsgidav_config.setdefault("port", 80)
    else:
        wsgidav_config["port"] = port
    if verbose is None:
        wsgidav_config.setdefault("verbose", 3)
    else:
        wsgidav_config["verbose"] = verbose
    wsgidav_config.setdefault("logging", {}).setdefault("enable", True)
    wsgidav_config.setdefault("server", "cheroot")

    from wsgidav.fs_dav_provider import FilesystemProvider # type: ignore
    from util.dav_provider import P115ShareFilesystemProvider

    wsgidav_config["provider_mapping"] = {
        "/": P115ShareFilesystemProvider.from_config_file(cookies_path, links_file, davconf_file, watch=watch_config), 
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

