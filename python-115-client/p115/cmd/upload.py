#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = "115 网盘批量上传"

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[2])
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from argparse import RawTextHelpFormatter
    from .init import subparsers

    parser = subparsers.add_parser("upload", description=__doc__, formatter_class=RawTextHelpFormatter)

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple, TypedDict


@dataclass
class Task:
    src_attr: Mapping
    dst_pid: int
    dst_attr: str | Mapping
    times: int = 0
    reasons: list[BaseException] = field(default_factory=list)


class Tasks(TypedDict):
    success: dict[str, Task]
    failed: dict[str, Task]
    unfinished: dict[str, Task]


class Result(NamedTuple):
    stats: dict
    tasks: Tasks


def main(args):
    if args.version:
        from p115 import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    import errno

    from collections.abc import Callable
    from contextlib import contextmanager
    from datetime import datetime
    from functools import partial
    from os import fspath, makedirs, scandir, stat
    from os.path import dirname, exists, expanduser, isdir, join as joinpath, normpath, realpath
    from pathlib import Path
    from sys import exc_info
    from textwrap import indent
    from threading import Lock
    from traceback import format_exc
    from typing import cast, ContextManager
    from urllib.error import URLError
    from warnings import warn

    from concurrenttools import thread_batch
    from p115 import check_response, P115Client
    from posixpatht import split, escape
    from rich.progress import (
        Progress, FileSizeColumn, MofNCompleteColumn, SpinnerColumn, TimeElapsedColumn, TransferSpeedColumn
    )
    from texttools import cycle_text, rotate_text

    cookies = args.cookies
    cookies_path = args.cookies_path
    src_path = args.src_path
    dst_path = args.dst_path
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

    do_request: None | Callable = None
    match use_request:
        case "httpx":
            from httpx import HTTPStatusError as StatusError, RequestError
            def get_status_code(e):
                return e.response.status_code
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
            do_request = partial(requests_request, session=Session())
            def get_status_code(e):
                return e.response.status_code
        case "urllib3":
            from urllib.error import HTTPError as StatusError # type: ignore
            try:
                from urllib3.exceptions import RequestError # type: ignore
                from urllib3_request import request as do_request
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "urllib3", "urllib3_request"], check=True)
                from urllib3.exceptions import RequestError # type: ignore
                from urllib3_request import request as do_request
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
            do_request = partial(urlopen_request, opener=build_opener(HTTPCookieProcessor(client.cookiejar)))
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

    fs = client.get_fs(request=do_request)

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

    def get_path_attr(path) -> dict:
        if isinstance(path, str):
            path = Path(path)
        attr = {
            "path": fspath(path), 
            "name": path.name, 
            "is_directory": path.is_dir(), 
        }
        attr.update(zip(("mode", "inode", "dev", "nlink", "uid", "gid", "size", "atime", "mtime", "ctime"), path.stat()))
        return attr

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
                step = yield
                progress.update(task, description=update_desc(), advance=step)
                progress.update(statistics_bar, description=update_stats_desc(), advance=step, total=tasks["size"])
        finally:
            progress.remove_task(task)

    def work(task: Task, submit):
        src_attr, dst_pid, dst_attr = task.src_attr, task.dst_pid, task.dst_attr
        src_path = src_attr["path"]
        name = dst_attr if isinstance(dst_attr, str) else dst_attr["name"]
        try:
            task.times += 1
            if src_attr["is_directory"]:
                subdattrs: None | dict = None
                try:
                    if isinstance(dst_attr, str):
                        resp = check_response(relogin_wrap(fs.fs_mkdir, name, dst_pid))
                        name = resp["file_name"]
                        dst_id = int(resp["file_id"])
                        task.dst_attr = {"id": dst_id, "parent_id": dst_pid, "name": name, "is_directory": True}
                        subdattrs = {}
                        console_print(f"[bold green][GOOD][/bold green] 📂 创建目录: [blue underline]{src_path!r}[/blue underline] ➜ [blue underline]{name!r}[/blue underline] in {dst_pid}")
                except FileExistsError:
                    dst_attr = task.dst_attr = relogin_wrap(fs.attr, [name], pid=dst_pid, ensure_dir=True)
                if subdattrs is None:
                    dst_id = cast(Mapping, dst_attr)["id"]
                    subdattrs = {
                        (attr["name"], attr["is_directory"]): attr 
                        for attr in relogin_wrap(fs.listdir_attr, dst_id)
                    }
                subattrs = list(map(get_path_attr, scandir(src_path)))
                update_tasks(
                    total=len(subattrs), 
                    files=sum(not a["is_directory"] for a in subattrs), 
                    size=sum(a["size"] for a in subattrs if not a["is_directory"]), 
                )
                progress.update(statistics_bar, description=update_stats_desc())
                pending_to_remove: list[int] = []
                for subattr in subattrs:
                    subname = subattr["name"]
                    subpath = subattr["path"]
                    is_directory = subattr["is_directory"]
                    key = subname, is_directory
                    if key in subdattrs:
                        subdattr = subdattrs[key]
                        subdpath = subdattr["path"]
                        if is_directory:
                            console_print(f"[bold yellow][SKIP][/bold yellow] 📂 目录已建: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{subdpath!r}[/blue underline]")
                            subtask = Task(subattr, dst_id, subdattr)
                        elif resume and subattr["size"] == subdattr["size"] and subattr["mtime"] <= subdattr["ctime"]:
                            console_print(f"[bold yellow][SKIP][/bold yellow] 📝 跳过文件: [blue underline]{subpath!r}[/blue underline] ➜ [blue underline]{subdpath!r}[/blue underline]")
                            update_success(1, 1, subattr["size"])
                            progress.update(statistics_bar, description=update_stats_desc())
                            continue
                        else:
                            subtask = Task(subattr, dst_id, subname)
                            pending_to_remove.append(subdattr["id"])
                    else:
                        subtask = Task(subattr, dst_id, subname)
                    unfinished_tasks[subpath] = subtask
                    submit(subtask)
                if pending_to_remove:
                    for i in range(0, len(pending_to_remove), 1_000):
                        part_ids = pending_to_remove[i:i+1_000]
                        try:
                            resp = relogin_wrap(fs.fs_batch_delete, part_ids)
                            console_print(f"""\
[bold green][DELETE][/bold green] 📝 删除文件列表
    ├ ids({len(part_ids)}) = {part_ids}
    ├ response = {resp}""")
                        except BaseException as e:
                            console_print(f"""[bold yellow][SKIP][/bold yellow] 📝 删除文件列表失败
    ├ ids({len(part_ids)}) = {part_ids}
    ├ reason = [red]{type(e).__module__}.{type(e).__qualname__}[/red]: {e}""")
                update_success(1)
            else:
                # TODO: 以后要支持断点续传，可用 分块上传 和 本地保存进度
                kwargs: dict = {}
                if src_attr["size"] <= 1 << 30: # 1 GB
                    # NOTE: 1 GB 以内使用网页版上传接口，这个接口的优势是上传完成后会自动产生 115 生活事件
                    kwargs["upload_directly"] = None
                elif src_attr["size"] > 1 << 34: # 16 GB
                    # NOTE: 介于 1 GB 和 16 GB 时直接流式上传，超过 16 GB 时，使用分块上传，分块大小 1 GB
                    kwargs["partsize"] = 1 << 30
                resp = client.upload_file(
                    src_path, 
                    name, 
                    pid=dst_pid, 
                    make_reporthook=partial(add_report, attr=src_attr), 
                    **kwargs, 
                )
                if resp.get("status") == 2 and resp.get("statuscode") == 0:
                    prompt = "秒传文件"
                else:
                    prompt = "上传文件"
                console_print(f"""\
[bold green][GOOD][/bold green] 📝 {prompt}: [blue underline]{src_path!r}[/blue underline] ➜ [blue underline]{name!r}[/blue underline] in {dst_pid}
    ├ response = {resp}""")
                update_success(1, 1, src_attr["size"])
            progress.update(statistics_bar, description=update_stats_desc())
            success_tasks[src_path] = unfinished_tasks.pop(src_path)
        except BaseException as e:
            task.reasons.append(e)
            update_errors(e, src_attr["is_directory"])
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
[bold red][FAIL][/bold red] ♻️ 发生错误（将重试）: [blue underline]{src_path!r}[/blue underline] ➜ [blue underline]{name!r}[/blue underline] in {dst_pid}
    ├ [red]{type(e).__module__}.{type(e).__qualname__}[/red]: {e}""")
                update_retry(1, not src_attr["is_directory"])
                submit(task)
            else:
                console_print(f"""\
[bold red][FAIL][/bold red] 💀 发生错误（将抛弃）: [blue underline]{src_path!r}[/blue underline] ➜ [blue underline]{name!r}[/blue underline] in {dst_pid}
{indent(format_exc().strip(), "    ├ ")}""")
                progress.update(statistics_bar, description=update_stats_desc())
                update_failed(1, not src_attr["is_directory"], src_attr.get("size"))
                failed_tasks[src_path] = unfinished_tasks.pop(src_path)
                if len(task.reasons) == 1:
                    raise
                else:
                    raise BaseExceptionGroup("max retries exceed", task.reasons)

    src_attr = get_path_attr(normpath(src_path))
    dst_attr = None
    name = src_attr["name"]
    is_directory = src_attr["is_directory"]
    with Progress(
        SpinnerColumn(), 
        *Progress.get_default_columns(), 
        TimeElapsedColumn(), 
        MofNCompleteColumn(), 
        TransferSpeedColumn(), 
        FileSizeColumn(), 
    ) as progress:
        console_print = progress.console.print
        if isinstance(dst_path, str):
            if dst_path == "0":
                dst_id = 0
            elif not dst_path.startswith("0") and dst_path.isascii() and dst_path.isdecimal():
                dst_id = int(dst_path)
            elif is_directory:
                dst_attr = relogin_wrap(fs.makedirs, dst_path, exist_ok=True)
                dst_path = dst_attr["path"]
                dst_id = dst_attr["id"]
            else:
                dst_dir, name = split(dst_path)
                dst_attr = relogin_wrap(fs.makedirs, dst_dir, exist_ok=True)
                dst_path = dst_attr["path"] + "/" + escape(name)
                dst_id = dst_attr["id"]
        else:
            dst_id = dst_path
        if name and is_directory and not no_root:
            dst_attr = relogin_wrap(fs.makedirs, [name], pid=dst_id, exist_ok=True)
            dst_path = dst_attr["path"]
            dst_id = dst_attr["id"]
        if not dst_attr:
            dst_attr = relogin_wrap(fs.attr, dst_id)
            dst_path = cast(str, dst_attr["path"])
            if is_directory:
                if not dst_attr["is_directory"]:
                    raise NotADirectoryError(errno.ENOTDIR, dst_attr)
            elif dst_attr["is_directory"]:
                dst_path = dst_path + "/" + escape(name)
            else:
                relogin_wrap(fs.remove, dst_attr["id"])
                dst_id = dst_attr["parent_id"]
                name = dst_attr["name"]
        if is_directory:
            task = Task(src_attr, dst_id, dst_attr)
        else:
            task = Task(src_attr, dst_id, name)

        unfinished_tasks: dict[str, Task] = {src_attr["path"]: task}
        success_tasks: dict[str, Task] = {}
        failed_tasks: dict[str, Task] = {}
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
        statistics_bar = progress.add_task(update_stats_desc())
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
parser.add_argument("-p", "--src-path", default=".", help="本地的路径，默认是当前工作目录")
parser.add_argument("-t", "--dst-path", default="/", help="115 网盘中的文件或目录的 id 或路径，默认值：'/'")
parser.add_argument("-m", "--max-workers", default=1, type=int, help="并发线程数，默认值 1")
parser.add_argument("-mr", "--max-retries", default=-1, type=int, 
                    help="""最大重试次数。
    - 如果小于 0（默认），则会对一些超时、网络请求错误进行无限重试，其它错误进行抛出
    - 如果等于 0，则发生错误就抛出
    - 如果大于 0（实际执行 1+n 次，第一次不叫重试），则对所有错误等类齐观，只要次数到达此数值就抛出""")
parser.add_argument("-l", "--lock-dir-methods", action="store_true", 
                    help="对 115 的文件系统进行增删改查的操作（但不包括上传和下载）进行加锁，限制为单线程，这样就可减少 405 响应，以降低扫码的频率")
parser.add_argument("-ur", "--use-request", choices=("httpx", "requests", "urllib3", "urlopen"), default="httpx", help="选择一个网络请求模块，默认值：httpx")
parser.add_argument("-n", "--no-root", action="store_true", help="上传目录时，直接合并到目标目录，而不是到与源目录同名的子目录")
parser.add_argument("-r", "--resume", action="store_true", help="断点续传")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

