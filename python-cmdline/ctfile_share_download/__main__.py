#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://github.com/ChenyangGao>"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="""\
    🔧 从城通网盘的分享，提取下载链接或下载文件

Source Code:  https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/ctfile_share_download
MIT Licensed: https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/ctfile_share_download/LICENSE

🌹 温馨提示：
1. 非 vip 状态下，城通网盘一个 ip 只允许最多同时下载 1 个文件
2. 即使一个文件下载完成了，最好再等待 1 秒，再开始下 1 个文件的下载，确保服务器更新了状态
3. 如果你已经是 vip，那就只要给相应的下载程序提供 Cookie 请求头
""", epilog=r"""------------------------------

🔨 使用示例：

1. 使用 wget 批量下载：

假设分享链接和口令如下：

.. code: shell

    url=https://url96.ctfile.com/d/35561896-59373355-6d3369
    password=4184

那么可以用以下命令进行批量下载（可以用 xargs -P num 指定 num 进程并行）：

.. code: shell

    python ctfile_share_download_url "$url $password" | xargs -n 1 bash -c 'url=$1; name=$(sed -E "s#.*\/([^/?]+)\?.*#\1#" <<<"$url"); wget -O "$name" "$url"' ''

或者使用这个封装函数

.. code: shell

    wget_download() {
        local url=$1
        local procs=$(($2))
        if [ $procs -le 0 ]; then
            procs=1
        fi
        /usr/bin/env python3 ctfile_share_download_url "$url" | xargs -n 1 -P "${procs}" bash -c 'url=$1; name=$(sed -E "s#.*\/([^/?]+)\?.*#\1#" <<<"$url"); wget -O "$name" "$url"' ''
    }
    wget_download "$url $password"

2. 获取所有非 zip 压缩包且未被下载的文件的下载链接：

.. code: shell

    python ctfile_share_download_url "$url $password" -t code -c '
    from os.path import exists

    def check(attr):
        if attr["isdir"]:
            return True
        name = attr["name"]
        return not name.endswith(".zip") and not exists(name)'
""", formatter_class=RawTextHelpFormatter)
parser.add_argument("url", nargs="?", help="""\
分享链接（链接中不要有空格）和密码（可以没有）
用空格隔开，一行一个
如果不传，则从 stdin 读取""")
parser.add_argument("-hs", "--headers", help="请求头，用冒号分开，一行一个")
parser.add_argument("-d", "--download-dir", help="下载文件夹，如果指定此参数，会下载文件且断点续传")
parser.add_argument("-sd", "--show-detail", action="store_true", help="获取文件的详细信息")
parser.add_argument("-p", "--print-attr", action="store_true", help="输出属性字典，而不是下载链接")
parser.add_argument("-c", "--predicate-code", help="断言，当断言的结果为 True 时，链接会被输出，未指定此参数则自动为 True")
parser.add_argument(
    "-t", "--predicate-type", choices=("expr", "re", "lambda", "stmt", "code", "path"), default="expr", 
    help="""断言类型
    - expr    （默认值）表达式，会注入一个名为 attr 的文件信息的 dict
    - re      正则表达式，如果文件的名字匹配此模式，则断言为 True
    - lambda  lambda 函数，接受一个文件信息的 dict 作为参数
    - stmt    语句，当且仅当不抛出异常，则视为 True，会注入一个名为 attr 的文件信息的 dict
    - code    代码，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个文件信息的 dict 作为参数
    - path    代码的路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个文件信息的 dict 作为参数

attr 字典的格式如下（包含这些 key）

.. code: python

    {
        'id': 999155365, 
        'isdir': False, 
        'name': '151-200.zip', 
        'size': '1.11 GB', 
        'tempdir': 'tempdir-UDIHNVdgXTNRYgJtAjoEYAQrBz9Wb1tjCGMEZlY2BToBZgIwXXIOZ1tuUDdUY1cwU2MBNAU1WGBfPQ', 
        'time': '2024-01-02', 
        'userid': 35561896, 
        'file_chk': 'd18881bc283c7fb23e2ae6f8691df09d', 
        'file_dir': '/d/35561896-59373355-1706524098-70dd9c3d531b8742', 
        'download_url': 'https://ch1-cmcc-dd.tv002.com/down/31789256feada8ecc67d82ddc3af6e3f/151-200.zip?cts=D223A94A212A221Fff483&ctp=223A94A212A221&ctt=1706545698&limit=1&spd=100000&ctk=31789256feada8ecc67d82ddc3af6e3f&chk=01d6784e6e3c9348f52dfb5eb22ef3bf-1195021931', 
        'relpath': '151-200.zip', 
}

指定 -sd 或 --show-detail 后，信息更多

.. code: python

    {
        'id': 999155365, 
        'isdir': False, 
        'name': '151-200.zip', 
        'size': 1195021931, 
        'tempdir': 'tempdir-A2EFN11qC2VXZFM8ATkAZAEuV29QaV9nXTZRM1MzDTICZVFjU3wNZAA1B2ADNFI1BTUCNwIyDD4KZg', 
        'time': '2024-01-02', 
        'userid': 35561896, 
        'file_chk': 'd18881bc283c7fb23e2ae6f8691df09d', 
        'file_dir': '/d/35561896-59373355-1706524037-762a058742d00274', 
        'download_url': 'https://ch1-cmcc-dd.tv002.com/down/aae258a33ea0e1f994b3bda118bb2e76/151-200.zip?cts=D223A94A212A221Fff483&ctp=223A94A212A221&ctt=1706545637&limit=1&spd=100000&ctk=aae258a33ea0e1f994b3bda118bb2e76&chk=01d6784e6e3c9348f52dfb5eb22ef3bf-1195021931', 
        'filename': '151-200.zip', 
        'created_time': datetime.datetime(2024, 1, 29, 10, 27, 17), 
        'modified_time': datetime.datetime(2024, 1, 6, 5, 42, 45), 
        'access_time': datetime.datetime(2024, 1, 6, 5, 42, 45), 
        'relpath': '151-200.zip', 
    }

可以通过 -i/--init-code 或 -ip/--init-code-path 提前为断言函数的全局命名空间注入一些变量，默认会注入 re （正则表达式模块）
""")
parser.add_argument("-i", "--init-code", help="执行这段代码一次，以初始化断言函数的全局命名空间")
parser.add_argument("-ip", "--init-code-path", help="执行此路径的代码一次，以初始化断言函数的全局命名空间")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.add_argument("-li", "--license", action="store_true", help="输出 license")
args = parser.parse_args()

if args.version:
    from pkgutil import get_data
    print(get_data("__main__", "VERSION").decode("ascii")) # type: ignore
    raise SystemExit(0)
if args.license:
    from pkgutil import get_data
    print(get_data("__main__", "LICENSE").decode("ascii")) # type: ignore
    raise SystemExit(0)

from sys import stderr, stdin
from __init__ import iterdir # type: ignore

url = args.url
headers = args.headers
download_dir = args.download_dir
print_attr = args.print_attr
predicate_code = args.predicate_code
predicate_type = args.predicate_type
init_code = args.init_code
init_code_path = args.init_code_path

if url:
    urls = url.splitlines()
else:
    from sys import stdin
    urls = (l.removesuffix("\n") for l in stdin)

if headers is not None:
    from util.text import headers_str_to_dict # type: ignore
    headers = headers_str_to_dict(headers)

if predicate_code:
    ns = {"re": __import__("re")}
    if predicate_type != "re":
        if init_code:
            from textwrap import dedent
            exec(dedent(init_code), ns)
        if init_code_path:
            from runpy import run_path
            ns = run_path(init_code_path, ns)
    from util.predicate import make_predicate # type: ignore
    predicate = make_predicate(predicate_code, ns, type=predicate_type)
else:
    predicate = None

kwargs: dict = {"predicate": predicate, "files_only": True}
if args.show_detail or download_dir:
    kwargs["show_detail"] = True
else:
    kwargs["show_download"] = True

try:
    if download_dir is None:
        for url in urls:
            if not url:
                continue
            parts = url.rsplit(" ", maxsplit=1)
            if len(parts) == 2:
                url, password = parts
            else:
                password = ""
            try:
                for attr in iterdir(url, password, **kwargs):
                    if print_attr:
                        print(attr, flush=True)
                    else:
                        print(attr["download_url"], flush=True)
            except BaseException as e:
                print(f"\r😮‍💨 \x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n  |_ \x1b[5m🙅\x1b[0m \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
                if isinstance(e, (BrokenPipeError, EOFError, KeyboardInterrupt)):
                    raise
    else:
        from collections import deque
        from os import get_terminal_size
        from os.path import join as joinpath
        from time import perf_counter
        from util.urlopen import download # type: ignore

        def progress(total=None):
            dq: deque[tuple[int, float]] = deque(maxlen=64)
            read_num = 0
            dq.append((read_num, perf_counter()))
            while True:
                read_num += yield
                cur_t = perf_counter()
                speed = (read_num - dq[0][0]) / 1024 / 1024 / (cur_t - dq[0][1])
                if total:
                    percentage = read_num / total * 100
                    print(f"\r\x1b[K{read_num} / {total} | {speed:.2f} MB/s | {percentage:.2f} %", end="", flush=True)
                else:
                    print(f"\r\x1b[K{read_num} | {speed:.2f} MB/s", end="", flush=True)
                dq.append((read_num, cur_t))

        for url in urls:
            if not url:
                continue
            parts = url.rsplit(" ", maxsplit=1)
            if len(parts) == 2:
                url, password = parts
            else:
                password = ""
            print("-"*get_terminal_size().columns)
            print(f"🚀 \x1b[1;5mPROCESSING\x1b[0m \x1b[4;34m{url!r}\x1b[0m {password!r}")
            try:
                for attr in iterdir(url, password, **kwargs):
                    if print_attr:
                        print(attr)
                    down_url = attr["download_url"]
                    try:
                        file = download(
                            down_url, 
                            joinpath(download_dir, attr["relpath"]), 
                            resume=True, 
                            headers=headers, 
                            make_reporthook=progress, 
                        )
                        print(f"\r😄 \x1b[K\x1b[1;32mDOWNLOADED\x1b[0m \x1b[4;34m{down_url!r}\x1b[0m\n |_ \x1b[5m⏬\x1b[0m \x1b[4;34m{file!r}\x1b[0m")
                    except BaseException as e:
                        print(f"\r😮‍💨 \x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{down_url!r}\x1b[0m\n  |_ \x1b[5m🙅\x1b[0m \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
                        if isinstance(e, (BrokenPipeError, EOFError, KeyboardInterrupt)):
                            raise
            except BaseException as e:
                print(f"\r😮‍💨 \x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n  |_ \x1b[5m🙅\x1b[0m \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
                if isinstance(e, (BrokenPipeError, EOFError, KeyboardInterrupt)):
                    raise
except (BrokenPipeError, EOFError):
    stderr.close()

