#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__doc__ = """\t\t🚀 115 直链服务简单且极速版 🍳

链接格式（每个参数都是\x1b[1;31m可选的\x1b[0m）：\x1b[4m\x1b[34mhttp://localhost{\x1b[1m\x1b[32mpath2\x1b[0m\x1b[4m\x1b[34m}?pickcode={\x1b[1m\x1b[32mpickcode\x1b[0m\x1b[4m\x1b[34m}&id={\x1b[1m\x1b[32mid\x1b[0m\x1b[4m\x1b[34m}&sha1={\x1b[1m\x1b[32msha1\x1b[0m\x1b[4m\x1b[34m}&path={\x1b[1m\x1b[32mpath\x1b[0m\x1b[4m\x1b[34m}\x1b[0m

- \x1b[1m\x1b[32mpickcode\x1b[0m: 文件的 \x1b[1m\x1b[32mpickcode\x1b[0m，优先级高于 \x1b[1m\x1b[32mid\x1b[0m
- \x1b[1m\x1b[32mid\x1b[0m: 文件的 \x1b[1m\x1b[32mid\x1b[0m，优先级高于 \x1b[1m\x1b[32msha1\x1b[0m
- \x1b[1m\x1b[32msha1\x1b[0m: 文件的 \x1b[1m\x1b[32msha1\x1b[0m，优先级高于 \x1b[1m\x1b[32mpath\x1b[0m
- \x1b[1m\x1b[32mpath\x1b[0m: 文件的路径，优先级高于 \x1b[1m\x1b[32mpath2\x1b[0m
- \x1b[1m\x1b[32mpath2\x1b[0m: 文件的路径，这个直接在接口路径之后，不在查询字符串中

🌍 支持如下环境变量 🛸

- \x1b[1m\x1b[32mcookies\x1b[0m: 115 登录 cookies，优先级高于 \x1b[1m\x1b[32mcookies_path\x1b[0m
- \x1b[1m\x1b[32mcookies_path\x1b[0m: 存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 \x1b[4m\x1b[34m115-cookies.txt\x1b[0m 文件中获取，此文件可以在如下路径之一
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录 下
- \x1b[1m\x1b[32mpath_persistence_commitment\x1b[0m: （\x1b[1;31m传入任何值都视为设置，包括空字符串\x1b[0m）路径持久性承诺，只要你能保证文件不会被移动（\x1b[1;31m可新增删除，但对应的路径不可被其他文件复用\x1b[0m），打开此选项，用路径请求直链时，可节约一半时间
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

cookies = environ.get("cookies", "")
cookies_path = environ.get("cookies_path", "")
path_persistence_commitment = environ.get("path_persistence_commitment") is not None

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
                if cookies := open(joinpath(cookies_dir, "115-cookies.txt")).read():
                    break
            except FileNotFoundError:
                pass
if not cookies:
    raise SystemExit("未能获得 cookies")


from collections.abc import Iterator
try:
    from collections.abc import Buffer # type: ignore
except ImportError:
    Buffer = bytes | bytearray | memoryview
from base64 import b64decode, b64encode
from posixpath import split as splitpath
from typing import cast, Final

try:
    from blacksheep import Application, Request, route, redirect, text
    from blacksheep.client.session import ClientSession
    from blacksheep.contents import FormContent
    from cachetools import LRUCache, TTLCache
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    from orjson import loads
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "blacksheep", "cachetools", "orjson", "pycryptodome"], check=True)
    from blacksheep import Application, Request, route, redirect, text
    from blacksheep.client.session import ClientSession
    from blacksheep.contents import FormContent
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

PATH_TO_ID: LRUCache[str, str] = LRUCache(65536)
ID_TO_PICKCODE: LRUCache[str, str] = LRUCache(65536)
SHA1_TO_PICKCODE: LRUCache[str, str] = LRUCache(65536)
URL_CACHE: TTLCache[tuple[str, str], str] = TTLCache(64, ttl=1)
PICKCODE_OF_IMAGE: set[str] = set()

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


@app.lifespan
async def register_http_client():
    async with ClientSession() as client:
        app.services.register(ClientSession, instance=client)
        yield


def process_info(info: dict, dir: None | str = None) -> str:
    fid = cast(str, info["fid"])
    fn = cast(str, info["n"])
    pickcode = SHA1_TO_PICKCODE[info["sha"]] = ID_TO_PICKCODE[fid] = info["pc"]
    if info.get("class") == "PIC" or info.get("u"):
        PICKCODE_OF_IMAGE.add(pickcode)
    if dir:
        PATH_TO_ID[dir + "/" + fn] = fid
    elif dir is not None:
        PATH_TO_ID[fn] = fid
    return pickcode


async def get_pickcode_by_id(client: ClientSession, id: str) -> str:
    if pickcode := ID_TO_PICKCODE.get(id):
        return pickcode
    resp = await client.get(
        "https://webapi.115.com/files/get_info", 
        params={"file_id": id}, 
        headers={"Cookie": cookies}, 
    )
    json = loads((await resp.read()) or b"")
    if not json["state"]:
        raise FileNotFoundError
    info = json["data"][0]
    if "fid" not in info:
        raise FileNotFoundError
    return process_info(info)


async def get_pickcode_by_sha1(client: ClientSession, sha1: str) -> str:
    if len(sha1) != 40:
        raise FileNotFoundError
    if pickcode := SHA1_TO_PICKCODE.get(sha1):
        return pickcode
    resp = await client.get(
        "https://webapi.115.com/files/search", 
        params={"search_value": sha1, "limit": 1, "show_dir": 0}, 
        headers={"Cookie": cookies}, 
    )
    json = loads((await resp.read()) or b"")
    if not json["state"] or not json["count"]:
        raise FileNotFoundError
    info = json["data"][0]
    if "fid" not in info:
        raise FileNotFoundError
    return process_info(info)


async def get_pickcode_by_path(client: ClientSession, path: str) -> str:
    path = path.strip("/")
    dir_, name = splitpath(path)
    if not name:
        raise FileNotFoundError
    if fid := PATH_TO_ID.get(path):
        if path_persistence_commitment and (pickcode := ID_TO_PICKCODE.get(fid)):
            return pickcode
        resp = await client.get(
            "https://webapi.115.com/files/file", 
            params={"file_id": fid}, 
            headers={"Cookie": cookies}, 
        )
        json = loads((await resp.read()) or b"")
        if json["state"]:
            info = json["data"][0]
            if info["file_name"] == name:
                return info["pick_code"]
        PATH_TO_ID.pop(path, None)
    if dir_:
        resp = await client.get(
            "https://webapi.115.com/files/getid", 
            params={"path": dir_}, 
            headers={"Cookie": cookies}, 
        )
        json = loads((await resp.read()) or b"")
        if not (pid := json["id"]):
            raise FileNotFoundError
    else:
        pid = 0
    params = {"count_folders": 0, "record_open_time": 0, "show_dir": 1, "cid": pid, "limit": 1000, "offset": 0}
    while True:
        resp = await client.get(
            "https://webapi.115.com/files", 
            params=params, 
            headers={"Cookie": cookies}, 
        )
        json = loads((await resp.read()) or b"")
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
        params["offset"] += 1000
    raise FileNotFoundError


async def get_image_url(client: ClientSession, pickcode: str) -> str:
    resp = await client.get(
        "https://webapi.115.com/files/image", 
        params={"pickcode": pickcode}, 
        headers={"Cookie": cookies}, 
    )
    json = loads((await resp.read()) or b"")
    return json["data"]["origin_url"]


@route("/", methods=["GET", "HEAD"])
@route("/{path:path}", methods=["GET", "HEAD"])
async def get_download_url(
    request: Request, 
    client: ClientSession, 
    pickcode: str = "", 
    id: str = "", 
    sha1: str = "", 
    path: str = "", 
    path2: str = "", 
):
    """获取文件的下载链接

    :param pickcode: 文件或目录的 pickcode，优先级高于 id
    :param id: 文件的 id，优先级高于 sha1
    :param sha1: 文件的 sha1，优先级高于 path
    :param path: 文件的路径，优先级高于 path2
    :param path2: 文件的路径，这个直接在接口路径之后，不在查询字符串中
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
        url = URL_CACHE.get((pickcode, user_agent))
        if url:
            return redirect(url)
        if pickcode in PICKCODE_OF_IMAGE:
            return redirect(await get_image_url(client, pickcode))
        resp = await client.post(
            "https://proapi.115.com/app/chrome/downurl", 
            content=FormContent({"data": rsa_encode(b'{"pickcode":"%s"}' % bytes(pickcode, "ascii")).decode("ascii")}), 
            headers={"Cookie": cookies, "User-Agent": user_agent}, 
        )
        json = loads((await resp.read()) or b"")
        if not json["state"]:
            raise FileNotFoundError
        data = loads(rsa_decode(json["data"]))
        item = next(info for info in data.values())
        ID_TO_PICKCODE[next(iter(data))] = item["pick_code"]
        # TODO: 还需要继续增加，目前不确定 115 到底支持哪些图片格式
        if item["file_name"].lower().endswith((".jpg", ".jpeg", ".png", ".svg", ".bmp", ".tiff", ".webp")):
            PICKCODE_OF_IMAGE.add(item["pick_code"])
        url = URL_CACHE[(pickcode, user_agent)] = item["url"]["url"]
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
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload, proxy_headers=True, forwarded_allow_ips="*")

