#!/usr/bin/env python3
# encoding: utf-8

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
    epilog="""
---------- 使用说明 ----------

你可以打开浏览器进行直接访问。

1. 如果想要访问某个路径，可以通过查询接口

    GET {path}

或者

    GET ?path={path}

也可以通过 pickcode 查询（对于分享无效）

    GET ?pickcode={pickcode}

也可以通过 id 查询

    GET ?id={id}

也可以通过 sha1 查询（必是文件）（对于分享无效）

    GET ?sha1={sha1}

2. 查询文件或文件夹的信息，返回 json

    GET ?method=attr

3. 查询文件夹内所有文件和文件夹的信息，返回 json

    GET ?method=list

4. 获取文件的下载链接

    GET ?method=url

5. 强制视为文件下载（而不进行多余的检测）

    GET ?method=file

6. 支持的查询参数

💡 如果是分享 （路由路径以 /<share 开始），则只有 id 和 method 有效，其它参数自动忽略

 参数      | 类型    | 必填 | 说明
---------  | ------- | ---- | ----------
pickcode   | string  | 否   | 文件或文件夹的 pickcode，优先级高于 id
id         | integer | 否   | 文件或文件夹的 id，优先级高于 sha1
sha1       | string  | 否   | 文件或文件夹的 id，优先级高于 path
path       | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
method     | string  | 否   | 0. '':     缺省值，下载文件或显示目录列表
           |         |      | 2. 'url':  这个文件的下载链接和请求头，JSON 格式
           |         |      | 2. 'attr': 这个文件或文件夹的信息，JSON 格式
           |         |      | 3. 'list': 这个文件夹内所有文件和文件夹的信息，JSON 格式
           |         |      | 4. 'file': 下载文件

当文件被下载时，可以有其它查询参数

 参数      | 类型    | 必填 | 说明
---------  | ------- | ---- | ----------
web        | string  | 否   | 使用 web 接口获取下载链接（文件由服务器代理转发，不走 302）
image      | string  | 否   | 文件作为图片打开

7. 支持 webdav

在浏览器或 webdav 挂载软件 中输入
    http://localhost:8000/<dav
目前没有用户名和密码就可以浏览，支持 302

8. 支持分享列表

在浏览器中输入
    http://localhost:8000/<share
在浏览器或 webdav 挂载软件 中输入
    http://localhost:8000/<dav/<share
""")

parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
parser.add_argument("-P", "--port", default=8000, type=int, help="端口号，默认值：8000")
parser.add_argument("-cp", "--cookies-path", default="", help="cookies 文件保存路径，默认为当前工作目录下的 115-cookies.txt")
parser.add_argument("-o", "--origin", help="[webdav] origin 或者说 base_url，用来拼接路径，获取完整链接，默认行为是自行确定")
parser.add_argument("-p1", "--predicate", help="[webdav] 断言，当断言的结果为 True 时，文件或目录会被显示")
parser.add_argument(
    "-t1", "--predicate-type", default="ignore", 
    choices=("ignore", "ignore-file", "expr", "lambda", "stmt", "module", "file", "re"), 
    help="""[webdav] 断言类型，默认值为 'ignore'
    - ignore       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - ignore-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 False
                   NOTE: https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 p115.P115PathBase 对象
    - lambda       lambda 函数，接受一个 p115.P115PathBase 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 p115.P115PathBase 对象
    - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115PathBase 对象作为参数
    - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115PathBase 对象作为参数
    - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
""")
parser.add_argument("-p2", "--strm-predicate", help="[webdav] strm 断言（优先级高于 -p1/--predicate），当断言的结果为 True 时，文件会被显示为带有 .strm 后缀的文本文件，打开后是链接")
parser.add_argument(
    "-t2", "--strm-predicate-type", default="filter", 
    choices=("filter", "filter-file", "expr", "lambda", "stmt", "module", "file", "re"), 
    help="""[webdav] 断言类型，默认值为 'filter'
    - filter       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - filter-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 True
                   请参考：https://git-scm.com/docs/gitignore#_pattern_format
    - expr         表达式，会注入一个名为 path 的 p115.P115PathBase 对象
    - lambda       lambda 函数，接受一个 p115.P115PathBase 对象作为参数
    - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的 p115.P115PathBase 对象
    - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115PathBase 对象作为参数
    - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个 p115.P115PathBase 对象作为参数
    - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
""")
parser.add_argument("-fs", "--fast-strm", action="store_true", help="""快速实现 媒体筛选 和 虚拟 strm，此命令优先级较高，相当于命令行指定

    --strm-predicate-type expr \\
    --strm-predicate '(
        path.media_type.startswith(("video/", "audio/")) and
        path.suffix.lower() != ".ass"
    )' \\
    --predicate-type expr \\
    --predicate '(
        path.is_dir() or
        path.media_type.startswith("image/") or
        path.suffix.lower() in (".nfo", ".ass", ".ssa", ".srt", ".idx", ".sub", ".txt", ".vtt", ".smi")
    )'
""")
parser.add_argument("-ass", "--load-libass", action="store_true", help="加载 libass.js，实现 ass/ssa 字幕特效")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.add_argument("-l", "--license", action="store_true", help="输出授权信息")
parser.add_argument("-d", "--debug", action="store_true", help="启用 debug 模式，当文件变动时自动重启 + 输出详细的错误信息")

args = parser.parse_args()
if args.version:
    print(".".join(map(str, __version__)))
    raise SystemExit(0)
elif args.license:
    print(__license_str_zh__)
    raise SystemExit(0)

# TODO: strm 支持 iso，m2ts 等

from path_predicate import make_predicate


# origin = args.origin
# if args.fast_strm:
#     predicate = make_predicate("""(
#     path.is_dir() or
#     path.media_type.startswith("image/") or
#     path.suffix.lower() in (".nfo", ".ass", ".ssa", ".srt", ".idx", ".sub", ".txt", ".vtt", ".smi")
# )""", type="expr")
# elif predicate := args.predicate or None:
#     predicate = make_predicate(predicate, {"re": __import__("re")}, type=args.predicate_type)

# if args.fast_strm:
#     strm_predicate = make_predicate("""(
#     path.media_type.startswith(("video/", "audio/")) and
#     path.suffix.lower() != ".ass"
# )""", type="expr")
# elif strm_predicate := args.strm_predicate or None:
#     strm_predicate = make_predicate(strm_predicate, {"re": __import__("re")}, type=args.strm_predicate_type)


