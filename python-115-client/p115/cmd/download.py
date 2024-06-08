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
from typing import NamedTuple


class Task(NamedTuple):
    src_attr: Mapping
    dst_path: str


class Result(NamedTuple):
    stats: dict
    unfinished_tasks: dict[int, Task]


def main(args) -> Result:
    from p115 import P115Client, __version__

    if args.version:
        globals()["print"](".".join(map(str, __version__)))
        raise SystemExit(0)

    import errno

    from contextlib import contextmanager
    from datetime import datetime
    from functools import partial
    from gzip import GzipFile
    from json import load
    from os import makedirs, scandir, stat
    from os.path import dirname, exists, expanduser, isdir, join as joinpath, normpath, realpath
    from platform import system
    from sys import exc_info
    from textwrap import indent
    from threading import Lock
    from traceback import format_exc
    from typing import ContextManager
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote
    from urllib.request import urlopen, Request
    from warnings import warn

    from concurrenttools import thread_batch
    from httpx import HTTPStatusError
    from rich.progress import (
        Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    )
    from texttools import cycle_text, rotate_text
    from urlopen import download

    cookies = args.cookies
    cookies_path = args.cookies_path
    push_id = args.push_id
    to_path = args.to_path
    share_link = args.share_link
    lock_dir_methods = args.lock_dir_methods
    max_workers = args.max_workers
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
                    print("[bold yellow][SCAN] 🦾 文件空缺[/bold yellow]")
            if need_update:
                if exc is None:
                    print("[bold yellow][SCAN] 🦾 重新扫码[/bold yellow]")
                else:
                    print("""{prompt}一个 Web API 受限 (响应 "405: Not Allowed"), 将自动扫码登录同一设备\n{exc}""".format(
                        prompt = "[bold yellow][SCAN] 🤖 重新扫码：[/bold yellow]", 
                        exc    = f"    ├ [red]{type(exc).__qualname__}[/red]: {exc}")
                    )
                client.login_another_app(device, replace=True)
                if cookies_path:
                    open(cookies_path, "w").write(client.cookies)
                    cookies_path_mtime = stat(cookies_path).st_mtime_ns

    def relogin_wrap(func, /, *args, **kwds):
        try:
            with ensure_cm(fs_lock):
                return func(*args, **kwds)
        except HTTPStatusError as e:
            if e.response.status_code != 405:
                raise
            exc = e
        relogin(exc)
        return relogin_wrap(func, *args, **kwds)

    client = P115Client(cookies, app=args.app)
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

    if share_link:
        fs = client.get_share_fs(share_link)
    else:
        fs = client.fs

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
            success["total"] += total
            if dirs:
                success["dirs"] += dirs
            if files:
                success["files"] += files

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
            return fs.get_url(attr["id"], detail=True)
        if attr.get("violated", False):
            if attr["size"] >= 1024 * 1024 * 115:
                return ""
            return fs.get_url_from_pickcode(attr["pickcode"], detail=True, use_web_api=True)
        else:
            return fs.get_url_from_pickcode(attr["pickcode"], detail=True)

    def pull(task, submit):
        attr, dst_path = task
        try:
            if attr["is_directory"]:
                try:
                    sub_entries = {entry.name: entry for entry in scandir(dst_path)}
                except FileNotFoundError:
                    makedirs(dst_path, exist_ok=True)
                    sub_entries = {}
                    print(f"[bold green][GOOD][/bold green] 📂 创建目录: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]")

                subattrs = relogin_wrap(fs.listdir_attr, attr["id"])
                update_tasks(
                    total=len(subattrs), 
                    files=sum(not a["is_directory"] for a in subattrs), 
                    size=sum(a["size"] for a in subattrs if not a["is_directory"]), 
                )
                progress.update(statistics_bar, total=tasks["total"], description=update_stats_desc())
                for subattr in subattrs:
                    name = escape_name(subattr["name"])
                    if name in sub_entries:
                        entry = sub_entries[name]
                        subpath = subattr["path"]
                        is_directory = subattr["is_directory"]
                        if is_directory != entry.is_dir(follow_symlinks=True):
                            print(f"[bold red][FAIL][/bold red] 💩 类型失配（将抛弃）: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{entry.path!r}[/blue underline]")
                            update_failed(1, not is_directory, subattr.get("size"))
                            progress.update(statistics_bar, advance=1, description=update_stats_desc())
                            continue
                        elif is_directory:
                            print(f"[bold yellow][SKIP][/bold yellow] 📂 目录已建: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{entry.path!r}[/blue underline]")
                        elif resume and not is_directory and subattr["size"] == entry.stat().st_size:
                            print(f"[bold yellow][SKIP][/bold yellow] 📝 跳过文件: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{entry.path!r}[/blue underline]")
                            update_success(1, 1, subattr["size"])
                            progress.update(statistics_bar, advance=1, description=update_stats_desc())
                            continue
                    subtask = taskmap[subattr["id"]] = Task(subattr, joinpath(dst_path, name))
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
                    headers=url.get("headers"), # type: ignore
                    make_reporthook=partial(add_report, attr=attr), 
                )
                print(f"[bold green][GOOD][/bold green] 📝 下载文件: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]")
                update_success(1, 1, attr["size"])
            progress.update(statistics_bar, advance=1, description=update_stats_desc())
            del taskmap[attr["id"]]
        except BaseException as e:
            update_errors(e, attr["is_directory"])
            retryable = True
            if isinstance(e, HTTPError):
                retryable = e.status != 404
            if retryable and isinstance(e, URLError):
                print(f"""\
[bold red][FAIL][/bold red] ♻️ 发生错误（将重试）: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]
    ├ {type(e).__qualname__}: {e}""")
                update_retry(1, not attr["is_directory"])
                submit(task)
            else:
                print(f"""\
[bold red][FAIL][/bold red] 💀 发生错误（将抛弃）: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]
{indent(format_exc().strip(), "    ├ ")}""")
                progress.update(statistics_bar, advance=1, description=update_stats_desc())
                update_failed(1, not attr["is_directory"], attr.get("size"))
                raise

    if isinstance(push_id, str):
        if not push_id.strip("/"):
            push_id = 0
        elif not push_id.startswith("0") and push_id.isascii() and push_id.isdecimal():
            push_id = int(push_id)

    with Progress(
        SpinnerColumn(), 
        *Progress.get_default_columns(), 
        TimeElapsedColumn(), 
        MofNCompleteColumn(), 
        TransferSpeedColumn(), 
        FileSizeColumn(), 
    ) as progress:
        print = progress.console.print
        push_attr: dict = relogin_wrap(fs.attr, push_id)
        name = escape_name(push_attr["name"])
        to_path = normpath(to_path)
        if exists(to_path):
            to_path_isdir = isdir(to_path)
            if push_attr["is_directory"]:
                if not to_path_isdir:
                    raise NotADirectoryError(errno.ENOTDIR, f"{to_path!r} is not directory")
                elif not no_root:
                    to_path = joinpath(to_path, name)
                    makedirs(to_path, exist_ok=True)
            elif to_path_isdir:
                to_path = joinpath(to_path, name)
                if isdir(to_path):
                    raise IsADirectoryError(errno.EISDIR, f"{to_path!r} is directory")
        elif no_root:
            makedirs(to_path)
        else:
            to_path = joinpath(to_path, name)
            makedirs(to_path)
        taskmap: dict[int, Task] = {push_attr["id"]: Task(push_attr, to_path)}
        tasks["total"] += 1
        unfinished["total"] += 1
        if push_attr["is_directory"]:
            tasks["dirs"] += 1
            unfinished["dirs"] += 1
        else:
            tasks["files"] += 1
            tasks["size"] += push_attr["size"]
            unfinished["files"] += 1
            unfinished["size"] += push_attr["size"]

        update_stats_desc = cycle_text(("...", "..", ".", ".."), prefix="📊 [cyan bold]statistics[/cyan bold] ", min_length=32 + 23, interval=0.1).__next__
        statistics_bar = progress.add_task(update_stats_desc(), total=1)
        closed = False
        try:
            thread_batch(pull, taskmap.values(), max_workers=max_workers)
            stats["is_completed"] = True
        finally:
            closed = True
            progress.remove_task(statistics_bar)
            stats["elapsed"] = str(datetime.now() - start_time)
            print(f"📊 [cyan bold]statistics:[/cyan bold] {stats}")
    return Result(stats, taskmap)


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
parser.add_argument("-p", "--push-id", default=0, help="115 网盘中的文件或目录的 id 或路径，默认值：0")
parser.add_argument("-t", "--to-path", default=".", help="本地的路径，默认是当前工作目录")
parser.add_argument("-s", "--share-link", nargs="?", help="""\
115 的分享链接
    1. 指定了则从分享链接下载
    2. 不指定则从 115 网盘下载""")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-l", "--lock-dir-methods", action="store_true", 
                    help="对 115 的文件系统进行增删改查的操作（但不包括上传和下载）进行加锁，限制为单线程，这样就可减少 405 响应，以降低扫码的频率")
parser.add_argument("-n", "--no-root", action="store_true", help="下载目录时，直接合并到目标目录，而不是到与源目录同名的子目录")
parser.add_argument("-r", "--resume", action="store_true", help="断点续传")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

