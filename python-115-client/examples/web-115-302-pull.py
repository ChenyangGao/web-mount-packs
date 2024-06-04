#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 7)
__doc__ = "从 115 的挂载拉取文件"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
)
parser.add_argument("-u", "--base-url", default="http://localhost", help="挂载的网址，默认值：http://localhost")
parser.add_argument("-p", "--push-id", type=int, default=0, help="对方 115 网盘中的文件或文件夹的 id，默认值：0")
parser.add_argument("-t", "--to-pid", type=int, default=0, help="保存到我的 115 网盘中的文件夹的 id，默认值：0")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -c/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
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


import logging

from collections.abc import Iterable
from json import dumps, load, JSONDecodeError
from os.path import expanduser, dirname, join as joinpath, realpath
from textwrap import indent
from threading import Lock
from traceback import format_exc
from typing import cast
from urllib.error import URLError
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
    run([executable, "-m", "pip", "install", "-U", "colored", "flask", "python-concurrenttools", "python-115", "Pygments"], check=True)
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
                record.levelname = highlight_prompt(record.levelname, "cyan")
            case logging.INFO:
                record.levelname = highlight_prompt(record.levelname, "green")
            case logging.WARNING:
                record.levelname = highlight_prompt(record.levelname, "yellow")
            case logging.ERROR:
                record.levelname = highlight_prompt(record.levelname, "red")
            case logging.CRITICAL:
                record.levelname = highlight_prompt(record.levelname, "magenta")
            case _:
                record.levelname = highlight_prompt(record.levelname, "grey")
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
        if fore_color == "grey":
            return "\x1b[2m"
        elif fore_color in COLORS_8_BIT:
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


def attr(id: int = 0, base_url: str = base_url) -> dict:
    return load(urlopen(f"{base_url}?id={id}&method=attr"))


def listdir(id: int = 0, base_url: str = base_url) -> list[dict]:
    return load(urlopen(f"{base_url}?id={id}&method=list"))


def read_bytes_range(url: str, bytes_range: str = "0-") -> bytes:
    with urlopen(Request(url, headers={"Range": f"bytes={bytes_range}"})) as resp:
        return resp.read()


def relogin_wrap(func, /, *args, **kwds):
    with lock:
        try:
            return func(*args, **kwds)
        except JSONDecodeError as e:
            pass
        client.login_another_app(device, replace=True)
        if cookies_path:
            open(cookies_path, "w").write(client.cookies)
        return func(*args, **kwds)


def pull(push_id=0, to_pid=0, base_url=base_url, max_workers=1):
    stats = {"tasks": 0, "files": 0, "dirs": 0, "errors": 0, "is_success": False}
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
                        dattr = {"id": dirid}
                        logger.info("{emoji} {prompt}{src_path} ➜ {name} @ {dirid} in {pid}\n    ├ response = {resp}".format(
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
                        logger.warning("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                            emoji    = blink_mark("🏃"), 
                            prompt   = highlight_prompt("[SKIP] 📂 目录存在：", "yellow"), 
                            src_path = highlight_path(attr["path"]), 
                            dst_path = highlight_path(dattr["path"]), 
                        ))
                    finally:
                        if dattr:
                            with count_lock:
                                stats["dirs"] += 1
                if subdattrs is None:
                    subdattrs = {
                        (attr["name"], attr["is_directory"]): attr 
                        for attr in relogin_wrap(fs.listdir_attr, dirid)
                    }
                subattrs = listdir(attr["id"], base_url)
                with count_lock:
                    stats["tasks"] += len(subattrs)
                for subattr in subattrs:
                    is_directory = subattr["is_directory"]
                    subdattr = subdattrs.get((subattr["name"], is_directory), {})
                    if is_directory:
                        if subdattr:
                            logger.warning("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                                emoji    = blink_mark("🏃"), 
                                prompt   = highlight_prompt("[SKIP] 📂 目录存在：", "yellow"), 
                                src_path = highlight_path(subattr["path"]), 
                                dst_path = highlight_path(subdattr["path"]), 
                            ))
                            with count_lock:
                                stats["dirs"] += 1
                        submit((subattr, dirid, subdattr))
                    elif subattr["sha1"] != subdattr.get("sha1"):
                        submit((subattr, dirid, None))
                    else:
                        logger.warning("{emoji} {prompt}{src_path} ➜ {dst_path}".format(
                            emoji    = blink_mark("🏃"), 
                            prompt   = highlight_prompt("[SKIP] 📝 文件存在：", "yellow"), 
                            src_path = highlight_path(subattr["path"]), 
                            dst_path = highlight_path(subdattr["path"]), 
                        ))
                        with count_lock:
                            stats["files"] += 1
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
                    logger.warning("""\
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
                else:
                    raise OSError(resp)
                resp_data = resp["data"]
                logger.info("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n    ├ response = {resp}".format(
                    emoji    = blink_mark("🤭"), 
                    prompt   = highlight_prompt("[GOOD] 📝 接收文件：", "green"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(resp_data["file_name"]), 
                    pid      = highlight_id(pid), 
                    resp     = highlight_as_json(resp_data), 
                ))
                with count_lock:
                    stats["files"] += 1
        except BaseException as e:
            with count_lock:
                stats["errors"] += 1
            retryable = False
            if isinstance(e, HTTPStatusError):
                match e.response.status_code:
                    case 405:
                        with lock:
                            client.login_another_app(device, replace=True)
                            if cookies_path:
                                open(cookies_path, "w").write(client.cookies)
                        retryable = True
            if retryable or isinstance(e, (URLError, TimeoutException)):
                logger.error("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n{exc}".format(
                    emoji    = blink_mark("💥"), 
                    prompt   = highlight_prompt("[FAIL] ♻️ 发生错误（将重试）：", "red"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(attr["name"]), 
                    pid      = highlight_id(pid), 
                    exc      = indent(highlight_exception(e), "    ├ ")
                ))
                submit((attr, pid, dattr))
            else:
                logger.error("{emoji} {prompt}{src_path} ➜ {name} in {pid}\n{exc}".format(
                    emoji    = blink_mark("⛔"), 
                    prompt   = highlight_prompt("[RUIN] 💀 发生错误（将抛弃）：", "red"), 
                    src_path = highlight_path(attr["path"]), 
                    name     = highlight_path(attr["name"]), 
                    pid      = highlight_id(pid), 
                    exc      = indent(highlight_traceback(), "    ├ ")
                ))
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
        logger.debug("{emoji} {prompt}\n    ├ {stats}".format(
            emoji  = blink_mark("📊"), 
            prompt = (
                highlight_prompt("[STAT] 📈 统计信息：", "light_green")
                if stats["is_success"] else
                highlight_prompt("[STAT] 📉 统计信息：", "orange_red_1")
            ), 
            stats  = highlight_object(stats)
        ))


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
fs = client.fs

lock = Lock()
count_lock = Lock()

logger = logging.Logger("115-pull", logging.DEBUG)
handler = logging.StreamHandler()
formatter = ColoredLevelNameFormatter(
    "[{asctime}] (%(levelname)s) {name} {arrow} %(message)s".format(
        asctime = colored_format("%(asctime)s", styles="bold"), 
        name    = colored_format("%(name)s", "blue", styles="bold"), 
        arrow   = colored_format("➜", "red")
    )
)
handler.setFormatter(formatter)
logger.addHandler(handler)

pull(push_id, to_pid, base_url=base_url, max_workers=max_workers)

