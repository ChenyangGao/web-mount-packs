#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__doc__ = "\t\t🌍🚢 alist 网络代理抓包 🕷️🕸️"

from argparse import ArgumentParser, RawTextHelpFormatter

DEFAULT_METHODS = [
    "GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", 
    "TRACE", "PATCH", "MKCOL", "COPY", "MOVE", "PROPFIND", 
    "PROPPATCH", "LOCK", "UNLOCK", "REPORT", "ACL", 
]

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter, 
    description=__doc__, 
    epilog="""\t\t🔧🔨 使用技巧 🔩🪛

本工具可以自己提供 collect 函数的定义，因此具有一定的可定制性

1. 把日志输出到本地文件

.. code: python

    python alist_proxy.py -c '
    import logging
    from logging.handlers import TimedRotatingFileHandler

    logger = logging.getLogger("alist")
    logger.setLevel(logging.INFO)
    handler = TimedRotatingFileHandler("alist.log", when="midnight", backupCount=3650)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
    logger.addHandler(handler)

    collect = logger.info
    '

2. 使用 mongodb 存储采集到的日志

.. code: python

    python alist_proxy.py -c '
    from pymongo import MongoClient

    client = MongoClient("localhost", 27017)
    collect = client.log.alist.insert_one
    '

3. 使用 sqlite 收集采集到的日志，单独开启一个线程作为工作线程

.. code: python

    python alist_proxy.py --queue-collect -c '
    from json import dumps
    from sqlite3 import connect
    from threading import local

    ctx = local()

    def collect(event):
        try:
            con = ctx.con
        except AttributeError:
            con = ctx.con = connect("alist_log.db")
            con.execute(\"""
            CREATE TABLE IF NOT EXISTS log ( 
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                data JSON 
            ); 
            \""")
        try:
            con.execute("INSERT INTO log(data) VALUES (?)", (dumps(event),))
            con.commit()
        except:
            con.rollback()
            raise
    '

4. 如果并发量特别大，可以按批插入数据，以 mongodb 为例

第 1 种策略是收集到一定数量时，进行批量插入

.. code: python

    python alist_proxy.py -c '
    from atexit import register
    from threading import Lock

    from pymongo import MongoClient

    client = MongoClient("localhost", 27017)

    BATCHSIZE = 100

    cache = []
    push = cache.append
    insert_many = client.log.alist.insert_many
    cache_lock = Lock()

    def work():
        with cache_lock:
            if len(cache) >= BATCHSIZE:
                insert_many(cache)
                cache.clear()

    def collect(event):
        push(event)
        work()

    def end_work():
        with cache_lock:
            if cache:
                insert_many(cache)
                cache.clear()

    register(end_work)
    '

第 2 种策略是定期进行批量插入

.. code: python

    python alist_proxy.py -c '
    from atexit import register
    from time import sleep
    from _thread import start_new_thread

    from pymongo import MongoClient

    client = MongoClient("localhost", 27017)

    INTERVAL = 1
    running = True

    cache = []
    collect = cache.append
    insert_many = client.log.alist.insert_many

    def worker():
        while running:
            length = len(cache)
            if length:
                insert_many(cache[:length])
                del cache[:length]
            sleep(INTERVAL)

    def end_work():
        global running
        running = False
        if cache:
            cache_copy = cache.copy()
            cache.clear()
            insert_many(cache_copy)

    register(end_work)

    start_new_thread(worker, ())
    '
"""
)
parser.add_argument("-b", "--base-url", default="http://localhost:5244", 
                    help="被代理的网络服务的 base_url，默认值：'http://localhost:5244'")
parser.add_argument("-m", "--method", metavar="method", dest="methods", default=DEFAULT_METHODS, nargs="*", 
                    help=f"被代理的 http 方法，默认值：{DEFAULT_METHODS}")
parser.add_argument("-c", "--collect", default="", help="""\
提供一段代码，里面必须暴露一个名为 collect 的函数，这个函数接受一个位置参数，用来传入 1 条日志
除此以外，我还会给这个函数注入一些全局变量
    - app: 这个 flask 应用对象
    - request: 当前的请求对象

默认的行为是把信息输出到日志里面，代码为

    collect = lambda event: app.logger.info(repr(event))

""")
parser.add_argument("-q", "--queue-collect", action="store_true", 
                    help=f"单独启动个线程用来执行收集，通过队列进行中转")

if __name__ == "__main__":
    parser.add_argument("-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值：'0.0.0.0'")
    parser.add_argument("-p", "--port", default=8000, type=int, help="端口号，默认值：8000")
    parser.add_argument("-d", "--debug", action="store_true", help="启用 flask 的 debug 模式")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
else:
    from sys import argv
    from warnings import warn

    try:
        args_start = argv.index("--")
        args, unknown = parser.parse_known_args(argv[args_start+1:])
        if unknown:
            warn(f"unknown args passed: {unknown}")
    except ValueError:
        args = parser.parse_args([])


from functools import partial
from json import loads
from shutil import COPY_BUFSIZE # type: ignore
from re import compile as re_compile
from textwrap import dedent
from traceback import format_exc

try:
    from flask import request, Flask, Response
    from urllib3 import request as urllib3_request
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "flask", "urllib3"], check=True)
    from flask import request, Flask, Response
    from urllib3 import request as urllib3_request


CRE_charset_search = re_compile(r"\bcharset=(?P<charset>[^ ;]+)").search

BASE_URL = args.base_url.rstrip("/")
if not BASE_URL.startswith(("http://", "https://")):
    if BASE_URL.startswith("/"):
        BASE_URL = "http://localhost" + BASE_URL
    elif BASE_URL.startswith("://"):
        BASE_URL = "http" + BASE_URL
    else:
        BASE_URL = "http://" + BASE_URL
METHODS = args.methods or DEFAULT_METHODS

app = Flask(__name__)
app.logger.level = 20

code = dedent(args.collect).strip()
if code:
    ns: dict = {"request": request, "app": app}
    exec(code, ns)
    collect = ns["collect"]
else:
    collect = lambda event: app.logger.info(repr(event))

queue_collect = args.queue_collect
if queue_collect:
    from _thread import start_new_thread
    from queue import Queue

    queue: Queue = Queue()
    work = collect

    def worker():
        while True:
            task = queue.get()
            try:
                work(task)
            except BaseException as e:
                app.logger.exception(e)
            finally:
                queue.task_done()

    start_new_thread(worker, ())
    collect = queue.put


def get_charset(content_type: str, default="utf-8") -> str:
    match = CRE_charset_search(content_type)
    if match is None:
        return "utf-8"
    return match["charset"]


@app.route("/", defaults={"path": ""}, methods=METHODS)  
@app.route("/<path:path>", methods=METHODS)
def redirect(path: str):
    payload = dict(
        method  = request.method, 
        url     = BASE_URL + request.url[len(request.host_url.rstrip("/")):], 
        headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}, 
    )
    result: dict = {
        "request": {
            "url": request.url, 
            "payload": dict(payload), 
        }
    }
    try:
        content_type = request.headers.get("content-type") or ""
        if content_type.startswith("application/json"):
            data = payload["body"] = request.get_data()
            result["request"]["payload"]["json"] = loads(data.decode(get_charset(content_type)))
        elif content_type.startswith(("text/", "application/xml", "application/x-www-form-urlencoded")):
            data = payload["body"] = request.get_data()
            result["request"]["payload"]["text"] = data.decode(get_charset(content_type))
        else:
            payload["body"] = iter(partial(request.stream.read, COPY_BUFSIZE), b"")
        response = urllib3_request( # type: ignore
            **payload, 
            timeout         = None, 
            redirect        = False, 
            preload_content = False, 
            decode_content  = False, 
        )
        result["response"] = {
            "status": response.status, 
            "headers": dict(response.headers), 
        }
        content_type = response.headers.get("content-type") or ""
        if content_type.startswith(("text/", "application/json", "application/xml")):
            excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
            headers          = [(k, v) for k, v in response.headers.items() if k.lower() not in excluded_headers]
            response.decode_content = True
            content = response.read()
            if content_type.startswith("application/json"):
                result["response"]["json"] = loads(content.decode(get_charset(content_type)))
            else:
                result["response"]["text"] = content.decode(get_charset(content_type))
            return Response(content, response.status, headers)
        else:
            return Response(response, response.status, list(response.headers.items()))
    except BaseException as e:
        result["exception"] = {
            "reason": f"{type(e).__module__}.{type(e).__qualname__}: {e}", 
            "traceback": format_exc(), 
        }
        raise
    finally:
        try:
            collect(result)
        except BaseException as e:
            app.logger.exception(e)


if __name__ == "__main__":
    if args.debug:
        app.logger.level = 10
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)

