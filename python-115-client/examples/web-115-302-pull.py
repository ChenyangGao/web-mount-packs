#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__doc__ = "从 115 的挂载拉取文件"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
)
parser.add_argument("-u", "--base-url", default="http://localhost", help="挂载的网址，默认值：http://localhost")
parser.add_argument("-p", "--push-id", type=int, default=0, help="对方 115 网盘中的文件或文件夹的 id，默认值：0")
parser.add_argument("-t", "--to-pid", type=int, default=0, help="保存到我的 115 网盘中的文件夹的 id，默认值：0")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，如果缺失，则从 115-cookies.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
args = parser.parse_args()
if args.version:
    print(".".join(map(str, __version__)))
    raise SystemExit(0)

from json import load, JSONDecodeError
from os.path import expanduser, dirname, join as joinpath, realpath
from sys import stderr
from textwrap import indent
from threading import Lock
from traceback import format_exc
from urllib.error import URLError
from urllib.request import urlopen, Request

try:
    from concurrenttools import thread_pool_batch
    from httpx import TimeoutException
    from p115 import P115Client, check_response
    from pygments import highlight
    from pygments.lexers import Python3Lexer, Python3TracebackLexer
    from pygments.formatters import TerminalFormatter
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "flask", "python-concurrenttools", "python-115", "Pygments"], check=True)
    from concurrenttools import thread_pool_batch
    from httpx import TimeoutException
    from p115 import P115Client, check_response
    from pygments import highlight
    from pygments.lexers import Python3Lexer, Python3TracebackLexer
    from pygments.formatters import TerminalFormatter


base_url = args.base_url
push_id = args.push_id
to_pid = args.to_pid
cookies = args.cookies
max_workers = args.max_workers
lock = Lock()

cookie_path = None
if not cookies:
    seen = set()
    for dir_ in (".", expanduser("~"), dirname(__file__)):
        dir_ = realpath(dir_)
        if dir_ in seen:
            continue
        seen.add(dir_)
        try:
            cookies = open(joinpath(dir_, "115-cookies.txt")).read()
            if cookies:
                cookie_path = joinpath(dir_, "115-cookies.txt")
                break
        except FileNotFoundError:
            pass

client = P115Client(cookies)
device = client.login_device()["icon"]
if cookie_path and cookies != client.cookies:
    open(cookie_path, "w").write(client.cookies)


def attr(id=0, base_url=base_url):
    return load(urlopen(f"{base_url}?id={id}&method=attr"))


def listdir(id=0, base_url=base_url):
    return load(urlopen(f"{base_url}?id={id}&method=list"))


def relogin_wrap(func, /, *args, **kwds):
    with lock:
        try:
            return func(*args, **kwds)
        except JSONDecodeError as e:
            pass
        client.login_another_app(device, replace=True)
        if cookie_path:
            open(cookie_path, "w").write(client.cookies)
        return func(*args, **kwds)


def pull(push_id=0, to_pid=0, base_url=base_url, max_workers=1):
    def read_range(url, rng):
        with urlopen(Request(url, headers={"Range": f"bytes={rng}"})) as resp:
            return resp.read()
    def pull(task, submit):
        attr, pid = task
        try:
            if attr["is_directory"]:
                try:
                    resp = check_response(relogin_wrap(client.fs_mkdir, {"cname": attr["name"], "pid": pid}))
                    dirid = int(resp["cid"])
                    print(f"\x1b[1m\x1b[38;5;2m创建目录：\x1b[0m\x1b[4;34m{resp['cname']!r}\x1b[0m in \x1b[1m\x1b[38;5;6m{dirid}\x1b[0m")
                except FileExistsError:
                    dattr = relogin_wrap(client.fs.attr, [attr["name"]], pid)
                    dirid = dattr["id"]
                    print(f"\x1b[1m\x1b[38;5;3m目录存在：\x1b[0m\x1b[4;34m{dattr['path']!r}\x1b[0m")
                for subattr in listdir(attr["id"], base_url):
                    submit((subattr, dirid))
            else:
                resp = check_response(client.upload_file_init(
                    attr["name"], 
                    pid=pid, 
                    filesize=attr["size"], 
                    file_sha1=attr["sha1"], 
                    read_range_bytes_or_hash=lambda rng, url=attr["url"]: read_range(url, rng), 
                ))
                data = resp["data"]
                data_str = highlight(repr(data), Python3Lexer(), TerminalFormatter()).rstrip()
                print(f"\x1b[1m\x1b[38;5;2m接收文件：\x1b[0m\x1b[0m\x1b[4;34m{attr['path']!r}\x1b[0m => {data_str}")
        except BaseException as e:
            data_str = highlight(repr(attr), Python3Lexer(), TerminalFormatter()).rstrip()
            if isinstance(e, (URLError, TimeoutException)):
                exc_str = indent(f"\x1b[38;5;1m{type(e).__qualname__}\x1b[0m: {e}", "    |_ ")
                print(f"\x1b[1m\x1b[38;5;1m发生错误（将重试）：\x1b[0m{data_str} -> {pid}\n{exc_str}", file=stderr)
                submit(task)
            else:
                exc_str = indent(highlight(format_exc(), Python3TracebackLexer(), TerminalFormatter()).rstrip(), "    |_ ")
                print(f"\x1b[1m\x1b[38;5;1m发生错误（将抛弃）：\x1b[0m{data_str} -> {pid}\n{exc_str}", file=stderr)
                raise
    if push_id == 0:
        tasks = [(a, to_pid) for a in listdir(push_id, base_url)]
    else:
        tasks = [(attr(push_id, base_url), to_pid)]
    thread_pool_batch(pull, tasks, max_workers=max_workers)


pull(push_id, to_pid, base_url=base_url, max_workers=max_workers)

