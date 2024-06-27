#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 1, 2)
__doc__ = "从 115 的挂载下载文件"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
)
parser.add_argument("-u", "--base-url", default="http://localhost", help="挂载的网址，默认值：http://localhost")
parser.add_argument("-P", "--password", default="", help="挂载的网址的密码，默认值：''，即没密码")
parser.add_argument("-p", "--src-path", default="/", help="115 网盘中的文件或目录的 id 或路径，默认值：'/'")
parser.add_argument("-t", "--dst-path", default=".", help="本地的路径，默认是当前工作目录")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-mr", "--max-retries", default=-1, type=int, 
                    help="""最大重试次数。
    - 如果小于 0（默认），则会对一些超时、网络请求错误进行无限重试，其它错误进行抛出
    - 如果等于 0，则发生错误就抛出
    - 如果大于 0（实际执行 1+n 次，第一次不叫重试），则对所有错误等类齐观，只要次数到达此数值就抛出""")
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
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from gzip import GzipFile
from json import load
from os import makedirs, scandir
from os.path import exists, isdir, join as joinpath, normpath
from pathlib import Path
from platform import system
from textwrap import indent
from threading import Lock
from traceback import format_exc
from typing import cast, ContextManager, NamedTuple, TypedDict
from urllib.error import HTTPError
from urllib.parse import quote, urljoin

try:
    from concurrenttools import thread_batch
    from rich.progress import (
        Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    )
    from texttools import cycle_text, rotate_text
    from urllib3.exceptions import MaxRetryError, RequestError
    from urllib3.poolmanager import PoolManager
    from urllib3_request import request as urllib3_request
    from download import download
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", 
         "python-concurrenttools", "python-texttools", "python-download", "rich", "urllib3_request"], check=True)
    from concurrenttools import thread_batch
    from rich.progress import (
        Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    )
    from texttools import cycle_text, rotate_text
    from urllib3.exceptions import MaxRetryError, RequestError
    from urllib3.poolmanager import PoolManager
    from urllib3_request import request as urllib3_request
    from download import download


urlopen = partial(urllib3_request, pool=PoolManager(num_pools=50))


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
    password: str = "", 
) -> dict:
    params: dict = {"method": "attr"}
    if password:
        params["password"] = password
    if isinstance(id_or_path, int):
        params["id"] = id_or_path
    else:
        params["path"] = id_or_path
    return urlopen(base_url, params=params, parse=True)


def listdir(
    id_or_path: int | str = 0, 
    /, 
    base_url: str = "http://localhost", 
    password: str = "", 
) -> list[dict]:
    params: dict = {"method": "list"}
    if password:
        params["password"] = password
    if isinstance(id_or_path, int):
        params["id"] = id_or_path
    else:
        params["path"] = id_or_path
    return urlopen(base_url, params=params, parse=True)


def main() -> Result:
    base_url = args.base_url
    password = args.password
    src_path = args.src_path
    dst_path = args.dst_path
    max_workers = args.max_workers
    max_retries = args.max_retries
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

                subattrs = listdir(task_id, base_url, password)
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
                download(
                    attr["url"], 
                    dst_path, 
                    resume=resume, 
                    make_reporthook=partial(add_report, attr=attr), 
                    urlopen=urlopen, 
                )
                console_print(f"[bold green][GOOD][/bold green] 📝 下载文件: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]")
                update_success(1, 1, attr["size"])
            progress.update(statistics_bar, advance=1, description=update_stats_desc())
            success_tasks[task_id] = unfinished_tasks.pop(task_id)
        except BaseException as e:
            task.reasons.append(e)
            update_errors(e, attr["is_directory"])
            if max_retries < 0:
                if isinstance(e, HTTPError):
                    retryable = not (400 <= cast(int, e.status) < 500)
                else:
                    retryable = isinstance(e, (MaxRetryError, RequestError))
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

    if isinstance(src_path, str):
        if src_path == "0":
            src_path = "/"
        elif not src_path.startswith("0") and src_path.isascii() and src_path.isdecimal():
            src_path = int(src_path)
    src_attr = attr(src_path, base_url, password)
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
    stats["src_path"] = urljoin(base_url, src_attr["path"])
    stats["dst_path"] = dst_path
    update_tasks(1, not src_attr["is_directory"], src_attr.get("size"))
    with Progress(
        SpinnerColumn(), 
        *Progress.get_default_columns(), 
        TimeElapsedColumn(), 
        MofNCompleteColumn(), 
        TransferSpeedColumn(), 
        FileSizeColumn(), 
    ) as progress:
        update_stats_desc = cycle_text(
            ("...", "..", ".", ".."), 
            prefix="📊 [cyan bold]statistics[/cyan bold] ", 
            min_length=32 + 23, 
            interval=0.1, 
        ).__next__
        statistics_bar = progress.add_task(update_stats_desc(), total=1)
        console_print = progress.console.print
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


if __name__ == "__main__":
    main()

