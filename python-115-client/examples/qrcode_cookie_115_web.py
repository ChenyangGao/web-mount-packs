#!/usr/bin/env python3
# encoding: utf-8

"扫码获取 115 cookie（网页版）"

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = [
    "AppEnum", "get_qrcode_token", "get_qrcode_status", "post_qrcode_result", 
    "get_qrcode", "login_with_qrcode", 
]

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description="""\
扫码获取 115 cookie

默认在命令行输出，需要安装 qrcode: pip install qrcode
    - https://pypi.org/project/qrcode/
可以指定 -o 或 --open-qrcode 直接打开图片扫码
""", formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "app", nargs="?", default="qandroid", 
        choices=("web", "ios", "115ios", "android", "115android", "115ipad", "tv", 
                 "qandroid", "windows", "mac", "linux", "wechatmini", "alipaymini"), 
        help="选择一个 app 进行登录，默认为 'qandroid'，注意：这会把已经登录的相同 app 踢下线", 
    )
    parser.add_argument("-H", "--host", default="localhost", help="ip 或 hostname，默认值 'localhost'")
    parser.add_argument("-p", "--port", default=8000, type=int, help="端口号，默认值 8000")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from shutil import copyfileobj
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import urlopen, Request


APPS = ["web", "ios", "115ios", "android", "115android", "115ipad", "tv", 
        "qandroid", "windows", "mac", "linux", "wechatmini", "alipaymini"]


class QrcodeScanHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ("", "/"):
            html = """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>115 扫码助手</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.3.1/styles/default.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.3.1/highlight.min.js"></script>
    <style>
        body {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            background-color: #f0f0f0;
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }

        .top-container {
            display: flex;
            flex: 1;
            height: 300px;
            margin-top: 50px;
        }

        .top-item {
            flex: 1;
            justify-content: center;
            align-items: center;
            border: 1px solid #000;
            width: 300px;
        }

        .bottom-container {
            display: flex;
            flex: 1;
            justify-content: center;
            align-items: center;
        }

        .bottom-item {
            display: flex;
            flex: 1;
            justify-content: center;
            align-items: center;
        }

        .qrcode {
            text-align: center;
            padding: 20px;
            background-color: #ffffff;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            width: 200px;
            height: 310px;
        }

        .qrcode img {
            width: 200px;
            height: 200px;
            display: block;
        }

        .qrcode h2 {
            margin-bottom: 20px;
            color: #333;
        }

        select {
            appearance: none;
            -webkit-appearance: none;
            -moz-appearance: none;
            width: 200px;
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 5px;
            background-color: #fff;
            background-image: url('data:image/svg+xml;base64,PHN2ZyBmaWxsPSIjMDAwMDAwIiBoZWlnaHQ9IjI0IiB2aWV3Qm94PSIwIDAgMTYgMTYiIHdpZHRoPSIyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNNC4yOTMgNi41ODdhMSAxIDAgMDAtMS40MjkgMS40MjdsNSA1Yy40MzQuNDM0IDEuMTM3LjQzNCAxLjU3NyAwbDUtNWEuOTk5Ljk5OSAwIDAwLTEuNDE2LTEuNDE3TDEwIDguODU0IDUuNzE0IDYuNTg3YTEgMSAwIDAwLTEuNDIzLjAwMXoiLz48L3N2Zz4=');
            background-repeat: no-repeat;
            background-position: right 10px center;
            background-size: 16px 16px;
            cursor: pointer;
            font-size: 16px;
            color: #333;
        }

        select:focus {
            border-color: #007BFF;
            outline: none;
            box-shadow: 0 0 5px rgba(0, 123, 255, 0.5);
        }

        .banner {
            width: 100%;
            background-color: #3498db;
            color: white;
            padding: 10px 0;
            text-align: center;
            font-size: 18px;
            font-weight: bold;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 1000;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        .banner p {
            margin: 0;
            height: 20px
        }

        .output-box-container {
            display: flex;
            align-items: center;
            width: 600px;
            background-color: #fff;
            padding: 10px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            text-align: center;
        }

        .output-box {
            flex-grow: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            background-color: #f9f9f9;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .copy-button {
            margin-left: 10px;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            background-color: #007BFF;
            color: #fff;
            cursor: pointer;
            transition: background-color 0.3s;
        }

        .copy-button:hover {
            background-color: #0056b3;
        }

        .json-container {
            height: 350px;
            min-width: 300px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            margin-left: 20px;
            overflow: scroll;
        }

        .alert {
            padding: 20px;
            background-color: #f44336; /* Red */
            color: white;
            opacity: 1;
            transition: opacity 0.6s; /* 600ms transition for fade-out effect */
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        }

        .alert.hide {
            opacity: 0;
            visibility: hidden;
        }
    </style>
</head>
<body>
    <div class="banner">
        <p id="status"></p>
    </div>
    <div class="top-container">
        <div class="top-item qrcode">
            <h2>请扫码登录</h2>
            <img id="qrcode" src="" />
            <select id="app">
""" + "\n".join(
        f'                <option value="{app}" selected>{app}</option>' 
        if app == args.app 
        else f'                <option value="{app}">{app}</option>' 
        for app in APPS) + """
            </select>
        </div>
        <div class="top-item json-container">
            <pre><code class="json" id="result"><p style="font-size: 20px; display: flex; align-items: center; justify-content: center; height: 300px">这里将会输出响应</p></code></pre>
        </div>
    </div>
    <div class="bottom-container">
        <div class="bottom-item">
            <div class="output-box-container">
                <div id="cookie" class="output-box">
                    这里将会输出 cookies
                </div>
                <button class="copy-button">复制</button>
            </div>
        </div>
    </div>
    <script>
    document.querySelector(".copy-button").addEventListener("click", function() {
        const outputBox = document.getElementById("cookie");
        const tempTextarea = document.createElement("textarea");
        tempTextarea.value = outputBox.textContent;
        document.body.appendChild(tempTextarea);
        tempTextarea.select();
        document.execCommand('copy');
        document.body.removeChild(tempTextarea);
    });
    </script>
    <script>
    async function loadQrcode() {
        const response = await fetch("/api/token");
        if (!response.ok)
            throw new Error(`Request failed with status: ${response.status}, message: ${response.statusText}`);
        const json = await response.json();
        const {state, data: {sign, time, uid}} = json;
        if (!state)
            throw Exception(`OSError: ${JSON.stringify(json)}`);
        document.getElementById("qrcode").src = `https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode?uid=${uid}`;
        let status;
        while (true) {
            try {
                status = await loadStatus(sign, time, uid);
            } catch (e) {
                console.error(e);
                continue;
            }
            if (status == 2) {
                await loadResult(uid);
                return true;
            } else if ( status != 0 && status != 1 )
                return false;
        }
    }

    async function loadStatus(sign, time, uid) {
        const response = await fetch(`/api/status?sign=${sign}&time=${time}&uid=${uid}`)
        if (!response.ok)
            throw new Error(`Request failed with status: ${response.status}, message: ${response.statusText}`);
        const json = await response.json();
        const {state, data: {status}} = json;
        if (!state)
            throw Exception(`OSError: ${JSON.stringify(json)}`);
        const statusElement = document.getElementById("status");
        switch (status) {
            case 0:
                statusElement.textContent = "[status=0] qrcode: waiting";
                break;
            case 1:
                statusElement.textContent = "[status=1] qrcode: scanned";
                break;
            case 2:
                statusElement.textContent = "[status=2] qrcode: signed in";
                break;
            case -1:
                statusElement.textContent = "[status=-1] qrcode: expired";
                break;
            case -2:
                statusElement.textContent = "[status=-2] qrcode: canceled";
                break;
            default:
                statusElement.textContent = `[status=${status}] qrcode: abort`;
        }
        return status
    }

    async function loadResult(uid) {
        const app = document.getElementById("app").value;
        const response = await fetch(`/api/result?app=${app}&uid=${uid}`)
        if (!response.ok)
            throw new Error(`Request failed with status: ${response.status}, message: ${response.statusText}`);
        const json = await response.json();
        if (!json.state)
            throw Exception(`OSError: ${JSON.stringify(json)}`);
        document.getElementById("result").textContent = JSON.stringify(json, null, 2);
        document.getElementById("cookie").textContent = Object.entries(json.data.cookie).map(([k, v]) => `${k}=${v}`).join("; ");
        hljs.highlightAll();
    }

    async function waitingForScan() {
        while (true) {
            try {
                if (await loadQrcode())
                    break
            } catch (e) {
                console.error(e)
            }
        }
    }

    waitingForScan()
    </script>
</body>
</html>
"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif self.path.startswith("/api/token"):
            response = urlopen("https://qrcodeapi.115.com/api/1.0/web/1.0/token/")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            copyfileobj(response, self.wfile)
        elif self.path.startswith("/api/status"):
            response = urlopen("https://qrcodeapi.115.com/get/status/?" + urlsplit(self.path).query)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers() 
            copyfileobj(response, self.wfile)
        elif self.path.startswith("/api/result"):
            query = dict(parse_qsl(urlsplit(self.path).query))
            url = f"https://passportapi.115.com/app/1.0/{query['app']}/1.0/login/qrcode/"
            response = urlopen(Request(
                url, 
                data=urlencode({"account": query["uid"]}).encode("utf-8"), 
                method="POST", 
            ))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            copyfileobj(response, self.wfile)


if __name__ == "__main__":
    with ThreadingHTTPServer((args.host, args.port), QrcodeScanHandler) as httpd:
        host, port = httpd.socket.getsockname()[:2]
        url_host = f'[{host}]' if ':' in host else host
        print(
            f"Serving HTTP on {host} port {port} "
            f"(http://{url_host}:{port}/) ..."
        )

        from _thread import start_new_thread
        from time import sleep
        from webbrowser import open as browser_open

        def open_browser():
            sleep(1)
            browser_open(f"http://localhost:{port}")

        start_new_thread(open_browser, ())
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received, exiting.")

