#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__doc__ = "从 115 的挂载下载文件"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
)
parser.add_argument("-u", "--base-url", default="http://localhost", help="挂载的网址，默认值：http://localhost")
parser.add_argument("-p", "--push-id", default=0, help="对方 115 网盘中的文件或文件夹的 id 或路径，默认值：0")
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

from collections.abc import Iterable, Iterator
from functools import partial
from gzip import GzipFile
from json import load
from itertools import accumulate, count, cycle, repeat
from os import makedirs, scandir
from os.path import exists, isdir, join as joinpath, normpath
from textwrap import indent
from threading import Lock
from time import perf_counter
from traceback import format_exc
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

try:
    from concurrenttools import thread_batch
    from rich.progress import Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    from urlopen import download
    from wcwidth import wcwidth, wcswidth
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "python-concurrenttools", "python-urlopen", "rich", "wcwidth"], check=True)
    from concurrenttools import thread_batch
    from rich.progress import Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    from urlopen import download
    from wcwidth import wcwidth, wcswidth # type: ignore


def attr(
    id_or_path: int | str = 0, 
    /, 
    base_url: str = "http://localhost", 
) -> dict:
    if isinstance(id_or_path, int):
        url = f"{base_url}?id={id_or_path}&method=attr"
    else:
        url = f"{base_url}?path={quote(id_or_path, safe=':/')}&method=attr"
    with urlopen(Request(url, headers={"Accept-Encoding": "gzip"})) as resp:
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
    with urlopen(Request(url, headers={"Accept-Encoding": "gzip"})) as resp:
        if resp.headers.get("Content-Encoding") == "gzip":
            resp = GzipFile(fileobj=resp)
        return load(resp)


def cycle_text(
    text_it: Iterable[str], 
    /, 
    prefix: str = "", 
    interval: float = 0, 
    min_length: int = 0, 
) -> Iterator[str]:
    prefix_len = wcswidth(prefix)
    if prefix:
        ajust_len = min_length - prefix_len
        if ajust_len > 0:
            text_it = (prefix + s + " " * (ajust_len - wcswidth(s)) for s in text_it)
        else:
            text_it = (prefix + s for s in text_it)
    if interval <= 0:
        return cycle(text_it)
    else:
        def wrapper():
            t = perf_counter()
            for p in cycle(text_it):
                yield p
                while (s := perf_counter()) - t < interval:
                    yield p
                t = s
        return wrapper()


def rotate_text(
    text: str, 
    length: int = 10, 
    interval: float = 0, 
) -> Iterator[str]:
    if length < 0:
        length = 0
    wcls = list(map(wcwidth, text))
    diff = sum(wcls) - length
    if diff <= 0:
        return repeat(text + " " * -diff)
    if all(v == 1 for v in wcls):
        del wcls
        if length <= 1:
            def wrap():
                yield from text
        else:
            def wrap():
                for i in range(diff + 1):
                    yield text[i:i+length]
                for j in range(1, length):
                    yield text[i+j:] + " " * j
    else:
        wcm = tuple(dict(zip(accumulate(wcls), count(1))).items())
        del wcls
        if length <= 1:
            def wrap():
                nonlocal wcm
                i = 0
                for _, j in wcm:
                    yield text[i:j]
                    i = j
                del wcm
        else:
            def wrap():
                nonlocal wcm
                size = len(wcm)
                for n, (right, j) in enumerate(wcm):
                    if right > length:
                        if n == 0:
                            break
                        n -= 1
                        right, j = wcm[n]
                        break
                if n == 0:
                    yield text[:j]
                else:
                    yield text[:j] + " " * (length - right)
                for m, (left, i) in enumerate(wcm):
                    while (right - left) < length:
                        n += 1
                        if n == size:
                            break
                        right, j = wcm[n]
                    if n == size:
                        break
                    if right - left == length:
                        yield text[i:j]
                    elif n - m == 1:
                        yield text[i:j]
                    else:
                        n -= 1
                        right, j = wcm[n]
                        yield text[i:j] + " " * (length - diff)
                for left, i in wcm[m:-1]:
                    yield text[i:] + " " * (left - diff)
                del wcm
    return cycle_text(wrap(), interval=interval)


def main() -> dict:
    base_url = args.base_url
    push_id = args.push_id
    to_path = args.to_path
    max_workers = args.max_workers
    resume = args.resume
    no_root = args.no_root

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
    count_lock = Lock()

    def add_report(_, attr):
        update_desc = rotate_text(attr["name"], 32, interval=0.1).__next__
        task = progress.add_task(update_desc(), total=attr["size"])
        try:
            while not closed:
                progress.update(task, description=update_desc(), advance=(yield))
        finally:
            progress.remove_task(task)

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
                progress.update(statistics_bar, total=tasks["total"], description=update_stats_desc())
                for subattr in subattrs:
                    name = subattr["name"]
                    if name in sub_entries:
                        entry = sub_entries[name]
                        subpath = subattr["path"]
                        is_directory = subattr["is_directory"]
                        if is_directory != entry.is_dir(follow_symlinks=True):
                            print(f"[bold red][FAIL][/bold red] 💩 类型失配（将抛弃）: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{entry.path!r}[/blue underline]")
                            with count_lock:
                                failed["total"] += 1
                                unfinished["total"] -= 1
                                if is_directory:
                                    failed["dirs"] += 1
                                    unfinished["dirs"] -= 1
                                else:
                                    failed["files"] += 1
                                    unfinished["files"] -= 1
                            progress.update(statistics_bar, advance=1, description=update_stats_desc())
                            continue
                        elif is_directory:
                            print(f"[bold yellow][SKIP][/bold yellow] 📂 目录已建: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{entry.path!r}[/blue underline]")
                        elif resume and not is_directory and subattr["size"] == entry.stat().st_size:
                            print(f"[bold yellow][SKIP][/bold yellow] 📝 跳过文件: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{entry.path!r}[/blue underline]")
                            with count_lock:
                                success["total"] += 1
                                success["files"] += 1
                                unfinished["total"] -= 1
                                unfinished["files"] -= 1
                            progress.update(statistics_bar, advance=1, description=update_stats_desc())
                            continue
                    subtask = taskmap[subattr["id"]] = (subattr, joinpath(dst_path, name))
                    submit(subtask)
            else:
                download(
                    attr["url"], 
                    dst_path, 
                    resume=resume, 
                    make_reporthook=partial(add_report, attr=attr), 
                )
                print(f"[bold green][GOOD][/bold green] 📝 下载文件: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]")
            with count_lock:
                success["total"] += 1
                unfinished["total"] -= 1
                if attr["is_directory"]:
                    success["dirs"] += 1
                    unfinished["dirs"] -= 1
                else:
                    success["files"] += 1
                    unfinished["files"] -= 1
            progress.update(statistics_bar, advance=1, description=update_stats_desc())
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
            if isinstance(e, HTTPError):
                retryable = e.status != 404
            if retryable and isinstance(e, URLError):
                print(f"""\
[bold red][FAIL][/bold red] ♻️ 发生错误（将重试）: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]
    ├ {type(e).__qualname__}: {e}""")
                submit(task)
            else:
                print(f"""\
[bold red][FAIL][/bold red] 💀 发生错误（将抛弃）: [blue underline]{attr['path']!r}[/blue underline] ➜ [blue underline]{dst_path!r}[/blue underline]
{indent(format_exc().strip(), "    ├ ")}""")
                with count_lock:
                    failed["total"] += 1
                    unfinished["total"] -= 1
                    if attr["is_directory"]:
                        failed["dirs"] += 1
                        unfinished["dirs"] -= 1
                    else:
                        failed["files"] += 1
                        unfinished["files"] -= 1
                progress.update(statistics_bar, advance=1, description=update_stats_desc())
                raise

    if isinstance(push_id, str):
        if not push_id.strip("/"):
            push_id = 0
        elif not push_id.startswith("0") and push_id.isascii() and push_id.isdecimal():
            push_id = int(push_id)

    push_attr: dict = attr(push_id, base_url)
    to_path = normpath(to_path)
    if exists(to_path):
        to_path_isdir = isdir(to_path)
        if push_attr["is_directory"]:
            if not to_path_isdir:
                raise NotADirectoryError(errno.ENOTDIR, f"{to_path!r} is not directory")
            elif not no_root:
                to_path = joinpath(to_path, push_attr["name"])
                makedirs(to_path, exist_ok=True)
        elif to_path_isdir:
            to_path = joinpath(to_path, push_attr["name"])
            if isdir(to_path):
                raise IsADirectoryError(errno.EISDIR, f"{to_path!r} is directory")
    elif no_root:
        makedirs(to_path)
    else:
        to_path = joinpath(to_path, push_attr["name"])
        makedirs(to_path)
    taskmap: dict[int, tuple[dict, str]] = {push_attr["id"]: (push_attr, to_path)}
    tasks["total"] += 1
    unfinished["total"] += 1
    if push_attr["is_directory"]:
        tasks["dirs"] += 1
        unfinished["dirs"] += 1
    else:
        tasks["files"] += 1
        unfinished["files"] += 1
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
            thread_batch(pull, taskmap.values(), max_workers=max_workers)
            stats["is_completed"] = True
        finally:
            closed = True
            progress.remove_task(statistics_bar)
            print(f"📊 [cyan bold]statistics:[/cyan bold] {stats}")
    return stats


if __name__ == "__main__":
    main()

