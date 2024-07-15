#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []
__doc__ = """\
    🌍 基于 alist 和 fuse 的只读文件系统，支持罗列 strm 🪩

⏰ 由于网盘对多线程访问的限制，请停用挂载目录的显示图标预览

1. Linux 要安装 libfuse：  https://github.com/libfuse/libfuse
2. MacOSX 要安装 MacFUSE： https://github.com/osxfuse/osxfuse
3. Windows 要安装 WinFsp： https://github.com/winfsp/winfsp
"""

epilog = """---------- 使用帮助 ----------

1. 隐藏所有 *.mkv 文件

.. code: console

    python-alist fuse --show-predicate '*.mkv'

2. 只显示所有文件夹和 *.mkv 文件

.. code: console

    python-alist fuse --show-predicate '* !/**/ !*.mkv'

或者

.. code: console

    python-alist fuse \\
        --show-predicate-type expr \\
        --show-predicate 'path.is_dir() or path.suffix.lower() == ".mkv"'

3. 把所有视频、音频显示为 .strm 文件，显示图片、字幕和 .nfo 文件

.. code: console

    python-alist fuse \\
        --strm-predicate-type expr \\
        --strm-predicate '(
            path.media_type.startswith(("video/", "audio/")) and 
            path.suffix.lower() != ".ass"
        )' \\
        --show-predicate-type expr \\
        --show-predicate '(
            path.is_dir() or 
            path.media_type.startswith("image/") or 
            path.suffix.lower() in (".nfo", ".ass", ".ssa", ".srt", ".idx", ".sub", ".txt", ".vtt", ".smi")
        )'

4. 把缓存保存到本地的 dbm 文件（不用担心性能问题，因为这种情况下会有 2 级缓存）

.. code: console

    python-alist fuse -c '
    import shelve
    cache = shelve.open("alist-cache")'

.. 本地持久化缓存模块（推荐选用 dbm-like (类 dbm 的) 风格的模块）:

    - dbm: https://docs.python.org/3/library/dbm.html
    - shelve: https://docs.python.org/3/library/shelve.html
    - sqlite3: https://docs.python.org/3/library/sqlite3.html
    - rocksdict: https://pypi.org/project/rocksdict/
    - speedict: https://pypi.org/project/speedict/
    - unqlite: https://github.com/coleifer/unqlite-python
    - vedis: https://github.com/coleifer/vedis-python
    - lmdb: https://pypi.org/project/lmdb/
    - lmdbm: https://pypi.org/project/lmdbm/
    - semidbm: https://pypi.org/project/semidbm/
    - pysos: https://pypi.org/project/pysos/
    - wiredtiger: https://pypi.org/project/wiredtiger/
    - sqlitedict: https://pypi.org/project/sqlitedict/
    - tinydb: https://pypi.org/project/tinydb/
    - diskcache: https://pypi.org/project/diskcache/
    - h5py: https://github.com/h5py/h5py
    - leveldb: https://github.com/jtolio/leveldb-py
    - pickledb: https://github.com/patx/pickledb

.. 序列化模块:

    - pickle: https://docs.python.org/3/library/pickle.html
    - marshal: https://docs.python.org/3/library/marshal.html
    - json: https://docs.python.org/3/library/json.html
    - orjson: https://pypi.org/project/orjson/
    - ujson: https://pypi.org/project/ujson/

.. 推荐阅读:

    - https://stackoverflow.com/questions/47233562/key-value-store-in-python-for-possibly-100-gb-of-data-without-client-server
    - https://charlesleifer.com/blog/completely-un-scientific-benchmarks-of-some-embedded-databases-with-python/
    - https://docs.python.org/3/library/persistence.html
    - https://stackoverflow.com/questions/4026359/memory-efficient-string-to-string-map-in-python-or-c

5. 自定义生成的 strm，例如把 base-url 设置为 http://my.302.server

.. code: console

    python-alist fuse --strm-predicate '*' --custom-strm 'http://my.302.server'

6. 用 vlc 播放时直接打开播放器，而不是由 fuse 转发

.. code: console

    python-alist fuse --direct-open-names vlc
"""

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[3])
    parser = ArgumentParser(description=__doc__, epilog=epilog, formatter_class=RawTextHelpFormatter)
else:
    from argparse import RawTextHelpFormatter
    from ..init import subparsers

    parser = subparsers.add_parser("fuse", description=__doc__, epilog=epilog, formatter_class=RawTextHelpFormatter)


def main(args):
    if args.version:
        from alist import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

    from alist.cmd.fuse.util.fuser import AlistFuseOperations
    from alist.cmd.fuse.util.log import logger
    from alist.cmd.fuse.util.predicate import make_predicate
    from alist.cmd.fuse.util.strm import parse as make_strm_converter

    mount_point = args.mount_point
    if not mount_point:
        from uuid import uuid4
        mount_point = str(uuid4())

    options = {
        "mountpoint": mount_point, 
        "auto_cache": True, 
        "foreground": True, 
        "max_readahead": 65536, 
        "ro": True, 
    }
    if fuse_options := args.fuse_options:
        for option in fuse_options:
            if "=" in option:
                name, value = option.split("=", 1)
                if value:
                    options[name] = value
                else:
                    options.pop(name, None)
            else:
                options[option] = True

    import logging

    log_level = args.log_level
    if log_level.isascii() and log_level.isdecimal():
        log_level = int(log_level)
    else:
        log_level = getattr(logging, log_level.upper(), logging.NOTSET)
    logger.setLevel(log_level)

    import re

    if predicate := args.show_predicate:
        predicate = make_predicate(predicate, {"re": re}, type=args.show_predicate_type)

    if strm_predicate := args.strm_predicate:
        strm_predicate = make_predicate(strm_predicate, {"re": re}, type=args.strm_predicate_type)

    strm_make = None
    if custom_strm := args.custom_strm:
        custom_strm_type = args.custom_strm_type
        if custom_strm_type == "file":
            from pathlib import Path
            custom_strm = custom_strm(custom_strm)
        strm_make = make_strm_converter(
            custom_strm, 
            {"re": re, "token": args.token}, 
            code_type=custom_strm_type, 
        )

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

    if direct_open_names := args.direct_open_names:
        direct_open_names = set(direct_open_names).__contains__

    if direct_open_exes := args.direct_open_exes:
        direct_open_exes = set(direct_open_names).__contains__

    from os.path import exists, abspath

    print(f"""
        👋 Welcome to use alist fuse 👏

    mounted at: {abspath(mount_point)!r}
    FUSE options: {options!r}
    """)

    if not exists(mount_point):
        import atexit
        from os import removedirs
        atexit.register(lambda: removedirs(mount_point))

    # https://code.google.com/archive/p/macfuse/wikis/OPTIONS.wiki
    AlistFuseOperations(
        origin=args.origin, 
        username=args.username, 
        password=args.password, 
        token=args.token, 
        base_dir=args.base_dir, 
        cache=cache, 
        max_readdir_workers=args.max_readdir_workers, 
        max_readdir_cooldown=args.max_readdir_cooldown, 
        predicate=predicate, 
        strm_predicate=strm_predicate, 
        strm_make=strm_make, 
        direct_open_names=direct_open_names, 
        direct_open_exes=direct_open_exes, 
    ).run(**options)


parser.add_argument("mount_point", nargs="?", help="挂载路径")
parser.add_argument("-o", "--origin", default="http://localhost:5244", help="alist 服务器地址，默认 http://localhost:5244")
parser.add_argument("-u", "--username", default="", help="用户名，默认为空")
parser.add_argument("-p", "--password", default="", help="密码，默认为空")
parser.add_argument("-t", "--token", default="", help="token，用于给链接做签名，默认为空")
parser.add_argument("-b", "--base-dir", default="/", help="挂载的目录，默认为 '/'")
parser.add_argument(
    "-mr", "--max-readdir-workers", default=5, type=int, 
    help="读取目录的文件列表的最大的并发线程数，默认值是 5，等于 0 则自动确定，小于 0 则不限制", 
)
parser.add_argument(
    "-mc", "--max-readdir-cooldown", default=30, type=float, 
    help="读取目录的文件列表的冷却时间（单位：秒），在冷却时间内会直接返回缓存的数据（避免更新），默认值是 30，小于等于 0 则不限制", 
)
parser.add_argument("-p1", "--show-predicate", help="断言，当断言的结果为 True 时，文件或目录会被显示")
parser.add_argument(
    "-t1", "--show-predicate-type", default="ignore", 
    choices=("ignore", "ignore-file", "expr", "lambda", "stmt", "module", "file", "re"), 
    help="""断言类型，默认值为 'ignore'
    - ignore       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - ignore-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 alist.AlistPath 对象
    - lambda       lambda 函数，接受一个 alist.AlistPath 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 alist.AlistPath 对象
    - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 alist.AlistPath 对象作为参数
    - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 alist.AlistPath 对象作为参数
    - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
""")
parser.add_argument("-p2", "--strm-predicate", help="strm 断言（优先级高于 -p1/--show-predicate），当断言的结果为 True 时，文件会被显示为带有 .strm 后缀的文本文件，打开后是链接")
parser.add_argument(
    "-t2", "--strm-predicate-type", default="filter", 
    choices=("filter", "filter-file", "expr", "lambda", "stmt", "module", "file", "re"), 
    help="""断言类型，默认值为 'filter'
    - filter       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - filter-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 alist.AlistPath 对象
    - lambda       lambda 函数，接受一个 alist.AlistPath 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 alist.AlistPath 对象
    - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 alist.AlistPath 对象作为参数
    - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 alist.AlistPath 对象作为参数
    - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
""")
parser.add_argument("-cs", "--custom-strm", help="自定义 strm 的内容")
parser.add_argument(
    "-ct", "--custom-strm-type", default="base-url", 
    choices=("base-url", "expr", "fstring", "lambda", "stmt", "module", "file", "resub"), 
    help="""自定义 strm 的操作类型，默认值 'base-url'，以返回值作为 strm 中的链接，如果报错，则生成空的 strm 文件
    - base-url  提供一个 base-url，用来拼接（相对）路径
    - expr      表达式，可从命名空间访问到一个名为 path 的 alist.AlistPath 对象
    - fstring   视为 fstring，可从命名空间访问到一个名为 path 的 alist.AlistPath 对象
    - lambda    lambda 函数，接受一个 alist.AlistPath 对象作为参数
    - stmt      语句，可从命名空间访问到一个名为 path 的 alist.AlistPath 对象，最后要产生一个名为 url 的变量到本地命名空间
    - module    模块，运行后需要在它的全局命名空间中生成一个 run 或 convert 函数，接受一个 alist.AlistPath 对象作为参数
    - file      文件路径，会被作为模块加载执行，运行后需要在它的全局命名空间中生成一个 run 或 convert 函数，接受一个 alist.AlistPath 对象作为参数
    - resub     正则表达式，模式替换，语法同 sed，格式为 /pattern/replacement/flag，用来对生成的链接进行搜索替换
上面的各个类型，都会注入几个全局变量
    - re      正则表达式模块
    - token   Alist 的 token，经命令行传入
""")
parser.add_argument(
    "-dn", "--direct-open-names", nargs="+", metavar="name", 
    help="为这些名字（忽略大小写）的程序直接打开链接", 
)
parser.add_argument(
    "-de", "--direct-open-exes", nargs="+", metavar="exec", 
    help="为这些路径的程序直接打开链接", 
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
parser.add_argument(
    "-fo", "--fuse-option", dest="fuse_options", metavar="option", nargs="+", 
    help="""fuse 挂载选项，支持如下几种格式：
    - name         设置 name 选项
    - name=        取消 name 选项
    - name=value   设置 name 选项，值为 value
参考资料：
    - https://man7.org/linux/man-pages/man8/mount.fuse3.8.html
    - https://code.google.com/archive/p/macfuse/wikis/OPTIONS.wiki
""")
parser.add_argument("-l", "--log-level", default="ERROR", help=f"指定日志级别，可以是数字或名称，不传此参数则不输出日志，默认值: 'ERROR'")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=main)


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)

