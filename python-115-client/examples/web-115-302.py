#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)

try:
    # pip install python-115
    from p115 import P115FileSystem, AuthenticationError
    # pip install flask
    from flask import Flask, request, redirect, render_template_string
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "python-115", "flask"], check=True)
    from p115 import P115FileSystem, AuthenticationError
    from flask import Flask, request, redirect, render_template_string
from posixpath import dirname

app = Flask(__name__)

# TODO: 把下面的 cookie 改成自己的
cookie = "UID=...;CID=...;SEID=..."
try:
    fs = P115FileSystem.login(cookie)
except AuthenticationError:
    fs = P115FileSystem.login()

template = """\
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
            {% if dirname is not none %}
            <tr>
                <td><a href="{{ dirname }}">..</a></td>
                <td></td>
                <td>{{ "--" if attr["is_directory"] else attr["size"] }}</td>
                <td>{{ attr["etime"] }}</td>
            </tr>
            {% endif %}
            {% for attr in subattrs %}
            <tr>
                <td><a href="{{ attr["path"] }}">{{ attr["name"] }}</a></td>
                {% if attr["is_directory"] %}
                <td></td>
                {% else %}
                <td><a href="iina://weblink?url={{ request.url }}/{{ attr["name"] }}">iina</a>
                <a href="potplayer://{{ request.url }}/{{ attr["name"] }}">potplayer</a>
                <a href="vlc://{{ request.url }}/{{ attr["name"] }}">vlc</a></td>
                {% endif %}
                <td>{{ "--" if attr["is_directory"] else attr["size"] }}</td>
                <td>{{ attr["etime"] }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>"""

@app.route('/')
def index():
    return download("/")

@app.get('/<path:path>')
def download(path):
    try:
        attr = fs.attr(path)
    except FileNotFoundError:
        return "", 404
    file_id = attr["id"]
    if attr["is_directory"]:
        return render_template_string(
            template, 
            attr=attr, 
            subattrs=fs.listdir_attr(file_id), 
            dirname=None if path == "/" else dirname(attr["path"]), 
        )
    headers = {}
    for key, val in request.headers:
        if key.lower() == "user-agent":
            headers["User-Agent"] = val
            break
    try:
        url = fs.get_url(file_id, headers=headers)
    except OSError:
        return "", 404
    return redirect(url)


if __name__ == "__main__":
    app.run(host="0.0.0.0")

