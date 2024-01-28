#!/usr/bin/env python3
# encoding: utf-8

__version__ = (0, 0, 2)
__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__license__ = "MIT <https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/ctfile_share_download/LICENSE>"
__all__ = ["iterdir"]

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description="""\
    从城通网盘的分享中提取下载链接

MIT licensed: https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/ctfile_share_download/LICENSE

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
    passcode=4184

那么可以用以下命令进行批量下载（可以用 xargs -P num 指定 num 进程并行）：

.. code: shell

    python ctfile_share_download_url.py "$url" -p "$passcode" | xargs -n 1 bash -c 'url=$1; name=$(sed -E "s#.*\/([^/?]+)\?.*#\1#" <<<"$url"); wget -O "$name" "$url"' ''

或者使用这个封装函数

.. code: shell

    wget_download() {
        local url=$1
        local passcode=$2
        local procs=$(($3))
        if [ $procs -le 0 ]; then
            procs=1
        fi
        /usr/bin/env python3 ctfile_share_download_url.py "$url" -p "$passcode" | xargs -n 1 -P "${procs}" bash -c 'url=$1; name=$(sed -E "s#.*\/([^/?]+)\?.*#\1#" <<<"$url"); wget -O "$name" "$url"' ''
    }
    wget_download $url $passcode

2. 获取所有非 zip 压缩包且未被下载的文件的下载链接：

.. code: shell

    python ctfile_share_download_url.py "$url" -p "$passcode" -t code -c '
    from os.path import exists

    def check(attr):
        if attr["isdir"]:
            return True
        name = attr["name"]
        return not name.endswith(".zip") and not exists(name)'
""", formatter_class=RawTextHelpFormatter)
    parser.add_argument("url", nargs="?", help="分享链接")
    parser.add_argument("-p", "--passcode", default="", help="口令")
    parser.add_argument("-c", "--predicate-code", help="断言，当断言的结果为 True 时，链接会被输出，未指定此参数则自动为 True")
    parser.add_argument(
        "-t", "--predicate-type", choices=("expr", "re", "lambda", "stmt", "code", "path"), default="expr", 
        help="""断言类型
    - expr    （默认值）表达式，会注入一个名为 attr 的字典，包含文件的信息
    - re      正则表达式，如果在文件的相对路径中可搜索到此模式（如果是目录，则有后缀斜杠 /），则断言为 True
    - lambda  lambda 函数，接受一个参数，此参数是一个包含文件信息的字典
    - stmt    语句，当且仅当不抛出异常，则视为 True，会注入一个名为 attr 的字典，包含文件的信息
    - code    代码，运行后需要在它的全局命名空间中生成一个 check 函数用于断言，接受一个参数，此参数是一个包含文件信息的字典
    - path    代码的路径，运行后需要在它的全局命名空间中生成一个 check 函数用于断言，接受一个参数，此参数是一个包含文件信息的字典

attr 字典的格式如下（包含这些 key）
    {
        'id': 999155365, 
        'isdir': False, 
        'name': '151-200.zip', 
        'size': '1.11 GB', 
        'tempdir': 'tempdir-AmBUZlViXDICMQ1iUmpXM1N8DDRbYlpiXDdZOw5uV2gBZlJgV3gPZlBlB2AFMgZmBjEEMQE1CDlcMg', 
        'parent_id': 59373355, 
        'relpath': '151-200.zip',
    }
""")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
    args = parser.parse_args()
    if args.version:
        print(*__version__, sep=".")
        raise SystemExit(0)
    if not args.url:
        parser.parse_args(["-h"])

from collections import deque
from html import unescape
from json import loads
from posixpath import basename, join as joinpath
from re import compile as re_compile
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import urlopen


CRE_VALUE_search = re_compile(r'(?<=value=")[^"]+').search
CRE_TEXT_search = re_compile(r"(?<=>)(?=\S)[^<]+").search
CRE_HREF_search = re_compile(r'(?<=href=")[^"]+').search


def _parse(item):
    fid = CRE_VALUE_search(item[0])[0]
    return {
        "id": int(fid[1:]), 
        "isdir": fid[0] == "d", 
        "name": unescape(CRE_TEXT_search(item[1])[0]), 
        "size": None if item[2] == "- -" else item[2], 
        "tempdir": CRE_HREF_search(item[1])[0][3:], 
    }


def get_dir_url(params):
    "输入查询参数，获取罗列文件夹的链接"
    api = "https://webapi.ctfile.com/getdir.php"
    resp = loads(urlopen(api+"?"+urlencode(params)).read())
    return "https://webapi.ctfile.com" + resp["file"]["url"]


def get_file_url(attr):
    "输入文件属性的字典，获取下载链接"
    api = "https://webapi.ctfile.com/getfile.php"
    params = {"path": "f", "f": attr["tempdir"]}
    resp = loads(urlopen(api+"?"+urlencode(params)).read())
    info = resp["file"]
    api = "https://webapi.ctfile.com/get_file_url.php"
    params = {"uid": info["userid"], "fid": info["file_id"], "file_chk": info["file_chk"]}
    return loads(urlopen(api+"?"+urlencode(params)).read())["downurl"]


def iterdir(url, passcode="", folder_id="", files_only=None, with_download_url=False, predicate=None):
    """遍历文件夹，获取文件或文件夹的属性字典

    :param url: 分享链接
    :param passcode: 口令
    :param folder_id: 文件夹的 id，如果为空，则用分享文件夹的 id
                      例如有个分享链接 https://url96.ctfile.com/d/35561896-59373355-6d3369?59374033
                      那么 35561896 是用户id，59373355 是分享文件夹的 id，59374033 是文件夹的 id
    :param files_only: 是否仅文件或文件夹
                        - None: 文件或文件夹（默认值）
                        - True: 仅文件
                        - False: 仅文件夹

    :return: 文件或文件夹的属性字典的迭代器
    """
    d = basename(urlsplit(url).path)
    if not folder_id:
        folder_id = d.split("-")[1]
    dq = deque(((int(folder_id), ""),))
    get, put = dq.popleft, dq.append
    params = {"path": "d", "d": d, "passcode": passcode}
    while dq:
        parent_id, dir_ = get()
        params["folder_id"] = parent_id
        link = get_dir_url(params)
        for attr in map(_parse, loads(urlopen(link).read())["aaData"]):
            attr["parent_id"] = parent_id
            relpath = attr["relpath"] = joinpath(dir_, attr["name"])
            if predicate and not predicate(attr):
                continue
            if attr["isdir"]:
                put((attr["id"], relpath))
                if files_only:
                    continue
            elif files_only == False:
                continue
            if with_download_url:
                if attr["isdir"]:
                    attr["download_url"] = None
                else:
                    while True:
                        try:
                            attr["download_url"] = get_file_url(attr)
                            break
                        except KeyError:
                            pass
            yield attr


if __name__ == "__main__":
    url = args.url
    passcode = args.passcode
    predicate_code = args.predicate_code
    predicate_type = args.predicate_type

    if predicate_code:
        from runpy import run_path
        from textwrap import dedent

        PREIDCATE_MAKERS = {}

        def register_maker(type):
            def register(func):
                PREIDCATE_MAKERS[type] = func
                return func
            return register

        def make_predicate(code, type="expr"):
            if not code:
                return None
            return PREIDCATE_MAKERS[type](code)

        @register_maker("expr")
        def make_predicate_expr(expr):
            expr = expr.strip()
            if not expr:
                return None
            code = compile(expr, "-", "eval")
            return lambda attr: eval(code, {"attr": attr})

        @register_maker("re")
        def make_predicate_re(expr):
            search = re_compile(expr).search
            return lambda attr: search(attr["name_all"] + "/"[:attr["isdir"]]) is not None

        @register_maker("lambda")
        def make_predicate_lambda(expr, *, _cre_check=re_compile(r"lambda\b").match):
            expr = expr.strip()
            if not expr:
                return None
            if _cre_check(expr) is None:
                expr = "lambda " + expr
            return eval(expr, {})

        @register_maker("stmt")
        def make_predicate_stmt(stmt):
            stmt = dedent(stmt).strip()
            if not stmt:
                return None
            code = compile(stmt, "-", "exec")
            def predicate(attr):
                try:
                    eval(code, {"attr": attr})
                    return True
                except:
                    return False
            return predicate

        @register_maker("code")
        def make_predicate_code(code):
            code = dedent(code).strip()
            if not code:
                return None
            ns = {}
            exec(code, ns)
            return ns.get("check")

        @register_maker("path")
        def make_predicate_path(path):
            ns = run_path(path, {}, run_name="__main__")
            return ns.get("check")

        predicate = make_predicate(predicate_code, predicate_type)
    else:
        predicate = None

    try:
        for item in iterdir(url, passcode, files_only=True, with_download_url=True, predicate=predicate):
            print(item["download_url"], flush=True)
    except BaseException as e:
        from sys import stderr
        print(f"{type(e).__qualname__}: {e}", file=stderr)

