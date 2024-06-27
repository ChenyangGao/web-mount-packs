#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = "115 网盘或分享链接批量下载"

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[2])
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from argparse import RawTextHelpFormatter
    from .init import subparsers

    parser = subparsers.add_parser("download", description=__doc__, formatter_class=RawTextHelpFormatter)

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import NamedTuple, TypedDict


@dataclass
class Task:
    src_attr: Mapping
    dst_path: str
    times: int = 0
    reasons: list[BaseException] = field(default_factory=list)


class Tasks(TypedDict):
    success: dict[int, Task]
    failed: dict[int, Task]
    unfinished: dict[int, Task]


class Result(NamedTuple):
    stats: dict
    tasks: Tasks


def main(args) -> Result:
    if args.version:
        from p115 import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    import errno

    from collections.abc import Callable
    from contextlib import contextmanager
    from datetime import datetime
    from functools import partial
    from os import makedirs, scandir, stat
    from os.path import dirname, exists, expanduser, isdir, join as joinpath, normpath, realpath
    from platform import system
    from shutil import COPY_BUFSIZE # type: ignore
    from sys import exc_info
    from textwrap import indent
    from threading import Lock
    from traceback import format_exc
    from typing import cast, ContextManager
    from urllib.error import URLError
    from warnings import warn

    from concurrenttools import thread_batch
    from p115 import P115Client
    from rich.progress import (
        Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    )
    from texttools import cycle_text, rotate_text
    from download import download, DEFAULT_ITER_BYTES as iter_bytes

    cookies = args.cookies
    cookies_path = args.cookies_path
    src_path = args.src_path
    dst_path = args.dst_path
    share_link = args.share_link
    lock_dir_methods = args.lock_dir_methods
    use_request = args.use_request
    max_workers = args.max_workers
    max_retries = args.max_retries
    resume = args.resume
    no_root = args.no_root

    if max_workers <= 0:
        max_workers = 1
    count_lock: None | ContextManager = None
    login_lock: None | ContextManager = None
    fs_lock: None | ContextManager = None
    if max_workers > 1:
        count_lock = Lock()
        login_lock = Lock()
        if lock_dir_methods:
            fs_lock = Lock()
    cookies_path_mtime = 0

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

    client = P115Client(cookies, app=args.app)

    urlopen: Callable
    do_request: None | Callable = None
    match use_request:
        case "httpx":
            from httpx import Client, HTTPStatusError as StatusError, RequestError
            from httpx_request import request as httpx_request
            def get_status_code(e):
                return e.response.status_code
            urlopen = partial(httpx_request, session=Client())
            iter_bytes = lambda resp: resp.iter_bytes(COPY_BUFSIZE)
        case "requests":
            try:
                from requests import Session
                from requests.exceptions import HTTPError as StatusError, RequestException as RequestError # type: ignore
                from requests_request import request as requests_request
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "requests", "requests_request"], check=True)
                from requests import Session
                from requests.exceptions import HTTPError as StatusError, RequestException as RequestError # type: ignore
                from requests_request import request as requests_request
            do_request = urlopen = partial(requests_request, session=Session())
            iter_bytes = lambda resp: resp.iter_content(COPY_BUFSIZE)
            def get_status_code(e):
                return e.response.status_code
        case "urllib3":
            from urllib.error import HTTPError as StatusError # type: ignore
            try:
                from urllib3.exceptions import RequestError # type: ignore
                from urllib3_request import request as urllib3_request
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "urllib3", "urllib3_request"], check=True)
                from urllib3.exceptions import RequestError # type: ignore
                from urllib3_request import request as urllib3_request
            do_request = urlopen = urllib3_request
            def get_status_code(e):
                return e.status
        case "urlopen":
            from urllib.error import HTTPError as StatusError, URLError as RequestError # type: ignore
            from urllib.request import build_opener, HTTPCookieProcessor
            try:
                from urlopen import request as urlopen_request
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "python-urlopen"], check=True)
                from urlopen import request as urlopen_request
            do_request = urlopen = partial(urlopen_request, opener=build_opener(HTTPCookieProcessor(client.cookiejar)))
            def get_status_code(e):
                return e.status

    device = client.login_device(request=do_request)["icon"]
    if device not in AVAILABLE_APPS:
        # 115 浏览器版
        if device == "desktop":
            device = "web"
        else:
            warn(f"encountered an unsupported app {device!r}, fall back to 'qandroid'")
            device = "qandroid"
    if cookies_path and cookies != client.cookies:
        open(cookies_path, "w").write(client.cookies)

    if share_link:
        fs = client.get_share_fs(share_link, request=do_request)
    else:
        fs = client.get_fs(request=do_request)

    match system():
        case "Windows":
            transtab = str.maketrans('<>/\\|:*?"', '＜＞／＼｜：＊？＂')
            def escape_name(name):
                return name.translate(transtab)
        case "Darwin":
            transtab = {ord("/"): ord(":"), ord(":"): ord("：")}
            def escape_name(name):
                return name.translate(transtab)
        case "Linux":
            def escape_name(name):
                return name.replace("/", "／")

    @contextmanager
    def ensure_cm(cm):
        if isinstance(cm, ContextManager):
            with cm as val:
                yield val
        else:
            yield cm

    def relogin(exc=None):
        nonlocal cookies_path_mtime
        if exc is None:
            exc = exc_info()[0]
        mtime = cookies_path_mtime
        with ensure_cm(login_lock):
            need_update = mtime == cookies_path_mtime
            if cookies_path and need_update:
                try:
                    mtime = stat(cookies_path).st_mtime_ns
                    if mtime != cookies_path_mtime:
                        client.cookies = open(cookies_path).read()
                        cookies_path_mtime = mtime
                        need_update = False
                except FileNotFoundError:
                    console_print("[bold yellow][SCAN] 🦾 文件空缺[/bold yellow]")
            if need_update:
                if exc is None:
                    console_print("[bold yellow][SCAN] 🦾 重新扫码[/bold yellow]")
                else:
                    console_print("""{prompt}一个 Web API 受限 (响应 "405: Not Allowed"), 将自动扫码登录同一设备\n{exc}""".format(
                        prompt = "[bold yellow][SCAN] 🤖 重新扫码：[/bold yellow]", 
                        exc    = f"    ├ [red]{type(exc).__qualname__}[/red]: {exc}")
                    )
                client.login_another_app(device, request=do_request, replace=True, timeout=5)
                if cookies_path:
                    open(cookies_path, "w").write(client.cookies)
                    cookies_path_mtime = stat(cookies_path).st_mtime_ns

    def relogin_wrap(func, /, *args, **kwds):
        try:
            with ensure_cm(fs_lock):
                return func(*args, **kwds)
        except StatusError as e:
            if get_status_code(e) != 405:
                raise
            relogin(e)
        return relogin_wrap(func, *args, **kwds)

    stats: dict = {
        # 开始时间
        "start_time": datetime.now(), 
        # 总耗时
        "elapsed": "", 
        # 源路径
        "src_path": "", 
        # 目标路径
        "dst_path": "", 
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

    def add_report(_, attr):
        update_desc = rotate_text(attr["name"], 32, interval=0.1).__next__
        task = progress.add_task(update_desc(), total=attr["size"])
        try:
            while not closed:
                progress.update(task, description=update_desc(), advance=(yield))
        finally:
            progress.remove_task(task)

    def get_url(attr) -> str:
        if share_link:
            return fs.get_url(attr["id"])
        if attr.get("violated", False):
            if attr["size"] >= 1024 * 1024 * 115:
                return ""
            return fs.get_url_from_pickcode(attr["pickcode"], use_web_api=True)
        else:
            return fs.get_url_from_pickcode(attr["pickcode"])

    def work(task: Task, submit):
        attr, dst_path = task.src_attr, task.dst_path
        task_id = attr["id"]
        try:
            task.times += 1
            if attr["is_directory"]:
                try:
                    sub_entries = {entry.name: entry for entry in scandir(dst_path)}
                except FileNotFoundError:
                    makedirs(dst_path, exist_ok=True)
                    sub_entries = {}
                    console_print(f"[bold green][GOOD][/bold green] 📂 创建目录: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]")

                subattrs = relogin_wrap(fs.listdir_attr, task_id)
                update_tasks(
                    total=len(subattrs), 
                    files=sum(not a["is_directory"] for a in subattrs), 
                    size=sum(a["size"] for a in subattrs if not a["is_directory"]), 
                )
                progress.update(statistics_bar, total=tasks["total"], description=update_stats_desc())
                seen: set[str] = set()
                for subattr in subattrs:
                    subpath = subattr["path"]
                    name = escape_name(subattr["name"])
                    subdpath = joinpath(dst_path, name)
                    if name in seen:
                        console_print(f"[bold red][FAIL][/bold red] 🗑️ 名称冲突（将抛弃）: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{subdpath!r}[/blue underline]")
                        continue
                    if name in sub_entries:
                        entry = sub_entries[name]
                        is_directory = subattr["is_directory"]
                        if is_directory != entry.is_dir(follow_symlinks=True):
                            console_print(f"[bold red][FAIL][/bold red] 💩 类型失配（将抛弃）: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{subdpath!r}[/blue underline]")
                            update_failed(1, not is_directory, subattr.get("size"))
                            progress.update(statistics_bar, advance=1, description=update_stats_desc())
                            continue
                        elif is_directory:
                            console_print(f"[bold yellow][SKIP][/bold yellow] 📂 目录已建: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{subdpath!r}[/blue underline]")
                        elif resume and not is_directory and subattr["size"] == entry.stat().st_size:
                            console_print(f"[bold yellow][SKIP][/bold yellow] 📝 跳过文件: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{subdpath!r}[/blue underline]")
                            update_success(1, 1, subattr["size"])
                            progress.update(statistics_bar, advance=1, description=update_stats_desc())
                            continue
                    seen.add(name)
                    subtask = unfinished_tasks[subattr["id"]] = Task(subattr, joinpath(dst_path, name))
                    submit(subtask)
                update_success(1)
            else:
                url = get_url(attr)
                if not url:
                    raise OSError(errno.ENODATA, f"can't get url for {attr!r}")
                download(
                    url, 
                    dst_path, 
                    resume=resume, 
                    make_reporthook=partial(add_report, attr=attr), 
                    urlopen=urlopen, 
                    iter_bytes=iter_bytes, 
                )
                console_print(f"[bold green][GOOD][/bold green] 📝 下载文件: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]")
                update_success(1, 1, attr["size"])
            progress.update(statistics_bar, advance=1, description=update_stats_desc())
            success_tasks[task_id] = unfinished_tasks.pop(task_id)
        except BaseException as e:
            task.reasons.append(e)
            update_errors(e, attr["is_directory"])
            if max_retries < 0:
                if isinstance(e, StatusError):
                    status_code = get_status_code(e)
                    if status_code == 405:
                        retryable = True
                        try:
                            relogin()
                        except:
                            pass
                    else:
                        retryable = not (400 <= status_code < 500)
                else:
                    retryable = isinstance(e, (RequestError, URLError, TimeoutError))
            else:
                retryable = task.times <= max_retries
            if retryable:
                console_print(f"""\
[bold red][FAIL][/bold red] ♻️ 发生错误（将重试）: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]
    ├ {type(e).__qualname__}: {e}""")
                update_retry(1, not attr["is_directory"])
                submit(task)
            else:
                console_print(f"""\
[bold red][FAIL][/bold red] 💀 发生错误（将抛弃）: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]
{indent(format_exc().strip(), "    ├ ")}""")
                progress.update(statistics_bar, advance=1, description=update_stats_desc())
                update_failed(1, not attr["is_directory"], attr.get("size"))
                failed_tasks[task_id] = unfinished_tasks.pop(task_id)
                if len(task.reasons) == 1:
                    raise
                else:
                    raise BaseExceptionGroup('max retries exceed', task.reasons)

    with Progress(
        SpinnerColumn(), 
        *Progress.get_default_columns(), 
        TimeElapsedColumn(), 
        MofNCompleteColumn(), 
        TransferSpeedColumn(), 
        FileSizeColumn(), 
    ) as progress:
        console_print = progress.console.print
        if isinstance(src_path, str):
            if src_path == "0":
                src_path = "/"
            elif not src_path.startswith("0") and src_path.isascii() and src_path.isdecimal():
                src_path = int(src_path)
        src_attr = relogin_wrap(fs.attr, src_path)
        is_directory = src_attr["is_directory"]
        name = escape_name(src_attr["name"])
        dst_path = normpath(dst_path)
        if exists(dst_path):
            dst_path_isdir = isdir(dst_path)
            if is_directory:
                if not dst_path_isdir:
                    raise NotADirectoryError(errno.ENOTDIR, f"{dst_path!r} is not directory")
                elif name and not no_root:
                    dst_path = joinpath(dst_path, name)
                    makedirs(dst_path, exist_ok=True)
            elif name and dst_path_isdir:
                dst_path = joinpath(dst_path, name)
                if isdir(dst_path):
                    raise IsADirectoryError(errno.EISDIR, f"{dst_path!r} is directory")
        elif is_directory:
            if no_root or not name:
                makedirs(dst_path)
            else:
                dst_path = joinpath(dst_path, name)
                makedirs(dst_path)
        unfinished_tasks: dict[int, Task] = {src_attr["id"]: Task(src_attr, dst_path)}
        success_tasks: dict[int, Task] = {}
        failed_tasks: dict[int, Task] = {}
        all_tasks: Tasks = {
            "success": success_tasks, 
            "failed": failed_tasks, 
            "unfinished": unfinished_tasks, 
        }
        stats["src_path"] = src_attr["path"]
        stats["dst_path"] = dst_path
        update_tasks(1, not src_attr["is_directory"], src_attr.get("size"))
        update_stats_desc = cycle_text(
            ("...", "..", ".", ".."), 
            prefix="📊 [cyan bold]statistics[/cyan bold] ", 
            min_length=32 + 23, 
            interval=0.1, 
        ).__next__
        statistics_bar = progress.add_task(update_stats_desc(), total=1)
        closed = False
        try:
            thread_batch(work, unfinished_tasks.values(), max_workers=max_workers)
            stats["is_completed"] = True
        finally:
            closed = True
            progress.remove_task(statistics_bar)
            stats["elapsed"] = str(datetime.now() - start_time)
            console_print(f"📊 [cyan bold]statistics:[/cyan bold] {stats}")
    return Result(stats, all_tasks)


from p115 import AVAILABLE_APPS

parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -c/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="""\
存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一: 
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录""")
parser.add_argument(
    "-a", "--app", default="qandroid", 
    choices=AVAILABLE_APPS, 
    help="必要时，选择一个 app 进行扫码登录，默认值 'qandroid'，注意：这会把已经登录的相同 app 踢下线")
parser.add_argument("-p", "--src-path", default="/", help="115 网盘中的文件或目录的 id 或路径，默认值：'/")
parser.add_argument("-t", "--dst-path", default=".", help="本地的路径，默认是当前工作目录，即 '.'")
parser.add_argument("-s", "--share-link", nargs="?", help="""\
115 的分享链接
    1. 指定了则从分享链接下载
    2. 不指定则从 115 网盘下载""")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-mr", "--max-retries", default=-1, type=int, 
                    help="""最大重试次数。
    - 如果小于 0（默认），则会对一些超时、网络请求错误进行无限重试，其它错误进行抛出
    - 如果等于 0，则发生错误就抛出
    - 如果大于 0（实际执行 1+n 次，第一次不叫重试），则对所有错误等类齐观，只要次数到达此数值就抛出""")
parser.add_argument("-l", "--lock-dir-methods", action="store_true", 
                    help="对 115 的文件系统进行增删改查的操作（但不包括上传和下载）进行加锁，限制为单线程，这样就可减少 405 响应，以降低扫码的频率")
parser.add_argument("-ur", "--use-request", choices=("httpx", "requests", "urllib3", "urlopen"), default="httpx", help="选择一个网络请求模块，默认值：httpx")
parser.add_argument("-n", "--no-root", action="store_true", help="下载目录时，直接合并到目标目录，而不是到与源目录同名的子目录")
parser.add_argument("-r", "--resume", action="store_true", help="断点续传")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

