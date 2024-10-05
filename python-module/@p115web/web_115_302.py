#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 2, 5)
__requirements__ = ["cachetools", "flask", "Flask-Compress", "orjson", "python-115", "urllib3_request", "werkzeug", "wsgidav"]
__doc__ = """\
    🕸️ 获取你的 115 网盘账号上文件信息和下载链接 🕷️

🚫 注意事项：请求头需要携带 User-Agent。
如果使用 web 的下载接口，则有如下限制：
    - 大于等于 115 MB 时不能下载
    - 不能直接请求直链，因为需要携带特定的 Cookie 和 User-Agent，所以文件由服务器代理转发，不走 302
"""

from argparse import ArgumentParser, RawTextHelpFormatter
from warnings import warn

try:
    from p115 import AVAILABLE_APPS
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", *__requirements__], check=True)
    from p115 import AVAILABLE_APPS

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
    epilog="""
---------- 使用说明 ----------

你可以打开浏览器进行直接访问。

1. 如果想要访问某个路径，可以通过查询接口

    GET {path}

或者

    GET ?path={path}

也可以通过 pickcode 查询

    GET ?pickcode={pickcode}

也可以通过 id 查询

    GET ?id={id}

也可以通过 sha1 查询（必是文件）

    GET ?sha1={sha1}

2. 查询文件或文件夹的信息，返回 json

    GET ?method=attr

3. 查询文件夹内所有文件和文件夹的信息，返回 json

    GET ?method=list

4. 获取文件的下载链接

    GET ?method=url

5. 查询文件或文件夹的备注

    GET ?method=desc

6. 支持的查询参数

 参数      | 类型    | 必填 | 说明
---------  | ------- | ---- | ----------
pickcode   | string  | 否   | 文件或文件夹的 pickcode，优先级高于 id
id         | integer | 否   | 文件或文件夹的 id，优先级高于 sha1
sha1       | string  | 否   | 文件或文件夹的 id，优先级高于 path
path       | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
method     | string  | 否   | 0. '':     缺省值，直接下载
           |         |      | 2. 'url':  这个文件的下载链接和请求头，JSON 格式
           |         |      | 2. 'attr': 这个文件或文件夹的信息，JSON 格式
           |         |      | 3. 'list': 这个文件夹内所有文件和文件夹的信息，JSON 格式
           |         |      | 4. 'desc': 这个文件或文件夹的备注，text/html

当文件被下载时，可以有其它查询参数

 参数      | 类型    | 必填 | 说明
---------  | ------- | ---- | ----------
web        | string  | 否   | 使用 web 接口获取下载链接（文件由服务器代理转发，不走 302）
m3u8       | string  | 否   | 文件作为 m3u8 打开，需要用到 web 的 cookies（如不提供则自动扫码）
definition | integer | 否   | m3u8 的分辨率，默认值 0，即所有分辨率，其它的选项：3 - HD（标清），4 - UD（高清）
image      | string  | 否   | 文件作为图片打开

7. 支持 webdav

在浏览器或 webdav 挂载软件 中输入（可以有个端口号） http://localhost/<dav
目前没有用户名和密码就可以浏览，支持 302
""")
parser.add_argument("-a", "--login-app", choices=("", *AVAILABLE_APPS), help="指定默认的登录 app，如果未指定，则默认为所传入 cookies 对应的 app，获取不到 app 则默认为 'qandroid'")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -cp/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="""\
存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一: 
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录""")
parser.add_argument("-wc", "--web-cookies", default="", help="提供一个 web 的 cookies，因为目前使用的获取 .m3u8 的接口，需要 web 的 cookies 才能正确获取数据，如不提供，则将自动扫码获取")
parser.add_argument("-l", "--lock-dir-methods", action="store_true", help="对 115 的文件系统进行增删改查的操作（但不包括上传和下载）进行加锁，限制为单线程，这样就可减少 405 响应，以降低扫码的频率")
parser.add_argument("-pc", "--path-persistence-commitment", action="store_true", help="路径持久性承诺，只要你能保证文件不会被移动（可新增删除，但对应的路径不可被其他文件复用），打开此选项，用路径请求直链时，可节约一半时间")
parser.add_argument("-ci", "--cdn-image", action="store_true", help="图片走 cdn 接口而不是走下载接口")
parser.add_argument("-ur", "--use-request", choices=("httpx", "requests", "urllib3", "urlopen"), default="urllib3", help="选择一个网络请求模块，默认值：urllib3")
parser.add_argument("-r", "--root", default=0, help="选择一个根 路径 或 id，默认值 0")
parser.add_argument("-P", "--password", default="", help="密码，如果提供了密码，那么每次访问必须携带请求参数 ?password={password}")
parser.add_argument("-o", "--origin", help="origin 或者说 base_url，用来拼接路径，获取完整链接，默认行为是自行确定")
parser.add_argument("-p1", "--predicate", help="断言，当断言的结果为 True 时，文件或目录会被显示")
parser.add_argument(
    "-t1", "--predicate-type", default="ignore", 
    choices=("ignore", "ignore-file", "expr", "lambda", "stmt", "module", "file", "re"), 
    help="""断言类型，默认值为 'ignore'
    - ignore       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - ignore-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 p115.P115Path 对象
    - lambda       lambda 函数，接受一个 p115.P115Path 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 p115.P115Path 对象
    - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115Path 对象作为参数
    - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115Path 对象作为参数
    - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
""")
parser.add_argument("-p2", "--strm-predicate", help="strm 断言（优先级高于 -p1/--predicate），当断言的结果为 True 时，文件会被显示为带有 .strm 后缀的文本文件，打开后是链接")
parser.add_argument(
    "-t2", "--strm-predicate-type", default="filter", 
    choices=("filter", "filter-file", "expr", "lambda", "stmt", "module", "file", "re"), 
    help="""断言类型，默认值为 'filter'
    - filter       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - filter-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 p115.P115Path 对象
    - lambda       lambda 函数，接受一个 p115.P115Path 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 p115.P115Path 对象
    - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115Path 对象作为参数
    - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115Path 对象作为参数
    - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
""")

if __name__ == "__main__":
    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
    parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值：80")
    parser.add_argument("-d", "--debug", action="store_true", help="启用 debug 模式，当文件变动时自动重启 + 输出详细的错误信息")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
else:
    from sys import argv

    try:
        args_start = argv.index("--")
        args, unknown = parser.parse_known_args(argv[args_start+1:])
        if unknown:
            warn(f"unknown args passed: {unknown}")
    except ValueError:
        args = parser.parse_args([])

try:
    from cachetools import LRUCache, TTLCache
    from flask import request, redirect, render_template_string, send_file, Flask, Response
    from flask_compress import Compress
    from orjson import dumps, loads
    from p115 import P115Client, P115FileSystem, P115Path, P115URL, AuthenticationError
    from posixpatht import escape as escape_name
    from urllib3.poolmanager import PoolManager
    from urllib3_request import request as urllib3_request
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from werkzeug.serving import run_simple
    from wsgidav.wsgidav_app import WsgiDAVApp
    from wsgidav.dav_error import DAVError
    from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", *__requirements__], check=True)
    import posixpatht
    from cachetools import LRUCache, TTLCache
    from flask import request, redirect, render_template_string, send_file, Flask, Response
    from flask_compress import Compress # type: ignore
    from orjson import dumps, loads
    from p115 import P115Client, P115FileSystem, P115Path, P115URL, AuthenticationError
    from posixpatht import escape as escape_name
    from urllib3.poolmanager import PoolManager
    from urllib3_request import request as urllib3_request
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from werkzeug.serving import run_simple
    from wsgidav.wsgidav_app import WsgiDAVApp # type: ignore
    from wsgidav.dav_error import DAVError # type: ignore
    from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider # type: ignore

import errno

from collections import UserString
from collections.abc import Callable, MutableMapping
from functools import cached_property, partial, update_wrapper
from hashlib import sha1
from html import escape
from io import BytesIO
from os import stat
from os.path import exists, expanduser, dirname, join as joinpath, realpath
from posixpath import splitext
from socket import getdefaulttimeout, setdefaulttimeout
from sys import exc_info
from threading import Lock
from time import localtime, strftime
from typing import cast
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlsplit

from util.predicate import make_predicate # type: ignore


if getdefaulttimeout() is None:
    setdefaulttimeout(30)

cookies = args.cookies
cookies_path = args.cookies_path
web_cookies = args.web_cookies
cookies_path_mtime = 0
lock_dir_methods = args.lock_dir_methods
path_persistence_commitment = args.path_persistence_commitment
cdn_image = args.cdn_image
use_request = args.use_request
root = args.root
password = args.password
origin = args.origin

import re

if predicate := args.predicate or None:
    predicate = make_predicate(predicate, {"re": re}, type=args.predicate_type)

if strm_predicate := args.strm_predicate or None:
    strm_predicate = make_predicate(strm_predicate, {"re": re}, type=args.strm_predicate_type)

login_lock = Lock()
web_login_lock = Lock()
fs_lock = Lock() if lock_dir_methods else None

def default(obj, /):
    if isinstance(obj, UserString):
        return str(obj)
    return NotImplemented

if not cookies:
    if cookies_path:
        try:
            cookies = open(cookies_path, encoding="utf-8").read().strip()
        except FileNotFoundError:
            pass
    else:
        seen = set()
        for cookies_dir in (".", expanduser("~"), dirname(__file__)):
            cookies_dir = realpath(cookies_dir)
            if cookies_dir in seen:
                continue
            seen.add(cookies_dir)
            try:
                path = joinpath(cookies_dir, "115-cookies.txt")
                if cookies := open(path, encoding="utf-8").read().strip():
                    cookies_path = path
                    cookies_path_mtime = stat(path).st_mtime_ns
                    break
            except FileNotFoundError:
                pass

client = P115Client(cookies or None, app=args.login_app or "qandroid")
if cookies_path and (not exists(cookies_path) or cookies != client.cookies):
    open(cookies_path, "w", encoding="utf-8").write(client.cookies)

urlopen = partial(urllib3_request, pool=PoolManager(num_pools=50))
do_request: None | Callable = None
match use_request:
    case "httpx":
        from httpx import HTTPStatusError as StatusError
        def get_status_code(e):
            return e.response.status_code
    case "requests":
        try:
            from requests import Session
            from requests.exceptions import HTTPError as StatusError # type: ignore
            from requests_request import request as requests_request
        except ImportError:
            from sys import executable
            from subprocess import run
            run([executable, "-m", "pip", "install", "-U", "requests", "requests_request"], check=True)
            from requests import Session
            from requests.exceptions import HTTPError as StatusError # type: ignore
            from requests_request import request as requests_request
        do_request = partial(requests_request, session=Session())
        def get_status_code(e):
            return e.response.status_code
    case "urllib3":
        from urllib.error import HTTPError as StatusError # type: ignore
        do_request = urlopen
        def get_status_code(e):
            return e.status
    case "urlopen":
        from urllib.error import HTTPError as StatusError # type: ignore
        try:
            from urlopen import request as do_request
        except ImportError:
            from sys import executable
            from subprocess import run
            run([executable, "-m", "pip", "install", "-U", "python-urlopen"], check=True)
            from urlopen import request as do_request
        def get_status_code(e):
            return e.status

if args.login_app:
    device = args.login_app
else:
    device = client.login_device(request=do_request)["icon"]
    if device not in AVAILABLE_APPS:
        # 115 浏览器版，实际就是 web
        if device == "desktop":
            device = "web"
        else:
            warn(f"encountered an unsupported app {device!r}, fall back to 'qandroid'")
            device = "qandroid"
fs = client.get_fs(client, cache_id_to_readdir=65536, cache_path_to_id=1048576, request=do_request)
# NOTE: id 到 pickcode 的映射
id_to_pickcode: MutableMapping[int, str] = LRUCache(65536)
# NOTE: sha1 到 pickcode 到映射
sha1_to_pickcode: MutableMapping[str, str] = LRUCache(65536)
# NOTE: 链接缓存，如果改成 None，则不缓存，可以自行设定 ttl (time-to-live)
url_cache: None | MutableMapping[tuple[str, str], P115URL] = TTLCache(1024, ttl=0.3)
# NOTE: 缓存图片的 CDN 直链 1 小时
image_url_cache: MutableMapping[str, None | P115URL] = TTLCache(65536, ttl=3600)
# NOTE: 每个 ip 对于某个资源的某个 range 请求，一定时间范围内，分别只放行一个，可以自行设定 ttl (time-to-live)
range_request_cooldown: MutableMapping[tuple[str, str, str, str], None] = TTLCache(1024, ttl=0.1)
# NOTE: webdav 的文件对象缓存
webdav_file_cache: MutableMapping[str, DAVNonCollection] = LRUCache(65536)

KEYS = (
    "id", "parent_id", "name", "path", "relpath", "sha1", "pickcode", "is_directory", 
    "size", "format_size", "ctime", "mtime", "atime", "thumb", "star", "labels", 
    "score", "hidden", "described", "violated", "url", "short_url", "ancestors", 
)
flask_app = Flask(__name__)
Compress(flask_app)


class DavPathBase:

    def __getattr__(self, attr, /):
        try:
            return self.attr[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    @cached_property
    def creationdate(self, /) -> float:
        return self.ctime

    @cached_property
    def ctime(self, /) -> float:
        return self.attr["ctime"]

    @cached_property
    def mtime(self, /) -> float:
        return self.attr["mtime"]

    @cached_property
    def name(self, /) -> str:
        return self.attr["name"]

    def get_creation_date(self, /) -> float:
        return self.ctime

    def get_display_name(self, /) -> str:
        return self.name

    def get_etag(self, /) -> str:
        return "%s-%s-%s" % (
            self.attr["pickcode"], 
            self.mtime, 
            self.size, 
        )

    def get_last_modified(self, /) -> float:
        return self.mtime

    def is_link(self, /) -> bool:
        return False

    def support_etag(self, /) -> bool:
        return True

    def support_modified(self, /) -> bool:
        return True


class FileResource(DavPathBase, DAVNonCollection):

    def __init__(
        self, 
        /, 
        path: str, 
        environ: dict, 
        attr: P115Path, 
    ):
        super().__init__(path, environ)
        self.attr = attr
        if cdn_image and image_url_cache and (url := image_url_cache.get(attr["pickcode"])):
            self.__dict__["url"] = url
            self.__dict__["size"] = url["size"]
        webdav_file_cache[path] = self

    @cached_property
    def origin(self, /) -> str:
        if origin:
            return origin
        return f"{self.environ['wsgi.url_scheme']}://{self.environ['HTTP_HOST']}"

    @cached_property
    def size(self, /) -> int:
        if self.path.endswith(".strm"):
            return len(self.strm_data)
        return self.attr["size"]

    @cached_property
    def strm_data(self, /) -> bytes:
        attr = self.attr
        name = attr["name"].translate({0x23: "%23", 0x2F: "%2F", 0x3F: "%3F"})
        url = joinpath(
            self.origin, 
            f"{name}?pickcode={attr['pickcode']}&id={attr['id']}&sha1={attr['sha1']}&password={password}", 
        )
        if attr.get("class") == "PIC" or attr.get("thumb"):
            url += "&image=true"
        return bytes(url, "utf-8")

    @property
    def url(self, /) -> str:
        if (url := self.__dict__.get("url", "")):
            return str(url)
        attr = self.attr
        user_agent = self.environ.get("HTTP_USER_AGENT", "")
        if cdn_image and attr.get("class") == "PIC" or attr.get("thumb"):
            url = get_image_url(attr["pickcode"], user_agent)
            self.__dict__["url"] = url
            self.__dict__["size"] = url["size"]
            return url["data"]["source_url"]
        else:
            return f"/{quote(attr['name'], safe='')}?id={attr['id']}&password={password}"

    def get_content(self, /):
        if self.path.endswith(".strm"):
            return BytesIO(self.strm_data)
        raise DAVError(302, add_headers=[("Location", self.url)])

    def get_content_length(self, /) -> int:
        return self.size

    def support_content_length(self, /) -> bool:
        return True

    def support_ranges(self, /) -> bool:
        return True


class FolderResource(DavPathBase, DAVCollection):

    def __init__(
        self, 
        /, 
        path: str, 
        environ: dict, 
        attr: P115Path, 
    ):
        super().__init__(path, environ)
        self.attr = attr

    @cached_property
    def children(self, /) -> dict[str, P115Path]:
        children: dict[str, P115Path] = {}
        for attr in relogin_wrap(self.attr.listdir_path):
            name = attr["name"]
            if not attr.is_dir() and strm_predicate and strm_predicate(attr):
                name = splitext(name)[0] + ".strm"
            elif predicate and not predicate(attr):
                continue
            children[name] = attr
        return children

    def get_member(self, /, name: str) -> FileResource | FolderResource:
        if not (attr := self.children.get(name)):
            raise DAVError(404, self.path + "/" + name)
        relpath = attr["path"][len(root_dir)-1:]
        if attr.is_dir():
            return FolderResource(relpath, self.environ, attr)
        else:
            if name.endswith(".strm"):
                relpath = splitext(relpath)[0] + ".strm"
            return FileResource(relpath, self.environ, attr)

    def get_member_list(self, /) -> list[FileResource | FolderResource]:
        return list(map(self.get_member, self.get_member_names()))

    def get_member_names(self, /) -> list[str]:
        return list(self.children)

    def get_property_value(self, /, name: str):
        if name == "{DAV:}getcontentlength":
            return 0
        elif name == "{DAV:}iscollection":
            return True
        return super().get_property_value(name)


class P115FileSystemProvider(DAVProvider):

    def __init__(self, /, fs: P115FileSystem):
        super().__init__()
        self.fs = fs

    def get_resource_inst(
        self, 
        /, 
        path: str, 
        environ: dict, 
    ) -> FolderResource | FileResource:
        if path in webdav_file_cache:
            return webdav_file_cache[path]
        id_or_path: int | str = self.fs.abspath(path.lstrip("/"))
        if id_or_path == "/":
            id_or_path = 0
        elif path_persistence_commitment and (fid := fs.path_to_id.get(id_or_path)):
            id_or_path = fid
        try:
            attr = relogin_wrap(self.fs.as_path, id_or_path)
        except FileNotFoundError:
            raise DAVError(404, path)
        if attr.is_dir():
            return FolderResource(path, environ, attr)
        else:
            if not attr.is_dir() and strm_predicate and strm_predicate(attr):
                path = splitext(path)[0] + ".strm"
            elif predicate and not predicate(attr):
                raise DAVError(404, path)
            return FileResource(path, environ, attr)

    def is_readonly(self, /) -> bool:
        return True


def format_bytes(
    n: int, 
    /, 
    unit: str = "", 
    precision: int = 2, 
) -> str:
    "scale bytes to its proper byte format"
    if unit == "B" or not unit and n < 1024:
        return f"{n} B"
    b = 1
    b2 = 1024
    for u in ["K", "M", "G", "T", "P", "E", "Z", "Y"]:
        b, b2 = b2, b2 << 10
        if u == unit if unit else n < b2:
            break
    return f"%.{precision}f {u}B" % (n / b)


class HTTPStatus(Exception):
    __slots__ = ("status", "message")

    def __init__(self, status: int, message: str = ""):
        self.status = status
        self.message = message


def redirect_exception_response(func, /):
    def wrapper(*args, **kwds):
        try:
            return func(*args, **kwds)
        except BaseException as exc:
            if isinstance(exc, HTTPStatus):
                return exc.message, exc.status
            elif isinstance(exc, StatusError):
                return str(exc), get_status_code(exc)
            elif isinstance(exc, AuthenticationError):
                return str(exc), 401 # Unauthorized
            elif isinstance(exc, PermissionError):
                return str(exc), 403 # Forbidden
            elif isinstance(exc, FileNotFoundError):
                return str(exc), 404 # Not Found
            elif isinstance(exc, (IsADirectoryError, NotADirectoryError)):
                return str(exc), 406 # Not Acceptable
            elif isinstance(exc, OSError):
                flask_app.logger.exception("500: internal server error")
                return str(exc), 500 # Internal Server Error
            else:
                flask_app.logger.exception("can't make response")
                return str(exc), 503 # Service Unavailable
    return update_wrapper(wrapper, func)


def get_m3u8(pickcode: str):
    global web_cookies
    user_agent = request.headers.get("User-Agent") or ""
    definition = request.args.get("definition") or "0"

    url = f"http://115.com/api/video/m3u8/{pickcode}.m3u8?definition={definition}"

    with web_login_lock:
        if not web_cookies:
            if device == "web":
                web_cookies = client.cookies
            else:
                web_cookies = client.login_another_app("web").cookies
    while True:
        try:
            data = urlopen(url, parse=False, headers={"User-Agent": user_agent, "Cookie": web_cookies})
            break
        except HTTPError as e:
            if e.status not in (403, 405):
                raise
            with web_login_lock:
                web_cookies = client.login_another_app("web", replace=device=="web").cookies
    if not data:
        raise FileNotFoundError(errno.ENOENT, f"this file does not have .m3u8, pickcode: {pickcode!r}")
    if definition == "0":
        return Response(data, mimetype="flask_app/x-mpegurl")
    return redirect(data.split()[-1].decode("ascii"))


def get_image_url(pickcode: str, user_agent: str = "") -> str:
    if image_url_cache and (url := image_url_cache.get(pickcode)):
        return url
    resp = relogin_wrap(
        client.fs_image, 
        pickcode, 
        headers={"User-Agent": user_agent}, 
        request=do_request, 
    )
    if not resp["state"]:
        raise FileNotFoundError(errno.ENOENT, pickcode)
    data = resp["data"]
    url = data["origin_url"]
    with urlopen(url, "HEAD", headers={"User-Agent": user_agent}) as resp:
        url = cast(str, resp.url)
    url = P115URL(url, data=data, size=int(resp.headers["Content-Length"]))
    if image_url_cache is not None:
        image_url_cache[pickcode] = url
    return url


def get_url(pickcode: str):
    if request.args.get("m3u8") not in (None, "0", "false"):
        return get_m3u8(pickcode)
    elif (
        cdn_image and 
        (as_image := request.args.get("image")) not in ("0", "false") and 
        (as_image is not None or image_url_cache and pickcode in image_url_cache)
    ):
        return redirect(get_image_url(pickcode))
    use_web_api = request.args.get("web") not in (None, "0", "false")
    request_headers = request.headers
    user_agent = request_headers.get("User-Agent") or ""
    range_request_key = (request.remote_addr or "", user_agent, pickcode, str(request.range))
    if range_request_key in range_request_cooldown:
        return "Too Many Requests", 429
    range_request_cooldown[range_request_key] = None
    if url_cache is not None:
        try:
            url = url_cache[(pickcode, user_agent)]
        except KeyError:
            url = url_cache[(pickcode, user_agent)] = relogin_wrap(
                fs.get_url_from_pickcode, 
                pickcode, 
                headers={"User-Agent": user_agent}, 
                use_web_api=use_web_api, 
            )
    else:
        url = relogin_wrap(
            fs.get_url_from_pickcode, 
            pickcode, 
            headers={"User-Agent": user_agent}, 
            use_web_api=use_web_api, 
        )
    headers = url["headers"]
    if request.args.get("method") == "url":
        return {"url": url, "headers": headers}
    headers["Content-Encoding"] = "identity"
    if use_web_api:
        if bytes_range := request_headers.get("Range"):
            headers["Range"] = bytes_range
        resp = urlopen(url, headers=headers)
        resp_headers = {
            k: v for k, v in resp.headers.items() 
            if k.lower() not in ("connection", "date")
        }
        return Response(
            resp, 
            headers=resp_headers, 
            status=resp.status, 
        )
    if cdn_image and url["file_name"].lower().endswith(
        (".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", 
         ".raw", ".svg", ".tif", ".tiff", ".webp")
    ):
        image_url_cache[pickcode] = None
    return redirect(url)


def relogin(exc=None):
    global cookies_path_mtime
    if exc is None:
        exc = exc_info()[0]
    mtime = cookies_path_mtime
    with login_lock:
        need_update = mtime == cookies_path_mtime
        if cookies_path and need_update:
            try:
                mtime = stat(cookies_path).st_mtime_ns
                if mtime != cookies_path_mtime:
                    client.cookies = open(cookies_path, encoding="utf-8").read()
                    cookies_path_mtime = mtime
                    need_update = False
            except FileNotFoundError:
                flask_app.logger.error("\x1b[1m\x1b[33m[SCAN] 🦾 文件空缺: %r\x1b[0m", cookies_path)
        if need_update:
            if exc is None:
                flask_app.logger.error("\x1b[1m\x1b[33m[SCAN] 🦾 重新扫码: %s\x1b[0m", device)
            else:
                flask_app.logger.error("""{prompt}一个 Web API 受限 (响应 "405: Not Allowed"), 将自动扫码登录同一设备: {device}\n{exc}""".format(
                    device = device, 
                    prompt = "\x1b[1m\x1b[33m[SCAN] 🤖 重新扫码：\x1b[0m", 
                    exc    = f"    ├ \x1b[31m{type(exc).__qualname__}\x1b[0m: {exc}")
                )
            client.login_another_app(device, replace=True, request=do_request, timeout=5)
            if cookies_path:
                open(cookies_path, "w", encoding="utf-8").write(client.cookies)
                cookies_path_mtime = stat(cookies_path).st_mtime_ns


def relogin_wrap(func, /, *args, **kwds):
    try:
        if fs_lock is None:
            return func(*args, **kwds)
        else:
            with fs_lock:
                return func(*args, **kwds)
    except StatusError as e:
        if get_status_code(e) != 405:
            raise
        relogin(e)
    return relogin_wrap(func, *args, **kwds)


@flask_app.get("/")
@redirect_exception_response
def index():
    match request.args.get("pic"):
        case "favicon":
            return send_file(BytesIO(b'<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="16" height="16" rx="8" fill="#2777F8"/><path d="M4.5874 6.99646C4.60631 6.96494 4.61891 6.92713 4.63152 6.90192C5.17356 5.81784 5.7219 4.74006 6.25764 3.64969C6.38999 3.37867 6.60429 3.25891 6.88792 3.25891H9.39012C9.71786 3.25891 10.0582 3.25261 10.3859 3.25891C10.7326 3.26521 11.0729 3.19589 11.4007 3.08243C11.4259 3.07613 11.4637 3.05722 11.4826 3.06352C11.5646 3.06983 11.6087 3.15807 11.5772 3.24C11.4196 3.56145 11.2557 3.88289 11.0793 4.20433C10.9532 4.43123 10.7515 4.55098 10.4994 4.55098H7.72618C7.42364 4.55098 7.20305 4.68334 7.077 4.96697C6.95094 5.23168 6.81228 5.49009 6.67992 5.75481C6.66101 5.78002 6.65471 5.80523 6.6358 5.83674C6.81858 5.88087 7.00767 5.91238 7.18414 5.94389C7.73249 6.06365 8.29343 6.1834 8.81026 6.4166C9.5792 6.75695 10.2158 7.25487 10.6444 7.97969C10.9091 8.42088 11.0667 8.88098 11.0982 9.3915C11.1927 10.5638 10.7578 11.5219 9.88176 12.2845C9.28296 12.8013 8.58336 13.1038 7.80812 13.2488C7.35432 13.3308 6.89422 13.3559 6.44042 13.3244C5.92359 13.2803 5.42567 13.1479 4.95927 12.9084C4.95296 12.9022 4.94036 12.9022 4.91515 12.8833C5.00969 12.8895 5.07271 12.9022 5.14205 12.9022C5.85426 12.9652 6.54756 12.8833 7.21566 12.6564C7.79551 12.4546 8.32494 12.1584 8.74723 11.6857C9.09388 11.295 9.28927 10.8475 9.35229 10.3306C9.44684 9.61841 9.18212 9.03855 8.72202 8.52173C8.24931 8.00489 7.66315 7.67716 7.00767 7.45655C6.49715 7.28639 5.98662 7.16663 5.45088 7.091C5.17986 7.04688 4.90254 7.02167 4.63152 6.99646C4.61891 7.00906 4.61261 7.00906 4.5874 6.99646Z" fill="white"/></svg>'), mimetype="image/svg+xml")
        case "figplayer":
            return redirect("https://omiapps.com/resource/app/icons/potplayerx.webp")
        case "fileball":
            return send_file(BytesIO(b'<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M0 6.5C0 2.91015 2.91015 0 6.5 0H25.5C29.0899 0 32 2.91015 32 6.5V25.5C32 29.0899 29.0899 32 25.5 32H6.5C2.91015 32 0 29.0899 0 25.5V6.5Z" fill="#FFCA28"/><path fill-rule="evenodd" clip-rule="evenodd" d="M7.75 7.875C6.50736 7.875 5.5 8.88236 5.5 10.125V21.875C5.5 23.1176 6.50736 24.125 7.75 24.125H24.25C25.4926 24.125 26.5 23.1176 26.5 21.875V12.025C26.5 10.7726 25.4774 9.7613 24.2251 9.77514L15.3125 9.875L13.1891 8.17631C12.9453 7.98126 12.6424 7.875 12.3302 7.875H7.75ZM16 20.7917C17.933 20.7917 19.5 19.2247 19.5 17.2917C19.5 15.3587 17.933 13.7917 16 13.7917C14.067 13.7917 12.5 15.3587 12.5 17.2917C12.5 19.2247 14.067 20.7917 16 20.7917Z" fill="white"/><path d="M15.5623 15.8389C15.476 15.7814 15.365 15.776 15.2735 15.825C15.1821 15.8739 15.125 15.9692 15.125 16.0729V18.3229C15.125 18.4267 15.1821 18.522 15.2735 18.5709C15.365 18.6199 15.476 18.6145 15.5623 18.557L17.2498 17.432C17.328 17.3798 17.375 17.292 17.375 17.1979C17.375 17.1039 17.328 17.0161 17.2498 16.9639L15.5623 15.8389Z" fill="white"/></svg>'), mimetype="image/svg+xml")
        case "iina":
            return send_file(BytesIO(b'<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><rect y="0.000244141" width="32" height="32" rx="7.51807" fill="url(#paint0_linear_10408_1309)"/><rect x="5.5" y="13.3784" width="2.00482" height="5.35904" rx="1.00241" fill="url(#paint1_linear_10408_1309)"/><rect x="9.02173" y="11.7976" width="2.62169" height="7.78795" rx="1.31084" fill="url(#paint2_linear_10408_1309)"/><path d="M13.2881 14.1557C13.2881 10.8731 13.2881 9.23184 14.1967 8.44754C14.4469 8.23163 14.7356 8.06495 15.0476 7.95629C16.1812 7.56155 17.6025 8.38219 20.4453 10.0235L23.8046 11.9629C26.6474 13.6042 28.0687 14.4248 28.2937 15.6039C28.3556 15.9285 28.3556 16.2618 28.2937 16.5864C28.0687 17.7654 26.6474 18.5861 23.8046 20.2274L20.4453 22.1668C17.6025 23.8081 16.1812 24.6287 15.0476 24.234C14.7356 24.1253 14.4469 23.9587 14.1967 23.7427C13.2881 22.9584 13.2881 21.3172 13.2881 18.0346L13.2881 14.1557Z" fill="url(#paint3_linear_10408_1309)"/><defs><linearGradient id="paint0_linear_10408_1309" x1="16" y1="0.000244141" x2="16" y2="32.0002" gradientUnits="userSpaceOnUse"><stop stop-color="#4E4E4E"/><stop offset="1" stop-color="#262525"/></linearGradient><linearGradient id="paint1_linear_10408_1309" x1="5.5" y1="16.0387" x2="7.50482" y2="15.7495" gradientUnits="userSpaceOnUse"><stop stop-color="#8148EF"/><stop offset="1" stop-color="#4A2CC4"/></linearGradient><linearGradient id="paint2_linear_10408_1309" x1="9.02173" y1="15.6636" x2="11.6536" y2="15.322" gradientUnits="userSpaceOnUse"><stop stop-color="#4435E1"/><stop offset="1" stop-color="#3E5EFA"/></linearGradient><linearGradient id="paint3_linear_10408_1309" x1="25.4842" y1="15.653" x2="13.4168" y2="12.8771" gradientUnits="userSpaceOnUse"><stop stop-color="#00DDFE"/><stop offset="1" stop-color="#0092FA"/></linearGradient></defs></svg>'), mimetype="image/svg+xml")
        case "infuse":
            return redirect("https://static.firecore.com/images/infuse/infuse-icon_2x.png")
        case "mpv":
            return send_file(BytesIO(b'<?xml version="1.0" encoding="UTF-8" standalone="no"?><svg xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:cc="http://creativecommons.org/ns#" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:svg="http://www.w3.org/2000/svg" xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 55.898387 55.898387" height="59.62495" width="59.62495"><metadata><rdf:RDF><cc:Work rdf:about=""><dc:format>image/svg+xml</dc:format><dc:type rdf:resource="http://purl.org/dc/dcmitype/StillImage" /><dc:title>Logo of mpv</dc:title></cc:Work></rdf:RDF></metadata><g transform="translate(-4.050806,-992.41299)" id="layer1"><circle r="27.949194" cy="1020.3622" cx="32" id="path4380" style="opacity:1;fill:#e5e5e5;fill-opacity:1;fill-rule:nonzero;stroke:none;stroke-width:0.10161044;stroke-linecap:round;stroke-linejoin:bevel;stroke-miterlimit:1;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:0.99215686" /><circle r="25.950588" cy="1019.5079" cx="32.727058" id="path4390" style="opacity:1;fill:#672168;fill-opacity:1;fill-rule:nonzero;stroke:none;stroke-width:0.0988237;stroke-linecap:round;stroke-linejoin:bevel;stroke-miterlimit:1;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:0.99215686" /><circle r="20" cy="1017.7957" cx="34.224396" id="path4400" style="opacity:1;fill:#420143;fill-opacity:1;fill-rule:nonzero;stroke:none;stroke-width:0.1;stroke-linecap:round;stroke-linejoin:bevel;stroke-miterlimit:1;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:0.99215686" /><path id="path4412" d="m 44.481446,1020.4807 a 12.848894,12.848894 0 0 1 -12.84889,12.8489 12.848894,12.848894 0 0 1 -12.8489,-12.8489 12.848894,12.848894 0 0 1 12.8489,-12.8489 12.848894,12.848894 0 0 1 12.84889,12.8489 z" style="fill:#dddbdd;fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.1;stroke-linecap:butt;stroke-linejoin:miter;stroke-miterlimit:4;stroke-dasharray:none;stroke-opacity:1" /><path id="path4426" d="m 28.374316,1014.709 v 11.4502 l 9.21608,-5.8647 z" style="fill:#691f69;fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.1;stroke-linecap:butt;stroke-linejoin:miter;stroke-miterlimit:4;stroke-dasharray:none;stroke-opacity:1" /></g></svg>'), mimetype="image/svg+xml")
        case "mxplayer":
            return send_file(BytesIO(b'<svg id="svg" width="100px" viewBox="0 0 100 100" height="100px" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><g id="svgg"><path id="path0" d="M47.333 2.447 C 44.804 2.654,41.449 3.238,37.838 4.099 C 36.827 4.340,34.775 5.042,32.667 5.869 C 31.213 6.440,27.478 8.258,26.784 8.733 C 26.436 8.972,26.090 9.167,26.015 9.167 C 25.624 9.167,20.550 12.838,19.003 14.240 C 16.084 16.885,12.607 20.793,11.216 22.991 C 10.894 23.500,10.494 24.067,10.329 24.250 C 10.163 24.433,9.804 25.016,9.531 25.545 C 9.258 26.075,8.953 26.606,8.853 26.726 C 8.267 27.432,6.137 32.182,5.232 34.800 C 2.837 41.731,1.961 51.320,3.142 57.667 C 3.321 58.629,3.592 60.129,3.743 61.000 C 3.963 62.269,5.332 66.789,5.990 68.417 C 6.440 69.530,8.141 73.073,8.631 73.917 C 8.951 74.467,9.401 75.254,9.632 75.667 C 9.863 76.079,10.364 76.829,10.747 77.333 C 11.129 77.837,11.486 78.362,11.540 78.500 C 12.001 79.669,18.426 86.557,20.168 87.750 C 20.570 88.025,21.086 88.422,21.315 88.632 C 21.842 89.116,25.549 91.634,25.950 91.780 C 26.115 91.840,26.558 92.098,26.935 92.353 C 27.956 93.045,31.932 94.904,33.876 95.600 C 42.948 98.843,51.123 99.447,60.583 97.570 C 62.142 97.261,63.979 96.823,64.667 96.597 C 67.249 95.747,68.898 95.147,69.810 94.724 C 70.327 94.484,71.275 94.046,71.917 93.749 C 72.558 93.453,73.496 92.965,74.000 92.665 C 74.504 92.365,75.254 91.933,75.667 91.706 C 76.079 91.478,76.792 91.015,77.250 90.676 C 77.708 90.338,78.196 90.018,78.333 89.965 C 80.371 89.185,88.473 81.008,90.417 77.771 C 90.600 77.466,91.045 76.774,91.405 76.233 C 92.525 74.553,93.455 72.785,95.077 69.250 C 98.036 62.806,99.454 52.414,98.443 44.583 C 98.289 43.392,98.119 42.079,98.065 41.667 C 97.643 38.416,95.090 31.158,93.200 27.835 C 92.861 27.238,92.533 26.629,92.473 26.482 C 92.412 26.335,91.999 25.666,91.556 24.996 C 91.113 24.327,90.675 23.660,90.583 23.516 C 88.060 19.536,82.404 13.785,78.333 11.062 C 77.921 10.786,77.246 10.330,76.833 10.050 C 75.738 9.306,72.984 7.716,72.417 7.500 C 72.148 7.398,71.250 6.985,70.422 6.582 C 69.594 6.179,68.467 5.701,67.917 5.520 C 67.367 5.339,66.242 4.954,65.417 4.665 C 60.715 3.018,52.563 2.018,47.333 2.447 M38.562 30.863 C 39.399 31.337,40.683 32.076,41.417 32.504 C 42.150 32.931,43.087 33.468,43.500 33.695 C 43.913 33.923,45.337 34.731,46.667 35.492 C 47.996 36.252,50.658 37.774,52.583 38.875 C 54.508 39.976,56.833 41.307,57.750 41.835 C 58.667 42.362,61.104 43.749,63.167 44.916 C 65.229 46.084,67.254 47.243,67.667 47.492 C 68.079 47.741,69.467 48.533,70.750 49.251 C 73.449 50.762,73.833 51.063,73.833 51.664 C 73.833 52.380,73.934 52.317,60.167 60.158 C 52.879 64.309,46.167 68.140,45.250 68.673 C 36.899 73.527,36.862 73.544,36.241 72.922 L 35.830 72.511 35.873 51.574 L 35.917 30.637 36.310 30.319 C 36.844 29.886,36.837 29.884,38.562 30.863 " stroke="none" fill="#3c8cec" fill-rule="evenodd"></path></g></svg>'), mimetype="image/svg+xml")
        case "nplayer":
            return redirect("https://nplayer.com/assets/img/logo_main.png")
        case "omniplayer":
            return redirect("https://cdn.okaapps.com/resource/icon/app_icons/omniplayer.png")
        case "potplayer":
            return send_file(BytesIO(b'<svg width="256pt" height="256pt" version="1.1" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg"><g id="#f8d714ff" fill="#f8d714"><path d="m14.48 5.74c3.4-1.07 7.01-0.71 10.52-0.77 70.34 0.02 140.68-0.01 211.02 0.01 5.46-0.33 10.91 2.69 13.41 7.57 2.08 3.81 1.52 8.3 1.6 12.47-0.01 68.66-0.01 137.32 0 205.98-0.06 4.38 0.49 9.15-1.94 13.05-2.6 4.58-7.88 7.21-13.09 6.96-71.98 0.04-143.96 0.03-215.93 0-5.25 0.27-10.56-2.37-13.17-6.99-2.42-3.88-1.87-8.63-1.93-12.99 0.02-70.34-0.01-140.67 0.01-211.01-0.43-6.21 3.59-12.31 9.5-14.28m107.84 33.69c-14.96 1.39-29.3 8.36-39.65 19.25-9.91 10.28-16.17 24-17.37 38.23-1.18 12.94 1.74 26.23 8.31 37.46 7.78 13.44 20.66 23.86 35.48 28.54 14.49 4.68 30.65 3.88 44.61-2.22 14.42-6.23 26.32-18.03 32.68-32.4 6.61-14.74 7.24-32.04 1.71-47.22-4.72-13.25-14.04-24.78-25.96-32.24-11.74-7.43-25.99-10.76-39.81-9.4m-58.68 142.57c0 11.33-0.01 22.66 0 34h7.36c0-4.13 0-8.26 0.01-12.38 4.89-0.21 10.28 0.89 14.7-1.78 6.64-4.22 5.84-16.13-1.84-18.76-6.53-2.02-13.51-0.71-20.23-1.08m31.36-0.02v34.03c2.21-0.01 4.43-0.02 6.64-0.03 0.01-11.3-0.09-22.6 0.05-33.89-2.23-0.1-4.46-0.07-6.69-0.11m14.91 9.93c-2.42 1.25-3.4 3.9-4.08 6.36 2.18 0.12 4.38 0.06 6.57 0.15 0.83-4.08 5.95-5.29 9.03-2.88 0.68 1.52 1.23 4.02-0.79 4.76-3.79 1.3-8.04 0.88-11.69 2.64-4.94 2.35-4.8 10.64 0.13 12.94 4.31 1.97 9.56 1.01 13.21-1.89 0.26 3.53 4.7 1.48 7.03 2.02-1.44-6.71-0.21-13.61-0.86-20.38-0.19-2.04-1.85-3.62-3.67-4.32-4.76-1.82-10.32-1.73-14.88 0.6m52.44 1.46c-4.44 4.27-4.97 11.44-2.64 16.91 2.61 6 10.47 8.19 16.25 5.72 3.31-1.17 5.09-4.4 6.6-7.34-1.94-0.02-3.87-0.03-5.8 0-1.88 2.97-5.81 4.17-8.96 2.5-2.29-1.05-2.56-3.78-2.98-5.95 6.09-0.03 12.18 0 18.27-0.01-0.37-3.83-0.81-7.91-3.32-11.01-4.08-5.29-12.77-5.47-17.42-0.82m30.89 1.79c0.06-1.38 0.12-2.77 0.16-4.15-2.13-0.01-4.27-0.01-6.4-0.01v25.01c2.21-0.01 4.43-0.03 6.64-0.04 0.32-5.5-0.92-11.27 1.04-16.55 1.5-3.15 5.26-3.51 8.33-3.15-0.01-2.14-0.01-4.28-0.02-6.42-3.98 0.03-7.62 1.94-9.75 5.31m-61.66-4.17c3.01 8.67 6.35 17.24 9.1 25.99 0.23 3.74-3.99 4.08-6.67 3.4-0.01 1.73-0.01 3.47-0.01 5.2 4.41 0.8 10.45 0.5 12.22-4.49 3.74-9.96 7.1-20.06 10.66-30.08-2.29-0.01-4.58-0.01-6.86-0.01-1.82 6.03-3.63 12.06-5.5 18.06-2.14-5.92-3.89-11.98-5.73-18.01-2.4-0.05-4.81-0.05-7.21-0.06z"/><path d="m111.13 74.07c1.31-0.17 2.41 0.69 3.5 1.25 13.64 8.39 27.33 16.71 41 25.05 1.27 0.84 3.17 1.74 2.53 3.64-1.02 1.06-2.3 1.82-3.55 2.58-13.78 8.18-27.43 16.6-41.23 24.75-1.21 1.08-3.48 0.59-3.29-1.3-0.22-17.35-0.01-34.71-0.1-52.06 0.12-1.36-0.28-3.1 1.14-3.91z"/><path d="m71 187.63c3.41 0.08 7.12-0.52 10.26 1.13 2.82 2.15 2.47 7.87-1.24 8.92-2.98 0.55-6.02 0.3-9.02 0.31v-10.36z"/><path d="m164.77 200.98c0.41-3.09 2.66-6.44 6.2-5.83 3.27-0.26 4.83 3.13 5.25 5.84-3.82 0.02-7.64 0.02-11.45-0.01z"/><path d="m112.05 208c1.75-3.68 6.75-2.65 10.01-3.99-0.17 2.65 0.47 6.23-2.36 7.73-2.87 2.1-8.98 0.72-7.65-3.74z"/></g><g id="#ffffffff"><path d="m122.32 39.43c13.82-1.36 28.07 1.97 39.81 9.4 11.92 7.46 21.24 18.99 25.96 32.24 5.53 15.18 4.9 32.48-1.71 47.22-6.36 14.37-18.26 26.17-32.68 32.4-13.96 6.1-30.12 6.9-44.61 2.22-14.82-4.68-27.7-15.1-35.48-28.54-6.57-11.23-9.49-24.52-8.31-37.46 1.2-14.23 7.46-27.95 17.37-38.23 10.35-10.89 24.69-17.86 39.65-19.25m-11.19 34.64c-1.42 0.81-1.02 2.55-1.14 3.91 0.09 17.35-0.12 34.71 0.1 52.06-0.19 1.89 2.08 2.38 3.29 1.3 13.8-8.15 27.45-16.57 41.23-24.75 1.25-0.76 2.53-1.52 3.55-2.58 0.64-1.9-1.26-2.8-2.53-3.64-13.67-8.34-27.36-16.66-41-25.05-1.09-0.56-2.19-1.42-3.5-1.25z" fill="#fff"/></g><g id="#222222ff" fill="#222"><path d="m63.64 182c6.72 0.37 13.7-0.94 20.23 1.08 7.68 2.63 8.48 14.54 1.84 18.76-4.42 2.67-9.81 1.57-14.7 1.78-0.01 4.12-0.01 8.25-0.01 12.38h-7.36c-0.01-11.34 0-22.67 0-34m7.36 5.63v10.36c3-0.01 6.04 0.24 9.02-0.31 3.71-1.05 4.06-6.77 1.24-8.92-3.14-1.65-6.85-1.05-10.26-1.13z"/><path d="m95 181.98c2.23 0.04 4.46 0.01 6.69 0.11-0.14 11.29-0.04 22.59-0.05 33.89-2.21 0.01-4.43 0.02-6.64 0.03v-34.03z"/><path d="m109.91 191.91c4.56-2.33 10.12-2.42 14.88-0.6 1.82 0.7 3.48 2.28 3.67 4.32 0.65 6.77-0.58 13.67 0.86 20.38-2.33-0.54-6.77 1.51-7.03-2.02-3.65 2.9-8.9 3.86-13.21 1.89-4.93-2.3-5.07-10.59-0.13-12.94 3.65-1.76 7.9-1.34 11.69-2.64 2.02-0.74 1.47-3.24 0.79-4.76-3.08-2.41-8.2-1.2-9.03 2.88-2.19-0.09-4.39-0.03-6.57-0.15 0.68-2.46 1.66-5.11 4.08-6.36m2.14 16.09c-1.33 4.46 4.78 5.84 7.65 3.74 2.83-1.5 2.19-5.08 2.36-7.73-3.26 1.34-8.26 0.31-10.01 3.99z"/><path d="m162.35 193.37c4.65-4.65 13.34-4.47 17.42 0.82 2.51 3.1 2.95 7.18 3.32 11.01-6.09 0.01-12.18-0.02-18.27 0.01 0.42 2.17 0.69 4.9 2.98 5.95 3.15 1.67 7.08 0.47 8.96-2.5 1.93-0.03 3.86-0.02 5.8 0-1.51 2.94-3.29 6.17-6.6 7.34-5.78 2.47-13.64 0.28-16.25-5.72-2.33-5.47-1.8-12.64 2.64-16.91m2.42 7.61c3.81 0.03 7.63 0.03 11.45 0.01-0.42-2.71-1.98-6.1-5.25-5.84-3.54-0.61-5.79 2.74-6.2 5.83z"/><path d="m193.24 195.16c2.13-3.37 5.77-5.28 9.75-5.31 0.01 2.14 0.01 4.28 0.02 6.42-3.07-0.36-6.83 0-8.33 3.15-1.96 5.28-0.72 11.05-1.04 16.55-2.21 0.01-4.43 0.03-6.64 0.04v-25.01c2.13 0 4.27 0 6.4 0.01-0.04 1.38-0.1 2.77-0.16 4.15z"/><path d="m131.58 190.99c2.4 0.01 4.81 0.01 7.21 0.06 1.84 6.03 3.59 12.09 5.73 18.01 1.87-6 3.68-12.03 5.5-18.06 2.28 0 4.57 0 6.86 0.01-3.56 10.02-6.92 20.12-10.66 30.08-1.77 4.99-7.81 5.29-12.22 4.49 0-1.73 0-3.47 0.01-5.2 2.68 0.68 6.9 0.34 6.67-3.4-2.75-8.75-6.09-17.32-9.1-25.99z"/></g></svg>'), mimetype="image/svg+xml")
        case "vlc":
            return send_file(BytesIO(b'<?xml version="1.0" ?><!DOCTYPE svg PUBLIC \'-//W3C//DTD SVG 1.1//EN\' \'http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\'><svg height="512px" style="enable-background:new 0 0 512 512;" version="1.1" viewBox="0 0 512 512" width="512px" xml:space="preserve" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><g id="_x31_2-vlc_x2C__media_x2C__player"><g><g><g><path d="M478.104,458.638l-59.65-119.619c-2.535-5.058-7.691-8.255-13.326-8.255H106.872 c-5.635,0-10.791,3.197-13.326,8.255L33.887,458.638c-2.325,4.637-2.053,10.141,0.66,14.538 c2.715,4.396,7.516,7.118,12.676,7.118h417.554c5.16,0,9.959-2.694,12.707-7.087 C480.193,468.778,480.404,463.307,478.104,458.638L478.104,458.638z M478.104,458.638" style="fill:#FF9800;"/></g><path d="M375.297,345.718c0,43.659-107.068,44.858-119.297,44.858c-12.23,0-119.302-1.199-119.302-44.858 c0-1.197,0.301-2.691,0.6-3.887l20.579-75.665c14.61,11.369,53.086,19.739,98.124,19.739s83.512-8.37,98.123-19.739 l20.578,75.665C375.002,343.026,375.297,344.521,375.297,345.718L375.297,345.718z M375.297,345.718" style="fill:#FCFCFC;"/><path d="M332.35,186.62c-18.787,5.975-46.227,9.565-76.35,9.565s-57.563-3.591-76.351-9.565l22.964-84.34 c15.506,2.69,34,4.187,53.387,4.187s37.879-1.496,53.387-4.187L332.35,186.62z M332.35,186.62" style="fill:#FCFCFC;"/><path d="M256,106.467c-19.387,0-37.881-1.496-53.387-4.187l10.439-37.982 c5.666-20.03,22.668-32.592,42.947-32.592s37.279,12.562,42.945,32.297l10.441,38.277 C293.879,104.971,275.387,106.467,256,106.467L256,106.467z M256,106.467" style="fill:#FF9800;"/><path d="M354.123,266.166c-14.611,11.369-53.086,19.739-98.123,19.739s-83.513-8.37-98.124-19.739 l21.772-79.546c18.789,5.975,46.228,9.565,76.351,9.565s57.563-3.591,76.35-9.565L354.123,266.166z M354.123,266.166" style="fill:#FF9800;"/></g></g></g><g id="Layer_1"/></svg>'), mimetype="image/svg+xml")
        case _:
            return query("/")


@flask_app.get("/<path:path>")
@redirect_exception_response
def query(path: str):
    if password and request.args.get("password") != password:
        raise PermissionError(errno.EACCES, "wrong password")
    scheme = request.environ.get("HTTP_X_FORWARDED_PROTO") or "http"
    netloc = unquote(urlsplit(request.url).netloc)
    origin = f"{scheme}://{netloc}"
    pickcode = request.args.get("pickcode")
    fid = request.args.get("id")
    sha1 = request.args.get("sha1") or ""
    path = fs.abspath(unquote(request.args.get("path") or path).lstrip("/"))

    def update_attr(attr):
        relpath = attr["relpath"] = attr["path"][len(cast(str, root_dir)):]
        path_url = "%s/%s" % (origin, relpath.translate({0x23: "%23", 0x3F: "%3F"}))
        if attr["is_directory"]:
            attr["url"] = f"{path_url}?id={attr['id']}"
            attr["short_url"] = f"{origin}?id={attr['id']}"
        else:
            pickcode = cast(str, attr["pickcode"])
            short_url = f"{origin}?pickcode={pickcode}"
            url = f"{path_url}?pickcode={pickcode}"
            if attr["violated"] and attr["size"] < 1024 * 1024 * 115:
                short_url += "&web=true"
                url += "&web=true"
            attr["url"] = url
            attr["short_url"] = short_url
            attr["format_size"] = format_bytes(attr["size"])
            sha1_to_pickcode[attr["sha1"]] = id_to_pickcode[attr["id"]] = pickcode
            if attr.get("class") == "PIC" or attr.get("thumb"):
                if cdn_image:
                    image_url_cache[pickcode] = None
                attr["url"] += "&image=true"
                attr["short_url"] += "&image=true"
        if password:
            attr["url"] += "&password=" + password
            attr["short_url"] += "&password=" + password
        attr["ancestors"] = attr["path"].ancestors
        attr["mtime_str"] = strftime("%F %X", localtime(attr["mtime"]))
        return attr

    match request.args.get("method"):
        case "attr":
            if not root_dir:
                attr = relogin_wrap(fs.attr, root)
            else:
                if pickcode:
                    fid = relogin_wrap(fs.get_id_from_pickcode, pickcode)
                if fid is not None:
                    attr = relogin_wrap(fs.attr, int(fid))
                elif sha1 := sha1.strip():
                    if len(sha1) != 40:
                        return "Bad sha1", 400
                    try:
                        attr = next(relogin_wrap(fs.search, root, search_value=sha1, limit=1, show_dir=0))
                        attr.path
                    except StopIteration:
                        return f"no such file: sha1={sha1!r}", 404
                elif path_persistence_commitment and (fid := fs.path_to_id.get(path)):
                    attr = relogin_wrap(fs.attr, fid)
                else:
                    attr = relogin_wrap(fs.attr, path)
                if root != 0 and not any(info["id"] == root for info in attr["path"].ancestors):
                    raise PermissionError(errno.EACCES, "out of root range")
            update_attr(attr)
            json_str = dumps({k: attr.get(k) for k in KEYS}, default=default)
            return Response(json_str, content_type="application/json; charset=utf-8")
        case "list":
            if not root_dir:
                raise NotADirectoryError(errno.ENOTDIR, "root is not directory")
            if pickcode:
                fid = relogin_wrap(fs.get_id_from_pickcode, pickcode)
            if fid is not None:
                children = relogin_wrap(fs.listdir_attr, int(fid))
            elif path_persistence_commitment and (fid := fs.path_to_id.get(path)):
                children = relogin_wrap(fs.listdir_attr, fid)
            else:
                children = relogin_wrap(fs.listdir_attr, path)
            if children and root != 0 and not any(info["id"] == root for info in children[0]["path"].ancestors[:-1]):
                raise PermissionError(errno.EACCES, "out of root range")
            json_str = dumps([
                {k: attr.get(k) for k in KEYS} 
                for attr in map(update_attr, children)
            ], default=default)
            return Response(json_str, content_type="application/json; charset=utf-8")
        case "desc":
            if not root_dir:
                return relogin_wrap(fs.desc, root)
            else:
                if pickcode:
                    fid = relogin_wrap(fs.get_id_from_pickcode, pickcode)
                if fid is not None:
                    return relogin_wrap(fs.desc, int(fid))
                elif path_persistence_commitment and (fid := fs.path_to_id.get(path)):
                    return relogin_wrap(fs.desc, fid)
                else:
                    return relogin_wrap(fs.desc, path)

    if not root_dir:
        return get_url(root_pickcode)
    if pickcode:
        return get_url(pickcode)
    if fid:
        file_id = int(fid)
        if pickcode := id_to_pickcode.get(file_id):
            return get_url(pickcode)
        attr = relogin_wrap(fs.attr, file_id)
    elif sha1 := sha1.strip():
        if pickcode := sha1_to_pickcode.get(sha1):
            return get_url(pickcode)
        try:
            attr = next(relogin_wrap(fs.search, root, search_value=sha1, limit=1, show_dir=0))
        except StopIteration:
            return f"no such file: sha1={sha1!r}", 404
    elif path_persistence_commitment and (fid := fs.path_to_id.get(path)):
        if pickcode := id_to_pickcode.get(fid):
            return get_url(pickcode)
        else:
            attr = relogin_wrap(fs.attr, fid)
    else:
        attr = relogin_wrap(fs.attr, path)
    if root != 0 and not any(info["id"] == root for info in attr["path"].ancestors):
        raise PermissionError(errno.EACCES, "out of root range")
    if not attr["is_directory"]:
        update_attr(attr)
        return get_url(attr["pickcode"])
    children = relogin_wrap(fs.listdir_attr, attr["id"])
    for subattr in children:
        update_attr(subattr)
    fid = attr["id"]
    if fid == root:
        header = f'<strong><a href="/?id={root}&method=list&password={password}" style="border: 1px solid black; text-decoration: none">/</a></strong>'
    else:
        ancestors = attr["path"].ancestors
        last_info = ancestors[-1]
        for i, info in enumerate(ancestors):
            if info["id"] == root:
                break
        header = f'<strong><a href="/?id={root}&password={password}" style="border: 1px solid black; text-decoration: none">/</a></strong>' + "".join(
                f'<strong><a href="/?id={info["id"]}&password={password}" style="border: 1px solid black; text-decoration: none">{escape(escape_name(info["name"]))}</a></strong>/' 
                for info in ancestors[i+1:-1]
            ) + f'<strong><a href="/?id={last_info["id"]}&method=list&password={password}" style="border: 1px solid black; text-decoration: none">{escape(escape_name(last_info["name"]))}</a></strong>'
    return render_template_string(
        """\
<!DOCTYPE html>
<html>
<head>
  <title>115 File List</title>
  <link rel="shortcut icon" href="/?pic=favicon" type="image/x-icon">
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
      min-width: 1200px;
      box-shadow: 0 0 20px rgba(0, 0, 0, 0.15);
    }
    thead tr {
      font-family: Lato-Bold;
      font-size: 18px;
      color: #3636f0;
      line-height: 1.4;
      background-color: #f0f0f0;
      position: sticky;
      top: 0;
    }
    th, td {
      padding: 12px 15px;
    }
    tbody tr {
      border-bottom: 1px solid #dddddd;
      background-color: #fff;
      transition: background-color 0.3s, transform 0.3s;
    }
    tbody tr:last-of-type {
      border-bottom: 2px solid #009879;
    }
    tbody tr:hover {
      color: #009879;
      font-weight: bold;
      background-color: rgba(230, 230, 230, 0.5);
      transform: scale(1.02);
    }

    .icon {
      border-radius: 10px;
      display: inline-block;
      padding: 8px;
      transition: background-color 0.5s;
    }
    .icon:hover {
        background-color: #d2d2d2;
    }

    /* Popup container - can be anything you want */
    .popup {
      position: relative;
      display: inline-block;
      cursor: pointer;
      -webkit-user-select: none;
      -moz-user-select: none;
      -ms-user-select: none;
      user-select: none;
    }
  
    /* The actual popup */
    .popup .popuptext {
      visibility: hidden;
      width: 160px;
      background-color: #555;
      color: #fff;
      text-align: center;
      border-radius: 6px;
      padding: 8px 0;
      position: absolute;
      z-index: 1;
      bottom: 125%;
      left: 50%;
      margin-left: -80px;
    }
  
    /* Popup arrow */
    .popup .popuptext::after {
      content: "";
      position: absolute;
      top: 100%;
      left: 50%;
      margin-left: -5px;
      border-width: 5px;
      border-style: solid;
      border-color: #555 transparent transparent transparent;
    }
  
    /* Toggle this class - hide and show the popup */
    .popup:hover .popuptext {
      visibility: visible;
      -webkit-animation: fadeIn 1s;
      animation: fadeIn 1s;
    }
  
    /* Add animation (fade in the popup) */
    @-webkit-keyframes fadeIn {
      from {opacity: 0;} 
      to {opacity: 1;}
    }
  
    @keyframes fadeIn {
      from {opacity: 0;}
      to {opacity:1 ;}
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
        <th style="width: 70px">M3U8</th>
        <th>Last Modified</th>
      </tr>
    </thead>
    <tbody>
      {%- if attr["id"] != root %}
      <tr>
        <td colspan="6"><a href="/?id={{ attr["parent_id"] }}&password={{ password }}" style="display: block; text-align: center; text-decoration: none; font-size: 30px">..</a></td>
      </tr>
      {%- endif %}
      {%- for attr in children %}
      <tr>
        {%- set name = attr["name"] %}
        {%- set url = attr["url"] %}
        <td style="max-width: 600px; word-wrap: break-word"><i class="file-type tp-{{ attr.get("ico") or "" }}"></i><a href="{{ url }}">{{ name }}</a></td>
        <td style="width: 160px; word-wrap: break-word;">
          {%- if not attr["is_directory"] %}
          <a class="popup" href="iina://weblink?url={{ url | urlencode }}"><img class="icon" src="/?pic=iina" /><span class="popuptext">IINA</span></a>
          <a class="popup" href="potplayer://{{ url }}"><img class="icon" src="/?pic=potplayer" /><span class="popuptext">PotPlayer</span></a>
          <a class="popup" href="vlc://{{ url }}"><img class="icon" src="/?pic=vlc" /><span class="popuptext">VLC</span></a>
          <a class="popup" href="filebox://play?url={{ url | urlencode }}"><img class="icon" src="/?pic=fileball" /><span class="popuptext">Fileball</span></a>
          <a class="popup" href="intent:{{ attr["short_url"] | urlencode }}#Intent;package=com.mxtech.videoplayer.pro;S.title={{ name }};end"><img class="icon" src="/?pic=mxplayer" /><span class="popuptext">MX Player</span></a>
          <a class="popup" href="infuse://x-callback-url/play?url={{ url | urlencode }}"><img class="icon" src="/?pic=infuse" /><span class="popuptext">infuse</span></a>
          <a class="popup" href="nplayer-{{ url }}"><img class="icon" src="/?pic=nplayer" /><span class="popuptext">nPlayer</span></a>
          <a class="popup" href="omniplayer://weblink?url={{ url | urlencode }}"><img class="icon" src="/?pic=omniplayer" /><span class="popuptext">OmniPlayer</span></a>
          <a class="popup" href="figplayer://weblink?url={{ url | urlencode }}"><img class="icon" src="/?pic=figplayer" /><span class="popuptext">Fig Player</span></a>
          <a class="popup" href="mpv://{{ url }}"><img class="icon" src="/?pic=mpv" /><span class="popuptext">MPV</span></a>
          {%- endif %}
        </td>
        {%- if attr["is_directory"] %}
        <td style="text-align: center;">--</td>
        {%- else %}
        <td style="text-align: right;"><span class="popup">{{ attr["format_size"] }}<span class="popuptext">{{ attr["size"] }}</span></span></td>
        {%- endif %}
        <td><a href="/?id={{ attr["id"] }}&method=attr&password={{ password }}">attr</a></td>
        <td><a href="/?id={{ attr["id"] }}&method=desc&password={{ password }}">desc</a></td>
        {%- if attr["is_directory"] %}
        <td style="text-align: center;">--</td>
        {%- else %}
        <td style="text-align: right">
            <a href="{{ url }}&m3u8=true&password={{ password }}">ALL(全部)</a><br />
            <a href="{{ url }}&m3u8=true&password={{ password }}&definition=3">HD(标清)</a><br />
            <a href="{{ url }}&m3u8=true&password={{ password }}&definition=4">UD(高清)</a>
        </td>
        {%- endif %}
        <td>{{ attr["mtime_str"] }}</td>
      </tr>
      {%- endfor %}
    </tbody>
  </table>
</body>
</html>""", 
        attr=attr, 
        children=children, 
        origin=origin, 
        header=header, 
        root=root, 
        password=password, 
    )


# NOTE: https://wsgidav.readthedocs.io/en/latest/user_guide_configure.html
WSGIDAV_CONFIG = {
    "host": args.host, 
    "port": args.port, 
    "mount_path": "/<dav", 
    "provider_mapping": {"/": P115FileSystemProvider(fs)}, 
    "simple_dc": {"user_mapping": {"*": True}}, 
}
wsgidav_app = WsgiDAVApp(WSGIDAV_CONFIG)
application = DispatcherMiddleware(flask_app, {"/<dav": wsgidav_app})

root_dir: str = ""
if root == 0:
    root_dir = "/"
elif not root.strip("./"):
    root = 0
    root_dir = "/"
else:
    if not root.startswith("0") and root.isascii() and root.isdecimal():
        root = int(root)
    try:
        relogin_wrap(fs.chdir, root)
    except NotADirectoryError:
        root_attr = relogin_wrap(fs.attr, root)
        root = root_attr["id"]
        root_pickcode = root_attr["pickcode"]
    else:
        root = fs.id
        if root == 0:
            root_dir = "/"
        else:
            root_dir = fs.path + "/"


if __name__ == "__main__":
    debug = args.debug
    kwargs = dict(
        hostname=args.host, 
        port=args.port, 
        application=application, 
        use_reloader=debug, 
        use_debugger=debug, 
        use_evalex=debug, 
        threaded=True, 
    )
    run_simple(**kwargs)

# TODO: 如果某个目录正在获取中，返回 concurrent.futures.Future，另一个线程如果也需要获取此目录，则直接获取此 future，对 web 和 webdav 都如此
# TODO: 可能是 wsgidav 的问题，propfind 响应太慢了，即使给文件夹做了缓存，需要看看怎么优化，可能需要对 propfind 的结果做缓存
# TODO: 完整的 wsgidav 配置文件支持
# TODO: 更完整信息的支持，类似 xattr

# TODO: 多应用共用 cookies
# TODO: 401 报错检查 cookies 是否被更新，如果是，则重跑
