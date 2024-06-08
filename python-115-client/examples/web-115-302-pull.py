#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 1, 3)
__doc__ = "从运行 web-115-302.py 的服务器上拉取文件到你的 115 网盘"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
)
parser.add_argument("-u", "--base-url", default="http://localhost", help="挂载的网址，默认值: http://localhost")
parser.add_argument("-p", "--push-id", default=0, help="对方 115 网盘中的文件或文件夹的 id 或路径，默认值: 0")
parser.add_argument("-t", "--to-pid", default=0, help="保存到我的 115 网盘中的文件夹的 id 或路径，默认值: 0")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -c/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="""\
存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一: 
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录""")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-l", "--lock-dir-methods", action="store_true", 
                    help="对 115 的文件系统进行增删改查的操作（但不包括上传和下载）进行加锁，限制为单线程，这样就可减少 405 响应，以降低扫码的频率")
parser.add_argument("-s", "--stats-interval", type=float, default=30, 
                    help="输出统计信息的时间间隔，单位 秒，默认值: 30，如果小于等于 0 则不输出")
parser.add_argument("-d", "--debug", action="store_true", help="输出 DEBUG 级别日志信息")
parser.add_argument("-ur", "--use-requests", action="store_true", help="使用 requests 执行请求，而不是默认的 httpx")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
args = parser.parse_args()
if args.version:
    print(".".join(map(str, __version__)))
    raise SystemExit(0)

import logging

from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from gzip import GzipFile
from inspect import currentframe, getframeinfo
from json import dumps, load, loads
from os import stat
from os.path import expanduser, dirname, join as joinpath, realpath
from sys import exc_info
from textwrap import indent
from _thread import start_new_thread
from threading import Lock, current_thread
from time import perf_counter, sleep
from traceback import format_exc
from typing import cast, ContextManager, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request
from warnings import warn

try:
    from colored.colored import back_rgb, fore_rgb, Colored
    from concurrenttools import thread_batch
    from httpx import HTTPStatusError, RequestError
    from p115 import check_response, P115Client, AVAILABLE_APPS
    from pygments import highlight
    from pygments.lexers import JsonLexer, Python3Lexer, Python3TracebackLexer
    from pygments.formatters import TerminalFormatter
    from requests import Session
    from requests.exceptions import HTTPError as RequestsHTTPError, RequestException
    from requests_request import request as requests_request
except ImportError:
    from sys import executable
    from subprocess import run
    run([
        executable, "-m", "pip", "install", "-U", 
        "colored", "flask", "httpx", "python-concurrenttools", "python-115", 
        "Pygments", "requests", "requests_request"], check=True)
    from colored.colored import back_rgb, fore_rgb, Colored # type: ignore
    from concurrenttools import thread_batch
    from httpx import HTTPStatusError, RequestError
    from p115 import check_response, P115Client, AVAILABLE_APPS
    from pygments import highlight
    from pygments.lexers import JsonLexer, Python3Lexer, Python3TracebackLexer
    from pygments.formatters import TerminalFormatter
    from requests import Session
    from requests.exceptions import HTTPError as RequestsHTTPError, RequestException
    from requests_request import request as requests_request


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

base_url = args.base_url
push_id = args.push_id
to_pid = args.to_pid
cookies = args.cookies
cookies_path = args.cookies_path
max_workers = args.max_workers
if max_workers <= 0:
    max_workers = 1
lock_dir_methods = args.lock_dir_methods
stats_interval = args.stats_interval
use_requests = args.use_requests
debug = args.debug

login_lock: None | ContextManager = None
count_lock: None | ContextManager = None
fs_lock: None | ContextManager = None
if max_workers > 1:
    login_lock = Lock()
    count_lock = Lock()
    if lock_dir_methods:
        fs_lock = Lock()
cookies_path_mtime = 0

request: None | Callable
if use_requests:
    request = partial(
        requests_request, 
        timeout=5, 
        session=Session(), 
        parse=lambda resp, content: loads(content), 
    )
else:
    request = None


class Task(NamedTuple):
    src_attr: Mapping
    dst_pid: int
    dst_attr: None | Mapping = None


class Result(NamedTuple):
    stats: dict
    unfinished_tasks: dict[int, Task]


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


@contextmanager
def ensure_cm(cm):
    if isinstance(cm, ContextManager):
        with cm as val:
            yield val
    else:
        yield cm


def attr(
    id_or_path: int | str = 0, 
    base_url: str = base_url, 
) -> dict:
    if isinstance(id_or_path, int):
        url = f"{base_url}?id={id_or_path}&method=attr"
    else:
        url = f"{base_url}?path={quote(id_or_path, safe=':/')}&method=attr"
    with urlopen(Request(url, headers={"Accept-Encoding": "gzip"}), timeout=60) as resp:
        if resp.headers.get("Content-Encoding") == "gzip":
            resp = GzipFile(fileobj=resp)
        return load(resp)


def listdir(
    id_or_path: int | str = 0, 
    base_url: str = base_url, 
) -> list[dict]:
    if isinstance(id_or_path, int):
        url = f"{base_url}?id={id_or_path}&method=list"
    else:
        url = f"{base_url}?path={quote(id_or_path, safe=':/')}&method=list"
    with urlopen(Request(url, headers={"Accept-Encoding": "gzip"}), timeout=60) as resp:
        if resp.headers.get("Content-Encoding") == "gzip":
            resp = GzipFile(fileobj=resp)
        return load(resp)


def read_bytes_range(url: str, bytes_range: str = "0-") -> bytes:
    with urlopen(Request(url, headers={"Range": f"bytes={bytes_range}"}), timeout=10) as resp:
        return resp.read()


@contextmanager
def ctx_monitor(
    call: None | Callable = None, 
    interval: float = 1, 
):
    if call is None:
        frame = getframeinfo(currentframe().f_back) # type: ignore
        start_t = perf_counter()
        prefix = "{thread_p} {thread}, {filename_p} {filename}, {lineno_p} {lineno}".format(
            thread_p   = colored_format("thread", "red", styles="bold"), 
            thread     = highlight_object(current_thread()), 
            filename_p = colored_format("file", "red", styles="bold"), 
            filename   = highlight_path(frame.filename), 
            lineno_p   = colored_format("lineno", "red", styles="bold"), 
            lineno     = highlight_id(frame.lineno), 
        )
        call = lambda: print(f"{prefix}: {perf_counter() - start_t} s")
    def loop_print(call):
        while running:
            call()
            sleep(interval)
    try:
        running = True
        yield start_new_thread(loop_print, (call,))
    finally:
        running = False


def relogin(
    exc: None | BaseException = None, 
    force: bool = False, 
):
    global cookies_path_mtime
    logger.debug("""{emoji} {prompt}""".format(
        emoji  = blink_mark("🤖"), 
        prompt = highlight_prompt("[SCAN] ⚙️ 排队扫码", "green"), 
    ))
    if exc is None:
        exc = exc_info()[1]
    mtime = cookies_path_mtime
    with ensure_cm(login_lock):
        need_update = force or mtime == cookies_path_mtime
        if not force and cookies_path and need_update:
            try:
                mtime = stat(cookies_path).st_mtime_ns
                if mtime != cookies_path_mtime:
                    client.cookies = open(cookies_path).read()
                    cookies_path_mtime = mtime
                    need_update = False
            except (FileNotFoundError, ValueError):
                logger.warning("""{emoji} {prompt}{file}""".format(
                    emoji  = blink_mark("🔥"), 
                    prompt = highlight_prompt("[SCAN] 🦾 文件空缺: ", "yellow"), 
                    file   = highlight_path(cookies_path), 
                ))
        if force or need_update:
            if exc is None:
                logger.warning("""{emoji} {prompt}轮到扫码""".format(
                    emoji  = blink_mark("🤖"), 
                    prompt = highlight_prompt("[SCAN] 🦾 重新扫码: ", "yellow"), 
                ))
            else:
                logger.warning("""{emoji} {prompt}一个 Web API 受限 (响应 "405: Not Allowed"), 将自动扫码登录同一设备\n{exc}""".format(
                    emoji  = blink_mark("🤖"), 
                    prompt = highlight_prompt("[SCAN] 🦾 重新扫码: ", "yellow"), 
                    exc    = indent(highlight_exception(exc), "    ├ ")
                ))
            client.login_another_app(device, replace=True, request=request, timeout=5)
            if cookies_path:
                open(cookies_path, "w").write(client.cookies)
                cookies_path_mtime = stat(cookies_path).st_mtime_ns
            logger.debug("""{emoji} {prompt}""".format(
                emoji  = blink_mark("🤖"), 
                prompt = highlight_prompt("[SCAN] 🎉 扫码成功", "green"), 
            ))
        else:
            logger.debug("""{emoji} {prompt}""".format(
                emoji  = blink_mark("🤖"), 
                prompt = highlight_prompt("[SCAN] 🙏 不用扫码", "green"), 
            ))


def relogin_wrap(func, /, *args, **kwds):
    kwds.setdefault("request", request)
    try:
        with ensure_cm(fs_lock):
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
) -> Result:
    # 统计信息
    stats: dict = {
        # 开始时间
        "start_time": datetime.now(), 
        # 总耗时
        "elapsed": "", 
        # 任务总数
        "tasks": {"total": 0, "files": 0, "dirs": 0, "size": 0}, 
        # 成功任务数
        "success": {"total": 0, "files": 0, "dirs": 0, "size": 0}, 
        # 失败任务数（发生错误但已抛弃）
        "failed": {"total": 0, "files": 0, "dirs": 0, "size": 0}, 
        # 重试任务数（发生错误但可重试），一个任务可以重试多次
        "retry": {"total": 0, "files": 0, "dirs": 0}, 
        # 未完成任务数：未运行、重试中或运行中
        "unfinished": {"total": 0, "files": 0, "dirs": 0, "size": 0}, 
        # 各种错误数量和分类汇总
        "errors": {"total": 0, "files": 0, "dirs": 0, "reasons": {}}, 
        # 是否执行完成：如果是 False，说明是被人为终止
        "is_completed": False, 
    }
    # 任务总数
    tasks: dict[str, int] = stats["tasks"]
    # 成功任务数
    success: dict[str, int] = stats["success"]
    # 失败任务数（发生错误但已抛弃）
    failed: dict[str, int] = stats["failed"]
    # 重试任务数（发生错误但可重试），一个任务可以重试多次
    retry: dict[str, int] = stats["retry"]
    # 未完成任务数：未运行、重试中或运行中
    unfinished: dict[str, int] = stats["unfinished"]
    # 各种错误数量和分类汇总
    errors: dict = stats["errors"]
    # 各种错误的分类汇总
    reasons: dict[str, int] = errors["reasons"]
    # 开始时间
    start_time = stats["start_time"]
    # 各个工作线程当前执行任务的统计信息
    thread_stats: dict = {}

    def update_tasks(total=1, files=0, size=0):
        dirs = total - files
        with ensure_cm(count_lock):
            tasks["total"] += total
            unfinished["total"] += total
            if dirs:
                tasks["dirs"] += dirs
                unfinished["dirs"] += dirs
            if files:
                tasks["files"] += files
                tasks["size"] += size
                unfinished["files"] += files
                unfinished["size"] += size

    def update_success(total=1, files=0, size=0):
        dirs = total - files
        with ensure_cm(count_lock):
            success["total"] += total
            unfinished["total"] -= total
            if dirs:
                success["dirs"] += dirs
                unfinished["dirs"] -= dirs
            if files:
                success["files"] += files
                success["size"] += size
                unfinished["files"] -= files
                unfinished["size"] -= size

    def update_failed(total=1, files=0, size=0):
        dirs = total - files
        with ensure_cm(count_lock):
            failed["total"] += total
            unfinished["total"] -= total
            if dirs:
                failed["dirs"] += dirs
                unfinished["dirs"] -= dirs
            if files:
                failed["files"] += files
                failed["size"] += size
                unfinished["files"] -= files
                unfinished["size"] -= size

    def update_retry(total=1, files=0):
        dirs = total - files
        with ensure_cm(count_lock):
            retry["total"] += total
            if dirs:
                retry["dirs"] += dirs
            if files:
                retry["files"] += files

    def update_errors(e, is_directory=False):
        exctype = type(e).__module__ + "." + type(e).__qualname__
        with ensure_cm(count_lock):
            errors["total"] += 1
            if is_directory:
                errors["dirs"] += 1
            else:
                errors["files"] += 1
            try:
                reasons[exctype] += 1
            except KeyError:
                reasons[exctype] = 1

    def show_stats():
        with ensure_cm(count_lock):
            stats["elapsed"] = str(datetime.now() - start_time)
            logger.info("""\
{emoji} {prompt}
    ├ statistics = {stats}
    ├ work thread stats({count}) = {thread}""".format(
            emoji  = blink_mark("📊"), 
            prompt = highlight_prompt("[STAT] 📈 执行统计: ", "magenta"), 
            stats  = highlight_object(stats), 
            count  = highlight_id(len(thread_stats)), 
            thread = highlight_object(thread_stats), 
        ))

    def work(task, submit):
        attr, pid, dattr = task
        cur_thread = current_thread()
        thread_stats[cur_thread] = {"task_id": attr["id"], "start_time": datetime.now()}
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
                            prompt   = highlight_prompt("[GOOD] 📂 创建目录: ", "green"), 
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
                            prompt   = highlight_prompt("[SKIP] 📂 目录存在: ", "yellow"), 
                            src_path = highlight_path(attr["path"]), 
                            dst_path = highlight_path(dattr["path"]), 
                        ))
                    finally:
                        if dattr:
                            taskmap[attr["id"]] = Task(attr, pid, dattr)
                if subdattrs is None:
                    subdattrs = {
                        (attr["name"], attr["is_directory"]): attr 
                        for attr in relogin_wrap(fs.listdir_attr, dirid)
                    }
                subattrs = listdir(attr["id"], base_url)
                update_tasks(
                    total=len(subattrs), 
                    files=sum(not a["is_directory"] for a in subattrs), 
                    size=sum(a["size"] for a in subattrs if not a["is_directory"]), 
                )
                for subattr in subattrs:
                    is_directory = subattr["is_directory"]
                    subdattr = subdattrs.get((subattr["name"], is_directory), {})
                    if is_directory:
                        if subdattr:
                            if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                                emoji    = blink_mark("🏃"), 
                                prompt   = highlight_prompt("[SKIP] 📂 目录存在: ", "yellow"), 
                                src_path = highlight_path(subattr["path"]), 
                                dst_path = highlight_path(subdattr["path"]), 
                            ))
                        subtask = taskmap[subattr["id"]] = Task(subattr, dirid, subdattr)
                        submit(subtask)
                    elif subattr["sha1"] != subdattr.get("sha1"):
                        subtask = taskmap[subattr["id"]] = Task(subattr, dirid, None)
                        submit(subtask)
                    else:
                        if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                            emoji    = blink_mark("🏃"), 
                            prompt   = highlight_prompt("[SKIP] 📝 文件存在: ", "yellow"), 
                            src_path = highlight_path(subattr["path"]), 
                            dst_path = highlight_path(subdattr["path"]), 
                        ))
                        update_success(1, 1, subattr["size"])
                update_success(1)
            else:
                resp = client.upload_file_init(
                    attr["name"], 
                    pid=pid, 
                    filesize=attr["size"], 
                    filesha1=attr["sha1"], 
                    read_range_bytes_or_hash=lambda rng, url=attr["url"]: read_bytes_range(url, rng), 
                    request=request, 
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
                        prompt   = highlight_prompt("[VARY] 🛤️ 秒传失败（直接上传）: ", "yellow"), 
                        src_path = highlight_path(attr["path"]), 
                        name     = highlight_path(attr["name"]), 
                        pid      = highlight_id(pid), 
                        attr     = highlight_object(attr), 
                        resp     = highlight_as_json(resp), 
                    ))
                    with urlopen(attr["url"], timeout=10) as resp:
                        resp = client.upload_file_sample(resp, attr["name"], pid=pid, request=request)
                elif status == 0 and statuscode in (0, 413):
                    raise URLError(resp)
                else:
                    raise OSError(resp)
                resp_data = resp["data"]
                if debug: logger.debug("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n    ├ response = {resp}".format(
                    emoji    = blink_mark("🤭"), 
                    prompt   = highlight_prompt("[GOOD] 📝 接收文件: ", "green"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(resp_data["file_name"]), 
                    pid      = highlight_id(pid), 
                    resp     = highlight_as_json(resp_data), 
                ))
                update_success(1, 1, attr["size"])
            del taskmap[attr["id"]]
        except BaseException as e:
            update_errors(e, attr["is_directory"])
            retryable = True
            if isinstance(e, (HTTPStatusError, RequestsHTTPError)):
                retryable = e.response.status_code == 405
                if retryable:
                    try:
                        relogin()
                    except:
                        pass
            elif isinstance(e, HTTPError):
                retryable = e.status != 404
            if retryable and isinstance(e, (HTTPStatusError, RequestError, RequestsHTTPError, RequestException, URLError, TimeoutError)):
                logger.error("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n{exc}".format(
                    emoji    = blink_mark("♻️"), 
                    prompt   = highlight_prompt("[FAIL] %s 发生错误（将重试）: " % ("📂" if attr["is_directory"] else "📝"), "red"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(attr["name"]), 
                    pid      = highlight_id(pid), 
                    exc      = indent(highlight_exception(e), "    ├ ")
                ))
                update_retry(1, not attr["is_directory"])
                submit((attr, pid, dattr))
            else:
                logger.error("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n{exc}".format(
                    emoji    = blink_mark("💀"), 
                    prompt   = highlight_prompt("[RUIN] %s 发生错误（将抛弃）: " % ("📂" if attr["is_directory"] else "📝"), "red"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(attr["name"]), 
                    pid      = highlight_id(pid), 
                    exc      = indent(highlight_traceback(), "    ├ ")
                ))
                update_failed(1, not attr["is_directory"], attr.get("size"))
                raise
        finally:
            del thread_stats[cur_thread]

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
    taskmap: dict[int, Task] = {
        push_attr["id"]: Task(push_attr, cast(int, to_pid), None)}
    update_tasks(1, not push_attr["is_directory"], push_attr.get("size"))
    try:
        is_completed = False
        if stats_interval:
            with ctx_monitor(show_stats, interval=stats_interval):
                thread_batch(work, taskmap.values(), max_workers=max_workers)
        else:
            thread_batch(work, taskmap.values(), max_workers=max_workers)
        is_completed = stats["is_completed"] = True
    finally:
        stats["elapsed"] = str(datetime.now() - start_time)
        if is_completed and not taskmap:
            logger.info("{emoji} {prompt}\n    ├ statistics = {stats}".format(
                emoji  = blink_mark("📊"), 
                prompt = highlight_prompt("[STAT] 🥳 统计信息: ", "green"), 
                stats  = highlight_object(stats), 
            ))
        else:
            logger.info("""\
{emoji} {prompt}
    ├ unfinished tasks({count}) = {tasks}
    ├ statistics = {stats}""".format(
                emoji  = blink_mark("⭕" if is_completed else "❌"), 
                prompt = (
                    highlight_prompt("[STAT] 🐶 统计信息: ", "yellow")
                    if is_completed else
                    highlight_prompt("[STAT] 🤯 统计信息: ", "red")
                ), 
                count  = highlight_id(len(taskmap)), 
                tasks  = highlight_object(taskmap), 
                stats  = highlight_object(stats), 
            ))
    return Result(stats, taskmap)


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
if device not in AVAILABLE_APPS:
    # 115 浏览器版
    if device == "desktop":
        device = "web"
    else:
        warn(f"encountered an unsupported app {device!r}, fall back to 'qandroid'")
        device = "qandroid"
if cookies_path and cookies != client.cookies:
    open(cookies_path, "w").write(client.cookies)
fs = client.fs

logger = logging.Logger("115-pull", logging.DEBUG if debug else logging.INFO)
handler = logging.StreamHandler()
formatter = ColoredLevelNameFormatter(
    "[{asctime}] (%(levelname)s) {name}:({thread}) {arrow} %(message)s".format(
        asctime = colored_format("%(asctime)s", styles="bold"), 
        name    = colored_format("%(name)s", "cyan", styles="bold"), 
        thread  = colored_format("%(threadName)s", "red", styles="bold"), 
        arrow   = colored_format("➜", "red"), 
    )
)
handler.setFormatter(formatter)
logger.addHandler(handler)


pull(push_id, to_pid, base_url=base_url, max_workers=max_workers)

