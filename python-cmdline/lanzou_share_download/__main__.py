#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__license__ = "MIT <https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/lanzou_share_download/LICENSE>"
__version__ = (0, 0, 5)

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="""\
从蓝奏云的分享，提取下载链接或下载文件

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

python lanzou_share_download_url.py "$url" -p "$password" | xargs -n 1 -P 4 wget --header='Accept-Language: zh-CN' --content-disposition

或者使用这个封装函数

.. code: shell

wget_download() {
    local url=$1
    local password=$2
    local procs=$(($3))
    if [ $procs -le 0 ]; then
        procs=1
    fi
    /usr/bin/env python3 lanzou_share_download_url.py "$url" -p "$password" | xargs -n 1 -P "${procs}" wget --header='Accept-Language: zh-CN' --content-disposition
}
wget_download $url $password 4
""", formatter_class=RawTextHelpFormatter)
parser.add_argument("url", nargs="?", help="分享链接")
parser.add_argument("-p", "--password", default="", help="密码")
parser.add_argument("-d", "--download-dir", help="下载文件夹，如果指定此参数，会下载文件，支持断点续传")
parser.add_argument("-c", "--predicate-code", help="断言，当断言的结果为 True 时，链接会被输出，未指定此参数则自动为 True")
parser.add_argument("-sd", "--show_detail", action="store_true", help="获取文件的详细信息")
parser.add_argument(
    "-t", "--predicate-type", choices=("expr", "re", "lambda", "stmt", "code", "path"), default="expr", 
    help="""断言类型
- expr    （默认值）表达式，会注入一个名为 attr 的字典，包含文件的信息
- re      正则表达式，如果在文件名中可搜索到此模式，则断言为 True
- lambda  lambda 函数，接受一个参数，此参数是一个包含文件信息的字典
- stmt    语句，当且仅当不抛出异常，则视为 True，会注入一个名为 attr 的字典，包含文件的信息
- code    代码，运行后需要在它的全局命名空间中生成一个 check 函数用于断言，接受一个参数，此参数是一个包含文件信息的字典
- path    代码的路径，运行后需要在它的全局命名空间中生成一个 check 函数用于断言，接受一个参数，此参数是一个包含文件信息的字典

attr 字典的格式如下（包含这些 key）
{
    'id': 'ijOJd1mgk4la', 
    'short_id': 'i1mgk4l', 
    'name': '115.txt', 
    'relpath': '115.txt', 
    'isdir': False, 
    'icon': 'txt', 
    'filename': '115.txt', 
    'size': 1074, 
    'created_time': datetime.datetime(2024, 1, 27, 15, 35, 3), 
    'modified_time': datetime.datetime(2024, 1, 27, 9, 54, 17), 
    'access_time': datetime.datetime(2024, 1, 27, 9, 54, 17), 
    'download_url': 'https://i-020.wwentua.com:446/01272300160384090bb/2024/01/27/4250d0adf257bd43501519cb3d0ff41c.txt?st=WoU5J44QEZlUagF5TsqfcA&e=1706371901&b=BWYOPwI3UHsEJVB_bVnI_c&fi=160384090&pid=223-94-212-221&up=2&mp=0&co=0', 
}
""")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
args = parser.parse_args()
if args.version:
    print(*__version__, sep=".")
    raise SystemExit(0)
if not args.url:
    parser.parse_args(["-h"])

url = args.url
password = args.password
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
        return lambda attr: search(attr["name_all"]) is not None

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
    kwargs = {"predicate": predicate}
    if args.show_detail:
        kwargs["show_detail"] = True
    else:
        kwargs["for_download"] = True
    for item in iterdir(url, password, **kwargs):
        print(item["download_url"], flush=True)
except BrokenPipeError:
    from sys import stderr
    stderr.close()
except BaseException as e:
    from sys import stderr
    print(f"{type(e).__qualname__}: {e}", file=stderr)

