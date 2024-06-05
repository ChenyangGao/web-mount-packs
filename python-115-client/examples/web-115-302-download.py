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

from collections.abc import Iterator
from functools import partial
from gzip import GzipFile
from json import load
from itertools import accumulate, count, cycle, repeat
from os import makedirs, scandir
from os.path import exists, isdir, join as joinpath, normpath
from textwrap import indent
from time import perf_counter
from traceback import format_exc
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

try:
    from concurrenttools import thread_pool_batch
    from rich.progress import Progress, SpinnerColumn, MofNCompleteColumn
    from urlopen import download
    from wcwidth import wcwidth
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "python-concurrenttools", "python-urlopen", "rich", "wcwidth"], check=True)
    from concurrenttools import thread_pool_batch
    from rich.progress import Progress, SpinnerColumn, MofNCompleteColumn
    from urlopen import download
    from wcwidth import wcwidth # type: ignore


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
    if interval <= 0:
        return cycle(wrap())
    else:
        def wrapper():
            t = perf_counter()
            for p in cycle(wrap()):
                yield p
                while (s := perf_counter()) - t < interval:
                    yield p
                t = s
        return wrapper()


def main():
    base_url = args.base_url
    push_id = args.push_id
    to_path = args.to_path
    max_workers = args.max_workers
    resume = args.resume
    no_root = args.no_root

    def add_report(_, attr):
        it = rotate_text(attr["name"], 32, interval=0.1)
        task = progress.add_task(next(it), total=attr["size"])
        try:
            while not closed:
                progress.update(task, description=next(it), advance=(yield))
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
                    print(f"[bold green][GOOD][/bold green] 创建目录: {attr['path']!r} ➜ {dst_path!r}")
                for subattr in listdir(attr["id"], base_url):
                    name = subattr["name"]
                    if name in sub_entries:
                        entry = sub_entries[name]
                        subpath = subattr["path"]
                        is_directory = subattr["is_directory"]
                        if is_directory != entry.is_dir(follow_symlinks=True):
                            print(f"[bold red][FAIL][/bold red] 类型失配（将抛弃）: {subpath!r} ➜ {entry.path!r}")
                            continue
                        elif is_directory:
                            print(f"[bold yellow][SKIP][/bold yellow] 跳过目录: {subpath!r} ➜ {entry.path!r}")
                        elif resume and not is_directory and subattr["size"] == entry.stat().st_size:
                            print(f"[bold yellow][SKIP][/bold yellow] 跳过文件: {subpath!r} ➜ {entry.path!r}")
                            continue
                    submit((subattr, joinpath(dst_path, name)))
            else:
                download(
                    attr["url"], 
                    dst_path, 
                    resume=resume, 
                    make_reporthook=partial(add_report, attr=attr), 
                )
                print(f"[bold green][GOOD][/bold green] 下载文件: {attr['path']!r} ➜ {dst_path!r}")
        except BaseException as e:
            retryable = True
            if isinstance(e, HTTPError):
                retryable = e.status != 404
            if retryable and isinstance(e, URLError):
                print(f"""\
[bold red][FAIL][/bold red] 发生错误（将重试）: {attr['path']!r} ➜ {dst_path!r}
    ├ {type(e).__qualname__}: {e}""")
                submit(task)
            else:
                print(f"""\
[bold red][FAIL][/bold red] 发生错误（将抛弃）: {attr['path']!r} ➜ {dst_path!r}
{indent(format_exc().strip(), "    ├ ")}""")
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
    try:
        closed = False
        with Progress(
            SpinnerColumn(), 
            *Progress.get_default_columns(), 
            MofNCompleteColumn(), 
        ) as progress:
            print = progress.console.print
            thread_pool_batch(pull, [(push_attr, to_path)], max_workers=max_workers)
    finally:
        closed = True


if __name__ == "__main__":
    main()

