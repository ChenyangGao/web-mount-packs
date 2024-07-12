#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__version_str__ = ".".join(map(str, __version__))
__doc__ = """\
    🕸️ 获取你的 115 网盘账号上文件信息和下载链接 🕷️

🚫 注意事项：请求头需要携带 User-Agent。
如果使用 web 的下载接口，则有如下限制：
    - 大于等于 115 MB 时不能下载
    - 不能直接请求直链，需要携带特定的 Cookie 和 User-Agent
"""

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from warnings import warn

    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, 
        description=__doc__, 
    )
    parser.add_argument("-c", "--cookies", default="", help="115 登录 cookies，优先级高于 -cp/--cookies-path")
    parser.add_argument("-cp", "--cookies-path", default="", help="""\
存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一: 
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录""")
    parser.add_argument("-wc", "--web-cookies", default="", help="提供一个 web 的 cookies，因为目前使用的获取 .m3u8 的接口，需要 web 的 cookies 才能正确获取数据，如不提供，则将自动扫码获取")
    parser.add_argument("-l", "--lock-dir-methods", action="store_true", help="对 115 的文件系统进行增删改查的操作（但不包括上传和下载）进行加锁，限制为不可并发，这样就可减少 405 响应，以降低扫码的频率")
    parser.add_argument("-pc", "--path-persistence-commitment", action="store_true", help="路径持久性承诺，只要你能保证文件不会被移动（可新增删除，但对应的路径不可被其他文件复用），打开此选项，用路径请求直链时，可节约一半时间")

    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值 '0.0.0.0'")
    parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值 80")
    parser.add_argument("-r", "--reload", action="store_true", help="此项目所在目录下的文件发生变动时重启，此选项仅用于调试")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        print(__version_str__)
        raise SystemExit(0)

    cookies = args.cookies
    cookies_path = args.cookies_path
    web_cookies = args.web_cookies
    lock_dir_methods = args.lock_dir_methods
    path_persistence_commitment = args.path_persistence_commitment
else:
    from os import environ

    print("""
\t\t🌍 支持如下环境变量 🛸

    - \x1b[1m\x1b[32mcookies\x1b[0m: 115 登录 cookies，优先级高于 \x1b[1m\x1b[32mcookies_path\x1b[0m
    - \x1b[1m\x1b[32mcookies_path\x1b[0m: 存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 \x1b[4m\x1b[34m115-cookies.txt\x1b[0m 文件中获取，此文件可以在如下路径之一
        1. 当前工作目录
        2. 用户根目录
        3. 此脚本所在目录 下
    - \x1b[1m\x1b[32mweb_cookies\x1b[0m: 提供一个 web 的 cookies，因为目前使用的获取 .m3u8 的接口，需要 web 的 cookies 才能正确获取数据，如不提供，则将自动扫码获取
    - \x1b[1m\x1b[32mlock_dir_methods\x1b[0m: （\x1b[1m\x1b传入任何值都视为设置，包括空字符串\x1b[0m）对 115 的文件系统进行增删改查的操作（\x1b[1m\x1b但不包括上传和下载\x1b[0m）进行加锁，限制为不可并发，这样就可减少 405 响应，以降低扫码的频率
    - \x1b[1m\x1b[32mpath_persistence_commitment\x1b[0m: （\x1b[1m\x1b传入任何值都视为设置，包括空字符串\x1b[0m）路径持久性承诺，只要你能保证文件不会被移动（\x1b[1m\x1b可新增删除，但对应的路径不可被其他文件复用\x1b[0m），打开此选项，用路径请求直链时，可节约一半时间
""")

    cookies = environ.get("cookies", "")
    cookies_path = environ.get("cookies_path", "")
    web_cookies = environ.get("web_cookies", "")
    lock_dir_methods = environ.get("lock_dir_methods") is not None
    path_persistence_commitment = environ.get("path_persistence_commitment") is not None


from asyncio import Lock
from collections.abc import Mapping, MutableMapping
from functools import partial, update_wrapper
from os import stat
from os.path import dirname, expanduser, join as joinpath, realpath
from sys import exc_info
from urllib.parse import quote

from cachetools import LRUCache, TTLCache
from blacksheep import (
    route, text, html, file, redirect, 
    Application, Content, Request, Response, StreamedContent
)
from blacksheep.server.openapi.common import ParameterInfo
from blacksheep.server.openapi.ui import ReDocUIProvider
from blacksheep.server.openapi.v3 import OpenAPIHandler
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from openapidocs.v3 import Info # type: ignore
from httpx import HTTPStatusError
from p115 import P115Client, P115Url, AVAILABLE_APPS


cookies_path_mtime = 0
login_lock = Lock()
web_login_lock = Lock()
fs_lock = Lock() if lock_dir_methods else None

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
                path = joinpath(dir_, "115-cookies.txt")
                cookies = open(path).read()
                cookies_path_mtime = stat(path).st_mtime_ns
                if cookies:
                    cookies_path = path
                    break
            except FileNotFoundError:
                pass

client = P115Client(cookies, app="qandroid")
if cookies_path and cookies != client.cookies:
    open(cookies_path, "w").write(client.cookies)

device = client.login_device()["icon"]
if device not in AVAILABLE_APPS:
    # 115 浏览器版
    if device == "desktop":
        device = "web"
    else:
        warn(f"encountered an unsupported app {device!r}, fall back to 'qandroid'")
        device = "qandroid"
fs = client.get_fs(client, path_to_id=LRUCache(65536))
# NOTE: id 到 pickcode 的映射
id_to_pickcode: MutableMapping[int, str] = LRUCache(65536)
# NOTE: 有些播放器，例如 IINA，拖动进度条后，可能会有连续 2 次请求下载链接，而后台请求一次链接大约需要 170-200 ms，因此弄个 0.3 秒的缓存
url_cache: MutableMapping[tuple[str, str], P115Url] = TTLCache(64, ttl=0.3)


app = Application()
logger = getattr(app, "logger")
docs = OpenAPIHandler(info=Info(
    title="115 filelist web api docs", 
    version=__version_str__, 
))
docs.ui_providers.append(ReDocUIProvider())
docs.bind_app(app)


@app.on_middlewares_configuration
def configure_forwarded_headers(app):
    app.middlewares.insert(0, ForwardedHeadersMiddleware())


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


async def relogin(exc=None):
    global cookies_path_mtime
    if exc is None:
        exc = exc_info()[0]
    mtime = cookies_path_mtime
    async with login_lock:
        need_update = mtime == cookies_path_mtime
        if cookies_path and need_update:
            try:
                mtime = stat(cookies_path).st_mtime_ns
                if mtime != cookies_path_mtime:
                    client.cookies = open(cookies_path).read()
                    cookies_path_mtime = mtime
                    need_update = False
            except FileNotFoundError:
                logger.error("\x1b[1m\x1b[33m[SCAN] 🦾 文件空缺\x1b[0m")
        if need_update:
            if exc is None:
                logger.error("\x1b[1m\x1b[33m[SCAN] 🦾 重新扫码\x1b[0m")
            else:
                logger.error("""{prompt}一个 Web API 受限 (响应 "405: Not Allowed"), 将自动扫码登录同一设备\n{exc}""".format(
                    prompt = "\x1b[1m\x1b[33m[SCAN] 🤖 重新扫码：\x1b[0m", 
                    exc    = f"    ├ \x1b[31m{type(exc).__module__}.{type(exc).__qualname__}\x1b[0m: {exc}")
                )
            await client.login_another_app(
                device, 
                replace=True, 
                timeout=5, 
                async_=True, 
            )
            if cookies_path:
                open(cookies_path, "w").write(client.cookies)
                cookies_path_mtime = stat(cookies_path).st_mtime_ns


async def call_wrap(func, /, *args, **kwds):
    kwds["async_"] = True
    try:
        if fs_lock is None:
            return await func(*args, **kwds)
        else:
            async with fs_lock:
                return await func(*args, **kwds)
    except HTTPStatusError as e:
        if e.response.status_code != 405:
            raise
        await relogin(e)
    return await call_wrap(func, *args, **kwds)


def normalize_attr(
    attr: Mapping, 
    origin: str = "", 
) -> dict:
    KEYS = (
        "id", "parent_id", "name", "path", "pickcode", "is_directory", "sha1", 
        "size", "ico", "ctime", "mtime", "atime", "thumb", "star", "labels", 
        "score", "hidden", "described", "violated", "ancestors", 
    )
    data = {k: attr[k] for k in KEYS if k in attr}
    data["id"] = str(data["id"])
    data["parent_id"] = str(data["parent_id"])
    for info in data["ancestors"]:
        info["id"] = str(info["id"])
        info["parent_id"] = str(info["parent_id"])
    if not attr["is_directory"]:
        pickcode = attr["pickcode"]
        url = f"{origin}/api/download{quote(attr['path'], safe=':/')}?pickcode={pickcode}"
        short_url = f"{origin}/api/download?pickcode={pickcode}"
        if attr["violated"] and attr["size"] < 1024 * 1024 * 115:
            url += "&web=true"
            short_url += "&web=true"
        data["format_size"] = format_bytes(attr["size"])
        data["url"] = url
        data["short_url"] = short_url
    return data


def redirect_exception_response(func, /):
    async def wrapper(*args, **kwds):
        try:
            return await func(*args, **kwds)
        except HTTPStatusError as e:
            return text(
                f"{type(e).__module__}.{type(e).__qualname__}: {e}", 
                e.response.status_code, 
            )
        except FileNotFoundError as e:
            return text(str(e), 404)
        except OSError as e:
            return text(str(e), 500)
        except Exception as e:
            return text(str(e), 503)
    return update_wrapper(wrapper, func)


@docs(responses={
    200: "返回对应文件或目录的信息", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/attr", methods=["GET", "HEAD"])
@route("/api/attr/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def get_attr(
    request: Request, 
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
):
    """获取文件或目录的属性

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    """
    if pickcode:
        id = await call_wrap(fs.get_id_from_pickcode, pickcode)
    attr = await call_wrap(fs.attr, (path or path2) if id < 0 else id)
    origin = f"{request.scheme}://{request.host}"
    return normalize_attr(attr, origin)


@docs(responses={
    200: "罗列对应目录", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/list", methods=["GET", "HEAD"])
@route("/api/list/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def get_list(
    request: Request, 
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
):
    """罗列归属于此目录的所有文件和目录属性

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    """
    if pickcode:
        id = await call_wrap(fs.get_id_from_pickcode, pickcode)
    children = await call_wrap(fs.listdir_attr, (path or path2) if id < 0 else id)
    origin = f"{request.scheme}://{request.host}"
    return [
        normalize_attr(attr, origin)
        for attr in children
    ]


@docs(responses={
    200: "返回对应文件或目录的祖先节点列表（包含自己）", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/ancestors", methods=["GET", "HEAD"])
@route("/api/ancestors/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def get_ancestors(
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
):
    """获取祖先节点

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    """
    if pickcode:
        id = await call_wrap(fs.get_id_from_pickcode, pickcode)
    return await call_wrap(fs.get_ancestors, (path or path2) if id < 0 else id)


@docs(responses={
    200: "返回对应文件或目录的备注", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/desc", methods=["GET", "HEAD"])
@route("/api/desc/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def get_desc(
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
):
    """获取备注

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    """
    if pickcode:
        id = await call_wrap(fs.get_id_from_pickcode, pickcode)
    return html(await call_wrap(fs.desc, (path or path2) if id < 0 else id))


@docs(responses={
    200: "返回对应文件的下载链接", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/url", methods=["GET", "HEAD"])
@route("/api/url/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def get_url(
    request: Request, 
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
    web: bool = False, 
):
    """获取下载链接

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    :param web: 是否使用 web 接口获取下载链接。如果文件被封禁，但小于 115 MB，启用此选项可成功下载文件
    """
    user_agent = (request.get_first_header(b"User-agent") or b"").decode("utf-8")
    if not pickcode:
        pickcode = await call_wrap(fs.get_pickcode, (path or path2) if id < 0 else id)
    try:
        url = url_cache[(pickcode, user_agent)]
    except KeyError:
        url = url_cache[(pickcode, user_agent)] = await call_wrap(
            fs.get_url_from_pickcode, 
            pickcode, 
            headers={"User-Agent": user_agent}, 
            use_web_api=web, 
        )
    return {"url": url, "headers": url["headers"]}


@docs(responses={
    200: "下载对应文件", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/download", methods=["GET", "HEAD"])
@route("/api/download/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def file_download(
    request: Request, 
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
    web: bool = False, 
):
    """下载文件

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    :param web: 是否使用 web 接口获取下载链接。如果文件被封禁，但小于 115 MB，启用此选项可成功下载文件
    """
    resp = await get_url.__wrapped__(request, pickcode, id, path, path2, web=web)
    url = resp["url"]
    headers = resp["headers"]
    if web:
        if bytes_range := request.get_first_header(b"Range"):
            headers["Range"] = bytes_range.decode("utf-8")
        stream = await client.request(url, headers=headers, parse=None, async_=True)
        resp_headers = [
            (k.encode("utf-8"), v.encode("utf-8")) 
            for k, v in stream.headers.items() 
            if k.lower() not in ("content-type", "content-disposition", "date")
        ]
        resp_headers.append((b"Content-Disposition", b'attachment; filename="%s"' % quote(url["file_name"]).encode("ascii")))
        return Response(
            stream.status_code, 
            headers=resp_headers, 
            content=StreamedContent(
                (stream.headers.get("Content-Type") or "application/octet-stream").encode("utf-8"), 
                partial(stream.aiter_bytes, 1 << 16), 
            ), 
        )
    return redirect(url)


@docs(responses={
    200: "返回对应文件的 m3u8 文件", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/m3u8", methods=["GET", "HEAD"])
@route("/api/m3u8/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def file_m3u8(
    request: Request, 
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
    definition: int = 4, 
):
    """获取音视频的 m3u8 文件

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    :param definition: 分辨率，默认值 4，如果传入 0，则获取所有 .m3u8 的链接。<br />&nbsp;&nbsp;3 - HD<br />&nbsp;&nbsp;4 - UD
    """
    global web_cookies
    user_agent = (request.get_first_header(b"User-agent") or b"").decode("utf-8")
    if not pickcode:
        pickcode = await call_wrap(fs.get_pickcode, (path or path2) if id < 0 else id)
    url = f"http://115.com/api/video/m3u8/{pickcode}.m3u8?definition={definition}"
    async with web_login_lock:
        if not web_cookies:
            if device == "web":
                web_cookies = client.cookies
            else:
                web_cookies = (await client.login_another_app("web", async_=True)).cookies
    while True:
        try:
            data = await client.request(
                url, 
                headers={"User-Agent": user_agent, "Cookie": web_cookies}, 
                parse=False, 
                async_=True, 
            )
            break
        except HTTPStatusError as e:
            if e.response.status_code not in (403, 405):
                raise
            async with web_login_lock:
                web_cookies = (await client.login_another_app("web", replace=device=="web", async_=True)).cookies
    if not data:
        raise FileNotFoundError("404: .m3u8 of this file was not found")
    if definition == 0:
        return Response(
            200, 
            content=Content(b"application/x-mpegurl", data), 
        )
    url = data.split()[-1].decode("ascii")
    data = await client.request(
        url, 
        headers={"User-Agent": user_agent}, 
        parse=False, 
        async_=True, 
    )
    return redirect(url)


@docs(responses={
    200: "返回对应视频文件的字幕信息", 
    404: "文件或目录不存在", 
    500: "服务器错误"
})
@route("/api/subtitle", methods=["GET", "HEAD"])
@route("/api/subtitle/{path:path2}", methods=["GET", "HEAD"])
@redirect_exception_response
async def file_subtitle(
    request: Request, 
    pickcode: str = "", 
    id: int = -1, 
    path: str = "", 
    path2: str = "", 
):
    """获取音视频的字幕信息

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件或目录的 id，优先级高于 path
    :param path: 文件或目录的路径，优先级高于 path2
    :param path2: 文件或目录的路径，这个直接在接口路径之后，不在查询字符串中
    """
    global web_cookies
    user_agent = (request.get_first_header(b"User-agent") or b"").decode("utf-8")
    if not pickcode:
        pickcode = await call_wrap(fs.get_pickcode, (path or path2) if id < 0 else id)
    resp = await call_wrap(client.fs_files_video_subtitle, pickcode)
    return resp


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload, proxy_headers=True, forwarded_allow_ips="*")

