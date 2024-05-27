#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = "115 文件夹信息遍历导出"

KEYS = (
    "id", "parent_id", "name", "path", "relpath", "sha1", "pickcode", "is_directory", 
    "size", "ctime", "mtime", "atime", "hidden", "violated", "play_long", "thumb", 
    "star", "score", "labels", "description", 
)

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from .init import subparsers

    parser = subparsers.add_parser("iterdir", description=__doc__)


def main(args):
    from p115 import P115FileSystem, P115Path, __version__

    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from os.path import expanduser, dirname, join as joinpath
    from sys import stdout
    from typing import Callable

    cookies = args.cookies
    if not cookies:
        for dir_ in (".", expanduser("~"), dirname(__file__)):
            try:
                cookies = open(joinpath(dir_, "115-cookies.txt")).read()
                if cookies:
                    break
            except FileNotFoundError:
                pass

    fs = P115FileSystem.login(cookies)
    if fs.client.cookies != cookies:
        open("115-cookies.txt", "w").write(fs.client.cookies)

    if args.password and not fs.hidden_mode:
        fs.hidden_switch(True, password=args.password)

    keys = args.keys or KEYS
    output_type = args.output_type

    path = args.path
    if path.isdecimal():
        fid = int(path)
        attr = fs.attr(fid)
    else:
        attr = fs.attr(path)
        fid = attr["id"]
    top_start = len(attr["path"]) + 1

    select = args.select
    if select:
        if select.startswith("lambda "):
            predicate = eval(select)
        else:
            predicate = eval("lambda path:" + select)
    else:
        predicate = None

    path_it = fs.iter(
        fid, 
        predicate=predicate, 
        min_depth=args.min_depth, 
        max_depth=args.max_depth, 
        topdown=True if args.depth_first else None, 
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

    from textwrap import dedent

    dump_code = dedent(args.dump).strip()
    if dump_code:
        if args.dump_exec:
            ns: dict = {}
            exec(dump_code, ns)
            dump = ns["dump"]
        else:
            code = compile(dump_code, "", "eval")
            dump = lambda path: eval(code, {"path": path})
        if output_file:
            write = file.buffer.write
        else:
            write = file.buffer.raw.write # type: ignore
        for path in path_it:
            result = dump(path)
            if not (result is None or isinstance(result, bytes)):
                result = bytes(str(result), "utf-8")
            if result:
                write(result)
                write(b"\n")
        return

    def get_key(path: P115Path, key: str):
        if key == "description":
            return path.desc
        elif key == "relpath":
            return path["path"][top_start:]
        else:
            return path.get(key)

    records = ({k: get_key(p, k) for k in keys} for p in path_it)

    dumps: Callable[..., bytes]
    if output_type in ("log", "json"):
        try:
            from orjson import dumps
        except ImportError:
            odumps: Callable[..., str]
            try:
                from ujson import dumps as odumps
            except ImportError:
                from json import dumps as odumps
            dumps = lambda obj: bytes(odumps(obj, ensure_ascii=False), "utf-8")
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


parser.add_argument("path", nargs="?", default="0", help="文件夹路径或 id，默认值 0，即根目录")
parser.add_argument("-c", "--cookies", help="115 登录 cookie，如果缺失，则从 115-cookies.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
parser.add_argument("-p", "--password", help="密码，用于进入隐藏模式，罗列隐藏文件")
parser.add_argument("-s", "--select", help="提供一个表达式（会注入一个变量 path，类型是 p115.P115Path），用于对路径进行筛选")
parser.add_argument("-k", "--keys", nargs="*", choices=KEYS, help=f"选择输出的 key，默认输出所有可选值")
parser.add_argument("-t", "--output-type", choices=("log", "json", "csv"), default="log", help="""\
输出类型，默认为 log
    - log   每行输出一条数据，每条数据输出为一个 json 的 object
    - json  输出一个 json 的 list，每条数据输出为一个 json 的 object
    - csv   输出一个 csv，第 1 行为表头，以后每行输出一条数据""")
parser.add_argument("-d", "--dump", default="", help="""\
(优先级高于 -k/--keys 和 -t/--output-type) 提供一段代码，每次调用，再行输出，尾部会添加一个 b'\n'。
如果结果 result 是
    - None，跳过
    - bytes，输出
    - 其它，先调用 `bytes(str(result), 'utf-8')`，再输出""")
parser.add_argument("-de", "--dump-exec", action="store_true", help="对 dump 代码进行 exec 解析（必须生成一个变量 dump，用于调用），否则用 eval 解析（会注入一个变量 path，类型是 p115.P115Path）")
parser.add_argument("-o", "--output-file", help="保存到文件，此时命令行会输出进度条")
parser.add_argument("-m", "--min-depth", default=0, type=int, help="最小深度，默认值 0，小于或等于 0 时不限")
parser.add_argument("-M", "--max-depth", default=-1, type=int, help="最大深度，默认值 -1，小于 0 时不限")
parser.add_argument("-dfs", "--depth-first", action="store_true", help="使用深度优先搜索，否则使用广度优先")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

