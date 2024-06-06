#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 11)
__doc__ = "从 115 的挂载拉取文件"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
)
parser.add_argument("-u", "--base-url", default="http://localhost", help="挂载的网址，默认值：http://localhost")
parser.add_argument("-p", "--push-id", default=0, help="对方 115 网盘中的文件或文件夹的 id 或路径，默认值：0")
parser.add_argument("-t", "--to-pid", default=0, help="保存到我的 115 网盘中的文件夹的 id 或路径，默认值：0")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -c/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可以在 1. 当前工作目录、2. 用户根目录 或者 3. 此脚本所在目录 下")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-d", "--debug", action="store_true", help="输出 DEBUG 级别日志信息")
parser.add_argument("-s", "--stats-interval", type=float, default=30, help="输出统计信息的时间间隔，单位 秒，默认值：30，如果小于等于 0 则不输出")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
args = parser.parse_args()
if args.version:
    print(".".join(map(str, __version__)))
    raise SystemExit(0)

base_url = args.base_url
push_id = args.push_id
to_pid = args.to_pid
cookies = args.cookies
cookies_path = args.cookies_path
max_workers = args.max_workers
debug = args.debug
stats_interval = args.stats_interval
cookies_path_mtime = 0


import logging

from collections.abc import Iterable
from gzip import GzipFile
from json import dumps, load
from os import stat
from os.path import expanduser, dirname, join as joinpath, realpath
from sys import exc_info
from textwrap import indent
from threading import Lock, Thread
from time import sleep
from traceback import format_exc
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

try:
    from colored.colored import back_rgb, fore_rgb, Colored
    from concurrenttools import thread_pool_batch
    from httpx import HTTPStatusError, TimeoutException
    from p115 import P115Client, check_response
    from pygments import highlight
    from pygments.lexers import JsonLexer, Python3Lexer, Python3TracebackLexer
    from pygments.formatters import TerminalFormatter
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "colored", "flask", "httpx", "python-concurrenttools", "python-115", "Pygments"], check=True)
    from colored.colored import back_rgb, fore_rgb, Colored # type: ignore
    from concurrenttools import thread_pool_batch
    from httpx import HTTPStatusError, TimeoutException
    from p115 import P115Client, check_response
    from pygments import highlight
    from pygments.lexers import JsonLexer, Python3Lexer, Python3TracebackLexer
    from pygments.formatters import TerminalFormatter


class ColoredLevelNameFormatter(logging.Formatter):

    def format(self, record):
        match record.levelno:
            case logging.DEBUG:
                record.levelname = colored_format(record.levelname, "cyan", styles="bold")
            case logging.INFO:
                record.levelname = colored_format(record.levelname, "green", styles="bold")
            case logging.WARNING:
                record.levelname = colored_format(record.levelname, "yellow", styles="bold")
            case logging.ERROR:
                record.levelname = colored_format(record.levelname, "red", styles="bold")
            case logging.CRITICAL:
                record.levelname = colored_format(record.levelname, "magenta", styles="bold")
            case _:
                record.levelname = colored_format(record.levelname, styles=("bold", "dim"))
        return super().format(record)


COLORS_8_BIT: dict[str, int] = {
    "dark": 0, 
    "red": 1, 
    "green": 2, 
    "yellow": 3, 
    "blue": 4, 
    "magenta": 5, 
    "cyan": 6, 
    "white": 7, 
}


def colored_format(
    object, 
    /, 
    fore_color: int | str | tuple[int | str, int | str, int | str] = "", 
    back_color: int | str | tuple[int | str, int | str, int | str] = "", 
    styles: int | str | Iterable[int | str] = "", 
    reset: bool = True, 
) -> str:
    if fore_color != "":
        if fore_color in COLORS_8_BIT:
            fore_color = "\x1b[%dm" % (COLORS_8_BIT[cast(str, fore_color)] + 30)
        elif isinstance(fore_color, (int, str)):
            fore_color = Colored(fore_color).foreground()
        else:
            fore_color = fore_rgb(*fore_color)

    if back_color != "":
        if back_color in COLORS_8_BIT:
            back_color = "\x1b[%dm" % (COLORS_8_BIT[cast(str, back_color)] + 40)
        elif isinstance(back_color, (int, str)):
            back_color = Colored(back_color).background()
        else:
            back_color = back_rgb(*back_color)

    styling: str = ""
    if styles != "":
        if isinstance(styles, (int, str)):
            styling = Colored(styles).attribute()
        else:
            styling = "".join(Colored(attr).attribute() for attr in styles if attr != "")

    terminator: str = "\x1b[0m" if reset else ""

    return f"{styling}{back_color}{fore_color}{object}{terminator}"


def highlight_prompt(
    promt: str, 
    color: int | str | tuple[int | str, int | str, int | str] = "", 
) -> str:
    return colored_format(promt, color, styles="bold")


def blink_mark(mark) -> str:
    return colored_format(mark, styles="blink")


def highlight_id(id: int) -> str:
    return colored_format(id, "cyan", styles="bold")


def highlight_path(path: str) -> str:
    return colored_format(repr(path), "blue", styles="underline")


def highlight_exception(exception: BaseException) -> str:
    return "%s: %s" % (colored_format(type(exception).__qualname__, "red"), exception)


def highlight_object(obj) -> str:
    return highlight(repr(obj), Python3Lexer(), TerminalFormatter()).rstrip()


def highlight_as_json(data) -> str:
    return highlight(dumps(data, ensure_ascii=False), JsonLexer(), TerminalFormatter()).rstrip()


def highlight_traceback() -> str:
    return highlight(format_exc(), Python3TracebackLexer(), TerminalFormatter()).rstrip()


def attr(id_or_path: int | str = 0, base_url: str = base_url) -> dict:
    if isinstance(id_or_path, int):
        url = f"{base_url}?id={id_or_path}&method=attr"
    else:
        url = f"{base_url}?path={quote(id_or_path, safe=':/')}&method=attr"
    with urlopen(Request(url, headers={"Accept-Encoding": "gzip"})) as resp:
        if resp.headers.get("Content-Encoding") == "gzip":
            resp = GzipFile(fileobj=resp)
        return load(resp)


def listdir(id_or_path: int | str = 0, base_url: str = base_url) -> list[dict]:
    if isinstance(id_or_path, int):
        url = f"{base_url}?id={id_or_path}&method=list"
    else:
        url = f"{base_url}?path={quote(id_or_path, safe=':/')}&method=list"
    with urlopen(Request(url, headers={"Accept-Encoding": "gzip"})) as resp:
        if resp.headers.get("Content-Encoding") == "gzip":
            resp = GzipFile(fileobj=resp)
        return load(resp)


def read_bytes_range(url: str, bytes_range: str = "0-") -> bytes:
    with urlopen(Request(url, headers={"Range": f"bytes={bytes_range}"})) as resp:
        return resp.read()


def relogin(exc=None):
    global cookies_path_mtime
    if exc is None:
        exc = exc_info()[0]
    mtime = cookies_path_mtime
    with lock:
        need_update = mtime == cookies_path_mtime
        if cookies_path and need_update:
            try:
                mtime = stat(cookies_path).st_mtime_ns
                if mtime != cookies_path_mtime:
                    client.cookies = open(cookies_path).read()
                    cookies_path_mtime = mtime
                    need_update = False
            except FileNotFoundError:
                pass
        if need_update:
            if exc is None:
                logger.warning("""{emoji} {prompt}NO MESSAGE""".format(
                    emoji  = blink_mark("🤖"), 
                    prompt = highlight_prompt("[SCAN] 🦾 重新扫码：", "yellow"), 
                ))
            else:
                logger.warning("""{emoji} {prompt}一个 Web API 受限 (响应 "405: Not Allowed"), 将自动扫码登录同一设备\n{exc}""".format(
                    emoji  = blink_mark("🤖"), 
                    prompt = highlight_prompt("[SCAN] 🦾 重新扫码：", "yellow"), 
                    exc    = indent(highlight_exception(exc), "    ├ ")
                ))
            client.login_another_app(device, replace=True)
            if cookies_path:
                open(cookies_path, "w").write(client.cookies)
                cookies_path_mtime = stat(cookies_path).st_mtime_ns


def relogin_wrap(func, /, *args, **kwds):
    try:
        return func(*args, **kwds)
    except HTTPStatusError as e:
        if e.response.status_code != 405:
            raise
        exc = e
    relogin(exc)
    return relogin_wrap(func, *args, **kwds)


def pull(
    push_id: int | str = 0, 
    to_pid: int | str = 0, 
    base_url: str = base_url, 
    max_workers: int = 1, 
) -> dict:
    stats: dict = {
        "tasks": {"total": 0, "files": 0, "dirs": 0}, 
        "unfinished": {"total": 0, "files": 0, "dirs": 0}, 
        "success": {"total": 0, "files": 0, "dirs": 0}, 
        "failed": {"total": 0, "files": 0, "dirs": 0}, 
        "errors": {"total": 0, "files": 0, "dirs": 0, "reasons": {}}, 
        "is_completed": False, 
    }
    tasks: dict[str, int] = stats["tasks"]
    success: dict[str, int] = stats["success"]
    failed: dict[str, int] = stats["failed"]
    unfinished: dict[str, int] = stats["unfinished"]
    errors: dict = stats["errors"]
    reasons: dict[str, int] = errors["reasons"]
    def pull(task, submit):
        attr, pid, dattr = task
        try:
            if attr["is_directory"]:
                subdattrs: None | dict = None
                if dattr:
                    dirid = dattr["id"]
                else:
                    try:
                        resp = check_response(relogin_wrap(client.fs_mkdir, {"cname": attr["name"], "pid": pid}))
                        dirid = int(resp["file_id"])
                        dattr = {"id": dirid, "is_directory": True}
                        if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {name} @ {dirid} in {pid}\n    ├ response = {resp}".format(
                            emoji    = blink_mark("🤭"), 
                            prompt   = highlight_prompt("[GOOD] 📂 创建目录：", "green"), 
                            src_path = highlight_path(attr["path"]), 
                            dirid    = highlight_id(dirid), 
                            name     = highlight_path(resp["file_name"]), 
                            pid      = highlight_id(pid), 
                            resp     = highlight_as_json(resp), 
                        ))
                        subdattrs = {}
                    except FileExistsError:
                        def finddir(pid, name):
                            for attr in relogin_wrap(fs.listdir_attr, pid):
                                if attr["is_directory"] and attr["name"] == name:
                                    return attr
                            raise FileNotFoundError(f"{name!r} in {pid}")
                        dattr = finddir(pid, attr["name"])
                        dirid = dattr["id"]
                        if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                            emoji    = blink_mark("🏃"), 
                            prompt   = highlight_prompt("[SKIP] 📂 目录存在：", "yellow"), 
                            src_path = highlight_path(attr["path"]), 
                            dst_path = highlight_path(dattr["path"]), 
                        ))
                    finally:
                        if dattr:
                            taskmap[attr["id"]] = (attr, pid, dattr)
                if subdattrs is None:
                    subdattrs = {
                        (attr["name"], attr["is_directory"]): attr 
                        for attr in relogin_wrap(fs.listdir_attr, dirid)
                    }
                subattrs = listdir(attr["id"], base_url)
                count = len(subattrs)
                count_dirs = sum(a["is_directory"] for a in subattrs)
                count_files = count - count_dirs
                with count_lock:
                    tasks["total"] += count
                    tasks["dirs"] += count_dirs
                    tasks["files"] += count_files
                    unfinished["total"] += count
                    unfinished["dirs"] += count_dirs
                    unfinished["files"] += count_files
                for subattr in subattrs:
                    is_directory = subattr["is_directory"]
                    subdattr = subdattrs.get((subattr["name"], is_directory), {})
                    if is_directory:
                        if subdattr:
                            if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                                emoji    = blink_mark("🏃"), 
                                prompt   = highlight_prompt("[SKIP] 📂 目录存在：", "yellow"), 
                                src_path = highlight_path(subattr["path"]), 
                                dst_path = highlight_path(subdattr["path"]), 
                            ))
                        subtask = taskmap[subattr["id"]] = (subattr, dirid, subdattr)
                        submit(subtask)
                    elif subattr["sha1"] != subdattr.get("sha1"):
                        subtask = taskmap[subattr["id"]] = (subattr, dirid, None)
                        submit(subtask)
                    else:
                        if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                            emoji    = blink_mark("🏃"), 
                            prompt   = highlight_prompt("[SKIP] 📝 文件存在：", "yellow"), 
                            src_path = highlight_path(subattr["path"]), 
                            dst_path = highlight_path(subdattr["path"]), 
                        ))
                        with count_lock:
                            success["total"] += 1
                            success["files"] += 1
                            unfinished["total"] -= 1
                            unfinished["files"] -= 1
            else:
                resp = client.upload_file_init(
                    attr["name"], 
                    pid=pid, 
                    filesize=attr["size"], 
                    filesha1=attr["sha1"], 
                    read_range_bytes_or_hash=lambda rng, url=attr["url"]: read_bytes_range(url, rng), 
                )
                status = resp["status"]
                statuscode = resp.get("statuscode", 0)
                if status == 2 and statuscode == 0:
                    pass
                elif status == 1 and statuscode == 0:
                    if debug: logger.debug("""\
{emoji} {prompt}{src_path} ➜ {name} in {pid}
    ├ attr = {attr}
    ├ response = {resp}""".format(
                        emoji    = blink_mark("🥹"), 
                        prompt   = highlight_prompt("[VARY] 🛤️ 秒传失败（直接上传）：", "yellow"), 
                        src_path = highlight_path(attr["path"]), 
                        name     = highlight_path(attr["name"]), 
                        pid      = highlight_id(pid), 
                        attr     = highlight_object(attr), 
                        resp     = highlight_as_json(resp), 
                    ))
                    resp = client.upload_file_sample(urlopen(attr["url"]), attr["name"], pid=pid)
                elif status == 0 and statuscode == 413:
                    raise URLError(resp)
                else:
                    raise OSError(resp)
                resp_data = resp["data"]
                if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n    ├ response = {resp}".format(
                    emoji    = blink_mark("🤭"), 
                    prompt   = highlight_prompt("[GOOD] 📝 接收文件：", "green"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(resp_data["file_name"]), 
                    pid      = highlight_id(pid), 
                    resp     = highlight_as_json(resp_data), 
                ))
            with count_lock:
                success["total"] += 1
                unfinished["total"] -= 1
                if attr["is_directory"]:
                    success["dirs"] += 1
                    unfinished["dirs"] -= 1
                else:
                    success["files"] += 1
                    unfinished["files"] -= 1
            del taskmap[attr["id"]]
        except BaseException as e:
            exctype = type(e).__module__ + "." + type(e).__qualname__
            with count_lock:
                errors["total"] += 1
                if attr["is_directory"]:
                    errors["dirs"] += 1
                else:
                    errors["files"] += 1
                try:
                    reasons[exctype] += 1
                except KeyError:
                    reasons[exctype] = 1
            retryable = True
            if isinstance(e, HTTPStatusError):
                retryable = e.response.status_code == 405
                if retryable:
                    relogin()
            elif isinstance(e, HTTPError):
                retryable = e.status != 404
            if retryable and isinstance(e, (URLError, TimeoutException)):
                logger.error("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n{exc}".format(
                    emoji    = blink_mark("♻️"), 
                    prompt   = highlight_prompt("[FAIL] %s 发生错误（将重试）：" % ("📂" if attr["is_directory"] else "📝"), "red"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(attr["name"]), 
                    pid      = highlight_id(pid), 
                    exc      = indent(highlight_exception(e), "    ├ ")
                ))
                submit((attr, pid, dattr))
            else:
                with count_lock:
                    failed["total"] += 1
                    unfinished["total"] -= 1
                    if attr["is_directory"]:
                        failed["dirs"] += 1
                        unfinished["dirs"] -= 1
                    else:
                        failed["files"] += 1
                        unfinished["files"] -= 1
                logger.error("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n{exc}".format(
                    emoji    = blink_mark("💀"), 
                    prompt   = highlight_prompt("[RUIN] %s 发生错误（将抛弃）：" % ("📂" if attr["is_directory"] else "📝"), "red"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(attr["name"]), 
                    pid      = highlight_id(pid), 
                    exc      = indent(highlight_traceback(), "    ├ ")
                ))
                raise
    stats_flag = True
    def show_stats(interval: float = 30):
        while stats_flag:
            with count_lock:
                logger.info("""{emoji} {prompt}\n    ├ statistics = {stats}""".format(
                    emoji  = blink_mark("📊"), 
                    prompt = highlight_prompt("[STAT] 📈 执行统计：", "magenta"), 
                    stats  = highlight_object(stats), 
                ))
            sleep(interval)
    if isinstance(push_id, str):
        if not push_id.strip("/"):
            push_id = 0
        elif not push_id.startswith("0") and push_id.isascii() and push_id.isdecimal():
            push_id = int(push_id)
    if isinstance(to_pid, str):
        if not to_pid.strip("/"):
            to_pid = 0
        elif not to_pid.startswith("0") and to_pid.isascii() and to_pid.isdecimal():
            to_pid = int(to_pid)
        else:
            to_pid = fs.makedirs(to_pid, exist_ok=True)["id"]
    if push_id == 0:
        push_attr = {"id": 0, "is_directory": True}
    else:
        push_attr = attr(push_id, base_url)
    taskmap: dict[int, tuple[dict, int, None | dict]] = {
        push_attr["id"]: (push_attr, cast(int, to_pid), None)}
    tasks["total"] += 1
    unfinished["total"] += 1
    if push_attr["is_directory"]:
        tasks["dirs"] += 1
        unfinished["dirs"] += 1
    else:
        tasks["files"] += 1
        unfinished["files"] += 1
    try:
        is_completed = False
        if stats_interval > 0:
            Thread(target=show_stats, args=(stats_interval,), daemon=True).start()
        thread_pool_batch(pull, taskmap.values(), max_workers=max_workers)
        is_completed = stats["is_completed"] = True
    finally:
        stats_flag = False
        logger.info("""\
{emoji} {prompt}
    ├ unfinished tasks({count}) = {tasks}
    ├ statistics = {stats}""".format(
            emoji  = blink_mark("📊"), 
            prompt = (
                highlight_prompt("[STAT] 🥳 统计信息：", "green")
                if is_completed else
                highlight_prompt("[STAT] ⛽ 统计信息：", "red")
            ), 
            count  = highlight_id(len(taskmap)), 
            tasks  = highlight_object(taskmap), 
            stats  = highlight_object(stats), 
        ))
    return stats


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
device = client.login_device()["icon"]
if cookies_path and cookies != client.cookies:
    open(cookies_path, "w").write(client.cookies)
fs = client.fs

lock = Lock()
count_lock = Lock()

logger = logging.Logger("115-pull", logging.DEBUG if debug else logging.INFO)
handler = logging.StreamHandler()
formatter = ColoredLevelNameFormatter(
    "[{asctime}] (%(levelname)s) {name} {arrow} %(message)s".format(
        asctime = colored_format("%(asctime)s", styles="bold"), 
        name    = colored_format("%(name)s", "cyan", styles="bold"), 
        arrow   = colored_format("➜", "red")
    )
)
handler.setFormatter(formatter)
logger.addHandler(handler)

pull(push_id, to_pid, base_url=base_url, max_workers=max_workers)

