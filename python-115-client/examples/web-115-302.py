#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 8)
__doc__ = "获取 115 文件信息和下载链接"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
    epilog="""
---------- 使用说明 ----------

你可以打开浏览器进行直接访问。

1. 如果想要访问某个路径，可以通过查询接口

    GET /{path}

或者

    GET /?path={path}

也可以通过 pickcode 查询

    GET /?pickcode={pickcode}

也可以通过 id 查询

    GET /?id={id}

2. 查询文件或文件夹的信息，返回 json

    GET /?method=attr

3. 查询文件夹内所有文件和文件夹的信息，返回 json

    GET /?method=list

4. 查询文件或文件夹的备注

    GET /?method=desc

5. 支持的查询参数

 参数    | 类型    | 必填 | 说明
-------  | ------- | ---- | ----------
pickcode | string  | 否   | 文件或文件夹的 pickcode，优先级高于 id
id       | integer | 否   | 文件或文件夹的 id，优先级高于 path
path     | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
method   | string  | 否   | 1. 'url': 【默认值】，这个文件的下载链接
         |         |      | 2. 'attr': 这个文件或文件夹的信息
         |         |      | 3. 'list': 这个文件夹内所有文件和文件夹的信息
         |         |      | 4. 'desc': 这个文件或文件夹的备注
""")
parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值 '0.0.0.0'")
parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值 80")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -c/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
args = parser.parse_args()
if args.version:
    print(".".join(map(str, __version__)))
    raise SystemExit(0)

try:
    from cachetools import LRUCache, TTLCache
    from flask import request, redirect, render_template_string, send_file, Flask, Response
    from p115 import P115Client, P115FileSystem
    from posixpatht import escape
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "cachetools", "flask", "posixpatht", "python-115"], check=True)
    from cachetools import LRUCache, TTLCache
    from flask import request, redirect, render_template_string, send_file, Flask, Response
    from p115 import P115Client, P115FileSystem
    from posixpatht import escape

from mimetypes import guess_type
from collections.abc import Callable, MutableMapping
from io import BytesIO
from json import JSONDecodeError
from os.path import expanduser, dirname, join as joinpath, realpath
from urllib.request import urlopen, Request
from urllib.parse import quote, unquote, urlsplit


dumps: Callable[..., bytes]
try:
    from orjson import dumps
except ImportError:
    odumps: Callable[..., str]
    try:
        from ujson import dumps as odumps
    except ImportError:
        from json import dumps as odumps
    dumps = lambda obj: bytes(odumps(obj, ensure_ascii=False), "utf-8")

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

client = P115Client(cookies, app="qandroid")
device = client.login_device()["icon"]
if cookies_path and cookies != client.cookies:
    open(cookies_path, "w").write(client.cookies)
fs = P115FileSystem(client, path_to_id=LRUCache(65536))
url_cache: MutableMapping[tuple[str, str], str] = TTLCache(65536, 60 * 30)

KEYS = (
    "id", "parent_id", "name", "path", "sha1", "pickcode", "is_directory", 
    "size", "ctime", "mtime", "atime", "thumb", "star", "labels", "score", 
    "hidden", "described", "violated", "url", 
)
application = Flask(__name__)


def get_url_with_pickcode(pickcode: str, use_web_api: bool = False):
    headers = {}
    user_agent = ""
    for key, val in request.headers:
        match key.lower():
            case "user-agent":
                user_agent = headers["User-Agent"] = val
            case "range":
                headers["Range"] = val
    try:
        try:
            url = url_cache[(pickcode, user_agent)]
        except KeyError:
            if not user_agent:
                headers["User-Agent"] = user_agent
            url_cache[(pickcode, user_agent)] = url = fs.get_url_from_pickcode(
                pickcode, detail=True, use_web_api=use_web_api, headers=headers)
        if use_web_api:
            resp = urlopen(Request(
                url, headers={**headers, "Cookie": "; ".join(f"{c.name}={c.value}" for c in client.cookiejar)}
            ))
            return send_file(resp, mimetype=resp.headers.get("Content-Type") or "application/octet-stream")
        else:
            resp = redirect(url)
            filename = url["file_name"] # type: ignore
            resp.headers["Content-Disposition"] = 'attachment; filename="%s"' % quote(filename)
            resp.headers["Content-Type"] = guess_type(filename)[0] or "application/octet-stream"
            return resp
    except OSError:
        return "Not Found", 404


def relogin_wrap(func, /, *args, **kwds):
    try:
        return func(*args, **kwds)
    except JSONDecodeError as e:
        pass
    client.login_another_app(device, replace=True)
    if cookies_path:
        open(cookies_path, "w").write(client.cookies)
    return func(*args, **kwds)


@application.get("/")
def index():
    pic = request.args.get("pic")
    if pic == "iina":
        return send_file(BytesIO(b'<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><rect y="0.000244141" width="32" height="32" rx="7.51807" fill="url(#paint0_linear_10408_1309)"/><rect x="5.5" y="13.3784" width="2.00482" height="5.35904" rx="1.00241" fill="url(#paint1_linear_10408_1309)"/><rect x="9.02173" y="11.7976" width="2.62169" height="7.78795" rx="1.31084" fill="url(#paint2_linear_10408_1309)"/><path d="M13.2881 14.1557C13.2881 10.8731 13.2881 9.23184 14.1967 8.44754C14.4469 8.23163 14.7356 8.06495 15.0476 7.95629C16.1812 7.56155 17.6025 8.38219 20.4453 10.0235L23.8046 11.9629C26.6474 13.6042 28.0687 14.4248 28.2937 15.6039C28.3556 15.9285 28.3556 16.2618 28.2937 16.5864C28.0687 17.7654 26.6474 18.5861 23.8046 20.2274L20.4453 22.1668C17.6025 23.8081 16.1812 24.6287 15.0476 24.234C14.7356 24.1253 14.4469 23.9587 14.1967 23.7427C13.2881 22.9584 13.2881 21.3172 13.2881 18.0346L13.2881 14.1557Z" fill="url(#paint3_linear_10408_1309)"/><defs><linearGradient id="paint0_linear_10408_1309" x1="16" y1="0.000244141" x2="16" y2="32.0002" gradientUnits="userSpaceOnUse"><stop stop-color="#4E4E4E"/><stop offset="1" stop-color="#262525"/></linearGradient><linearGradient id="paint1_linear_10408_1309" x1="5.5" y1="16.0387" x2="7.50482" y2="15.7495" gradientUnits="userSpaceOnUse"><stop stop-color="#8148EF"/><stop offset="1" stop-color="#4A2CC4"/></linearGradient><linearGradient id="paint2_linear_10408_1309" x1="9.02173" y1="15.6636" x2="11.6536" y2="15.322" gradientUnits="userSpaceOnUse"><stop stop-color="#4435E1"/><stop offset="1" stop-color="#3E5EFA"/></linearGradient><linearGradient id="paint3_linear_10408_1309" x1="25.4842" y1="15.653" x2="13.4168" y2="12.8771" gradientUnits="userSpaceOnUse"><stop stop-color="#00DDFE"/><stop offset="1" stop-color="#0092FA"/></linearGradient></defs></svg>'), mimetype="image/svg+xml")
    elif pic == "vlc":
        return send_file(BytesIO(b'<?xml version="1.0" ?><!DOCTYPE svg PUBLIC \'-//W3C//DTD SVG 1.1//EN\' \'http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\'><svg height="512px" style="enable-background:new 0 0 512 512;" version="1.1" viewBox="0 0 512 512" width="512px" xml:space="preserve" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><g id="_x31_2-vlc_x2C__media_x2C__player"><g><g><g><path d="M478.104,458.638l-59.65-119.619c-2.535-5.058-7.691-8.255-13.326-8.255H106.872 c-5.635,0-10.791,3.197-13.326,8.255L33.887,458.638c-2.325,4.637-2.053,10.141,0.66,14.538 c2.715,4.396,7.516,7.118,12.676,7.118h417.554c5.16,0,9.959-2.694,12.707-7.087 C480.193,468.778,480.404,463.307,478.104,458.638L478.104,458.638z M478.104,458.638" style="fill:#FF9800;"/></g><path d="M375.297,345.718c0,43.659-107.068,44.858-119.297,44.858c-12.23,0-119.302-1.199-119.302-44.858 c0-1.197,0.301-2.691,0.6-3.887l20.579-75.665c14.61,11.369,53.086,19.739,98.124,19.739s83.512-8.37,98.123-19.739 l20.578,75.665C375.002,343.026,375.297,344.521,375.297,345.718L375.297,345.718z M375.297,345.718" style="fill:#FCFCFC;"/><path d="M332.35,186.62c-18.787,5.975-46.227,9.565-76.35,9.565s-57.563-3.591-76.351-9.565l22.964-84.34 c15.506,2.69,34,4.187,53.387,4.187s37.879-1.496,53.387-4.187L332.35,186.62z M332.35,186.62" style="fill:#FCFCFC;"/><path d="M256,106.467c-19.387,0-37.881-1.496-53.387-4.187l10.439-37.982 c5.666-20.03,22.668-32.592,42.947-32.592s37.279,12.562,42.945,32.297l10.441,38.277 C293.879,104.971,275.387,106.467,256,106.467L256,106.467z M256,106.467" style="fill:#FF9800;"/><path d="M354.123,266.166c-14.611,11.369-53.086,19.739-98.123,19.739s-83.513-8.37-98.124-19.739 l21.772-79.546c18.789,5.975,46.228,9.565,76.351,9.565s57.563-3.591,76.35-9.565L354.123,266.166z M354.123,266.166" style="fill:#FF9800;"/></g></g></g><g id="Layer_1"/></svg>'), mimetype="image/svg+xml")
    elif pic == "potplayer":
        return send_file(BytesIO(b'<svg width="256pt" height="256pt" version="1.1" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg"><g id="#f8d714ff" fill="#f8d714"> <path d="m14.48 5.74c3.4-1.07 7.01-0.71 10.52-0.77 70.34 0.02 140.68-0.01 211.02 0.01 5.46-0.33 10.91 2.69 13.41 7.57 2.08 3.81 1.52 8.3 1.6 12.47-0.01 68.66-0.01 137.32 0 205.98-0.06 4.38 0.49 9.15-1.94 13.05-2.6 4.58-7.88 7.21-13.09 6.96-71.98 0.04-143.96 0.03-215.93 0-5.25 0.27-10.56-2.37-13.17-6.99-2.42-3.88-1.87-8.63-1.93-12.99 0.02-70.34-0.01-140.67 0.01-211.01-0.43-6.21 3.59-12.31 9.5-14.28m107.84 33.69c-14.96 1.39-29.3 8.36-39.65 19.25-9.91 10.28-16.17 24-17.37 38.23-1.18 12.94 1.74 26.23 8.31 37.46 7.78 13.44 20.66 23.86 35.48 28.54 14.49 4.68 30.65 3.88 44.61-2.22 14.42-6.23 26.32-18.03 32.68-32.4 6.61-14.74 7.24-32.04 1.71-47.22-4.72-13.25-14.04-24.78-25.96-32.24-11.74-7.43-25.99-10.76-39.81-9.4m-58.68 142.57c0 11.33-0.01 22.66 0 34h7.36c0-4.13 0-8.26 0.01-12.38 4.89-0.21 10.28 0.89 14.7-1.78 6.64-4.22 5.84-16.13-1.84-18.76-6.53-2.02-13.51-0.71-20.23-1.08m31.36-0.02v34.03c2.21-0.01 4.43-0.02 6.64-0.03 0.01-11.3-0.09-22.6 0.05-33.89-2.23-0.1-4.46-0.07-6.69-0.11m14.91 9.93c-2.42 1.25-3.4 3.9-4.08 6.36 2.18 0.12 4.38 0.06 6.57 0.15 0.83-4.08 5.95-5.29 9.03-2.88 0.68 1.52 1.23 4.02-0.79 4.76-3.79 1.3-8.04 0.88-11.69 2.64-4.94 2.35-4.8 10.64 0.13 12.94 4.31 1.97 9.56 1.01 13.21-1.89 0.26 3.53 4.7 1.48 7.03 2.02-1.44-6.71-0.21-13.61-0.86-20.38-0.19-2.04-1.85-3.62-3.67-4.32-4.76-1.82-10.32-1.73-14.88 0.6m52.44 1.46c-4.44 4.27-4.97 11.44-2.64 16.91 2.61 6 10.47 8.19 16.25 5.72 3.31-1.17 5.09-4.4 6.6-7.34-1.94-0.02-3.87-0.03-5.8 0-1.88 2.97-5.81 4.17-8.96 2.5-2.29-1.05-2.56-3.78-2.98-5.95 6.09-0.03 12.18 0 18.27-0.01-0.37-3.83-0.81-7.91-3.32-11.01-4.08-5.29-12.77-5.47-17.42-0.82m30.89 1.79c0.06-1.38 0.12-2.77 0.16-4.15-2.13-0.01-4.27-0.01-6.4-0.01v25.01c2.21-0.01 4.43-0.03 6.64-0.04 0.32-5.5-0.92-11.27 1.04-16.55 1.5-3.15 5.26-3.51 8.33-3.15-0.01-2.14-0.01-4.28-0.02-6.42-3.98 0.03-7.62 1.94-9.75 5.31m-61.66-4.17c3.01 8.67 6.35 17.24 9.1 25.99 0.23 3.74-3.99 4.08-6.67 3.4-0.01 1.73-0.01 3.47-0.01 5.2 4.41 0.8 10.45 0.5 12.22-4.49 3.74-9.96 7.1-20.06 10.66-30.08-2.29-0.01-4.58-0.01-6.86-0.01-1.82 6.03-3.63 12.06-5.5 18.06-2.14-5.92-3.89-11.98-5.73-18.01-2.4-0.05-4.81-0.05-7.21-0.06z"/> <path d="m111.13 74.07c1.31-0.17 2.41 0.69 3.5 1.25 13.64 8.39 27.33 16.71 41 25.05 1.27 0.84 3.17 1.74 2.53 3.64-1.02 1.06-2.3 1.82-3.55 2.58-13.78 8.18-27.43 16.6-41.23 24.75-1.21 1.08-3.48 0.59-3.29-1.3-0.22-17.35-0.01-34.71-0.1-52.06 0.12-1.36-0.28-3.1 1.14-3.91z"/> <path d="m71 187.63c3.41 0.08 7.12-0.52 10.26 1.13 2.82 2.15 2.47 7.87-1.24 8.92-2.98 0.55-6.02 0.3-9.02 0.31v-10.36z"/> <path d="m164.77 200.98c0.41-3.09 2.66-6.44 6.2-5.83 3.27-0.26 4.83 3.13 5.25 5.84-3.82 0.02-7.64 0.02-11.45-0.01z"/> <path d="m112.05 208c1.75-3.68 6.75-2.65 10.01-3.99-0.17 2.65 0.47 6.23-2.36 7.73-2.87 2.1-8.98 0.72-7.65-3.74z"/></g><g id="#ffffffff"><path d="m122.32 39.43c13.82-1.36 28.07 1.97 39.81 9.4 11.92 7.46 21.24 18.99 25.96 32.24 5.53 15.18 4.9 32.48-1.71 47.22-6.36 14.37-18.26 26.17-32.68 32.4-13.96 6.1-30.12 6.9-44.61 2.22-14.82-4.68-27.7-15.1-35.48-28.54-6.57-11.23-9.49-24.52-8.31-37.46 1.2-14.23 7.46-27.95 17.37-38.23 10.35-10.89 24.69-17.86 39.65-19.25m-11.19 34.64c-1.42 0.81-1.02 2.55-1.14 3.91 0.09 17.35-0.12 34.71 0.1 52.06-0.19 1.89 2.08 2.38 3.29 1.3 13.8-8.15 27.45-16.57 41.23-24.75 1.25-0.76 2.53-1.52 3.55-2.58 0.64-1.9-1.26-2.8-2.53-3.64-13.67-8.34-27.36-16.66-41-25.05-1.09-0.56-2.19-1.42-3.5-1.25z" fill="#fff"/></g><g id="#222222ff" fill="#222"> <path d="m63.64 182c6.72 0.37 13.7-0.94 20.23 1.08 7.68 2.63 8.48 14.54 1.84 18.76-4.42 2.67-9.81 1.57-14.7 1.78-0.01 4.12-0.01 8.25-0.01 12.38h-7.36c-0.01-11.34 0-22.67 0-34m7.36 5.63v10.36c3-0.01 6.04 0.24 9.02-0.31 3.71-1.05 4.06-6.77 1.24-8.92-3.14-1.65-6.85-1.05-10.26-1.13z"/> <path d="m95 181.98c2.23 0.04 4.46 0.01 6.69 0.11-0.14 11.29-0.04 22.59-0.05 33.89-2.21 0.01-4.43 0.02-6.64 0.03v-34.03z"/> <path d="m109.91 191.91c4.56-2.33 10.12-2.42 14.88-0.6 1.82 0.7 3.48 2.28 3.67 4.32 0.65 6.77-0.58 13.67 0.86 20.38-2.33-0.54-6.77 1.51-7.03-2.02-3.65 2.9-8.9 3.86-13.21 1.89-4.93-2.3-5.07-10.59-0.13-12.94 3.65-1.76 7.9-1.34 11.69-2.64 2.02-0.74 1.47-3.24 0.79-4.76-3.08-2.41-8.2-1.2-9.03 2.88-2.19-0.09-4.39-0.03-6.57-0.15 0.68-2.46 1.66-5.11 4.08-6.36m2.14 16.09c-1.33 4.46 4.78 5.84 7.65 3.74 2.83-1.5 2.19-5.08 2.36-7.73-3.26 1.34-8.26 0.31-10.01 3.99z"/> <path d="m162.35 193.37c4.65-4.65 13.34-4.47 17.42 0.82 2.51 3.1 2.95 7.18 3.32 11.01-6.09 0.01-12.18-0.02-18.27 0.01 0.42 2.17 0.69 4.9 2.98 5.95 3.15 1.67 7.08 0.47 8.96-2.5 1.93-0.03 3.86-0.02 5.8 0-1.51 2.94-3.29 6.17-6.6 7.34-5.78 2.47-13.64 0.28-16.25-5.72-2.33-5.47-1.8-12.64 2.64-16.91m2.42 7.61c3.81 0.03 7.63 0.03 11.45 0.01-0.42-2.71-1.98-6.1-5.25-5.84-3.54-0.61-5.79 2.74-6.2 5.83z"/> <path d="m193.24 195.16c2.13-3.37 5.77-5.28 9.75-5.31 0.01 2.14 0.01 4.28 0.02 6.42-3.07-0.36-6.83 0-8.33 3.15-1.96 5.28-0.72 11.05-1.04 16.55-2.21 0.01-4.43 0.03-6.64 0.04v-25.01c2.13 0 4.27 0 6.4 0.01-0.04 1.38-0.1 2.77-0.16 4.15z"/> <path d="m131.58 190.99c2.4 0.01 4.81 0.01 7.21 0.06 1.84 6.03 3.59 12.09 5.73 18.01 1.87-6 3.68-12.03 5.5-18.06 2.28 0 4.57 0 6.86 0.01-3.56 10.02-6.92 20.12-10.66 30.08-1.77 4.99-7.81 5.29-12.22 4.49 0-1.73 0-3.47 0.01-5.2 2.68 0.68 6.9 0.34 6.67-3.4-2.75-8.75-6.09-17.32-9.1-25.99z"/></g></svg>'), mimetype="image/svg+xml")
    elif pic == "mxplayer":
        return send_file(BytesIO(b'<svg id="svg" width="100px" viewBox="0 0 100 100" height="100px" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><g id="svgg"><path id="path0" d="M47.333 2.447 C 44.804 2.654,41.449 3.238,37.838 4.099 C 36.827 4.340,34.775 5.042,32.667 5.869 C 31.213 6.440,27.478 8.258,26.784 8.733 C 26.436 8.972,26.090 9.167,26.015 9.167 C 25.624 9.167,20.550 12.838,19.003 14.240 C 16.084 16.885,12.607 20.793,11.216 22.991 C 10.894 23.500,10.494 24.067,10.329 24.250 C 10.163 24.433,9.804 25.016,9.531 25.545 C 9.258 26.075,8.953 26.606,8.853 26.726 C 8.267 27.432,6.137 32.182,5.232 34.800 C 2.837 41.731,1.961 51.320,3.142 57.667 C 3.321 58.629,3.592 60.129,3.743 61.000 C 3.963 62.269,5.332 66.789,5.990 68.417 C 6.440 69.530,8.141 73.073,8.631 73.917 C 8.951 74.467,9.401 75.254,9.632 75.667 C 9.863 76.079,10.364 76.829,10.747 77.333 C 11.129 77.837,11.486 78.362,11.540 78.500 C 12.001 79.669,18.426 86.557,20.168 87.750 C 20.570 88.025,21.086 88.422,21.315 88.632 C 21.842 89.116,25.549 91.634,25.950 91.780 C 26.115 91.840,26.558 92.098,26.935 92.353 C 27.956 93.045,31.932 94.904,33.876 95.600 C 42.948 98.843,51.123 99.447,60.583 97.570 C 62.142 97.261,63.979 96.823,64.667 96.597 C 67.249 95.747,68.898 95.147,69.810 94.724 C 70.327 94.484,71.275 94.046,71.917 93.749 C 72.558 93.453,73.496 92.965,74.000 92.665 C 74.504 92.365,75.254 91.933,75.667 91.706 C 76.079 91.478,76.792 91.015,77.250 90.676 C 77.708 90.338,78.196 90.018,78.333 89.965 C 80.371 89.185,88.473 81.008,90.417 77.771 C 90.600 77.466,91.045 76.774,91.405 76.233 C 92.525 74.553,93.455 72.785,95.077 69.250 C 98.036 62.806,99.454 52.414,98.443 44.583 C 98.289 43.392,98.119 42.079,98.065 41.667 C 97.643 38.416,95.090 31.158,93.200 27.835 C 92.861 27.238,92.533 26.629,92.473 26.482 C 92.412 26.335,91.999 25.666,91.556 24.996 C 91.113 24.327,90.675 23.660,90.583 23.516 C 88.060 19.536,82.404 13.785,78.333 11.062 C 77.921 10.786,77.246 10.330,76.833 10.050 C 75.738 9.306,72.984 7.716,72.417 7.500 C 72.148 7.398,71.250 6.985,70.422 6.582 C 69.594 6.179,68.467 5.701,67.917 5.520 C 67.367 5.339,66.242 4.954,65.417 4.665 C 60.715 3.018,52.563 2.018,47.333 2.447 M38.562 30.863 C 39.399 31.337,40.683 32.076,41.417 32.504 C 42.150 32.931,43.087 33.468,43.500 33.695 C 43.913 33.923,45.337 34.731,46.667 35.492 C 47.996 36.252,50.658 37.774,52.583 38.875 C 54.508 39.976,56.833 41.307,57.750 41.835 C 58.667 42.362,61.104 43.749,63.167 44.916 C 65.229 46.084,67.254 47.243,67.667 47.492 C 68.079 47.741,69.467 48.533,70.750 49.251 C 73.449 50.762,73.833 51.063,73.833 51.664 C 73.833 52.380,73.934 52.317,60.167 60.158 C 52.879 64.309,46.167 68.140,45.250 68.673 C 36.899 73.527,36.862 73.544,36.241 72.922 L 35.830 72.511 35.873 51.574 L 35.917 30.637 36.310 30.319 C 36.844 29.886,36.837 29.884,38.562 30.863 " stroke="none" fill="#3c8cec" fill-rule="evenodd"></path></g></svg>'), mimetype="image/svg+xml")
    else:
        return query("/")


@application.get("/<path:path>")
def query(path: str):
    method = request.args.get("method", "url")
    pickcode = request.args.get("pickcode")
    fid: None | int | str = request.args.get("id")
    use_web_api = False if request.args.get("web") in (None, "false") else True
    scheme = request.environ.get("HTTP_X_FORWARDED_PROTO") or "http"
    netloc = urlsplit(unquote(request.url)).netloc
    origin = f"{scheme}://{netloc}"
    def append_url(attr):
        path_url = attr.get("path_url") or "%s%s" % (origin, quote(attr["path"], safe=":/"))
        if attr["is_directory"]:
            attr["short_url"] = f"origin?id={attr['id']}"
            attr["url"] = f"{path_url}?id={attr['id']}"
        else:
            short_url = f"{origin}?pickcode={attr['pickcode']}"
            url = f"{path_url}?pickcode={attr['pickcode']}"
            if attr["violated"] and attr["size"] < 1024 * 1024 * 115:
                short_url += "&web=true"
                url += "&web=true"
            attr["short_url"] = short_url
            attr["url"] = url
        return attr
    if method == "attr":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                attr = relogin_wrap(fs.attr, int(fid))
            else:
                path = request.args.get("path") or path
                attr = relogin_wrap(fs.attr, path)
        except FileNotFoundError:
            return "Not Found", 404
        append_url(attr)
        json_str = dumps({k: attr.get(k) for k in KEYS})
        return Response(json_str, content_type='application/json; charset=utf-8')
    elif method == "list":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                children = relogin_wrap(fs.listdir_attr, int(fid))
            else:
                path = request.args.get("path") or path
                children = relogin_wrap(fs.listdir_attr, path)
        except FileNotFoundError:
            return "Not Found", 404
        except NotADirectoryError as exc:
            return f"Bad Request: {exc}", 400
        json_str = dumps([
            {k: attr.get(k) for k in KEYS} 
            for attr in map(append_url, children)
        ])
        return Response(json_str, content_type='application/json; charset=utf-8')
    elif method == "desc":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                return fs.desc(int(fid))
            else:
                path = request.args.get("path") or path
                return fs.desc(path)
        except FileNotFoundError:
            return "Not Found", 404
    if pickcode:
        return get_url_with_pickcode(pickcode, use_web_api)
    try:
        if fid is not None:
            attr = relogin_wrap(fs.attr, int(fid))
        else:
            path = request.args.get("path") or path
            attr = relogin_wrap(fs.attr, path)
    except FileNotFoundError:
        return "Not Found", 404
    if not attr["is_directory"]:
        return get_url_with_pickcode(attr["pickcode"], use_web_api)
    try:
        children = relogin_wrap(fs.listdir_attr, attr["id"])
    except NotADirectoryError as exc:
        return f"Bad Request: {exc}", 400
    for subattr in children:
        subattr["path_url"] = "%s%s" % (origin, quote(subattr["path"], safe=":/"))
        append_url(subattr)
    fid = attr["id"]
    if fid == 0:
        header = f'<strong><a href="{origin}?id=0&method=list" style="border: 1px solid black; text-decoration: none">/</a></strong>'
    else:
        ancestors = fs.get_ancestors(int(attr["id"]))
        info = ancestors[-1]
        header = f'<strong><a href="{origin}?id=0" style="border: 1px solid black; text-decoration: none">/</a></strong>' + "".join(
                f'<strong><a href="{origin}?id={info["id"]}" style="border: 1px solid black; text-decoration: none">{escape(info["name"])}</a></strong>/' 
                for info in ancestors[1:-1]
            ) + f'<strong><a href="{origin}?id={info["id"]}&method=list" style="border: 1px solid black; text-decoration: none">{escape(info["name"])}</a></strong>'
    return render_template_string(
        """\
<!DOCTYPE html>
<html>
<head>
    <title>115 File List</title>
    <link href="//cdnres.115.com/site/static/style_v10.0/file/css/file_type.css?_vh=bf604a2_70" rel="stylesheet" type="text/css">
    <style>
        a:hover {
            color: red;
        }
        .file-type {
            flex: 1;
            min-width: 0;
            position: relative;
            height: 32px;
            padding-left: 47px;
            flex-direction: column;
            justify-content: center;
        }
        td {
            vertical-align: middle;
        }
        img {
            height: 32px;
            width: 32px; 
        }
        table {
            border-collapse: collapse;
            margin: 25px 0;
            font-size: 0.9em;
            font-family: sans-serif;
            min-width: 400px;
            box-shadow: 0 0 20px rgba(0, 0, 0, 0.15);
        }
        thead tr {
            background-color: #009879;
            color: #ffffff;
            text-align: left;
        }
        th, td {
            padding: 12px 15px;
        }
        tbody tr {
            border-bottom: 1px solid #dddddd;
            transition: background-color 0.3s, transform 0.3s;
        }
        tbody tr:nth-of-type(even) {
            background-color: #f3f3f3;
        }
        tbody tr:last-of-type {
            border-bottom: 2px solid #009879;
        }
        tbody tr:hover {
            color: #009879;
            background-color: rgba(135, 206, 235, 0.5);
            transform: scale(1.02);
        }
    </style>
</head>
<body>
    {{ header | safe }}
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Open</th>
                <th>Size</th>
                <th>Attr</th>
                <th>Desc</th>
                <th>Last Modified</th>
            </tr>
        </thead>
        <tbody>
            {% if attr["id"] != 0 %}
            <tr>
                <td colspan="6"><a href="/?id={{ attr["parent_id"] }}" style="display: block; text-align: center; text-decoration: none; font-size: 30px">..</a></td>
            </tr>
            {% endif %}
            {% for attr in children %}
            <tr>
                {% set name = attr["name"] %}
                {% set url = attr["url"] %}
                <td><i class="file-type tp-{{ attr.get("ico", "folder") }}"></i><a href="{{ url }}">{{ name }}</a></td>
                {% if attr["is_directory"] %}
                <td></td>
                <td>--</td>
                {% else %}
                <td>
                    <a href="iina://weblink?url={{ url }}"><img src="/?pic=iina" /></a>
                    <a href="potplayer://{{ url }}"><img src="/?pic=potplayer" /></a>
                    <a href="vlc://{{ url }}"><img src="/?pic=vlc" /></a>
                    <a href="intent:{{ attr["short_url"] }}#Intent;package=com.mxtech.videoplayer.pro;S.title={{ name }};end"><img src="/?pic=mxplayer" /></a>
                </td>
                </td>
                <td>{{ attr["size"] }}</td>
                {% endif %}
                <td><a href="{{ attr["path_url"] }}?id={{ attr["id"] }}&method=attr">attr</a></td>
                <td><a href="{{ attr["path_url"] }}?id={{ attr["id"] }}&method=desc">desc</a></td>
                <td>{{ attr["etime"] }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>""", 
        attr=attr, 
        children=children, 
        origin=origin, 
        header=header, 
    )


application.run(host=args.host, port=args.port, threaded=True)

