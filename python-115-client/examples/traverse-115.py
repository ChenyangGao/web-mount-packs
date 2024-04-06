#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)

KEYS = (
    "id", "parent_id", "name", "path", "sha1", "pickcode", "is_directory", 
    "size", "ctime", "mtime", "atime", "thumb", "star", 
)

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="115 文件夹信息遍历导出", formatter_class=RawTextHelpFormatter)
parser.add_argument("path", nargs="?", default="0", help="文件夹路径或 id，默认值 0，即根目录")
parser.add_argument("-c", "--cookie", help="115 登录 cookie，如果缺失，则从 115-cookie.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
parser.add_argument("-k", "--keys", nargs="*", choices=KEYS, help=f"选择输出的 key，默认输出所有可选值")
parser.add_argument("-s", "--select", help="提供一个表达式（会注入一个变量 path，类型是 p115.P115Path），用于对路径进行筛选")
parser.add_argument("-t", "--output-type", choices=("log", "json", "csv"), default="log", help="""输出类型，默认为 json
- log   每行输出一条数据，每条数据输出为一个 json 的 object
- json  输出一个 json 的 list，每条数据输出为一个 json 的 object
- csv   输出一个 csv，第 1 行为表头，以后每行输出一条数据
""")
parser.add_argument("-o", "--output-file", help="保存到文件，此时命令行会输出进度条")
parser.add_argument("-m", "--min-depth", default=0, type=int, help="最小深度，默认值 0，小于 0 时不限")
parser.add_argument("-M", "--max-depth", default=-1, type=int, help="最大深度，默认值 -1，小于 0 时不限")
parser.add_argument("-dfs", "--depth-first", action="store_true", help="使用深度优先搜索，否则使用广度优先")
args = parser.parse_args()

try:
    from p115 import P115FileSystem
except ImportError:
    from subprocess import run
    from sys import executable
    run([executable, "-m", "pip", "install", "python-115"], check=True)
    from p115 import P115FileSystem

from os.path import expanduser, dirname, join as joinpath


cookie = args.cookie
if not cookie:
    for dir_ in (".", expanduser("~"), dirname(__file__)):
        try:
            cookie = open(joinpath(dir_, "115-cookie.txt")).read()
            if cookie:
                break
        except FileNotFoundError:
            pass

fs = P115FileSystem.login(cookie)
if fs.client.cookie != cookie:
    open("115-cookie.txt", "w").write(fs.client.cookie)

keys = args.keys or KEYS
output_type = args.output_type

path = args.path
if path.isdecimal():
    fid = int(path)
else:
    attr = fs.attr(path)
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
    try:
        from tqdm import tqdm
    except ImportError:
        run([executable, "-m", "pip", "install", "tqdm"], check=True)
        from tqdm import tqdm
    file = open(output_file, "w")
    path_it = iter(tqdm(path_it))
else:
    from sys import stdout as file # type: ignore

records = ({k: p.get(k) for k in keys} for p in path_it)

try:
    if output_type == "json":
        from json import dumps
        write = file.buffer.write
        write(b"[")
        for i, record in enumerate(records):
            if i:
                write(b", ")
            write(bytes(dumps(record, ensure_ascii=False), "utf-8"))
        write(b"]")
    elif output_type == "log":
        from json import dumps
        write = file.buffer.write
        flush = file.buffer.flush
        for record in records:
            write(bytes(dumps(record, ensure_ascii=False), "utf-8"))
            write(b"\n")
            flush()
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

