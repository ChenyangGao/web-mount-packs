#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["main"]
__doc__ = "遍历并导出 115 目录信息"

from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from pathlib import Path

if __name__ == "__main__":
    path[0] = str(Path(__file__).parents[2])
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from .init import subparsers

    parser = subparsers.add_parser("iterdir", description=__doc__, formatter_class=RawTextHelpFormatter)

from collections import UserString
from collections.abc import Callable
from functools import partial
from hashlib import algorithms_available
from sys import path, stderr, stdout
from typing import Final

from p115 import AVAILABLE_APPS
from posixpatht import joins


BASE_KEYS: Final = (
    "is_directory", "id", "parent_id", "pickcode", "name", "size", "sha1", "labels", 
    "score", "ico", "mtime", "user_utime", "ctime", "user_ptime", "atime", "user_otime", 
    "utime", "star", "is_shortcut", "hidden", "has_desc", "violated", "status", "class", 
    "thumb", "video_type", "play_long", "current_time", "last_time", "played_end", "path", 
)
EXTRA_KEYS: Final = (
    "ancestors", "relpath", "desc", "url", # "hashes", 
)


def default(obj, /):
    if isinstance(obj, UserString):
        return str(obj)
    return NotImplemented


def parse_args(argv: None | list[str] = None, /) -> Namespace:
    args = parser.parse_args(argv)
    if args.version:
        from p115 import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args


def main(argv: None | list[str] | Namespace = None, /):
    if isinstance(argv, Namespace):
        args = argv
    else:
        args = parse_args(argv)

    from orjson import dumps
    from p115.component import P115Client, P115Path

    if not (cookies := args.cookies):
        if cookies_path := args.cookies_path:
            cookies = Path(cookies_path)
        else:
            cookies = Path("115-cookies.txt")
    client = P115Client(cookies, check_for_relogin=True)

    do_request: None | Callable
    match args.use_request:
        case "httpx":
            do_request = None
        case "requests":
            try:
                from requests import Session
                from requests_request import request as requests_request
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "requests", "requests_request"], check=True)
                from requests import Session
                from requests_request import request as requests_request
            do_request = partial(requests_request, session=Session())
        case "urllib3":
            try:
                from urllib3_request import request as do_request
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "urllib3", "urllib3_request"], check=True)
                from urllib3_request import request as do_request
        case "urlopen":
            try:
                from urlopen import request as urlopen_request
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "python-urlopen"], check=True)
                from urlopen import request as urlopen_request
            do_request = partial(urlopen_request, cookies=client.cookiejar)

    fs = client.get_fs(request=do_request)

    if args.password and not fs.hidden_mode():
        fs.hidden_switch(True, password=args.password)

    has_base_keys: bool = False
    keys: list[str] = args.keys or []
    if args.kind_keys:
        if keys:
            if "*" in keys:
                has_base_keys = True
                keys.remove("*")
            else:
                for k in ("id", "parent_id", "pickcode", "name", "path", "size", "sha1", "is_directory"):
                    if k not in keys:
                        keys.append(k)
        else:
            keys = ["id", "parent_id", "pickcode", "name", "path", "size", "sha1", "is_directory"]
    elif keys:
        if "*" in keys:
            has_base_keys = True
            keys.remove("*")
    else:
        has_base_keys = True

    hash_types = args.hash_types
    output_type = args.output_type
    fpath = args.path
    if fpath == "0" or not fpath.startswith("0") and fpath.isdecimal():
        fid = int(fpath)
        attr = fs.attr(fid)
    else:
        attr = fs.attr(fpath)
        fid = attr["id"]

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
        # TODO: 写一个单独的模块，用来保存这个函数
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
        file = open(output_file, "w", newline="")
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
        for fpath in path_it:
            result = dump(fpath)
            if not (result is None or isinstance(result, bytes)):
                result = bytes(str(result), "utf-8")
            if result:
                write(result)
                write(b"\n")
        return

    def convert_hash(h, /):
        if isinstance(h, int):
            return h
        elif isinstance(h, bytes):
            return h.hex()
        else:
            return h.hexdigest()

    def get_keys(path: P115Path):
        d = {}
        if has_base_keys:
            for k in BASE_KEYS:
                try:
                    d[k] = path[k]
                except KeyError:
                    pass
        for k in keys:
            if k in d:
                continue
            match k:
                case "ancestors":
                    d[k] = path["path"].ancestors
                case "relpath":
                    if fid == 0:
                        d[k] = path.path[1:]
                    else:
                        ancestors = path["path"].ancestors
                        for i, a in enumerate(ancestors):
                            if a["id"] == fid:
                                break
                        d[k] = joins([a["name"] for a in ancestors[i+1:]])
                case "desc":
                    d[k] = path.desc if path.get("has_desc") else ""
                case "url":
                    d[k] = None if path.is_dir() else path.url
                case _:
                    d[k] = path.get(k)
        if hash_types:
            if path.is_dir():
                d["hashes"] = None
            else:
                d["hashes"] = {k: convert_hash(h) for k, h in zip(hash_types, path.hashes(*hash_types)[1])}
        return d

    records = map(get_keys, path_it)

    if output_type in ("log", "json"):
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
                write(dumps(record, default=default))
            write(b"]")
        elif output_type == "log":
            for record in records:
                write(dumps(record, default=default))
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
        stderr.close()
    finally:
        file.close()


parser.add_argument("path", nargs="?", default="0", help="文件夹路径或 id，默认值 0，即根目录")
parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -cp/--cookies-path")
parser.add_argument("-cp", "--cookies-path", help="cookies 文件保存路径，默认为当前工作目录下的 115-cookies.txt")
parser.add_argument("-p", "--password", help="密码，用于进入隐藏模式，罗列隐藏文件")
parser.add_argument("-s", "--select", help="提供一个表达式（会注入一个变量 path，类型是 p115.P115Path），用于对路径进行筛选")
parser.add_argument("-k", "--keys", metavar="key", nargs="*", choices=("*", *BASE_KEYS, *EXTRA_KEYS), help=f"""\
选择输出的 key。默认为 '*'，会输出 [基本 keys] 并忽略其中未能获得的 key。如果自行选择 key，则被选中的每个 key 的默认值是 None
- 基本 keys: {BASE_KEYS}
- 扩展 keys: {EXTRA_KEYS}
""")
parser.add_argument("-kk", "--kind-keys", action="store_true", 
                    help="帮你选好的一组 key，相当于：-k id parent_id pickcode name path size sha1 is_directory")
parser.add_argument("-hs", "--hash-types", metavar="hashalg", nargs="*", choices=("crc32", "ed2k", *algorithms_available), 
                    help="选择哈希算法进行计算，会增加一个扩展 key 'hashes'，值为一个字典，key 是算法名，值是计算出的十六进制值")
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
parser.add_argument("-de", "--dump-exec", action="store_true", 
                    help="对 dump 代码进行 exec 解析（必须生成一个变量 dump，用于调用），否则用 eval 解析（会注入一个变量 path，类型是 p115.P115Path）")
parser.add_argument("-o", "--output-file", help="保存到文件，此时命令行会输出进度条")
parser.add_argument("-m", "--min-depth", default=0, type=int, help="最小深度，默认值 0，小于或等于 0 时不限")
parser.add_argument("-M", "--max-depth", default=-1, type=int, help="最大深度，默认值 -1，小于 0 时不限")
parser.add_argument("-dfs", "--depth-first", action="store_true", help="使用深度优先搜索，否则使用广度优先")
parser.add_argument("-ur", "--use-request", choices=("httpx", "requests", "urllib3", "urlopen"), default="httpx", help="选择一个网络请求模块，默认值：httpx")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    main()

