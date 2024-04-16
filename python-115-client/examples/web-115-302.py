#!/usr/bin/env python3
# encoding: utf-8

"获取 115 文件信息和下载链接"

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, 
        description="获取 115 文件信息和下载链接", 
        epilog="""
---------- 使用说明 ----------

你可以打开浏览器进行直接访问。

1. 如果想要访问某个路径，可以通过查询接口

    GET /{path}

或者

    GET /?&path={path}

也可以通过 pickcode 查询

    GET /?&pickcode={pickcode}

也可以通过 id 查询

    GET /?&id={id}

2. 查询文件或文件夹的信息，需要返回 json，可以通过

    GET /?method=attr

3. 查询文件夹内所有文件和文件夹的信息，需要返回 json，可以通过

    GET /?method=list

4. 支持的查询参数

 参数    | 类型    | 必填 | 说明
-------  | ------- | ---- | ----------
pickcode | string  | 否   | 文件或文件夹的 pickcode，优先级高于 id
id       | integer | 否   | 文件或文件夹的 id，优先级高于 path
path     | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
method   | string  | 否   | 1. 'url': 【默认值】，这个文件的下载链接
         |         |      | 2. 'attr': 这个文件或文件夹的信息
         |         |      | 3. 'list': 这个文件夹内所有文件和文件夹的信息
""")
    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值 '0.0.0.0'")
    parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值 80")
    parser.add_argument("-c", "--cookie", help="115 登录 cookie，如果缺失，则从 115-cookie.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
    parser.add_argument("-pc", "--use-path-cache", action="store_true", help="启用 path 到 id 的缓存")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

try:
    from p115 import P115FileSystem
    from flask import Flask, jsonify, request, redirect, render_template_string
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "python-115", "flask"], check=True)
    from p115 import P115FileSystem
    from flask import Flask, jsonify, request, redirect, render_template_string

from os.path import expanduser, dirname, join as joinpath
from posixpath import dirname, realpath
from urllib.parse import quote, unquote


cookie = None
path_cache = None # type: None | dict
if __name__ == "__main__":
    cookie = args.cookie
    if args.use_path_cache:
        path_cache = {}
if not cookie:
    seen = set()
    for dir_ in (".", expanduser("~"), dirname(__file__)):
        dir_ = realpath(dir_)
        if dir_ in seen:
            continue
        seen.add(dir_)
        try:
            cookie = open(joinpath(dir_, "115-cookie.txt")).read()
            if cookie:
                break
        except FileNotFoundError:
            pass

fs = P115FileSystem.login(cookie, path_to_id=path_cache)
if not cookie and fs.client.cookie != cookie:
    open("115-cookie.txt", "w").write(fs.client.cookie)

KEYS = (
    "id", "parent_id", "name", "path", "sha1", "pickcode", "is_directory", 
    "size", "ctime", "mtime", "atime", "thumb", "star", 
)
application = Flask(__name__)


def get_url_with_pickcode(pickcode):
    headers = {}
    for key, val in request.headers:
        if key.lower() == "user-agent":
            headers["User-Agent"] = val
            break
    try:
        url = fs.get_url_from_pickcode(pickcode, detail=True, headers=headers)
        resp = redirect(url)
        resp.headers["Content-Disposition"] = 'attachment; filename="%s"' % quote(url["file_name"]) # type: ignore
        return resp
    except OSError:
        return "Not Found", 404


@application.get("/")
def index():
    return query("/")


@application.get("/<path:path>")
def query(path):
    method = request.args.get("method", "url")
    pickcode = request.args.get("pickcode")
    fid = request.args.get("id") # type: None | int | str
    if method == "attr":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                attr = fs.attr(int(fid))
            else:
                path = request.args.get("path") or path
                attr = fs.attr(path)
        except FileNotFoundError:
            return "Not Found", 404
        return jsonify({k: attr.get(k) for k in KEYS})
    elif method == "list":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                children = fs.listdir_attr(int(fid))
            else:
                path = request.args.get("path") or path
                children = fs.listdir_attr(path)
        except FileNotFoundError:
            return "Not Found", 404
        except NotADirectoryError as exc:
            return f"Bad Request: {exc}", 400
        return jsonify([{k: attr.get(k) for k in KEYS} for attr in children])
    if pickcode:
        return get_url_with_pickcode(pickcode)
    try:
        if fid is not None:
            attr = fs.attr(int(fid))
        else:
            path = request.args.get("path") or path
            attr = fs.attr(path)
    except FileNotFoundError:
        return "Not Found", 404
    if not attr["is_directory"]:
        return get_url_with_pickcode(attr["pickcode"])
    try:
        children = fs.listdir_attr(attr["id"])
    except NotADirectoryError as exc:
        return f"Bad Request: {exc}", 400
    url = unquote(request.url)
    try:
        origin = url[:url.index("/", 8)]
    except ValueError:
        origin = url
    for subattr in children:
        subpath = quote(subattr["path"], safe=":/")
        if subattr["is_directory"]:
            subattr["url"] = f"{origin}{subpath}?id={subattr['id']}"
        else:
            subattr["url"] = f"{origin}{subpath}?pickcode={subattr['pickcode']}"
    return render_template_string(
        """\
<!DOCTYPE html>
<html>
<head>
    <title>115 File List</title>
</head>
<body>
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Open</th>
                <th>Size</th>
                <th>Last Modified</th>
            </tr>
        </thead>
        <tbody>
            {% if attr["id"] != 0 %}
            <tr>
                <td><a href="/?id={{ attr["parent_id"] }}">..</a></td>
                <td></td>
                <td>--</td>
                <td>--</td>
            </tr>
            {% endif %}
            {% for attr in children %}
            <tr>
                {% set name = attr["name"] %}
                {% set url = attr["url"] %}
                <td><a href="{{ url }}">{{ name }}</a></td>
                {% if attr["is_directory"] %}
                <td></td>
                <td>--</td>
                {% else %}
                <td><a href="iina://weblink?url={{ url }}">iina</a>
                <a href="potplayer://{{ url }}">potplayer</a>
                <a href="vlc://{{ url }}">vlc</a></td>
                <td>{{ attr["size"] }}</td>
                {% endif %}
                <td>{{ attr["etime"] }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>""", 
        attr=attr, 
        children=children, 
        origin=origin, 
    )


if __name__ == "__main__":
    application.run(host=args.host, port=args.port, threaded=True)

