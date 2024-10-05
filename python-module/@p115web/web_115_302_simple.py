#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 9)
__requirements__ = ["blacksheep", "cachetools", "orjson", "p115cipher", "uvicorn"]

from os.path import dirname, expanduser, join as joinpath, realpath

__doc__ = """\
        \x1b[5m🚀\x1b[0m 115 直链服务简单且极速版 \x1b[5m🍳\x1b[0m

链接格式（每个参数都是\x1b[1;31m可选的\x1b[0m）：\x1b[4m\x1b[34mhttp://localhost{\x1b[1;32mpath2\x1b[0m\x1b[4m\x1b[34m}?pickcode={\x1b[1;32mpickcode\x1b[0m\x1b[4m\x1b[34m}&id={\x1b[1;32mid\x1b[0m\x1b[4m\x1b[34m}&sha1={\x1b[1;32msha1\x1b[0m\x1b[4m\x1b[34m}&path={\x1b[1;32mpath\x1b[0m\x1b[4m\x1b[34m}&image={\x1b[1;32mimage\x1b[0m\x1b[4m\x1b[34m}&disable_pc={\x1b[1;32mdisable_pc\x1b[0m\x1b[4m\x1b[34m}\x1b[0m

- \x1b[1;32mpickcode\x1b[0m: 文件的 \x1b[1;32mpickcode\x1b[0m，优先级高于 \x1b[1;32mid\x1b[0m
- \x1b[1;32mid\x1b[0m: 文件的 \x1b[1;32mid\x1b[0m，优先级高于 \x1b[1;32msha1\x1b[0m
- \x1b[1;32msha1\x1b[0m: 文件的 \x1b[1;32msha1\x1b[0m，优先级高于 \x1b[1;32mpath\x1b[0m
- \x1b[1;32mpath\x1b[0m: 文件的路径，优先级高于 \x1b[1;32mpath2\x1b[0m
- \x1b[1;32mimage\x1b[0m: 接受 \x1b[1;36m1\x1b[0m | \x1b[1;36mtrue\x1b[0m 或 \x1b[1;36m0\x1b[0m | \x1b[1;36mfalse\x1b[0m，如果为 \x1b[1;36m1\x1b[0m | \x1b[1;36mtrue\x1b[0m 且提供 \x1b[1;32mpickcode\x1b[0m 且设置了环境变量 \x1b[1;32mcdn_image\x1b[0m，则视为请求图片
- \x1b[1;32mdisable_pc\x1b[0m: 接受 \x1b[1;36m1\x1b[0m | \x1b[1;36mtrue\x1b[0m 或 \x1b[1;36m0\x1b[0m | \x1b[1;36mfalse\x1b[0m，如果为 \x1b[1;36m1\x1b[0m | \x1b[1;36mtrue\x1b[0m，则此次请求视 \x1b[1;32mpath_persistence_commitment\x1b[0m 为 \x1b[1;36mFalse\x1b[0m

        \x1b[5m🌍\x1b[0m 环境变量 \x1b[5m🛸\x1b[0m

- \x1b[1;32mcookies\x1b[0m: 115 登录 cookies，优先级高于 \x1b[1;32mcookies_path\x1b[0m
- \x1b[1;32mcookies_path\x1b[0m: 存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 \x1b[4m\x1b[34m115-cookies.txt\x1b[0m 文件中获取，此文件可以在如下路径之一（按先后顺序）
    1. 当前工作目录: \x1b[4m\x1b[34m%(file_in_cwd)s\x1b[0m
    2. 用户根目录: \x1b[4m\x1b[34m%(file_in_home)s\x1b[0m
    3. 此脚本所在目录: \x1b[4m\x1b[34m%(file_in_dir)s\x1b[0m
- \x1b[1;32mpath_persistence_commitment\x1b[0m: （\x1b[1;31m传入任何值都视为设置，包括空字符串\x1b[0m）路径持久性承诺，只要你能保证文件不会被移动（\x1b[1;31m可新增删除，但对应的路径不可被其他文件复用\x1b[0m），打开此选项，用路径请求直链时，可节约一半时间
- \x1b[1;32mcdn_image\x1b[0m: （\x1b[1;31m传入任何值都视为设置，包括空字符串\x1b[0m）图片走 cdn，设置此参数会创建一个图片直链的缓存
- \x1b[1;32mcdn_image_warmup_ids\x1b[0m: 为图片的 cdn 缓存进行预热，接受文件夹 id，如果有多个用逗号(\x1b[1;36m,\x1b[0m)隔开
- \x1b[1;32mcdn_image_warmup_no_path_cache\x1b[0m: （\x1b[1;31m传入任何值都视为设置，包括空字符串\x1b[0m）为图片的 cdn 缓存进行预热时，不建立路径到 id 的映射，以加快预热速度，但使用路径获取图片时速度慢很多
- \x1b[1;32murl_ttl\x1b[0m: 直链存活时间（\x1b[1;31m单位：秒\x1b[0m），默认值 \x1b[1;36m1\x1b[0m。特别的，若 \x1b[1;36m= 0\x1b[0m，则不缓存；若 \x1b[1;36m< 0\x1b[0m，则不限时
- \x1b[1;32murl_reuse_factor\x1b[0m: 直链最大复用次数，默认值 \x1b[1;36m-1\x1b[0m。特别的，若 \x1b[1;36m= 0\x1b[0m 或 \x1b[1;36m= 1\x1b[0m，则不缓存；若 \x1b[1;36m< 0\x1b[0m，则不限次数
- \x1b[1;32murl_range_request_cooldown\x1b[0m: range 请求冷却时间，默认值 \x1b[1;36m0\x1b[0m，某个 ip 对某个资源执行一次 range 请求后必须过一定的冷却时间后才能对相同范围再次请求。特别的，若 \x1b[1;36m<= 0\x1b[0m，则不需要冷却

        \x1b[5m🔨\x1b[0m 如何运行 \x1b[5m🪛\x1b[0m

在脚本所在目录下，创建一个 \x1b[4m\x1b[34m115-cookies.txt\x1b[0m，并把 115 的 cookies 保存其中，格式为

    UID=...; CID=...; SEID=...

然后进入脚本所在目录，运行（默认端口：\x1b[1;36m80\x1b[0m，可用命令行参数 \x1b[1m-p\x1b[0m/\x1b[1m--port\x1b[0m 指定其它）

    python web_115_302_simple.py

或者（默认端口：\x1b[1;36m8000\x1b[0m，可用命令行参数 \x1b[1m--port\x1b[0m 指定其它）

    uvicorn web_115_302_simple:app
""" % {
    "file_in_cwd": joinpath(realpath("."), "115-cookies.txt"), 
    "file_in_home": joinpath(realpath(expanduser("~")), "115-cookies.txt"), 
    "file_in_dir": joinpath(realpath(dirname(__file__)), "115-cookies.txt"), 
}

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, 
        description=__doc__, 
    )
    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
    parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值：80")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

print(__doc__)

from os import environ, stat

cookies = bytes(environ.get("cookies", "").strip(), "latin-1")
cookies_path = environ.get("cookies_path", "")
cookies_path_mtime = 0
device = ""
path_persistence_commitment = environ.get("path_persistence_commitment") is not None
cdn_image = environ.get("cdn_image") is not None
cdn_image_warmup_ids = environ.get("cdn_image_warmup_ids", "")
cdn_image_warmup_no_path_cache = environ.get("cdn_image_warmup_no_path_cache") is not None
url_ttl = float(environ.get("url_ttl", "1"))
url_reuse_factor = int(environ.get("url_reuse_factor", "-1"))
url_range_request_cooldown = int(environ.get("url_range_request_cooldown", "0"))

if not cookies:
    if cookies_path:
        try:
            cookies = open(cookies_path, "rb").read().strip()
            cookies_path_mtime = stat(cookies_path).st_mtime_ns
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
                if cookies := open(path, "rb").read().strip():
                    cookies_path = path
                    cookies_path_mtime = stat(cookies_path).st_mtime_ns
                    break
            except FileNotFoundError:
                pass
if not cookies:
    raise SystemExit("unable to get cookies")


import errno
import logging

from asyncio import create_task, sleep, Lock
from collections.abc import Iterable, Iterator, MutableMapping
try:
    from collections.abc import Buffer # type: ignore
except ImportError:
    Buffer = bytes | bytearray | memoryview
from base64 import b64decode, b64encode
from enum import Enum
from functools import partial, update_wrapper
from posixpath import split as splitpath
from time import time
from typing import cast, Final
from urllib.parse import urlencode, urlsplit

try:
    import blacksheep
    from blacksheep import Application, route, redirect, text
    from blacksheep.client.session import ClientSession
    from blacksheep.common.types import normalize_headers
    from blacksheep.contents import FormContent
    from blacksheep.exceptions import HTTPException
    from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
    from blacksheep.messages import Request, Response
    from cachetools import LRUCache, TTLCache
    from orjson import dumps, loads
    from p115cipher import rsa_encode, rsa_decode
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", *__requirements__], check=True)
    import blacksheep
    from blacksheep import Application, route, redirect, text
    from blacksheep.client.session import ClientSession
    from blacksheep.common.types import normalize_headers
    from blacksheep.contents import FormContent
    from blacksheep.exceptions import HTTPException
    from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
    from blacksheep.messages import Request, Response
    from cachetools import LRUCache, TTLCache
    from orjson import dumps, loads
    from p115cipher import rsa_encode, rsa_decode


# TODO: 把各种工具放入函数，不要是全局变量
# TODO: 这个工具，集成到 p115 中

app = Application()
logger = getattr(app, "logger")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[\x1b[1m%(asctime)s\x1b[0m] (\x1b[1;36m%(levelname)s\x1b[0m) \x1b[5;31m➜\x1b[0m %(message)s"))
logger.addHandler(handler)
cookies_lock = Lock()

# NOTE: id 到 pickcode 的映射
ID_TO_PICKCODE: MutableMapping[str, str] = LRUCache(65536)
# NOTE: sha1 到 pickcode 到映射
SHA1_TO_PICKCODE: MutableMapping[str, str] = LRUCache(65536)
# NOTE: 路径到 id 到映射
PATH_TO_ID: MutableMapping[str, str] = LRUCache(1048576 if path_persistence_commitment else 65536)
# NOTE: 链接缓存，如果改成 None，则不缓存，可以自行设定 ttl (time-to-live)
URL_CACHE: None | MutableMapping[tuple[str, str], tuple[str, int]] = None
if url_reuse_factor not in (0, 1):
    if url_ttl > 0:
        URL_CACHE = TTLCache(1024, ttl=url_ttl)
    elif url_ttl < 0:
        URL_CACHE = LRUCache(1024)
# NOTE: 缓存图片的 CDN 直链 1 小时
IMAGE_URL_CACHE: MutableMapping[str, bytes] = TTLCache(float("inf"), ttl=3600)
# NOTE: 每个 ip 对于某个资源的某个 range 请求，一定时间范围内，分别只放行一个，可以自行设定 ttl (time-to-live)
RANGE_REQUEST_COOLDOWN: None | MutableMapping[tuple[str, str, str, bytes], None] = None
if url_range_request_cooldown > 0:
    RANGE_REQUEST_COOLDOWN = TTLCache(8196, ttl=url_range_request_cooldown)


# TODO: 登录使用单独的模块，另外两个 qrcode_cookie*.py 的文件要被删掉
# TODO: 实现同步和异步的版本
AppEnum = Enum("AppEnum", {
    "web": 1, 
    "ios": 6, 
    "115ios": 8, 
    "android": 9, 
    "115android": 11, 
    "115ipad": 14, 
    "tv": 15, 
    "qandroid": 16, 
    "windows": 19, 
    "mac": 20, 
    "linux": 21, 
    "wechatmini": 22, 
    "alipaymini": 23, 
})


def get_enum_name(val, cls):
    if isinstance(val, cls):
        return val.name
    try:
        if isinstance(val, str):
            return cls[val].name
    except KeyError:
        pass
    return cls(val).name


def redirect_exception_response(func, /):
    async def wrapper(*args, **kwds):
        try:
            return await func(*args, **kwds)
        except BaseException as e:
            message = f"{type(e).__module__}.{type(e).__qualname__}: {e}"
            logger.error(message)
            if isinstance(e, HTTPException):
                return text(message, e.status)
            elif isinstance(e, AuthenticationError):
                return text(str(e), 401)
            elif isinstance(e, PermissionError):
                return text(str(e), 403)
            elif isinstance(e, FileNotFoundError):
                return text(str(e), 404)
            elif isinstance(e, (IsADirectoryError, NotADirectoryError)):
                return text(str(e), 406)
            elif isinstance(e, OSError):
                return text(str(e), 500)
            elif isinstance(e, Exception):
                return text(str(e), 503)
            raise
    return update_wrapper(wrapper, func)


async def do_request(
    client: ClientSession, 
    url: str | bytes | blacksheep.url.URL, 
    method: str = "GET", 
    content: None | blacksheep.contents.Content = None, 
    headers: None | dict[str, str] = None, 
    params: None | dict[str, str] = None, 
) -> Response:
    global cookies, cookies_path_mtime
    request_headers: list[tuple[bytes, bytes]]
    if headers:
        request_headers = normalize_headers(headers) # type: ignore
    else:
        request_headers = []
    current_cookies = cookies
    request_headers.append((b"Cookie", current_cookies))
    request = Request(method.upper(), client.get_url(url, params), request_headers)
    response = await client.send(request.with_content(content) if content else request)
    if response.status == 405:
        async with cookies_lock:
            if cookies_path:
                try:
                    if cookies_path_mtime != stat(cookies_path).st_mtime_ns:
                        cookies = open(cookies_path, "rb").read().strip()
                        cookies_path_mtime = stat(cookies_path).st_mtime_ns
                except FileNotFoundError:
                    pass
            if current_cookies == cookies:
                await relogin(client)
        return await do_request(client, url, method, content, headers, params)
    if response.status >= 400:
        raise HTTPException(response.status, response.reason)
    return response


async def request_json(
    client: ClientSession, 
    url: str | bytes | blacksheep.url.URL, 
    method: str = "GET", 
    content: None | blacksheep.contents.Content = None, 
    headers: None | dict[str, str] = None, 
    params: None | dict[str, str] = None, 
) -> dict:
    global cookies, cookies_path_mtime
    current_cookies = cookies
    resp = await do_request(client, url, method, content=content, headers=headers, params=params)
    json = loads((await resp.read()) or b"")
    try:
        return check_response(json)
    except AuthenticationError:
        async with cookies_lock:
            if cookies_path:
                try:
                    if cookies_path_mtime != stat(cookies_path).st_mtime_ns:
                        cookies = open(cookies_path, "rb").read().strip()
                        cookies_path_mtime = stat(cookies_path).st_mtime_ns
                except FileNotFoundError:
                    pass
            if current_cookies == cookies:
                raise
        return await request_json(client, url, method, content=content, headers=headers, params=params)


# TODO: 不需要此接口，直接根据 user_id 的 ssoent 来判断
async def login_device(client: ClientSession) -> str:
    url = "https://passportapi.115.com/app/1.0/web/1.0/login_log/login_devices"
    resp = await request_json(client, url)
    return next((d["icon"] for d in resp["data"]["list"] if d["is_current"]), "qandroid")


async def login_qrcode_token(client: ClientSession) -> dict:
    """获取二维码
    """
    url = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
    return await request_json(client, url)


async def login_qrcode_scan(client: ClientSession, uid: str) -> dict:
    """扫描二维码
    """
    url = f"https://qrcodeapi.115.com/api/2.0/prompt.php"
    return await request_json(client, url, params={"uid": uid})


async def login_qrcode_scan_confirm(client: ClientSession, uid: str) -> dict:
    """确认扫描二维码
    """
    url = f"https://hnqrcodeapi.115.com/api/2.0/slogin.php"
    return await request_json(client, url, params={"key": uid, "uid": uid, "client": "0"})


async def login_qrcode_scan_result(client: ClientSession, uid: str, app: str = "web") -> dict:
    """把扫码结果绑定到设备
    """
    app = get_enum_name(app, AppEnum)
    url = "https://passportapi.115.com/app/1.0/%s/1.0/login/qrcode/" % app
    return await request_json(client, url, "POST", content=FormContent({"account": uid}))


async def relogin(client: ClientSession) -> dict:
    """自动扫二维码重新登录
    """
    global cookies, cookies_path_mtime, device
    if not device:
        device = await login_device(client)
    logger.warning(f"\x1b[1m\x1b[33m[SCAN] 🦾 重新扫码: {device!r} 🦿\x1b[0m")
    uid = (await login_qrcode_token(client))["data"]["uid"]
    await login_qrcode_scan(client, uid)
    await login_qrcode_scan_confirm(client, uid)
    resp = await login_qrcode_scan_result(client, uid, device)
    cookies = bytes("; ".join("%s=%s" % e for e in resp["data"]["cookie"].items()), "latin-1")
    if cookies_path:
        open(cookies_path, "wb").write(cookies)
        cookies_path_mtime = stat(cookies_path).st_mtime_ns
    return resp


# TODO: 不需要传入 dir，但有全局的 id_to_dir，可以自动确定路径
def process_info(info: dict, dir: None | str = None) -> str:
    if "file_id" in info:
        file_id = cast(str, info["file_id"])
        file_name = cast(str, info["file_name"])
        pick_code = cast(str, info["pick_code"])
        thumb = info.get("img_url", "")
        if "sha1" in info:
            SHA1_TO_PICKCODE[info["sha1"]] = pick_code
    else:
        file_id = cast(str, info["fid"])
        file_name = cast(str, info["n"])
        pick_code = cast(str, info["pc"])
        thumb = info.get("u", "")
        SHA1_TO_PICKCODE[info["sha"]] = pick_code
    ID_TO_PICKCODE[file_id] = pick_code
    if cdn_image and thumb:
        IMAGE_URL_CACHE[pick_code] = bytes(reduce_image_url_layers(thumb), "utf-8")
    if dir:
        PATH_TO_ID[dir + "/" + file_name] = file_id
    elif dir is not None:
        PATH_TO_ID[file_name] = file_id
    return pick_code


@app.on_middlewares_configuration
def configure_forwarded_headers(app):
    app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))


@app.lifespan
async def register_http_client():
    async with ClientSession(follow_redirects=False) as client:
        app.services.register(ClientSession, instance=client)
        yield


async def get_dir_patht_by_id(
    client: ClientSession, 
    id: str, 
    /, 
) -> list[tuple[str, str]]:
    json = await request_json(
        client, 
        "https://webapi.115.com/files", 
        params={
            "count_folders": "0", "record_open_time": "0", "show_dir": "1", 
            "cid": id, "limit": "1", "offset": "0", 
        }, 
    )
    return [(info["cid"], info["name"]) for info in json["path"][1:]]


async def get_attr(id: int, /):
    ...



# TODO: 这个函数需要进行优化
async def get_pickcode_by_id(
    client: ClientSession, 
    id: str, 
    /, 
) -> str:
    if pickcode := ID_TO_PICKCODE.get(id):
        return pickcode
    json = await request_json(
        client, 
        "https://webapi.115.com/files/get_info", 
        params={"file_id": id}, 
    )
    info = json["data"][0]
    if "fid" not in info:
        raise FileNotFoundError(errno.ENOENT, id)
    return process_info(info)


async def get_pickcode_by_sha1(
    client: ClientSession, 
    sha1: str, 
    /, 
) -> str:
    if len(sha1) != 40:
        raise ValueError(f"invalid sha1 {sha1!r}")
    if pickcode := SHA1_TO_PICKCODE.get(sha1):
        return pickcode
    json = await request_json(
        client, 
        "https://webapi.115.com/files/shasearch", 
        params={"sha1": sha1}, 
    )
    if not json["state"]:
        raise FileNotFoundError(errno.ENOENT, f"no such sha1 {sha1!r}")
    return process_info(json["data"])


async def get_pickcode_by_path(
    client: ClientSession, 
    path: str, 
    disable_pc: bool = False, 
    /, 
) -> str:
    path = path.strip("/")
    dir_, name = splitpath(path)
    if not name:
        raise FileNotFoundError(path)
    if fid := PATH_TO_ID.get(path):
        if not disable_pc and path_persistence_commitment and (pickcode := ID_TO_PICKCODE.get(fid)):
            return pickcode
        json = await request_json(
            client, 
            "https://webapi.115.com/files/file", 
            params={"file_id": fid}, 
        )
        if json["state"]:
            info = json["data"][0]
            if info["file_name"] == name:
                return info["pick_code"]
        PATH_TO_ID.pop(path, None)
    if dir_:
        json = await request_json(
            client, 
            "https://webapi.115.com/files/getid", 
            params={"path": dir_}, 
        )
        if not (pid := json["id"]):
            raise FileNotFoundError(path)
    else:
        pid = 0
    # 使用 iterdir 方法
    params = {"count_folders": 0, "record_open_time": 0, "show_dir": 1, "cid": pid, "limit": 10_000, "offset": 0}
    while True:
        json = await request_json(
            client, 
            "https://webapi.115.com/files", 
            params=params, 
        )
        it = iter(json["data"])
        for info in it:
            if "fid" in info:
                pickcode = process_info(info, dir_)
                if info["n"] == name:
                    for info in it:
                        process_info(info, dir_)
                    return pickcode
        if json["offset"] + len(json["data"]) == json["count"]:
            break
        params["offset"] += 5000
    raise FileNotFoundError(path)


def reduce_image_url_layers(url: str) -> str:
    if not url.startswith(("http://thumb.115.com/", "https://thumb.115.com/")):
        return url
    urlp = urlsplit(url)
    sha1 = urlp.path.rsplit("/")[-1].split("_")[0]
    return f"https://imgjump.115.com/?sha1={sha1}&{urlp.query}&size=0"


async def iterdir():
    ...

async def iter_files(
    client: ClientSession, 
    cid: str = "0", 
    /, 
) -> AsyncIterator[dict]:
    api = "https://webapi.115.com/files"
    payload: dict = {
        "aid": 1, "asc": 1, "cid": cid, "count_folders": 0, "cur": 0, "custom_order": 1, 
        "limit": 10_000, "o": "user_ptime", "offset": 0, "show_dir": 0, 
    }
    ...


# TODO: 这个函数的代码不该这么多
async def warmup_cdn_image(
    client: ClientSession, 
    cid: str = "0", 
    /, 
    cache: None | dict[str, str] = None, 
) -> int:
    api = "https://webapi.115.com/files"
    payload: dict = {
        "aid": 1, "asc": 1, "cid": cid, "count_folders": 0, "cur": 0, "custom_order": 1, 
        "limit": 10_000, "o": "user_ptime", "offset": 0, "show_dir": 0, "type": 2, 
    }
    count = 0
    while True:
        resp = await request_json(client, api, params=payload)
        for item in resp["data"]:
            # TODO: 使用 process_info，改名为 normalize_info
            file_id = item["file_id"]
            pickcode = item["pick_code"]
            IMAGE_URL_CACHE[pickcode] = bytes(reduce_image_url_layers(item["thumb_url"]), "utf-8")
            ID_TO_PICKCODE[file_id] = pickcode
            SHA1_TO_PICKCODE[item["sha1"]] = pickcode
            if cache is not None:
                parent_id = str(item["parent_id"])
                dirname = ""
                if parent_id != "0" and not (dirname := cache.get(parent_id, "")):
                    patht = await get_dir_patht_by_id(client, parent_id)
                    for pid, name in patht:
                        if dirname:
                            dirname += "/" + name
                        else:
                            dirname = name
                        cache[pid] = dirname
                path = item["file_name"]
                if dirname:
                    path = dirname + "/" + path
                PATH_TO_ID[path] = file_id
        total = resp["count"]
        delta = len(resp["data"])
        count += delta
        logger.info("successfully cached %s (finished=%s, total=%s) cdn images in %s", delta, count, total, id)
        if count >= total:
            break
        payload["offset"] += 10_000
    return count


if cdn_image and cdn_image_warmup_ids:
    async def periodically_warmup_cdn_image(client: ClientSession, ids: str):
        id_list = [int(id) for id in ids.split(",") if id]
        if not id_list:
            return
        cache: None | dict[str, str] = None
        if not cdn_image_warmup_no_path_cache:
            cache = {}
        while True:
            start = time()
            for id in map(str, id_list):
                if cache and id in cache:
                    logger.warning("skipped cdn images warmup-ing in %s", id)
                    continue
                logger.info("background task start: warmup-ing cdn images in %s", id)
                try:
                    count = await warmup_cdn_image(client, id, cache=cache)
                except Exception:
                    logger.exception("error occurred while warmup-ing cdn images in %s", id)
                else:
                    logger.info("background task stop: warmup-ed cdn images in %s, count=%s", id, count)
            if (interval := start + 3600 - time()) > 0:
                await sleep(interval)

    @app.on_start
    async def configure_background_tasks(app: Application):
        client = app.services.resolve(ClientSession)
        create_task(periodically_warmup_cdn_image(client, cdn_image_warmup_ids))


# TODO: 如果需要根据文件 id 获取基本的信息，可以用 fs_file_skim（可以一次查多个），如果可能还需要图片链接，则用fs_info
# TODO: 可以是 id 也可以是 pickcode（为了加速）
# 这个接口有多个信息可用（pick_code,file_sha1，但无id）
async def get_image_url(
    client: ClientSession, 
    pickcode: str, 
) -> bytes:
    """获取图片的 cdn 链接
    """
    if IMAGE_URL_CACHE and (url := IMAGE_URL_CACHE.get(pickcode)):
        return url
    json = await request_json(
        client, 
        "https://webapi.115.com/files/image", 
        params={"pickcode": pickcode}, 
    )
    origin_url = json["data"]["origin_url"]
    resp = await do_request(client, origin_url, "HEAD")
    url = cast(bytes, resp.get_first_header(b"Location"))
    if IMAGE_URL_CACHE is not None:
        IMAGE_URL_CACHE[pickcode] = url
    return url


# TODO 这个函数需要大大拆分，进行巨大的简化
@route("/", methods=["GET", "HEAD"])
@route("/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def get_download_url(
    request: Request, 
    client: ClientSession, 
    pickcode: str = "", 
    id: str = "", 
    sha1: str = "", 
    path: str = "", 
    path2: str = "", 
    image: bool = False, 
    disable_pc: bool = False, 
):
    """获取文件的下载链接

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件的 id，优先级高于 sha1
    :param sha1: 文件的 sha1，优先级高于 path
    :param path: 文件的路径，优先级高于 path2
    :param path2: 文件的路径，这个直接在接口路径之后，不在查询字符串中
    :param image: 视为图片（当提供 pickcode 且设置了环境变量 cdn_image）
    :param disable_pc: 视 path_persistence_commitment 为 False
    """
    try:
        user_agent = (request.get_first_header(b"User-agent") or b"").decode("utf-8")
        if not (pickcode := pickcode.strip()):
            if id := id.strip():
                pickcode = await get_pickcode_by_id(client, id)
            elif sha1 := sha1.strip():
                pickcode = await get_pickcode_by_sha1(client, sha1)
            else:
                pickcode = await get_pickcode_by_path(client, path or path2)
        if RANGE_REQUEST_COOLDOWN is not None:
            key = (request.client_ip or "", user_agent, pickcode, request.get_first_header(b"Range") or b"")
            if key in RANGE_REQUEST_COOLDOWN:
                return text("Too Many Requests", 429)
            RANGE_REQUEST_COOLDOWN[key] = None
        if URL_CACHE is not None and (t := URL_CACHE.get((pickcode, user_agent))):
            url, times = t
            if url_reuse_factor < 0 or times < url_reuse_factor:
                URL_CACHE[(pickcode, user_agent)] = (url, times + 1)
                return redirect(url)
        if cdn_image and (image or pickcode in IMAGE_URL_CACHE):
            return redirect(await get_image_url(client, pickcode))
        # TODO: 需要单独封装
        json = await request_json(
            client, 
            "https://proapi.115.com/app/chrome/downurl", 
            method="POST", 
            content=FormContent({"data": rsa_encode(b'{"pickcode":"%s"}' % bytes(pickcode, "ascii")).decode("ascii")}), 
            headers={"User-Agent": user_agent}, 
        )
        data = loads(rsa_decode(json["data"]))
        item = next(info for info in data.values())
        ID_TO_PICKCODE[next(iter(data))] = item["pick_code"]
        # NOTE: 还需要继续增加，目前不确定 115 到底支持哪些图片格式
        if cdn_image and item["file_name"].lower().endswith((
            ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".raw", ".svg", ".tif", ".tiff", ".webp", 
        )):
            IMAGE_URL_CACHE[item["pick_code"]] = "" # type: ignore
        url = item["url"]["url"]
        if URL_CACHE is not None:
            URL_CACHE[(pickcode, user_agent)] = (url, 1)
        return redirect(cast(str, url))
    except (FileNotFoundError, KeyError):
        return text("not found", 404) 


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        from sys import executable
        from subprocess import run
        run([executable, "-m", "pip", "install", "-U", "uvicorn"], check=True)
        import uvicorn
    uvicorn.run(
        app=app, 
        host=args.host, 
        port=args.port, 
        proxy_headers=True, 
        forwarded_allow_ips="*", 
    )

# TODO 作为模块提供，返回一个 app 对象，以便和其它模块集成
# TODO 换个框架 robyn？
# TODO 同步框架选用 flask，异步框架还要再挑一挑
# TODO 与 webdav 集成（可以关闭）
# TODO 应该作为单独模块提供（以便和其它项目集成），提交到 pypi，名字叫 p115302，提供同步和异步的版本，但不依赖于p115
# TODO 任何接口都要有一个单独的封装函数
# TODO 各种函数都要简化或者拆分
# TODO 查询sha1用新的接口
# TODO 如果图片需要路径，则用批量打星标的办法实现
# TODO 缓存 id_to_dir
# TODO 更好的算法，以快速更新 PATH_TO_ID
# TODO 这个文件可以实现为一个模块
# TODO 不需要判断 login_device
# TODO 可以为多种类型的文件预热（例如图片或视频）
# TODO 允许对链接进行签名：命令行传入token（有token时才做签名），链接里可以包含截止时间（默认为0，即永不失效），然后由 f"302@115-{t}-{value}#{type}-{token}" t 是截止时间，后面的 type 是类型，包括sha1,pickcode,path,id，再计算一下哈希

