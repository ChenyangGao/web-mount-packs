#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="""\
    🔧 从 OneDrive 的分享，提取下载链接或下载文件

Source Code:  https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/onedrive_share_download
MIT Licensed: https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/onedrive_share_download/LICENSE
""", epilog=r"""------------------------------

🔨 使用示例：

假设分享链接如下：

.. code: shell

    url='https://1drv.ms/u/s!ArCCzt1ktlAEa6xRPcK0_aQllqk?e=x1bLhA'

0. 输出下载链接或属性字典

可以用以下命令输出下载链接

.. code: shell

    python onedrive_share_download "$url"

可以通过 -p/--print-attr 参数输出属性字典

.. code: shell

    python onedrive_share_download "$url"

1. 使用自带的下载器下载：

可以通过 -d/--download-dir 参数指定下载目录，下载到当前目录可指定为 ""

.. code: shell

    python onedrive_share_download "$url" -d ""

2. 使用 wget 批量下载：

可以用以下命令进行批量下载（可以用 xargs -P num 指定 num 进程并行）：

.. code: shell

    python onedrive_share_download "$url" | xargs -n 1 -P 4 wget --content-disposition

或者使用这个封装函数

.. code: shell

    wget_download() {
        local url=$1
        local procs=$(($2))
        if [ $procs -le 0 ]; then
            procs=1
        fi
        /usr/bin/env python3 onedrive_share_download "$url" | xargs -n 1 -P "${procs}" wget --content-disposition
    }
    wget_download "$url" 4
""", formatter_class=RawTextHelpFormatter)
parser.add_argument("url", nargs="?", help="""\
分享链接（链接中不要有空格）
用空格隔开，一行一个
如果不传，则从 stdin 读取""")
parser.add_argument("-d", "--download-dir", help="下载文件夹，如果指定此参数，会下载文件且断点续传")
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
        "createdBy": {
            "application": {
                "displayName": "MSOffice15",
                "id": "480728c5"
            },
            "user": {
                "displayName": "salt tiger",
                "id": "450b664ddce82b0"
            },
            "oneDriveSync": {
                "@odata.type": "#oneDrive.identity",
                "id": "44ed5573-c89c-4db2-a42b-fa1cf63af3ea"
            }
        },
        "createdDateTime": "2019-06-18T17:03:49.803Z",
        "cTag": "adDo0NTBCNjY0RERDRTgyQjAhMTA4LjYzODM0MzE3Nzc1OTAzMDAwMA",
        "eTag": "aNDUwQjY2NEREQ0U4MkIwITEwOC4w",
        "id": "450B664DDCE82B0!108",
        "lastModifiedBy": {
            "application": {
                "displayName": "MSOffice15",
                "id": "480728c5"
            },
            "user": {
                "displayName": "salt tiger",
                "id": "450b664ddce82b0"
            },
            "oneDriveSync": {
                "@odata.type": "#oneDrive.identity",
                "id": "44ed5573-c89c-4db2-a42b-fa1cf63af3ea"
            }
        },
        "lastModifiedDateTime": "2023-10-31T02:56:15.903Z",
        "name": "Addison-Wesley",
        "parentReference": {
            "driveId": "450b664ddce82b0",
            "driveType": "personal",
            "id": "450B664DDCE82B0!107",
            "name": "Verycd Share",
            "path": "/drives/450b664ddce82b0/items/450B664DDCE82B0!107:"
        },
        "size": 3873285304,
        "webUrl": "https://1drv.ms/f/s!ArCCzt1ktlAEbKxRPcK0_aQllqk",
        "fileSystemInfo": {
            "createdDateTime": "2017-06-20T16:52:38Z",
            "lastModifiedDateTime": "2018-04-02T04:57:15Z"
        },
        "folder": {
            "childCount": 73,
            "folderView": {
                "viewType": "thumbnails",
                "sortBy": "name",
                "sortOrder": "ascending"
            },
            "folderType": "document"
        },
        "reactions": {
            "commentCount": 0
        },
        "shared": {
            "effectiveRoles": [
                "read"
            ],
            "owner": {
                "user": {
                    "displayName": "salt tiger",
                    "id": "450b664ddce82b0"
                }
            },
            "scope": "users"
        },
        "isdir": true,
        "relpath": "Addison-Wesley"
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

try:
    if download_dir is None:
        for url in urls:
            if not url:
                continue
            try:
                for attr in iterdir(url, predicate=predicate, max_depth=-1):
                    if attr["isdir"]:
                        continue
                    if print_attr:
                        print(attr, flush=True)
                    else:
                        print(attr["@content.downloadUrl"], flush=True)
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
            print("-"*get_terminal_size().columns)
            print(f"🚀 \x1b[1;5mPROCESSING\x1b[0m \x1b[4;34m{url!r}\x1b[0m")
            try:
                for attr in iterdir(url, predicate=predicate, max_depth=-1):
                    if attr["isdir"]:
                        continue
                    if print_attr:
                        print(attr)
                    down_url = attr["@content.downloadUrl"]
                    try:
                        file = download(
                            down_url, 
                            joinpath(download_dir, attr["relpath"]), 
                            resume=True, 
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

