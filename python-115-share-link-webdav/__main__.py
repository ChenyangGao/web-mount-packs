#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    description="""
    115 分享链接 webdav 挂载工具 (version: 0.0.2)

源码地址：https://github.com/ChenyangGao/web-mount-packs/tree/main/python-115-share-link-webdav
""", formatter_class=RawTextHelpFormatter)
parser.add_argument("-ck", "--cookie-path", default="cookie.txt", help="""保存 cookie 的文件，如果没有，就扫码登录，缺省时则用当前工作目录下的 cookie.txt 文件，格式为

    UID=XXXX; CID=YYYY; SEID=ZZZZ; 

""")
parser.add_argument("-l", "--links-file", default="links.yml", help="""包含分享链接的配置文件（必须 yaml 文件格式，UTF-8编码），
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
parser.add_argument("-c", "--config", default="wsgidav.yaml", 
help="""WsgiDav 的配置文件（必须 yaml 文件格式，UTF-8编码），
缺省时则用当前工作目录下的 wsgidav.yaml 文件，不存在时会自动创建，
命令行的 --host|-H、--port|-p|-P 和 --verbose|-v 有更高优先级""")
parser.add_argument("-H", "--host", help="主机地址，默认 0.0.0.0，你也可以用 localhost、127.0.0.1 或者其它")
parser.add_argument("-p", "-P", "--port", type=int, help="端口号，默认 8080")
parser.add_argument("-v", "--verbose", type=int, choices=range(6), help="""输出日志信息，默认级别 3

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

args = parser.parse_args()

cookie_path = args.cookie_path
links_file = args.links_file
wsgidav_config_file = args.config
host = args.host
port = args.port
verbose = args.verbose

from os import environ, path as os_path
from yaml import load as yaml_load, Loader as yaml_Loader
from pip_tool import ensure_install

environ["PIP_INDEX_URL"] = "http://mirrors.aliyun.com/pypi/simple/"

ensure_install("Crypto", "pycryptodome")
ensure_install("yaml", "pyyaml")
ensure_install("qrcode")
ensure_install("requests")
ensure_install("cheroot")
ensure_install("wsgidav")
# NOTE: 二次尝试，确保一定装上 😂
ensure_install("wsgidav.wsgidav_app", "wsgidav")

from pan115 import Pan115Client

try:
    cookie = open(cookie_path, encoding="latin-1").read().strip()
except FileNotFoundError:
    cookie = None

from cheroot import wsgi
from wsgidav.wsgidav_app import WsgiDAVApp

from pan115_sharelink_dav_provider import Pan115ShareLinkFilesystemProvider

client = Pan115Client(cookie)
if client.cookie != cookie:
    open(cookie_path, "w", encoding="latin-1").write(client.cookie)

try:
    wsgidav_config_raw = open(wsgidav_config_file, encoding="utf-8").read()
except FileNotFoundError:
    from pkgutil import get_data
    wsgidav_config_raw = get_data("src", "sample_wsgidav.yaml")
    open(wsgidav_config_file, "wb").write(wsgidav_config_raw)

wsgidav_config = yaml_load(wsgidav_config_raw, Loader=yaml_Loader)

if host is not None:
    wsgidav_config["host"] = host
if port is not None:
    wsgidav_config["port"] = port
if verbose is not None:
    wsgidav_config["verbose"] = verbose
wsgidav_config["provider_mapping"] = {
    "/": Pan115ShareLinkFilesystemProvider.from_config(cookie, open(links_file, encoding="utf-8").read())
}

app = WsgiDAVApp(wsgidav_config)

server_args = {
    "bind_addr": (
        wsgidav_config.get("host", "0.0.0.0"), 
        wsgidav_config.get("port", 8080), 
    ),
    "wsgi_app": app,
}
server = wsgi.Server(**server_args)

try:
    print("""
    💥 Welcome to 115 share link webdav 😄
""")
    server.start()
except KeyboardInterrupt:
    print("Received Ctrl-C: stopping...")
finally:
    server.stop()
