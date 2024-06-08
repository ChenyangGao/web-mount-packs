#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__doc__ = "从 115 的挂载下载文件"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
)
parser.add_argument("-u", "--base-url", default="http://localhost", help="挂载的网址，默认值：http://localhost")
parser.add_argument("-p", "--push-id", default=0, help="115 网盘中的文件或目录的 id 或路径，默认值：0")
parser.add_argument("-t", "--to-path", default=".", help="本地的路径，默认是当前工作目录")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-n", "--no-root", action="store_true", help="下载目录时，直接合并到目标目录，而不是到与源目录同名的子目录")
parser.add_argument("-r", "--resume", action="store_true", help="断点续传")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
args = parser.parse_args()
if args.version:
    print(".".join(map(str, __version__)))
    raise SystemExit(0)

import errno

from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from gzip import GzipFile
from json import load
from os import makedirs, scandir
from os.path import exists, isdir, join as joinpath, normpath
from platform import system
from textwrap import indent
from threading import Lock
from traceback import format_exc
from typing import ContextManager, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

try:
    from concurrenttools import thread_batch
    from rich.progress import (
        Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    )
    from texttools import cycle_text, rotate_text
    from urlopen import download
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", 
         "python-concurrenttools", "python-texttools", "python-urlopen", "rich"], check=True)
    from concurrenttools import thread_batch
    from rich.progress import (
        Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    )
    from texttools import cycle_text, rotate_text
    from urlopen import download


class Task(NamedTuple):
    src_attr: Mapping
    dst_path: str


class Result(NamedTuple):
    stats: dict
    unfinished_tasks: dict[int, Task]


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


def attr(
    id_or_path: int | str = 0, 
    /, 
    base_url: str = "http://localhost", 
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
    /, 
    base_url: str = "http://localhost", 
) -> list[dict]:
    if isinstance(id_or_path, int):
        url = f"{base_url}?id={id_or_path}&method=list"
    else:
        url = f"{base_url}?path={quote(id_or_path, safe=':/')}&method=list"
    with urlopen(Request(url, headers={"Accept-Encoding": "gzip"}), timeout=60) as resp:
        if resp.headers.get("Content-Encoding") == "gzip":
            resp = GzipFile(fileobj=resp)
        return load(resp)


def main() -> Result:
    base_url = args.base_url
    push_id = args.push_id
    to_path = args.to_path
    max_workers = args.max_workers
    resume = args.resume
    no_root = args.no_root
    if max_workers <= 0:
        max_workers = 1
    count_lock = Lock() if max_workers > 1 else None

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

    def work(task, submit):
        attr, dst_path = task
        try:
            if attr["is_directory"]:
                try:
                    sub_entries = {entry.name: entry for entry in scandir(dst_path)}
                except FileNotFoundError:
                    makedirs(dst_path, exist_ok=True)
                    sub_entries = {}
                    print(f"[bold green][GOOD][/bold green] 📂 创建目录: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]")

                subattrs = listdir(attr["id"], base_url)
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
                download(
                    attr["url"], 
                    dst_path, 
                    resume=resume, 
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

    push_attr: dict = attr(push_id, base_url)
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
    with Progress(
        SpinnerColumn(), 
        *Progress.get_default_columns(), 
        TimeElapsedColumn(), 
        MofNCompleteColumn(), 
        TransferSpeedColumn(), 
        FileSizeColumn(), 
    ) as progress:
        update_stats_desc = cycle_text(("...", "..", ".", ".."), prefix="📊 [cyan bold]statistics[/cyan bold] ", min_length=32 + 23, interval=0.1).__next__
        statistics_bar = progress.add_task(update_stats_desc(), total=1)
        print = progress.console.print
        closed = False
        try:
            thread_batch(work, taskmap.values(), max_workers=max_workers)
            stats["is_completed"] = True
        finally:
            closed = True
            progress.remove_task(statistics_bar)
            print(f"📊 [cyan bold]statistics:[/cyan bold] {stats}")
    return Result(stats, taskmap)


if __name__ == "__main__":
    main()

