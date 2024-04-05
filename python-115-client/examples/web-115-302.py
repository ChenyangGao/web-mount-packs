#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="获取 115 文件信息和下载链接", formatter_class=RawTextHelpFormatter, epilog="")
parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值 '0.0.0.0'")
parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值 80")
parser.add_argument("-c", "--cookie", help="115 登录 cookie，如果缺失，则从 115-cookie.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下")
parser.add_argument("-pc", "--use-path-cache", action="store_true", help="启用 path 到 id 的缓存")
args = parser.parse_args()

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
from posixpath import dirname
from urllib.parse import unquote


cookie = args.cookie
if not cookie:
    for dir_ in (".", expanduser("~"), dirname(__file__)):
        try:
            cookie = open(joinpath(dir_, "115-cookie.txt")).read()
            if cookie:
                break
        except FileNotFoundError:
            pass

path_cache = {} if args.use_path_cache else None
fs = P115FileSystem.login(cookie, path_to_id=path_cache)
if fs.client.cookie != cookie:
    open("115-cookie.txt", "w").write(fs.client.cookie)

KEYS = (
    "id", "parent_id", "name", "path", "sha1", "pick_code", "is_directory", 
    "size", "ctime", "mtime", "atime", "thumb", "star", 
)
app = Flask(__name__)


def get_url_with_pickcode(pickcode):
    headers = {}
    for key, val in request.headers:
        if key.lower() == "user-agent":
            headers["User-Agent"] = val
            break
    try:
        return redirect(fs.client.download_url(pickcode, headers=headers))
    except OSError:
        return "Not Found", 404


@app.get("/")
def index():
    return query("/")


@app.get("/<path:path>")
def query(path):
    method = request.args.get("method", "url")
    fid = request.args.get("id")
    if method == "attr":
        try:
            if fid:
                attr = fs.attr(int(fid))
            else:
                path = request.args.get("path") or path
                attr = fs.attr(path)
        except FileNotFoundError:
            return "Not Found", 404
        return jsonify({k: attr.get(k) for k in KEYS})
    elif method == "list":
        try:
            if fid:
                children = fs.listdir_attr(int(fid))
            else:
                path = request.args.get("path") or path
                children = fs.listdir_attr(path)
        except FileNotFoundError:
            return "Not Found", 404
        except NotADirectoryError as exc:
            return f"Bad Request: {exc}", 400
        return jsonify([{k: attr[k] for k in KEYS} for attr in children])
    pickcode = request.args.get("pickcode")
    if pickcode:
        return get_url_with_pickcode(pickcode)
    try:
        if fid:
            attr = fs.attr(int(fid))
        else:
            path = request.args.get("path") or path
            attr = fs.attr(path)
    except FileNotFoundError:
        return "Not Found", 404
    if not attr["is_directory"]:
        return get_url_with_pickcode(attr["pick_code"])
    url = unquote(request.url)
    try:
        origin = url[:url.index("/", 8)]
    except ValueError:
        origin = url
    try:
        children = fs.listdir_attr(attr["id"])
    except NotADirectoryError as exc:
        return f"Bad Request: {exc}", 400
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
                {% if attr["is_directory"] %}
                <td><a href="/?id={{ attr["id"] }}">{{ name }}</a></td>
                <td></td>
                <td>--</td>
                {% else %}
                <td><a href="/?pickcode={{ attr["pick_code"] }}">{{ name }}</a></td>
                {% set url = origin + "?pickcode=" + attr["pick_code"] %}
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


app.run(host=args.host, port=args.port, threaded=True)

