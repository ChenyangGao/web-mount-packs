#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="目录树工具集", formatter_class=RawTextHelpFormatter)
parser.set_defaults(func=None)

subparsers = parser.add_subparsers()

KEYS = ("inode", "name", "path", "relpath", "isdir", "islink", "stat")

parser_iter = subparsers.add_parser("iter", description="目录树信息遍历导出")

parser_iter.add_argument("path", nargs="?", default="", help="文件夹路径，默认为当前工作目录")
parser_iter.add_argument("-s", "--select", help="提供一个表达式（会注入一个变量 path，类型是 pathlib.Path），用于对路径进行筛选")
parser_iter.add_argument("-m", "--min-depth", default=0, type=int, help="最小深度，默认值 0，小于 0 时不限")
parser_iter.add_argument("-M", "--max-depth", default=-1, type=int, help="最大深度，默认值 -1，小于 0 时不限")
parser_iter.add_argument("-v", "--version", action="store_true", help="输出版本号")

parser_iter.add_argument("-k", "--keys", nargs="*", choices=KEYS, help=f"选择输出的 key，默认输出所有可选值")
parser_iter.add_argument("-t", "--output-type", choices=("log", "json", "csv"), default="log", help="""\
输出类型，默认为 log
- log   每行输出一条数据，每条数据输出为一个 json 的 object
- json  输出一个 json 的 list，每条数据输出为一个 json 的 object
- csv   输出一个 csv，第 1 行为表头，以后每行输出一条数据
""")
parser_iter.add_argument("-o", "--output-file", help="保存到文件，此时命令行会输出进度条")
parser_iter.add_argument("-dfs", "--depth-first", action="store_true", help="使用深度优先搜索，否则使用广度优先")
parser_iter.add_argument("-fl", "--follow-symlinks", action="store_true", help="是否跟进符号连接（如果为否，则会把符号链接视为文件，即使它指向目录）")

def main_iter(args):
    from iterdir import __version__, iterdir, DirEntry

    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from collections.abc import Callable, Iterator
    from os import fsdecode, lstat, stat, stat_result, PathLike
    from os.path import abspath, isdir, islink, relpath
    from operator import attrgetter
    from pathlib import Path
    from sys import stdout
    from typing import Optional

    STAT_FIELDS = tuple(
        f for f in dir(stat_result) 
        if f.startswith("st_")
    )

    def stat_to_dict(
        path: None | bytes | str | PathLike = None, 
        /, 
        follow_symlinks: bool = False, 
    ) -> Optional[dict]:
        getstat: Callable[[bytes | str | PathLike], stat_result]
        if follow_symlinks:
            getstat = stat
        else:
            getstat = lstat
        try:
            return dict(zip(
                STAT_FIELDS, 
                attrgetter(*STAT_FIELDS)(getstat(path or ".")), 
            ))
        except OSError:
            return None

    select = args.select
    predicate: Optional[Callable[[DirEntry], Optional[bool]]]
    if select:
        if select.startswith("lambda "):
            pred = eval(select)
        else:
            pred = eval("lambda path:" + select)
        predicate = lambda e: pred(Path(fsdecode(e)))
    else:
        predicate = None

    path = args.path
    top = abspath(path)
    fmap: dict[str, Callable] = {
        "inode": DirEntry.inode, 
        "name": lambda e: e.name, 
        "path": lambda e: e.path, 
        "relpath": lambda e: relpath(abspath(e), top), 
        "isdir": isdir, 
        "islink": islink, 
        "stat": stat_to_dict, 
    }

    keys = args.keys or KEYS
    if keys:
        fmap = {k: fmap[k] for k in keys if k in fmap}

    path_it: Iterator[DirEntry] = iterdir(
        DirEntry(path), 
        topdown=True if args.depth_first else None, 
        min_depth=args.min_depth, 
        max_depth=args.max_depth, 
        predicate=predicate, 
        follow_symlinks=args.follow_symlinks, 
    )

    output_file = args.output_file
    if output_file:
        from collections import deque
        from time import perf_counter

        def format_time(t):
            m, s = divmod(t, 60)
            if m < 60:
                return f"{m:02.0f}:{s:09.06f}"
            h, m = divmod(m, 60)
            if h < 24:
                return f"{h:02.0f}:{m:02.0f}:{s:09.06f}"
            d, h = divmod(h, 60)
            return f"{d}d{h:02.0f}:{m:02.0f}:{s:09.06f}"

        def progress(it):
            write = stdout.buffer.raw.write # type: ignore
            dq: deque[tuple[int, float]] = deque(maxlen=10*60)
            push = dq.append
            total = 0
            ndirs = 0
            nfiles = 0
            start_t = last_t = perf_counter()
            write(f"\r\x1b[K🗂️  {total} = 📂 {ndirs} + 📝 {nfiles}".encode())
            push((total, start_t))
            for p in it:
                total += 1
                if p.is_dir():
                    ndirs += 1
                else:
                    nfiles += 1
                cur_t = perf_counter()
                if cur_t - last_t > 0.1:
                    speed = (total - dq[0][0]) / (cur_t - dq[0][1])
                    write(f"\r\x1b[K🗂️  {total} = 📂 {ndirs} + 📝 {nfiles} | 🕙 {format_time(cur_t-start_t)} | 🚀 {speed:.3f} it/s".encode())
                    push((total, cur_t))
                    last_t = cur_t
                yield p
            cur_t = perf_counter()
            speed = total / (cur_t - start_t)
            write(f"\r\x1b[K🗂️  {total} = 📂 {ndirs} + 📝 {nfiles} | 🕙 {format_time(cur_t-start_t)} | 🚀 {speed:.3f} it/s".encode())
        file = open(output_file, "w")
        path_it = iter(progress(path_it))
    else:
        file = stdout # type: ignore

    records = ({k: f(e) for k, f in fmap.items()} for e in path_it)

    output_type = args.output_type
    dumps: Callable[..., bytes]
    if output_type in ("log", "json"):
        try:
            from orjson import dumps
        except ImportError:
            odumps: Callable
            try:
                from ujson import dumps as odumps
            except ImportError:
                from json import dumps as odumps
            dumps = lambda obj, /: bytes(odumps(obj, ensure_ascii=False), "utf-8")
        if output_file:
            write = file.buffer.write
        else:
            write = file.buffer.raw.write # type: ignore

    try:
        if output_type == "json":
            write(b"[")
            for i, record in enumerate(records):
                if i:
                    write(b", ")
                write(dumps(record))
            write(b"]")
        elif output_type == "log":
            for record in records:
                write(dumps(record))
                write(b"\n")
        else:
            from csv import DictWriter

            writer = DictWriter(file, fieldnames=keys)
            writer.writeheader()
            for record in records:
                writer.writerow(record)
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:
        from sys import stderr
        stderr.close()
    finally:
        file.close()

parser_iter.set_defaults(func=main_iter)

parser_stats = subparsers.add_parser("stats", description="目录树遍历统计")

parser_stats.add_argument("paths", nargs="*", help="文件夹路径，多个用空格隔开，默认从 stdin 读取")
parser_stats.add_argument("-s", "--select", help="提供一个表达式（会注入一个变量 path，类型是 pathlib.Path），用于对路径进行筛选")
parser_stats.add_argument("-m", "--min-depth", default=0, type=int, help="最小深度，默认值 0，小于 0 时不限")
parser_stats.add_argument("-M", "--max-depth", default=-1, type=int, help="最大深度，默认值 -1，小于 0 时不限")
parser_stats.add_argument("-v", "--version", action="store_true", help="输出版本号")

def main_stats(args):
    from json import dumps
    from iterdir import __version__, DirEntry, statsdir

    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from collections.abc import Callable, Iterable
    from os import fsdecode
    from pathlib import Path
    from typing import Optional

    select = args.select
    predicate: Optional[Callable[[DirEntry], Optional[bool]]]
    if select:
        if select.startswith("lambda "):
            pred = eval(select)
        else:
            pred = eval("lambda path:" + select)
        predicate = lambda e: pred(Path(fsdecode(e)))
    else:
        predicate = None

    paths: Iterable[str]
    if args.paths:
        paths = args.paths
    else:
        from sys import stdin
        paths = (path.removesuffix("\n") for path in stdin)

    try:
        for path in paths:
            print(
                dumps(
                    statsdir(
                        path, 
                        min_depth=args.min_depth, 
                        max_depth=args.max_depth, 
                        predicate=predicate, 
                    ), 
                    ensure_ascii=False, 
                ), 
                flush=True, 
            )
    except BrokenPipeError:
        from sys import stderr
        stderr.close()
    except (EOFError, KeyboardInterrupt):
        pass

parser_stats.set_defaults(func=main_stats)

args = parser.parse_args()
if args.func:
    args.func(args)
else:
    parser.parse_args(["-h"])

