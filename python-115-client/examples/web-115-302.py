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
        return send_file(BytesIO(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00@\x00\x00\x00@\x08\x06\x00\x00\x00\xaaiq\xde\x00\x00\x0f\xaeIDATx\x9c\xec[]\x8c\\\xd5}\xff\x9dsg\xee\xcc\xac\xf7\x13\x83\xbdn1&\xae\xbfI\\acG\x80\x04\t\xf8\xa9j\x1fP\xcc\x03nU\xd3\xaa\x15\x95\xec\xf2P$V}\x82D a\xa1J\xa8\xadTJBE)V\xa2\xb84ji\x93\x96\xd2\xa8\xae"\x82Ul\x87\xe0\x96\xf5bg\x83\xd7\x8e\xbd\xf6b\xb3\xbb3;s\xe7\xde{\xfe\xd5\xf9\xb8\xf7\x9e\xfb5\xbb\xeb&\xb2\x148\xab\xa39s\xe6\xdes\xcf\xef\xf7\xff<\xe7\x9e\xe5\xf8\x94\x97\xcf\x08\xb8\xd1\x13\xb8\xd1\xe53\x02\xb2\x1d}}}p\x1c\xe7\xc6\xcc\xe6\x17\\\xfa\xfb\xfbs}9\x02\xb6n\xddZxaAa\x00$SU\x005\x00u\x00\x8dL\xed\xfb9\xd5\xec\xb8u\xf3\xcc\xaa\x99\x03[\xca\x84w\xee\xdc\x99\xeb\xab\x94]|\xe8\xd0!\xec\xd8\xb1#\xfe\xdel6\xf1\xcc3\xcf\xe0\xf8\xf1\xe3\xf2\x9e\xba\xeb\xba\xb7\xdd|\xf3\xcdw\x0f\r\ro\xab\xd5\xdc\xd5\x95Je\xd0q*.c\xac\x02\x06\xc6\xe4\x9c\xf4\'S\x13L\xda\xc8O\x98@\xe6C\xb5\xe4\'\x91\xec\xa2\xb8\x98~!D\x18\x86a7\x08\x82\xf9n\xd7\xbb2?\xdf\x1c\xbfz\xed\xea;^\xa7s\x06@{\xcb\x96-\xc1\xd3O?\x8d\x95+W\xc6\xa3OLL\xe0\xc0\x81\x03\x858K\t\x90\xe0\xf7\xec\xd9\xa3\xda\'O\x9e\xc4\xc1\x83\x07\xf9\xe9\xd3\xa7\x07FGG\xf7\xae[w\xfbc\x83\x83\x83\xbb\x82 @\x18\x86`\nZR\x11\xb5%\xd2\xccwD}\xc8R\x105\x14z\xd3\xd4m\xb2\xfaS\x15\x84\xd15\x80\xc3\x1d)\xa0SSS\xe7\xfez||\xfc\xf0\x13O<1\xf7\xea\xab\xaf\x86\x0f<\xf0\x80\x1agdd\xa4\x0c\xe6\xe2N\xf0\xf0\xe1\xc3\xd8\xbd{w\xf5\xfc\xf9\xf3_\xbc\xe7\xde{\xdf\xd9\xb4y\xf37*\x95\xca\xaev\xbb\rI@Qa\x91\x88\x15\xf8\xb4\xb8c\xf0,\xfa\xdd\\\xc3\n\xae\x89\xc6({\x88T\nA\xf0}\x1f\xae\xeb~~\xc3\x86\x8d\x7f\xb1{\xf7\x17O\xce\xcd\xcd\xed\xd9\xb3g\x8f\xfb\xfc\xf3\xcf/\x06\xaf7\x01\'N\x9c\xc0\xa3\x8f>Zm4\x1a_\xbak\xd7\xae\x7f!A[\x02?(\xb78\xd3Ov\x1f\xe5\x7fO\xac"\xeaJ\xbe#E\x90Ef\x8f\xe7E\x17\t!\xe0T\x9cu_\xf8\xc2\xf6\xef\x0c\r\r?466V{\xf3\xcd7\xaf\x8f\x00i\xf3\xfb\xf6\xed\xe3\xae\xeb\xdeu\xe7\x8e\x1d\xdf\xf6:\xdeH!({2d\xe1+\xd0\x02\x96\x82\x9bhA\x0c\xd0nk\xb7Q\xfc\x9c\x94\x86\xe4\t\x11$\x1a[\xb6ny\xa5\xbf\xbf\xff\xc1\xfd\xfb\xf7;\xd3\xd3\xd3\xcb\'\xe0\xd9g\x9f\x85\xb4\xf9\xed\xdb\x7f\xfdo\xbc\x8e7\\:BT,R\x8c\t[]L\xb5\xd5w\xc6R\xfd\xa9Vd\xef\xd9v\xf69D\x88\x07$\xbb?\xa9$\xa8\xbei\xd3\xe6oLOO\xaf\x1c\x1b\x1b+U\xa2R\x02\xde}\xf7\xdd\xca\xaaU\xab\xf6r\xce\xb7,\n\xbeD)" 1#\xbd\xaf,\xbc\x97\n\xee\xca\x8dP2d\xa5RY\xb3z\xf5\xea?<u\xeaT\xa9\xb3\xef\xe5\x03\xea\xb7\xde\xba\xf61\xe9\xe8(\tT\xa5\x93a9\x81PF\x07zO\xb6\x10 KH`\x05\xcfZ\xac\xc8H1::\xfa\x07&\x97(,e\x04\xb0j\xb5z[\x7f\x7f\xff.\xb2$Hq\x88\xa2\xd2v,q\xcah\xaa\xe9\x8f\xda\xa9\xd0\x06K\xda\x94\xd0\x1d+\x8e\ty\xba\x9fba\xe4{\xcd\x1f%m\xd7\xad\xdd\xde\xd7\xd7\xb7\xb3\x0ck\xaeSJ\xbc\xddn\xf3\x91\x91\x9b\xee\xeev\xbb\x16\x9d(h\xb3\xb8\x92\xfa\xe4q\x9b\xa2\xdf"^blT\x12\xd3-\x82\xed\xeb`\xdf\x9bp\x8c\xd4u(\xf5\t22\x0c\x0e\x0e\xde-\'w\xf5\xea\xd5\x1c\x019\xdb\x98\x9c\x9cD\xb7\xdb\xe5\x03\x03\xfd\xdb\xfc\xc0\x07c\xdc\x1a\x91\xe5+\x99DG\x82\xa6\xc8\x93s#8f\xe9\xabn\xdbR\x8d\xdd\xa1\xa5\xd3dI<\xd6\x08\x9b\xb4\x9c\xf4\xb3\x98\xf3\xce\xb3\xdehl\x95)\xf3\xe9\xd3\xa7s\x89K\x8e\x80\xb9\xb99\xa5\x19\x95JuU\x94\x9f\xeaI\xf2\\\xe0M\xdbfDB\xd4\xc3U\xb4"s\x11\ta\xdd\xaf\xa7\xaa\x13\x1e*\x8c\xf3&\xf5MkH\xccGZK\xe2\xec\xd1\xea\xb7\xcd\xa0Z\xa9\xae\x96\x13Jit\x19\x01\x11B\xce\xf9\x00`K\xa5\xe0"3\xfd(^S\xa4\t\x99\x8c(\x96\x1c\tx\xf5\x114Gn\x87\xe3/`\xe0\xeaY8a\xd7d\x82\xe9| \x89\x00\x94\xf2!\x89i\xd8\xfe$\xed\x1bRs&\x80;\nKa(\xecA\x00\xabE99K\xe5\xb3\xcc\xc2\x16\x99\x82\xd1\x0e\xe2)s\x88!\x90P\x13\xfd\xe9\xa6\x871\xb5}\x1f\xd0\xa8\x03.\x83\x13\xcec\xf4\x837p\xeb\x8f\x8e\xc0\xed\xcc\x81G\xeb\x86\x88\x84H\x0b\x90\x95\xaa\xa5\x059\xff\x90hC\xd4f`\xb52\x02z\x85A\x07\xb6oI\t\x80%UI\x9c\xc7U\xc8J\xa6M\x0cB\x10\xa4\xf6\x7f<\xbc\x15S\x1b\xf7\x02\xbc\x1a\xfb\x8e\xb06\x88\x0bw\xed\xc3\x7f\xff\xde\xdf\xe1\xdc\x9d\x0f\xc1\x0f\x05B\xb3\xc0\x92U\x84Bfu\xca|D\x04H$\x8e\xb2\x08l\x916h\xc9,\x93\x00"T\xc9\xf6\xb0V6\x97x|\x0e\x90\x03\x92\x80\xe5\'d\xad\xa8OE\x02q\x84\x82!\x0c\t\x97V\xdfk\xae7\x8e3\x1e\x8cA\xd4\x06\xf0\xd1\x83\x07q\xf2\xf7_\xc4\xf4\xc6{\x10(\x02\x82\x84\x04\xa1IH\xa2\x86\xc8\xad\n\x133\xcbk\x03\xf5H\x1aJ\xf3\x00\x89,\xf1\xb4\\;7\xd2\x80UU@uUmV\x95\xee&\xee\x93\x04(\r\x90\x92\x16\x84\xe6\xc0\xe7\xd2\xab%a\xaaED{t\x13>|\xe4Y\xfc\xcf\xef>\x87\xe6\xd0\xeaX\x13B\xa1I\x101\t\xc8\x81\x8f\xc6-\xd2\x04R\x8c/\x8f\x009\x08K\x07afm\x02I\xa9W\xd4\x86\x0c\xd9\x95*\xba*\x12\xaa\x10\xe4(\xf5\x97Z\xe0W\x07\xf3\xf1:U\r\xb9p0\xb7\xf9n\xfc\xf8\xc9\xd70\xf9\x9b\x7f\x04\xcf\xa9&f!\x84\xaa)\x93\xc8\x98C:\x97\xb0\xe7\xbf|\x02\xac\xa4\xce85\xa5\xeeR\xcd]\xbd\x1bE5\xb33U\x03H\x92\xa0\xdb\x824\x19\x92\x80\x908\x02I\x18\xab\x96\x83\x17\xd9>\x07\xa840\xbd\xe7\xb7\xf1\xde3\xaf\xe3\xc2\x97\xbf\x82.\x98"BD\xfeA\x84\xc6?\xe47I\xec\xec\xf4zM\xc0\xf2\xe2,\x91\x90RwG\x81ej[\xae\x0eP\x1dD\xf5x\x9bNP\x03\x82\x06 "\x13!\xed\x14\xed\xac\xb0\x1c\xb8\xd5\'4\x11\xe1\xc0\x08.<\xf2\'\xf8\xdf\xaf\xbe\x82\xd9\xf5\xdb\x10\x84\x81\x06o|\x83$A\x08\x91\x03\x9cJ\xcf\x8bb\xb8)\xa5\xab\xa4X\xb5\x0cO\x8cE\xb6_\x03\x93Q\x85j`R\x0b\x98c"\x00\x03\x13\x9b\xe0\x0e\xeeE\xd0p\xe05\xbf\x0f\xd6\xfc\xae&\xa2(]-\x02,\x8a\x88\xd12\xf2\xd6n\xc0\x87_\xfd:\x86\x7f\xf8o\x18\xfd\xf6K\xa8_:o\x92K\x96[\x1d\xa52\xc6(qZ\xb6\x06X\x0b\r\x15\x01\x94\x8d\xbaF\xdd\xeb\xaa]\tG\xc0D\x03\x0c\r\xa5\x15\x8d\xcaCh\xd4oE\xbd\xbe\x06\xd5\x91\x07\x11\xf2Q\xa3\x01,\x97\xa3\xe7\xab\xe8\xa1\t\x86\x08^\xc5\'\xf7\xfd\x06\xc6\xff\xfc[8\xbf\xff\x00\xban=\x15.\x95Id#\xc4\xf5\x9a@\xe2\x00LzKz\x07\x9c)\x12\\\xfc\xaa\xffe\xfc\x1a\x1d\xc0\xca\xceo\x81\t\xd9_E\x85\r\x83\x13\xc0\x08p\xb8\x0b\xf0\x86\x0e\x91\xb6\xf7/R\xffl\xbbP\x13\xccw9e\xb7\x8e\x99\xbd\xfb1\xf1\x97\x87\xd1\xba\xeds1\t\xca9\x8aLn\xb0\x88\t\x94\x12 ,[BD\x80\xaa\x155\xf8\x1a\xe7~\x0cT\x7f\x05\x83\xd5\xcd\xa8\x84\xc3\x8a\x1cN\xd2\x0c\xa0*L\x92$(\xd2\x9e\x12\xf5/\xf2\x03e\xe0S\x11\x83!X\xb5\x06?\xf9\xda\x0b\x98\xdd\xb6\xdd8F\x8a5A\xc4y\xc1\xffC\x034\x83Q\xc6\xa7\x13\x1b\xe9\x04\x19\x1cT\x98\x0b\x87q8\xbcb"B\x05\x10\t\x01\xcc\xc4v\x9d1"\xaf\x01\xd9\xef\xbd\x9cbNCB \x10@7\x00\xf1*.<z\x10\xbe\xeb"\x14\xa1N\x98D\xde!.\x9b\x80x\x1f$\x8a\x06\x86y25\xf9\x8b\x16C\\\x81\x8e*\xd2\x8b\xb3\xc5}\x80\xc8\xf8\x81"\xedPIE\x00\xf8!\xe0y\xc0B\x1bh\xb5 \xe0`~\xfd\xe6$k\xcc\xe6\x04\xd7\x17\x05D\x1cO\x11gT\xda\xc9\xc8\xf1\xf4\xbaES\x10\x11\xc6\xac\x893\xe3\x9a\xed\xdc=\x07\x98\x97I8\xd3V\xc0e\x87\x94|\x00P\x17\xf0\xdb@\xa7\t\xcc\xcf\x02\xcdy\x95m\n\xa1\x07e\\\x80\x91~\x0fE\xbd\xf3\xa0^\x04 \x06\xcf2\x04\xc8\xcfh\xdbC\xaf\xfc$\xc8P?(2\x81h1g\xbcr,\xfd\xecg\xaf*\x01\t\xd2\xea.\xd5\x1e]@x\x1a\xbc\xd7\x04\xdaM`a\x1eh\xce\xa1~v\\\xd9>\x8b"\x0e\xd3&\x88\xc2-\x92%\x10\x90H_\x98!B\x10\x93 \x03\x13\x15\x84^\x0e)\xe1\x06\xaa?%E\x06k\xe1"2\xa0)\xbd \x12\x193PR\'-u\xa9\xee\x81\xaf\xa5\x1e\xb4\x01\x7fA\x83\xf7Z\x80\xb7\x00tZ\xb8\xe9\xbb\xdf\x843?\'C\x8f^\xfe\xaag\xb1\x04\xf8\xf5i\x80\x16\x9b\x9ec\x08\x01\xa3z\xd2\xe1\x89\n.\xd3;\xb8%\xf8\x12:b\n\x1d\xcc\x18\r\xa0X\x03\x14;\n|\xa8j\x02\x1c\x99\xd5`\x96\x04\xd2\xd57\xea\xeeu\x01\xea\x00\xc1\x02\xd0m%\xd5\xef\x80\xb5fq\xd3?\xff-V\xfct\x02\xe0<J}\x92])f\xf9\xb0\xe5\x13\xa09`\n|\x08\x99\xd1\x0b\xa9\x822\xb3\x13\x0c\xa7\xfc\xbf\xc7\x80x\x1b\x0b\x98\x83\xaf\xf8\x16\x10\xce\x02\x88\xcc\xa2\'\x0c@a\x1b$|C@j\x8b8OB\x04<\xb4\xd4]\x02\x0f\x8d\xd4}\t\xba\xa9\x80#\xf4P\x9f8\x8e\xe1\xa3\xdfA\xb55\x07\xc6y\xe6\x1d\xa4I\xdf\x88\xc5\xa1p\xf9\x04(\xfc\xc2\xf8\x80\x10\xa4`:\xc6\xfa\xd5{j\\\xa3\x8f\x00V\x01\xb8\xa34\xb7\x19\xbe\x81\xfe\xee#\x10\x9c\xa1\x1b\x1cC\xe0\x9d\xd3&#\x02=\t\x91\xdd+7d\xc8\xc7H\xe0R\xcb|\xa9\xee\x1e ,\xe0R\xfa\xb2\x86\x1dT\xa7\xcfb\xf0\x87o\xa0~\xe1\x8c\xdaAR\x9b\xb6\x8c\xe9\xdd${\xcf\xc3\xde\x91*\x85\xdf\xcb\x07\xc4\xef\xe4\xd5\xec\x94\x9d3\xb5&3\x0bc)U\x05\xbe\x02\n\x99R\xc1\xd9\xee\x7f`!<\x0e\xd6v\xe1\xf9\xe7 B\xe9\xb4$\xa0PW\xe9\xd4(C\x82\x04.\x7f\x93\xe1\r\x12\xb8\x94\xb0\x04\xdcJ\x08\x08;`\xedO0t\xec\x1f\xb0\xe2\xcc\xbbjz\xdcz\x1d\xcf\xcd\x86-3/\x1cUDb\x14i\xf2\xf5\xfa\x00s\\A\x1a\xb4\xb2\xa9 \xde\x06\xd5Q \xd0+CQQ;\xc6\xd2,\xa44\xbc\xe0\x92\xd1\x1f\xe9\x18}]U\xe2\xd2\x05B_\x03u\xb8\x8ah\x8a\\\x16\xa9\xbb\xa7\x81\x87\x06\xb8\x92x[}\xf6}\xf8\x03\x0c\xbe\xf7\xafp:-\x13~\xf5\xb3\x14xn\x9dK\xb0\x8d\x80\xd2\xfa\xbc\\\x02\xf4\xebE\xb3w\xafI\x08c\xcf\xca\xa4scA\xbc9\xa2\xb7\xba8(\xde:7\x04H\xfb\x97\x1a 5\xa1;\x0ftWh\xf02b\xa8\x83-\xa1v\xac\xc28\xb9\xb0\x95\x00\x17\x1ej\x17~\x84\xa1\x13\xaf\xa3\xbap->ha\x03\x8eHH\x0efD`\x19l\xd7w\xbdy\x80\x8e\x02&\x14\xca\x07\xa8P\x07\x93\xe7\x92\xb1Y\x99\x02\xab\x87s\xb3+\xcc\x8d\xf7\x0f\x94\xe4\xa5\x06H\xf2x\xeb2D\xb5O\'3\xa1kr\xd0\xc0\xa8|[\x878\xf9I\x1d8s\xe71\xf4\xde\x11\xd4/O\xa4O\x98X\x80%\x11Z\xedY\xee\xc4\t-\xe3el\xcf< \x8eOjE\',\xe5 \x03\x94\xe9\x98g\xb6\xc3u\xea\x15\xed\xe9\x1b\xad\x91\xeaO\x01\xdck\x1f\xa2\xe3\x0e\x03\x81\x07T+&L\x06F\xf5=%q\xd6\x99\xc1\x8a\xc9\xef\xa3\x7f\xf2\xbf\xc0EP\x08\xda&$\xb1{kj\x85\xc0\xcbu\xa0G\x14\xb0\xef\x8a\xbe\x85Q\x0c\xb0\xb2\x9d\xd0"\xc3z1\x12\x87\xbe@i\xc4\x8a\x8bo\xa33\xb4Ygq\xd2\x0c\x94\x06\x84F\x0b<\xf4M\xfd\'\x06\xce|\x0f<\xf4\xf4\xea\x823\xcb\xd1\xf1\xfc9$d7\xba\x17\xf7\xf8\xcb#@\xc8\x0c\x06IB\x01\xcb\xab\xaa\x89s3\x07f\x9c"7K`s\x08"\xca\x00\x95&\x084\xae\xbe\x8f\xc6\xc5\xb7\xd1^u\x97\xd6\x14C@\xed\xca\t\x0cL~\x0f\xd5\xf6\x958\x9c\xa5l\x9c\xb3\x98\x10fI\x9cYi\x04C\xef%/Q\x9cf-\x99\x00\x99\x03t\x91J%)\xcd8i\x93 \xa3\xf6\x14i\x84\xfd\x06\x94\x84\xb9N\xed\x0c\xe0\xa6\xb3\xdfB\xe7\xd2\x0f\xe07F\xc1\x84\x07wn\x12\x8ewM\xeb\x8c\r\x9c\xf3\xf8-Q\xf2\xb6(m\xeb6\xe0\xb4\xec\xb3;\xe0*\xa3\xf1\x96M\x80\x10\xa2\x99~\x84\xbdGh\x0cA\xce\x8d\x8a\x1e\xcc,\xb31\x0b*sJ\xb0\xd6<\x87\xda\xfcG\xf1\x12;ZU\xca{\x8a<|j\xdf\xcf\xf2\xf0\xe5%\xff\x9b\x10a\xb3\xec\xa6\xdc~\x809%*\x82 \xb8\x0c;}7\x8b\xa2\xc81\x92Q\xed\xfc\xfe\x9b\xf9=\x05>!\x81\xc7\xc9K\x04\x98\xebe5\xe7q[Wd\xc0G\xf02o\x8a\x97\xd0\x0e\xc3\xf0\x8a\x9cT\xb5Z]\x9c\x80\xf5\xeb\xd7\xa3Z\xad\x8an\xb7;N\x19\x05\xd0#\'v\x1d\xaf\x7fu.\x1b\xb7\xc9d\x8f\xf1\xb5\n\xbc1\x10\xae\x92\xc6\xd8\xabK\xe0\xfa\xd3\xd8\xb9}\xd82\xf3\xfc\xc2]n*X^g\xda^\xb7;.\'\xb4q\xe3\xc6\x1c\x019\x13\x90,\xf5\xf5\xf5\x89f\xb3\xf5\x0eR\x0cX\xef\xf6\xcdr3\x13w\n\xb4,2\x18\x8a\xe9V\x0b\x14\t\xcet1\xfb\xa8\x1cc\xa9\xa3t\xf9B%\x87\x11\x8b\xaeK\xe6\xe8u:\xc7\xa4$n\xb9\xe5\x96\xdc\x95e[b\x14\x86\xc1Y\xcf\xf3~\\L/\x90_\xcff\xab}53\x1a`\x854n\xd9<X\xe6|@\x11\xa0d\x1eT\xf0\xbc\xe2\xdd_\x82\xef\x07?\xf3<\xefX\xb4\xa7\xbcT\x02d\xe9\xcc\xce~\xf2\xe2bP\xf3\xd3+\x88\xc8\xcc"\x81\x99\x85\x0cl\x87\x87\xf4\xd1\xd0\xcc8\xd9\xf1\x8bD\x80\x92\xebggg\xbf\x0e\xa0U\x06\xb2\x94\x80;\xee\xb8#h6\x9b\xdf\xf4}\x7f\xb2\xe4II\x93,k\xa0\x8ce\xa4\x84\x92\x9c-J\x16/\x05\x87a\xa9x\x1c*\xe9G\xd1s\xd5\x81\xafpf~~\xee\xc5\r\x1b6\xf8\xcb&\xe0\xa9\xa7\x9e\xc2\xda\xb5k\xe7\xa7\xa7/?F$\x16P\xf2\xc0\x9cH\xb2 r$,R\x8a\xdcH\xd1\xfd\x8b\xa8\x05\t\n\xae\\\xb9|phhh\xe6\xd0\xa1C\xa53(%`dd\x04\xaf\xbd\xf6Z\xe8\xfb\xdd\xa3\x97.M\xefO\x91P:\xd3^\xa5\x0c\xc9R\xee-\x1b\xa7xL"\x05\xfe\x8f\xdb\xed\xf6?\xbe\xf4\xd2K\xc1\xbau\xebJG\xebyZ\xfc\xbe\xfb\xee\xc3\x0b/\xbc\xd0\xf5\xbc\xce?]\xbcx\xf1+A\xe0_(\xa6\xbeL-\x96"\xbel\xdfb\x1e\xa7\xec\xac\x83\xbe&\x0c\x83\x8f\xa7\xa7/\xfdN\xab\xd5zell\xac\xf3\xf0\xc3\x0f\xf7\x82\xb8\xf8\xff\x0b<\xfe\xf8\xe3x\xeb\xad\xb7\xba+W\xae\xfc\xf7\xa9\xa9\xa9;gff\xfe\xd4\xf7\xfd\x9f$g\x94\x96"\xd5\xdc\xf9\xad\x0c\xe8\xa5\x16\xb2\xc6\xa2\xd4\xe8~\x10\xfc\xec\xe3\x8f\xaf~mjj\xea\xf3\xb5Z\xed\xf5#G\x8et\x9e{\xee\xb9EG,]\x0cMLL\xc4\xffi144\x84\x97_~9|\xf2\xc9\'g\xde\x7f\xff\xfd?\x9b\x9f\x9f\xff+\xd7u\xef\xac\xd5\xea\xf7\xb8\xae\xbb\xcd\xa98\xab8\xe7\x03\x0c\xac\x9e\x1c\x19\xfb\x85\x142\x19VW\xa6\xea2\xc3\xebv\xfdq\xcf\xeb\x1c3\xa1\xae%\x1d\x9e\xb4y\xa9\xf6\xc7\x8f\x1fW7}\xf0\xc1\x07\xa5\x03\xe6&\xbas\xe7N\x9c9sF\x86\x8f\xc5&cNIE[Be.\xfd\xe7^l\x9bH\xa7\xa0\x8b\x94\xfb\xef\xbf\x1fG\x8f\x1e\xed}\x91\\\x0b\xfc\xb2\xfe\xdb\x9c\xd4\xe4\xcfJ\xa6|\xf6\x9f\xa37z\x027\xba|\xea\t\xf8\xbf\x00\x00\x00\xff\xff\xa1\xee\xb0\xd2\xe5O\x02\xe6\x00\x00\x00\x00IEND\xaeB`\x82'), mimetype="image/webp")
    elif pic == "vlc":
        return send_file(BytesIO(b'<?xml version="1.0" ?><!DOCTYPE svg PUBLIC \'-//W3C//DTD SVG 1.1//EN\' \'http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\'><svg height="512px" style="enable-background:new 0 0 512 512;" version="1.1" viewBox="0 0 512 512" width="512px" xml:space="preserve" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><g id="_x31_2-vlc_x2C__media_x2C__player"><g><g><g><path d="M478.104,458.638l-59.65-119.619c-2.535-5.058-7.691-8.255-13.326-8.255H106.872 c-5.635,0-10.791,3.197-13.326,8.255L33.887,458.638c-2.325,4.637-2.053,10.141,0.66,14.538 c2.715,4.396,7.516,7.118,12.676,7.118h417.554c5.16,0,9.959-2.694,12.707-7.087 C480.193,468.778,480.404,463.307,478.104,458.638L478.104,458.638z M478.104,458.638" style="fill:#FF9800;"/></g><path d="M375.297,345.718c0,43.659-107.068,44.858-119.297,44.858c-12.23,0-119.302-1.199-119.302-44.858 c0-1.197,0.301-2.691,0.6-3.887l20.579-75.665c14.61,11.369,53.086,19.739,98.124,19.739s83.512-8.37,98.123-19.739 l20.578,75.665C375.002,343.026,375.297,344.521,375.297,345.718L375.297,345.718z M375.297,345.718" style="fill:#FCFCFC;"/><path d="M332.35,186.62c-18.787,5.975-46.227,9.565-76.35,9.565s-57.563-3.591-76.351-9.565l22.964-84.34 c15.506,2.69,34,4.187,53.387,4.187s37.879-1.496,53.387-4.187L332.35,186.62z M332.35,186.62" style="fill:#FCFCFC;"/><path d="M256,106.467c-19.387,0-37.881-1.496-53.387-4.187l10.439-37.982 c5.666-20.03,22.668-32.592,42.947-32.592s37.279,12.562,42.945,32.297l10.441,38.277 C293.879,104.971,275.387,106.467,256,106.467L256,106.467z M256,106.467" style="fill:#FF9800;"/><path d="M354.123,266.166c-14.611,11.369-53.086,19.739-98.123,19.739s-83.513-8.37-98.124-19.739 l21.772-79.546c18.789,5.975,46.228,9.565,76.351,9.565s57.563-3.591,76.35-9.565L354.123,266.166z M354.123,266.166" style="fill:#FF9800;"/></g></g></g><g id="Layer_1"/></svg>'), mimetype="image/svg+xml")
    elif pic == "potplayer":
        return send_file(BytesIO(b'<svg width="256pt" height="256pt" version="1.1" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg"><g id="#f8d714ff" fill="#f8d714"> <path d="m14.48 5.74c3.4-1.07 7.01-0.71 10.52-0.77 70.34 0.02 140.68-0.01 211.02 0.01 5.46-0.33 10.91 2.69 13.41 7.57 2.08 3.81 1.52 8.3 1.6 12.47-0.01 68.66-0.01 137.32 0 205.98-0.06 4.38 0.49 9.15-1.94 13.05-2.6 4.58-7.88 7.21-13.09 6.96-71.98 0.04-143.96 0.03-215.93 0-5.25 0.27-10.56-2.37-13.17-6.99-2.42-3.88-1.87-8.63-1.93-12.99 0.02-70.34-0.01-140.67 0.01-211.01-0.43-6.21 3.59-12.31 9.5-14.28m107.84 33.69c-14.96 1.39-29.3 8.36-39.65 19.25-9.91 10.28-16.17 24-17.37 38.23-1.18 12.94 1.74 26.23 8.31 37.46 7.78 13.44 20.66 23.86 35.48 28.54 14.49 4.68 30.65 3.88 44.61-2.22 14.42-6.23 26.32-18.03 32.68-32.4 6.61-14.74 7.24-32.04 1.71-47.22-4.72-13.25-14.04-24.78-25.96-32.24-11.74-7.43-25.99-10.76-39.81-9.4m-58.68 142.57c0 11.33-0.01 22.66 0 34h7.36c0-4.13 0-8.26 0.01-12.38 4.89-0.21 10.28 0.89 14.7-1.78 6.64-4.22 5.84-16.13-1.84-18.76-6.53-2.02-13.51-0.71-20.23-1.08m31.36-0.02v34.03c2.21-0.01 4.43-0.02 6.64-0.03 0.01-11.3-0.09-22.6 0.05-33.89-2.23-0.1-4.46-0.07-6.69-0.11m14.91 9.93c-2.42 1.25-3.4 3.9-4.08 6.36 2.18 0.12 4.38 0.06 6.57 0.15 0.83-4.08 5.95-5.29 9.03-2.88 0.68 1.52 1.23 4.02-0.79 4.76-3.79 1.3-8.04 0.88-11.69 2.64-4.94 2.35-4.8 10.64 0.13 12.94 4.31 1.97 9.56 1.01 13.21-1.89 0.26 3.53 4.7 1.48 7.03 2.02-1.44-6.71-0.21-13.61-0.86-20.38-0.19-2.04-1.85-3.62-3.67-4.32-4.76-1.82-10.32-1.73-14.88 0.6m52.44 1.46c-4.44 4.27-4.97 11.44-2.64 16.91 2.61 6 10.47 8.19 16.25 5.72 3.31-1.17 5.09-4.4 6.6-7.34-1.94-0.02-3.87-0.03-5.8 0-1.88 2.97-5.81 4.17-8.96 2.5-2.29-1.05-2.56-3.78-2.98-5.95 6.09-0.03 12.18 0 18.27-0.01-0.37-3.83-0.81-7.91-3.32-11.01-4.08-5.29-12.77-5.47-17.42-0.82m30.89 1.79c0.06-1.38 0.12-2.77 0.16-4.15-2.13-0.01-4.27-0.01-6.4-0.01v25.01c2.21-0.01 4.43-0.03 6.64-0.04 0.32-5.5-0.92-11.27 1.04-16.55 1.5-3.15 5.26-3.51 8.33-3.15-0.01-2.14-0.01-4.28-0.02-6.42-3.98 0.03-7.62 1.94-9.75 5.31m-61.66-4.17c3.01 8.67 6.35 17.24 9.1 25.99 0.23 3.74-3.99 4.08-6.67 3.4-0.01 1.73-0.01 3.47-0.01 5.2 4.41 0.8 10.45 0.5 12.22-4.49 3.74-9.96 7.1-20.06 10.66-30.08-2.29-0.01-4.58-0.01-6.86-0.01-1.82 6.03-3.63 12.06-5.5 18.06-2.14-5.92-3.89-11.98-5.73-18.01-2.4-0.05-4.81-0.05-7.21-0.06z"/> <path d="m111.13 74.07c1.31-0.17 2.41 0.69 3.5 1.25 13.64 8.39 27.33 16.71 41 25.05 1.27 0.84 3.17 1.74 2.53 3.64-1.02 1.06-2.3 1.82-3.55 2.58-13.78 8.18-27.43 16.6-41.23 24.75-1.21 1.08-3.48 0.59-3.29-1.3-0.22-17.35-0.01-34.71-0.1-52.06 0.12-1.36-0.28-3.1 1.14-3.91z"/> <path d="m71 187.63c3.41 0.08 7.12-0.52 10.26 1.13 2.82 2.15 2.47 7.87-1.24 8.92-2.98 0.55-6.02 0.3-9.02 0.31v-10.36z"/> <path d="m164.77 200.98c0.41-3.09 2.66-6.44 6.2-5.83 3.27-0.26 4.83 3.13 5.25 5.84-3.82 0.02-7.64 0.02-11.45-0.01z"/> <path d="m112.05 208c1.75-3.68 6.75-2.65 10.01-3.99-0.17 2.65 0.47 6.23-2.36 7.73-2.87 2.1-8.98 0.72-7.65-3.74z"/></g><g id="#ffffffff"> <path d="m122.32 39.43c13.82-1.36 28.07 1.97 39.81 9.4 11.92 7.46 21.24 18.99 25.96 32.24 5.53 15.18 4.9 32.48-1.71 47.22-6.36 14.37-18.26 26.17-32.68 32.4-13.96 6.1-30.12 6.9-44.61 2.22-14.82-4.68-27.7-15.1-35.48-28.54-6.57-11.23-9.49-24.52-8.31-37.46 1.2-14.23 7.46-27.95 17.37-38.23 10.35-10.89 24.69-17.86 39.65-19.25m-11.19 34.64c-1.42 0.81-1.02 2.55-1.14 3.91 0.09 17.35-0.12 34.71 0.1 52.06-0.19 1.89 2.08 2.38 3.29 1.3 13.8-8.15 27.45-16.57 41.23-24.75 1.25-0.76 2.53-1.52 3.55-2.58 0.64-1.9-1.26-2.8-2.53-3.64-13.67-8.34-27.36-16.66-41-25.05-1.09-0.56-2.19-1.42-3.5-1.25z" fill="#fff"/></g><g id="#222222ff" fill="#222"> <path d="m63.64 182c6.72 0.37 13.7-0.94 20.23 1.08 7.68 2.63 8.48 14.54 1.84 18.76-4.42 2.67-9.81 1.57-14.7 1.78-0.01 4.12-0.01 8.25-0.01 12.38h-7.36c-0.01-11.34 0-22.67 0-34m7.36 5.63v10.36c3-0.01 6.04 0.24 9.02-0.31 3.71-1.05 4.06-6.77 1.24-8.92-3.14-1.65-6.85-1.05-10.26-1.13z"/> <path d="m95 181.98c2.23 0.04 4.46 0.01 6.69 0.11-0.14 11.29-0.04 22.59-0.05 33.89-2.21 0.01-4.43 0.02-6.64 0.03v-34.03z"/> <path d="m109.91 191.91c4.56-2.33 10.12-2.42 14.88-0.6 1.82 0.7 3.48 2.28 3.67 4.32 0.65 6.77-0.58 13.67 0.86 20.38-2.33-0.54-6.77 1.51-7.03-2.02-3.65 2.9-8.9 3.86-13.21 1.89-4.93-2.3-5.07-10.59-0.13-12.94 3.65-1.76 7.9-1.34 11.69-2.64 2.02-0.74 1.47-3.24 0.79-4.76-3.08-2.41-8.2-1.2-9.03 2.88-2.19-0.09-4.39-0.03-6.57-0.15 0.68-2.46 1.66-5.11 4.08-6.36m2.14 16.09c-1.33 4.46 4.78 5.84 7.65 3.74 2.83-1.5 2.19-5.08 2.36-7.73-3.26 1.34-8.26 0.31-10.01 3.99z"/> <path d="m162.35 193.37c4.65-4.65 13.34-4.47 17.42 0.82 2.51 3.1 2.95 7.18 3.32 11.01-6.09 0.01-12.18-0.02-18.27 0.01 0.42 2.17 0.69 4.9 2.98 5.95 3.15 1.67 7.08 0.47 8.96-2.5 1.93-0.03 3.86-0.02 5.8 0-1.51 2.94-3.29 6.17-6.6 7.34-5.78 2.47-13.64 0.28-16.25-5.72-2.33-5.47-1.8-12.64 2.64-16.91m2.42 7.61c3.81 0.03 7.63 0.03 11.45 0.01-0.42-2.71-1.98-6.1-5.25-5.84-3.54-0.61-5.79 2.74-6.2 5.83z"/> <path d="m193.24 195.16c2.13-3.37 5.77-5.28 9.75-5.31 0.01 2.14 0.01 4.28 0.02 6.42-3.07-0.36-6.83 0-8.33 3.15-1.96 5.28-0.72 11.05-1.04 16.55-2.21 0.01-4.43 0.03-6.64 0.04v-25.01c2.13 0 4.27 0 6.4 0.01-0.04 1.38-0.1 2.77-0.16 4.15z"/> <path d="m131.58 190.99c2.4 0.01 4.81 0.01 7.21 0.06 1.84 6.03 3.59 12.09 5.73 18.01 1.87-6 3.68-12.03 5.5-18.06 2.28 0 4.57 0 6.86 0.01-3.56 10.02-6.92 20.12-10.66 30.08-1.77 4.99-7.81 5.29-12.22 4.49 0-1.73 0-3.47 0.01-5.2 2.68 0.68 6.9 0.34 6.67-3.4-2.75-8.75-6.09-17.32-9.1-25.99z"/></g></svg>'), mimetype="image/svg+xml")
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
            attr["url"] = f"{path_url}?id={attr['id']}"
        else:
            url = f"{path_url}?pickcode={attr['pickcode']}"
            if attr["violated"] and attr["size"] < 1024 * 1024 * 115:
                url += f"&web=true"
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
                    <a href="intent://{{ url }}#Intent;package=com.mxtech.videoplayer.pro;S.title={{ name }};end"><img src="/?pic=mxplayer" /></a>
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

