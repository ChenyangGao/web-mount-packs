#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="""\
    🔧 从蓝奏云的分享，提取下载链接或下载文件

MIT licensed: https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/lanzou_share_download/LICENSE
""", epilog=r"""------------------------------

🔨 使用示例：

1. 使用 wget 批量下载：

假设分享链接和密码如下：

.. code: shell

    url=https://yxssp.lanzoui.com/b518919/
    password=afia

那么可以用以下命令进行批量下载（可以用 xargs -P num 指定 num 进程并行）：

.. code: shell

    python lanzou_share_download_url "$url $password" | xargs -n 1 -P 4 wget --header='Accept-Language: zh-CN' --content-disposition

或者使用这个封装函数

.. code: shell

    wget_download() {
        local url=$1
        local procs=$(($2))
        if [ $procs -le 0 ]; then
            procs=1
        fi
        /usr/bin/env python3 lanzou_share_download_url "$url" | xargs -n 1 -P "${procs}" wget --header='Accept-Language: zh-CN' --content-disposition
    }
    wget_download "$url $password" 4
""", formatter_class=RawTextHelpFormatter)
parser.add_argument("url", nargs="?", help="""\
分享链接（链接中不要有空格）和密码（可以没有）
用空格隔开，一行一个
如果不传，则从 stdin 读取""")
parser.add_argument("-hs", "--headers", help="请求头，用冒号分开，一行一个")
parser.add_argument("-d", "--download-dir", help="下载文件夹，如果指定此参数，会下载文件且断点续传")
parser.add_argument("-sd", "--show-detail", action="store_true", help="获取文件的详细信息，下载链接也会变成直链（不指定时为 302 链接）")
parser.add_argument("-c", "--predicate-code", help="断言，当断言的结果为 True 时，链接会被输出，未指定此参数则自动为 True")
parser.add_argument(
    "-t", "--predicate-type", choices=("expr", "re", "lambda", "stmt", "code", "path"), default="expr", 
    help="""断言类型
    - expr    （默认值）表达式，会注入一个名为 attr 的字典，包含文件的信息
    - re      正则表达式，如果在文件名中可搜索到此模式，则断言为 True
    - lambda  lambda 函数，接受一个参数，此参数是一个包含文件信息的字典
    - stmt    语句，当且仅当不抛出异常，则视为 True，会注入一个名为 attr 的字典，包含文件的信息
    - code    代码，运行后需要在它的全局命名空间中生成一个 check 函数用于断言，接受一个参数，此参数是一个包含文件信息的字典
    - path    代码的路径，运行后需要在它的全局命名空间中生成一个 check 函数用于断言，接受一个参数，此参数是一个包含文件信息的字典

attr 字典的格式如下（包含这些 key），下载链接是 302 链接

.. code: python

    {
        'id': 'i6cgB1mk4r5a', 
        'short_id': 'i1mk4r5', 
        'name': 'Speedtest-Premium-v5.3.1_build_206980-Mod-arm64-v8a_yxssp.com.apk', 
        'relpath': 'Speedtest-Premium-v5.3.1_build_206980-Mod-arm64-v8a_yxssp.com.apk', 
        'isdir': False, 
        'icon': 'apk', 
        'download_url': 'http://develope-oss.lanzouc.com/file/?CW9XaQ4/ADFRWAA4UGVQPFFuATlUWAt5UDJQM11lBnNSNwcjDyZVLFNVAiZUZQBsBDdXJ1dlU3wKewc0UyEDMQknVzEODAA2UXIAP1BoUDVRVAE2VDsLP1BuUG5dMQYqUh8HPw82VSxTZAImVG0ANwRqV39XflNpCmwHXlN2A3oJeldzDiMAelFkADlQaVB/UWoBdFRgCy9QMVA/XW0GYlINBzkPNlU8UzQCYlQwADQEa1diVz9TaAo9BydTaQNxCTRXMw5qAGRRNwBjUD1QZ1E7ASJUewt5UGpQZF0xBjVSZgd/D2JVMFMqAmZUOAAuBG1XZFcxUzQKaAdjU24DZgk5VzIOYQBkUTEAN1AxUGlRPgFmVD4Lb1A2UGVdMwYzUjMHZA8zVWBTPQIxVGMAMwRwVzNXeFM6CisHdFN8A2cJe1dpDjcAaVEzAGNQMVBlUT8BNlQtC31QPlA7XWQGYVJvB2EPZVUxUzMCYVQwADQEbFdjVzFTfwojBydTaQNuCX5XPQ5iAGNRNwBgUDFQYVE4ATdUOAs5UHFQI11xBnBSbwdhD2VVMVMzAmBUMwA3BGxXYlc/U3cKeAdoU38DPwk7VzIOYAB6UT4AYlAqUGNROgE2VCULO1BlUGc=', 
    }

指定 -sd 或 --show-detail 后，信息更多，且下载链接变为直链

.. code: python

    {
        'id': 'i6cgB1mk4r5a', 
        'short_id': 'i1mk4r5', 
        'name': 'Speedtest-Premium-v5.3.1_build_206980-Mod-arm64-v8a_yxssp.com.apk', 
        'relpath': 'Speedtest-Premium-v5.3.1_build_206980-Mod-arm64-v8a_yxssp.com.apk', 
        'isdir': False, 
        'icon': 'apk', 
        'filename': 'Speedtest-Premium-v5.3.1_build_206980-Mod-arm64-v8a_yxssp.com.apk', 
        'size': 39005960, 
        'created_time': datetime.datetime(2024, 1, 29, 4, 54, 46), 
        'modified_time': datetime.datetime(2024, 1, 28, 10, 7, 11), 
        'access_time': datetime.datetime(2024, 1, 28, 10, 7, 11), 
        'download_url': 'https://i-010.wwentua.com:446/01291200160550790bb/2024/01/28/369eebad02206a585b5fa324a4aa8ec2.apk?st=4cUHqZHiM7fNve0KGxb7Qg&e=1706506286&b=AQBcLFI3B2cENQMhATQDdFR1XSxRAFQgBzFaOlwyA3QHOF1wA3VUZAB7XzpRLwM2CAIAPgdzC2QJNl82XARSYgFjXGpSawc6BGEDeAEcA2hUZV0sUTFUIAc5WmFcbwMsByNdZQNiVA4ALF9xUXIDdAgtAHIHZQtiCTdffFw6UiABOA_c_c&fi=160550790&pid=223-94-212-221&up=2&mp=0&co=0', 
    }
""")
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
predicate_code = args.predicate_code
predicate_type = args.predicate_type

if url:
    urls = url.splitlines()
else:
    from sys import stdin
    urls = (l.removesuffix("\n") for l in stdin)

if headers is not None:
    from util.text import headers_str_to_dict # type: ignore
    headers = headers_str_to_dict(headers)
    headers.setdefault("Accept-language", "zh-CN")
else:
    headers = {"Accept-language": "zh-CN"}

if predicate_code:
    from util.predicate import make_predicate # type: ignore
    predicate = make_predicate(predicate_code, predicate_type)
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
                for item in iterdir(url, password, **kwargs):
                    print(item["download_url"], flush=True)
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
            parts = url.rsplit(" ", maxsplit=1)
            if len(parts) == 2:
                url, password = parts
            else:
                password = ""
            try:
                for item in iterdir(url, password, **kwargs):
                    down_url = item["download_url"]
                    try:
                        file = download(
                            down_url, 
                            joinpath(download_dir, item["relpath"]), 
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

