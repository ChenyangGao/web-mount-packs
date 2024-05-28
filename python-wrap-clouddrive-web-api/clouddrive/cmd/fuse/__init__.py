#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = """\
    🌍 基于 clouddrive 和 fuse 的只读文件系统，支持罗列 strm 🪩

⏰ 由于网盘对多线程访问的限制，请停用挂载目录的显示图标预览

1. Linux 要安装 libfuse：  https://github.com/libfuse/libfuse
2. MacOSX 要安装 MacFUSE： https://github.com/osxfuse/osxfuse
3. Windows 要安装 WinFsp： https://github.com/winfsp/winfsp
"""

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from fuser import CloudDriveFuseOperations # type: ignore
    from util.log import logger # type: ignore
    from util.predicate import make_predicate # type: ignore

    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
else:
    from argparse import RawTextHelpFormatter
    from ..init import subparsers
    from .fuser import CloudDriveFuseOperations
    from .util.log import logger
    from .util.predicate import make_predicate

    parser = subparsers.add_parser("fuse", description=__doc__, formatter_class=RawTextHelpFormatter)


def main(args):
    if args.version:
        from clouddrive import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    mount_point = args.mount_point
    if not mount_point:
        from uuid import uuid4
        mount_point = str(uuid4())

    import logging

    log_level = args.log_level
    if isinstance(log_level, str):
        try:
            log_level = int(log_level)
        except ValueError:
            log_level = getattr(logging, log_level.upper(), logging.NOTSET)
    logger.setLevel(log_level)

    import re

    predicate = args.show_predicate
    if predicate:
        predicate = make_predicate(predicate, {"re": re}, type=args.show_predicate_type)

    strm_predicate = args.strm_predicate
    if strm_predicate:
        strm_predicate = make_predicate(strm_predicate, {"re": re}, type=args.strm_predicate_type)

    from re import compile as re_compile

    CRE_PAT_IN_STR = re_compile(r"[^\\ ]*(?:\\(?s:.)[^\\ ]*)*")

    cache = None
    make_cache = args.make_cache
    if make_cache:
        from textwrap import dedent
        code = dedent(make_cache)
        ns = {} # type: dict
        exec(code, ns)
        cache = ns.get("cache")

    direct_open_names = args.direct_open_names
    if direct_open_names:
        names = {n.replace(r"\ ", " ") for n in CRE_PAT_IN_STR.findall(direct_open_names) if n}
        if names:
            direct_open_names = names.__contains__

    direct_open_exes = args.direct_open_exes
    if direct_open_exes:
        exes = {n.replace(r"\ ", " ") for n in CRE_PAT_IN_STR.findall(direct_open_exes) if n}
        if names:
            direct_open_exes = exes.__contains__

    from os.path import exists, abspath

    print(f"""
        👋 Welcome to use clouddrive fuse 👏

    mounted at: {abspath(mount_point)!r}
    """)

    if not exists(mount_point):
        import atexit
        from os import removedirs
        atexit.register(lambda: removedirs(mount_point))

    # https://code.google.com/archive/p/macfuse/wikis/OPTIONS.wiki
    CloudDriveFuseOperations(
        args.origin, 
        args.username, 
        args.password, 
        cache=cache, 
        predicate=predicate, 
        strm_predicate=strm_predicate, 
        max_readdir_workers=args.max_readdir_workers, 
        direct_open_names=direct_open_names, 
        direct_open_exes=direct_open_exes, 
    ).run(
        mountpoint=mount_point, 
        ro=True, 
        allow_other=args.allow_other, 
        foreground=not args.background, 
        nothreads=args.nothreads, 
        debug=args.debug, 
    )


parser.add_argument("mount_point", nargs="?", help="挂载路径")
parser.add_argument("-o", "--origin", default="http://localhost:19798", help="clouddrive 服务器地址，默认 http://localhost:19798")
parser.add_argument("-u", "--username", default="", help="用户名，默认为空")
parser.add_argument("-p", "--password", default="", help="密码，默认为空")
parser.add_argument(
    "-m", "--max-readdir-workers", default=8, type=int, 
    help="读取目录的文件列表的最大的并发线程数，默认值是 8，等于 0 则自动确定，小于 0 则不限制", 
)
parser.add_argument("-p1", "--show-predicate", help="断言，当断言的结果为 True 时，文件或目录会被显示")
parser.add_argument(
    "-t1", "--show-predicate-type", default="ignore", 
    choices=("ignore", "ignore-file", "expr", "re", "lambda", "stmt", "code", "path"), 
    help="""断言类型，默认值为 'ignore'
    - ignore       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - ignore-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 clouddrive.CloudDrivePath 对象
    - re           正则表达式，如果文件的名字匹配此模式，则断言为 True
    - lambda       lambda 函数，接受一个 clouddrive.CloudDrivePath 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 clouddrive.CloudDrivePath 对象
    - code         代码，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 clouddrive.CloudDrivePath 对象作为参数
    - path         代码的路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 clouddrive.CloudDrivePath 对象作为参数
""")
parser.add_argument("-p2", "--strm-predicate", help="strm 断言，当断言的结果为 True 时，文件会被显示为带有 .strm 后缀的文本文件，打开后是链接")
parser.add_argument(
    "-t2", "--strm-predicate-type", default="filter", 
    choices=("filter", "filter-file", "expr", "re", "lambda", "stmt", "code", "path"), 
    help="""断言类型，默认值为 'filter'
    - filter       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - filter-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 clouddrive.CloudDrivePath 对象
    - re           正则表达式，如果文件的名字匹配此模式，则断言为 True
    - lambda       lambda 函数，接受一个 clouddrive.CloudDrivePath 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 clouddrive.CloudDrivePath 对象
    - code         代码，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 clouddrive.CloudDrivePath 对象作为参数
    - path         代码的路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 clouddrive.CloudDrivePath 对象作为参数
""")
parser.add_argument(
    "-dn", "--direct-open-names", 
    help="为这些名字（忽略大小写）的程序直接打开链接，有多个时用空格分隔（如果文件名中包含空格，请用 \\ 转义）", 
)
parser.add_argument(
    "-de", "--direct-open-exes", 
    help="为这些路径的程序直接打开链接，有多个时用空格分隔（如果文件名中包含空格，请用 \\ 转义）", 
)
parser.add_argument("-c", "--make-cache", help="""\
请提供一段代码，这段代码执行后，会产生一个名称为 cache 的值，将会被作为目录列表的缓存，如果代码执行成功却没有名为 cache 的值，则 cache 为 {}
例如提供的代码为

.. code: python

    from cachetools import TTLCache
    from sys import maxsize

    cache = TTLCache(maxsize, ttl=3600)

就会产生一个容量为 sys.maxsize 而 key 的存活时间为 1 小时的缓存

这个 cache 至少要求实现接口

    __getitem__, __setitem__

建议实现 collections.abc.MutableMapping 的接口，即以下接口

    __getitem__, __setitem__, __delitem__, __iter__, __len__

最好再实现析构方法

    __del__

Reference:
    - https://docs.python.org/3/library/dbm.html
    - https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping
    - https://docs.python.org/3/library/collections.abc.html#collections-abstract-base-classes
""")
parser.add_argument("-d", "--debug", action="store_true", help="调试模式，输出更多信息")
parser.add_argument("-l", "--log-level", default=0, help=f"指定日志级别，可以是数字或名称，不传此参数则不输出日志，默认值: 0 (NOTSET)")
parser.add_argument("-b", "--background", action="store_true", help="后台运行")
parser.add_argument("-s", "--nothreads", action="store_true", help="不用多线程")
parser.add_argument("--allow-other", action="store_true", help="允许 other 用户（也即不是 user 和 group）")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

