#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 8)
__requirements__ = ["blacksheep", "cachetools", "orjson", "pycryptodome"]
__doc__ = """\
        \x1b[5m🚀\x1b[0m 115 直链服务简单且极速版 \x1b[5m🍳\x1b[0m

链接格式（每个参数都是\x1b[1;31m可选的\x1b[0m）：\x1b[4m\x1b[34mhttp://localhost{\x1b[1;32mpath2\x1b[0m\x1b[4m\x1b[34m}?pickcode={\x1b[1;32mpickcode\x1b[0m\x1b[4m\x1b[34m}&id={\x1b[1;32mid\x1b[0m\x1b[4m\x1b[34m}&sha1={\x1b[1;32msha1\x1b[0m\x1b[4m\x1b[34m}&path={\x1b[1;32mpath\x1b[0m\x1b[4m\x1b[34m}\x1b[0m

- \x1b[1;32mpickcode\x1b[0m: 文件的 \x1b[1;32mpickcode\x1b[0m，优先级高于 \x1b[1;32mid\x1b[0m
- \x1b[1;32mid\x1b[0m: 文件的 \x1b[1;32mid\x1b[0m，优先级高于 \x1b[1;32msha1\x1b[0m
- \x1b[1;32msha1\x1b[0m: 文件的 \x1b[1;32msha1\x1b[0m，优先级高于 \x1b[1;32mpath\x1b[0m
- \x1b[1;32mpath\x1b[0m: 文件的路径，优先级高于 \x1b[1;32mpath2\x1b[0m
- \x1b[1;32mpath2\x1b[0m: 文件的路径，这个直接在接口路径之后，不在查询字符串中

        \x1b[5m🌍\x1b[0m 环境变量 \x1b[5m🛸\x1b[0m

- \x1b[1;32mcookies\x1b[0m: 115 登录 cookies，优先级高于 \x1b[1;32mcookies_path\x1b[0m
- \x1b[1;32mcookies_path\x1b[0m: 存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 \x1b[4m\x1b[34m115-cookies.txt\x1b[0m 文件中获取，此文件可以在如下路径之一
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录 下
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
"""

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, 
        description=__doc__, 
    )
    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
    parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值：80")
    parser.add_argument("-r", "--reload", action="store_true", help="此项目所在目录下的文件发生变动时重启，此选项仅用于调试")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

from os import environ

print(__doc__)

from os.path import dirname, expanduser, join as joinpath, realpath

cookies = environ.get("cookies", "").strip()
device = ""
cookies_path = environ.get("cookies_path", "")
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
            cookies = open(cookies_path).read()
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
                if cookies := open(joinpath(cookies_dir, "115-cookies.txt")).read().strip():
                    cookies_path = joinpath(cookies_dir, "115-cookies.txt")
                    break
            except FileNotFoundError:
                pass
if not cookies:
    raise SystemExit("未能获得 cookies")


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
from functools import update_wrapper
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
    from blacksheep.messages import Request, Response
    from cachetools import LRUCache, TTLCache
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    from orjson import loads
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
    from blacksheep.messages import Request, Response
    from cachetools import LRUCache, TTLCache
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    from orjson import loads


G_kts: Final = bytes((
    0xf0, 0xe5, 0x69, 0xae, 0xbf, 0xdc, 0xbf, 0x8a, 0x1a, 0x45, 0xe8, 0xbe, 0x7d, 0xa6, 0x73, 0xb8, 
    0xde, 0x8f, 0xe7, 0xc4, 0x45, 0xda, 0x86, 0xc4, 0x9b, 0x64, 0x8b, 0x14, 0x6a, 0xb4, 0xf1, 0xaa, 
    0x38, 0x01, 0x35, 0x9e, 0x26, 0x69, 0x2c, 0x86, 0x00, 0x6b, 0x4f, 0xa5, 0x36, 0x34, 0x62, 0xa6, 
    0x2a, 0x96, 0x68, 0x18, 0xf2, 0x4a, 0xfd, 0xbd, 0x6b, 0x97, 0x8f, 0x4d, 0x8f, 0x89, 0x13, 0xb7, 
    0x6c, 0x8e, 0x93, 0xed, 0x0e, 0x0d, 0x48, 0x3e, 0xd7, 0x2f, 0x88, 0xd8, 0xfe, 0xfe, 0x7e, 0x86, 
    0x50, 0x95, 0x4f, 0xd1, 0xeb, 0x83, 0x26, 0x34, 0xdb, 0x66, 0x7b, 0x9c, 0x7e, 0x9d, 0x7a, 0x81, 
    0x32, 0xea, 0xb6, 0x33, 0xde, 0x3a, 0xa9, 0x59, 0x34, 0x66, 0x3b, 0xaa, 0xba, 0x81, 0x60, 0x48, 
    0xb9, 0xd5, 0x81, 0x9c, 0xf8, 0x6c, 0x84, 0x77, 0xff, 0x54, 0x78, 0x26, 0x5f, 0xbe, 0xe8, 0x1e, 
    0x36, 0x9f, 0x34, 0x80, 0x5c, 0x45, 0x2c, 0x9b, 0x76, 0xd5, 0x1b, 0x8f, 0xcc, 0xc3, 0xb8, 0xf5, 
))
RSA_encrypt: Final = PKCS1_v1_5.new(RSA.construct((
    0x8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683, 
    0x10001, 
))).encrypt

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


to_bytes = int.to_bytes
from_bytes = int.from_bytes


def bytes_xor(v1: Buffer, v2: Buffer, /, size: int = 0) -> Buffer:
    if size:
        v1 = v1[:size]
        v2 = v2[:size]
    else:
        size = len(v1)
    return to_bytes(from_bytes(v1) ^ from_bytes(v2), size)


def acc_step(
    start: int, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int, int]]:
    if stop is None:
        start, stop = 0, start
    for i in range(start + step, stop, step):
        yield start, (start := i), step
    if start != stop:
        yield start, stop, stop - start


def xor(src: Buffer, key: Buffer, /) -> bytearray:
    src = memoryview(src)
    key = memoryview(key)
    secret = bytearray()
    if i := len(src) & 0b11:
        secret += bytes_xor(src, key, i)
    for i, j, s in acc_step(i, len(src), len(key)):
        secret += bytes_xor(src[i:j], key[:s])
    return secret


def gen_key(
    rand_key: Buffer, 
    sk_len: int = 4, 
    /, 
) -> bytearray:
    xor_key = bytearray()
    if rand_key and sk_len > 0:
        length = sk_len * (sk_len - 1)
        index = 0
        for i in range(sk_len):
            x = (rand_key[i] + G_kts[index]) & 0xff
            xor_key.append(G_kts[length] ^ x)
            length -= sk_len
            index += sk_len
    return xor_key


def rsa_encode(data: Buffer, /) -> bytes:
    xor_text: Buffer = bytearray(16)
    tmp = memoryview(xor(data, b"\x8d\xa5\xa5\x8d"))[::-1]
    xor_text += xor(tmp, b"x\x06\xadL3\x86]\x18L\x01?F")
    cipher_data = bytearray()
    xor_text = memoryview(xor_text)
    for l, r, _ in acc_step(0, len(xor_text), 117):
        cipher_data += RSA_encrypt(xor_text[l:r])
    return b64encode(cipher_data)


def rsa_decode(cipher_data: Buffer, /) -> bytearray:
    rsa_e = 65537
    rsa_n = 94467199538421168685115018334776065898663751652520808966691769684389754194866868839785962914624862265689699980316658987338198288176273874160782292722912223482699621202960645813656296092078123617049558650961406540632832570073725203873545017737008711614000139573916153236215559489283800593547775766023112169091
    cipher_data = memoryview(b64decode(cipher_data))
    data = bytearray()
    for l, r, _ in acc_step(0, len(cipher_data), 128):
        p = pow(from_bytes(cipher_data[l:r]), rsa_e, rsa_n)
        b = to_bytes(p, (p.bit_length() + 0b111) >> 3)
        data += memoryview(b)[b.index(0)+1:]
    m = memoryview(data)
    key_l = gen_key(m[:16], 12)
    tmp = memoryview(xor(m[16:], key_l))[::-1]
    return xor(tmp, b"\x8d\xa5\xa5\x8d")


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


class AuthenticationError(OSError):
    pass


def check_response(resp: dict, /) -> dict:
    """检测 115 的某个接口的响应，如果成功则直接返回，否则根据具体情况抛出一个异常
    """
    if resp.get("state", True):
        return resp
    if "errno" in resp:
        match resp["errno"]:
            # {"state": false, "errno": 99, "error": "请重新登录", "request": "/app/uploadinfo", "data": []}
            case 99:
                raise AuthenticationError(resp)
            # {"state": false, "errno": 911, "errcode": 911, "error_msg": "请验证账号"}
            case 911:
                raise AuthenticationError(resp)
            # {"state": false, "errno": 20004, "error": "该目录名称已存在。", "errtype": "war"}
            case 20004:
                raise FileExistsError(errno.EEXIST, resp)
            # {"state": false, "errno": 20009, "error": "父目录不存在。", "errtype": "war"}
            case 20009:
                raise FileNotFoundError(errno.ENOENT, resp)
            # {"state": false, "errno": 91002, "error": "不能将文件复制到自身或其子目录下。", "errtype": "war"}
            case 91002:
                raise OSError(errno.ENOTSUP, resp)
            # {"state": false, "errno": 91004, "error": "操作的文件(夹)数量超过5万个", "errtype": "war"}
            case 91004:
                raise OSError(errno.ENOTSUP, resp)
            # {"state": false, "errno": 91005, "error": "空间不足，复制失败。", "errtype": "war"}
            case 91005:
                raise OSError(errno.ENOSPC, resp)
            # {"state": false, "errno": 90008, "error": "文件（夹）不存在或已经删除。", "errtype": "war"}
            case 90008:
                raise FileNotFoundError(errno.ENOENT, resp)
            # {"state": false,  "errno": 231011, "error": "文件已删除，请勿重复操作","errtype": "war"}
            case 231011:
                raise FileNotFoundError(errno.ENOENT, resp)
            # {"state": false, "errno": 990009, "error": "删除[...]操作尚未执行完成，请稍后再试！", "errtype": "war"}
            # {"state": false, "errno": 990009, "error": "还原[...]操作尚未执行完成，请稍后再试！", "errtype": "war"}
            # {"state": false, "errno": 990009, "error": "复制[...]操作尚未执行完成，请稍后再试！", "errtype": "war"}
            # {"state": false, "errno": 990009, "error": "移动[...]操作尚未执行完成，请稍后再试！", "errtype": "war"}
            case 990009:
                raise OSError(errno.EBUSY, resp)
            # {"state": false, "errno": 990023, "error": "操作的文件(夹)数量超过5万个", "errtype": ""}
            case 990023:
                raise OSError(errno.ENOTSUP, resp)
            # {"state": 0, "errno": 40100000, "code": 40100000, "data": {}, "message": "参数错误！", "error": "参数错误！"}
            case 40100000:
                raise OSError(errno.EINVAL, resp)
            # {"state": 0, "errno": 40101032, "code": 40101032, "data": {}, "message": "请重新登录", "error": "请重新登录"}
            case 40101032:
                raise AuthenticationError(resp)
    elif "errNo" in resp:
        match resp["errNo"]:
            case 990001:
                raise AuthenticationError(resp)
    elif "code" in resp:
        match resp["code"]:
            # {'state': False, 'code': 20018, 'message': '文件不存在或已删除。'}
            # {'state': False, 'code': 800001, 'message': '目录不存在。'}
            case 20018 | 800001:
                raise FileNotFoundError(errno.ENOENT, resp)
            # {'state': False, 'code': 990002, 'message': '参数错误。'}
            case 990002:
                raise OSError(errno.EINVAL, resp)
            case _:
                raise OSError(errno.EIO, resp)
    raise OSError(errno.EIO, resp)


def redirect_exception_response(func, /):
    async def wrapper(*args, **kwds):
        try:
            return await func(*args, **kwds)
        except HTTPException as e:
            return text(
                f"{type(e).__module__}.{type(e).__qualname__}: {e}", 
                e.status, 
            )
        except AuthenticationError as e:
            return text(str(e), 401)
        except PermissionError as e:
            return text(str(e), 403)
        except FileNotFoundError as e:
            return text(str(e), 404)
        except (IsADirectoryError, NotADirectoryError) as e:
            return text(str(e), 406)
        except OSError as e:
            return text(str(e), 500)
        except Exception as e:
            return text(str(e), 503)
    return update_wrapper(wrapper, func)


async def do_request(
    client: ClientSession, 
    url: str | bytes | blacksheep.url.URL, 
    method: str = "GET", 
    content: None | blacksheep.contents.Content = None, 
    headers: None | dict[str, str] = None, 
    params: None | dict[str, str] = None, 
) -> Response:
    current_cookies = cookies
    if headers is None:
        headers = {"Cookie": cookies}
    else:
        headers["Cookie"] = cookies
    request = Request(method.upper(), client.get_url(url, params), normalize_headers(headers))
    response = await client.send(request.with_content(content) if content else request)
    if response.status == 405:
        async with cookies_lock:
            if current_cookies == cookies:
                await relogin(client)
        headers["Cookies"] = cookies
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
    resp = await do_request(client, url, method, content=content, headers=headers, params=params)
    json = loads((await resp.read()) or b"")
    return check_response(json)


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


async def login_qrcode_result(client: ClientSession, uid: str, app: str = "web") -> dict:
    """把扫码结果绑定到设备
    """
    app = get_enum_name(app, AppEnum)
    url = "https://passportapi.115.com/app/1.0/%s/1.0/login/qrcode/" % app
    return await request_json(client, url, "POST", content=FormContent({"account": uid}))


async def relogin(client: ClientSession) -> dict:
    """自动扫二维码重新登录
    """
    global cookies, device
    if not device:
        device = await login_device(client)
    logger.warning(f"\x1b[1m\x1b[33m[SCAN] 🦾 重新扫码: {device!r} 🦿\x1b[0m")
    uid = (await login_qrcode_token(client))["data"]["uid"]
    await login_qrcode_scan(client, uid)
    await login_qrcode_scan_confirm(client, uid)
    resp = await login_qrcode_result(client, uid, device)
    cookies = "; ".join("%s=%s" % e for e in resp["data"]["cookie"].items())
    if cookies_path:
        open(cookies_path, "w").write(cookies)
    return resp


def process_info(info: dict, dir: None | str = None) -> str:
    fid = cast(str, info["fid"])
    fn = cast(str, info["n"])
    pickcode = SHA1_TO_PICKCODE[info["sha"]] = ID_TO_PICKCODE[fid] = info["pc"]
    if cdn_image and ((thumb := info.get("u", "")) or info.get("class") == "PIC"):
        IMAGE_URL_CACHE[pickcode] = bytes(reduce_image_url_layers(thumb), "utf-8")
    if dir:
        PATH_TO_ID[dir + "/" + fn] = fid
    elif dir is not None:
        PATH_TO_ID[fn] = fid
    return pickcode


@app.lifespan
async def register_http_client():
    async with ClientSession(follow_redirects=False) as client:
        app.services.register(ClientSession, instance=client)
        yield


async def get_dir_patht_by_id(client: ClientSession, id: str) -> list[tuple[str, str]]:
    json = await request_json(
        client, 
        "https://webapi.115.com/files", 
        params={
            "count_folders": "0", "record_open_time": "0", "show_dir": "1", 
            "cid": id, "limit": "1", "offset": "0", 
        }, 
    )
    return [(info["cid"], info["name"]) for info in json["path"][1:]]


async def get_pickcode_by_id(client: ClientSession, id: str) -> str:
    if pickcode := ID_TO_PICKCODE.get(id):
        return pickcode
    json = await request_json(
        client, 
        "https://webapi.115.com/files/get_info", 
        params={"file_id": id}, 
    )
    info = json["data"][0]
    if "fid" not in info:
        raise FileNotFoundError(id)
    return process_info(info)


async def get_pickcode_by_sha1(client: ClientSession, sha1: str) -> str:
    if len(sha1) != 40:
        raise FileNotFoundError(sha1)
    if pickcode := SHA1_TO_PICKCODE.get(sha1):
        return pickcode
    json = await request_json(
        client, 
        "https://webapi.115.com/files/search", 
        params={"search_value": sha1, "limit": "1", "show_dir": "0"}, 
    )
    if not json["count"]:
        raise FileNotFoundError(sha1)
    return process_info(json["data"][0])


async def get_pickcode_by_path(
    client: ClientSession, 
    path: str, 
    disable_pc: bool = False, 
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
    params = {"count_folders": 0, "record_open_time": 0, "show_dir": 1, "cid": pid, "limit": 5000, "offset": 0}
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


async def warmup_cdn_image(client: ClientSession, id: str = "0", cache: None | dict[str, str] = None) -> int:
    api = "https://proapi.115.com/android/files/imglist"
    payload: dict = {"cid": id, "limit": 5000, "offset": 0, "o": "user_ptime", "asc": 1, "cur": 0}
    count = 0
    while True:
        resp = await request_json(client, api, params=payload)
        for item in resp["data"]:
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
        payload["offset"] += 5000
    return count


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


async def configure_background_tasks(app: Application):
    client = app.services.resolve(ClientSession)
    create_task(periodically_warmup_cdn_image(client, cdn_image_warmup_ids))

if cdn_image and cdn_image_warmup_ids:
    app.on_start += configure_background_tasks


async def get_image_url(client: ClientSession, pickcode: str) -> bytes:
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
        if cdn_image and item["file_name"].lower().endswith((".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".raw", ".svg", ".tif", ".tiff", ".webp")):
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
    uvicorn.run(
        app=app, 
        host=args.host, 
        port=args.port, 
        reload=args.reload, 
        proxy_headers=True, 
        forwarded_allow_ips="*", 
    )

