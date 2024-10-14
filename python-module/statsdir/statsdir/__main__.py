#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "目录树遍历统计"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)

parser.add_argument("paths", nargs="*", help="文件夹路径，多个用空格隔开，默认从 stdin 读取")
parser.add_argument("-m", "--min-depth", default=0, type=int, help="最小深度，默认值 0，小于 0 时不限")
parser.add_argument("-M", "--max-depth", default=-1, type=int, help="最大深度，默认值 -1，小于 0 时不限")
parser.add_argument("-s", "--select", default="", help="对路径进行筛选，提供一个表达式（会注入一个变量 path，类型是 pathlib.Path）或函数（会传入一个参数，类型是 pathlib.Path）")
parser.add_argument("-se", "--select-exec", action="store_true", help="对 -s/--select 传入的代码用 exec 运行，其中必须存在名为 select 的函数。否则，视为表达式或 lambda 函数")
parser.add_argument("-k", "--key", default="", help="对路径进行分组统计，提供一个表达式（会注入一个变量 path，类型是 pathlib.Path）或函数（会传入一个参数，类型是 pathlib.Path）")
parser.add_argument("-ke", "--key-exec", action="store_true", help="对 -k/--key 传入的代码用 exec 运行，其中必须存在名为 key 的函数。否则，视为表达式或 lambda 函数")
parser.add_argument("-fl", "--follow-symlinks", action="store_true", help="跟进符号连接，否则会把符号链接视为文件，即使它指向目录")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")


def parse_args(argv=None):
    args = parser.parse_args(argv)
    if args.version:
        from statsdir import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args



def main(argv=None):
    args = parse_args(argv)

    from collections.abc import Callable, Iterable
    from json import dumps
    from os import fsdecode
    from pathlib import Path
    from textwrap import dedent
    from typing import Any

    from iterdir import DirEntry
    from statsdir import statsdir

    predicate: None | Callable[[DirEntry], None | bool] = None
    select_code = dedent(args.select).strip()
    if select_code:
        ns = {"re": __import__("re")}
        if args.select_exec:
            exec(select_code, ns)
            select = ns.get("select")
        elif select_code.startswith("lambda "):
            select = eval(select_code, ns)
        else:
            select = eval("lambda path:" + select_code, ns)
        if callable(select):
            predicate = lambda e: select(Path(fsdecode(e)))

    key: None | Callable[[DirEntry], Any] = None
    key_code = dedent(args.key).strip()
    if key_code:
        ns = {}
        if args.key_exec:
            exec(key_code, ns)
            keyf = ns.get("key")
        elif key_code.startswith("lambda "):
            keyf = eval(key_code, ns)
        else:
            keyf = eval("lambda path:" + key_code, ns)
        if callable(keyf):
            key = lambda e: keyf(Path(fsdecode(e)))

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
                        follow_symlinks=args.follow_symlinks, 
                        key=key, 
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


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

