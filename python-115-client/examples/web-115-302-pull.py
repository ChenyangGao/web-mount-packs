#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 5)
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

import logging

from json import load, JSONDecodeError
from os.path import expanduser, dirname, join as joinpath, realpath
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
count_lock = Lock()

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
fs = client.fs


class ColoredLevelNameFormatter(logging.Formatter):

    def format(self, record):
        match record.levelno:
            case logging.DEBUG:
                # cyan
                record.levelname = f"\x1b[1;34m{record.levelname}\x1b[0m"
            case logging.INFO:
                # green
                record.levelname = f"\x1b[1;32m{record.levelname}\x1b[0m"
            case logging.WARNING:
                # yellow
                record.levelname = f"\x1b[1;33m{record.levelname}\x1b[0m"
            case logging.ERROR:
                # red
                record.levelname = f"\x1b[1;31m{record.levelname}\x1b[0m"
            case logging.CRITICAL:
                # magenta
                record.levelname = f"\x1b[1;35m{record.levelname}\x1b[0m"
            case _:
                # dark grey
                record.levelname = f"\x1b[1;2m{record.levelname}\x1b[0m"
        return super().format(record)


logger = logging.Logger("115-pull", logging.DEBUG)
handler = logging.StreamHandler()
formatter = ColoredLevelNameFormatter(
    "[\x1b[1m%(asctime)s\x1b[0m] (%(levelname)s) \x1b[1;36m\x1b[0m"
    "\x1b[1;34m%(name)s\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)


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
    stats = {"tasks": 0, "files": 0, "dirs": 0, "errors": 0, "is_success": False}
    def pull(task, submit):
        attr, pid, dattr = task
        try:
            if attr["is_directory"]:
                subdattrs: None | dict = None
                if dattr:
                    dirid = dattr["id"]
                    logger.warning(f"\x1b[1m\x1b[38;5;3m目录存在：\x1b[0m\x1b[4;34m{attr['path']!r}\x1b[0m => \x1b[4;34m{dattr['path']!r}\x1b[0m")
                else:
                    try:
                        resp = check_response(relogin_wrap(client.fs_mkdir, {"cname": attr["name"], "pid": pid}))
                        dirid = int(resp["cid"])
                        dattr = relogin_wrap(fs.attr, dirid)
                        logger.info(f"\x1b[1m\x1b[38;5;2m创建目录：\x1b[0m\x1b[4;34m{resp['cname']!r}\x1b[0m in \x1b[1m\x1b[38;5;6m{dirid}\x1b[0m")
                        subdattrs = {}
                    except FileExistsError:
                        def finddir(pid, name):
                            for attr in fs.listdir_attr(pid):
                                if attr["is_directory"] and attr["name"] == name:
                                    return attr
                            raise FileNotFoundError(f"{name!r} in {pid}")
                        dattr = relogin_wrap(finddir, pid, attr["name"])
                        dirid = dattr["id"]
                        logger.warning(f"\x1b[1m\x1b[38;5;3m目录存在：\x1b[0m\x1b[4;34m{attr['path']!r}\x1b[0m => \x1b[4;34m{dattr['path']!r}\x1b[0m")
                    with count_lock:
                        stats["dirs"] += 1
                if subdattrs is None:
                    subdattrs = {(attr["name"], attr["is_directory"]): attr for attr in relogin_wrap(fs.listdir_attr, dirid)}
                subattrs = listdir(attr["id"], base_url)
                with count_lock:
                    stats["tasks"] += len(subattrs)
                for subattr in subattrs:
                    is_directory = subattr["is_directory"]
                    subdattr = subdattrs.get((subattr["name"], is_directory), {})
                    if is_directory:
                        if subdattr:
                            with count_lock:
                                stats["dirs"] += 1
                        submit((subattr, dirid, subdattr))
                    elif subattr["sha1"] != subdattr.get("sha1"):
                        submit((subattr, dirid, None))
                    else:
                        with count_lock:
                            stats["files"] += 1
                        logger.warning(f"\x1b[1m\x1b[38;5;3m文件存在：\x1b[0m\x1b[4;34m{subattr['path']!r}\x1b[0m => \x1b[4;34m{subdattr['path']!r}\x1b[0m")
            else:
                resp = client.upload_file_init(
                    attr["name"], 
                    pid=pid, 
                    filesize=attr["size"], 
                    file_sha1=attr["sha1"], 
                    read_range_bytes_or_hash=lambda rng, url=attr["url"]: read_range(url, rng), 
                )
                status = resp["status"]
                statuscode = resp.get("statuscode", 0)
                if status == 2 and statuscode == 0:
                    pass
                elif status == 1 and statuscode == 0:
                    data_str = highlight(repr(attr), Python3Lexer(), TerminalFormatter()).rstrip()
                    logger.warning(f"\x1b[1m\x1b[38;5;3m秒传失败（直接上传）：\x1b[0m{data_str} -> {pid}")
                    resp = client.upload_file_sample(urlopen(attr["url"]), attr["name"], pid=pid)
                else:
                    raise OSError(resp)
                data = resp["data"]
                data_str = highlight(repr(data), Python3Lexer(), TerminalFormatter()).rstrip()
                logger.info(f"\x1b[1m\x1b[38;5;2m接收文件：\x1b[0m\x1b[0m\x1b[4;34m{attr['path']!r}\x1b[0m => {data_str}")
                with count_lock:
                    stats["files"] += 1
        except BaseException as e:
            with count_lock:
                stats["errors"] += 1
            data_str = highlight(repr(attr), Python3Lexer(), TerminalFormatter()).rstrip()
            if isinstance(e, (URLError, TimeoutException)):
                exc_str = indent(f"\x1b[38;5;1m{type(e).__qualname__}\x1b[0m: {e}", "    |_ ")
                logger.error(f"\x1b[1m\x1b[38;5;1m发生错误（将重试）：\x1b[0m{data_str} -> {pid}\n{exc_str}")
                submit((attr, pid, dattr))
            else:
                exc_str = indent(highlight(format_exc(), Python3TracebackLexer(), TerminalFormatter()).rstrip(), "    |_ ")
                logger.error(f"\x1b[1m\x1b[38;5;1m发生错误（将抛弃）：\x1b[0m{data_str} -> {pid}\n{exc_str}")
                raise
    if push_id == 0:
        tasks = [({"id": 0, "is_directory": True}, to_pid, fs.attr(to_pid))]
    else:
        tasks = [(attr(push_id, base_url), to_pid, None)]
    stats["tasks"] += 1
    try:
        thread_pool_batch(pull, tasks, max_workers=max_workers)
        stats["is_success"] = True
    finally:
        data_str = highlight(repr(stats), Python3Lexer(), TerminalFormatter()).rstrip()
        logger.debug(data_str)


pull(push_id, to_pid, base_url=base_url, max_workers=max_workers)

