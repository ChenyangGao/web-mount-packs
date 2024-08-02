#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 6)
__all__ = ["make_application", "make_application_with_fs_events", "make_application_with_fs_event_stream"]

import logging

from asyncio import get_running_loop, to_thread, TaskGroup
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from inspect import isawaitable, iscoroutinefunction
from itertools import islice
from os.path import basename as os_basename
from posixpath import basename, join as joinpath, split as splitpath
from shutil import COPY_BUFSIZE # type: ignore
from re import compile as re_compile
from traceback import format_exc
from typing import cast, Any
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import fromstring

from aiohttp import ClientSession
from alist import AlistClient
from blacksheep import redirect, Application, Request, Response, Router, WebSocket
from blacksheep.contents import Content, StreamedContent
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from orjson import dumps, loads
from redis.asyncio import Redis
from redis.exceptions import ResponseError


DEFAULT_METHODS = [
    "GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", 
    "TRACE", "PATCH", "MKCOL", "COPY", "MOVE", "PROPFIND", 
    "PROPPATCH", "LOCK", "UNLOCK", "REPORT", "ACL", 
]
CRE_charset_search = re_compile(r"\bcharset=(?P<charset>[^ ;]+)").search
CRE_copy_name_extract = re_compile(r"^copy \[(.*?)\]\(/(.*?)\) to \[(.*?)\]\(/(.*)\)$").fullmatch
CRE_upload_name_extract = re_compile(r"^upload (.*?) to \[(.*?)\]\(/(.*)\)$").fullmatch
CRE_transfer_name_extract = re_compile(r"^transfer (.*?) to \[(.*)\]$").fullmatch
logging.basicConfig(format="[\x1b[1m%(asctime)s\x1b[0m] (\x1b[1;36m%(levelname)s\x1b[0m) "
                            "\x1b[0m\x1b[1;35malist-proxy\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s")


def get_charset(content_type: str, default: str = "utf-8") -> str:
    match = CRE_charset_search(content_type)
    if match is None:
        return "utf-8"
    return match["charset"]


def make_application(
    base_url: str = "http://localhost:5244", 
    collect: None | Callable[[dict], Any] = None, 
    project: None | Callable[[dict], Any] = None, 
    methods: list[str] = DEFAULT_METHODS, 
    threaded: bool = False, 
) -> Application:
    """创建一个 blacksheep 应用，用于反向代理 alist，并持续收集每个请求事件的消息

    :param base_url: alist 的 base_url
    :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
    :param project: 调用以对请求事件的消息进行映射处理，如果结果为 None，则丢弃此消息
    :param methods: 需要监听的 HTTP 方法集
    :param threaded: collect 和 project，如果不是 async 函数，就放到单独的线程中运行

    :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    """
    app = Application(router=Router())
    logger = getattr(app, "logger")
    logger.level = 20

    if collect is None:
        collect = logger.info
    if threaded:
        if not iscoroutinefunction(collect):
            collect = partial(to_thread, collect)
        if project is not None and not iscoroutinefunction(project):
            project = partial(to_thread, project)
        @app.lifespan
        async def register_executor(app: Application):
            executor = ThreadPoolExecutor(thread_name_prefix="alist-proxy")
            setattr(get_running_loop(), "_default_executor", executor)
            try:
                with executor:
                    app.services.register(ThreadPoolExecutor, instance=executor)
                    yield
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

    @app.on_middlewares_configuration
    def configure_forwarded_headers(app: Application):
        app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))

    @app.on_start
    async def on_start(app: Application):
        app.__dict__["running"] = True

    @app.lifespan
    async def register_task_group(app: Application):
        async def work(result: dict):
            try:
                task = result
                if project is not None:
                    if isawaitable(task := project(task)):
                        task = await task
                if task is not None and isawaitable(ret := collect(task)):
                    await ret
            except BaseException as e:
                logger.exception(f"can't collect data: {result!r}")
        async with TaskGroup() as task_group:
            app.services.register(TaskGroup, instance=task_group)
            create_task = task_group.create_task
            task_group.__dict__["collect"] = lambda result: create_task(work(result))
            yield
            app.__dict__["running"] = False

    @app.lifespan
    async def register_http_client(app: Application):
        async with ClientSession() as client:
            app.services.register(ClientSession, instance=client)
            yield

    @app.router.route("/", methods=methods)  
    @app.router.route("/<path:path>", methods=methods)
    async def proxy(
        request: Request, 
        client: ClientSession, 
        task_group: TaskGroup, 
        path: str = "", 
    ):
        proxy_base_url = f"{request.scheme}://{request.host}"
        request_headers = [
            (k, base_url + v[len(proxy_base_url):] if k == "destination" and v.startswith(proxy_base_url) else v)
            for k, v in ((str(k.lower(), "latin-1"), str(v, "latin-1")) for k, v in request.headers)
            if k != "host"
        ]
        url_path = str(request.url)
        payload: dict = dict(
            method  = request.method, 
            url     = base_url + url_path, 
            headers = request_headers, 
        )
        result: dict = {
            "request": {
                "url": proxy_base_url + url_path, 
                "payload": dict(payload), 
            }
        }
        try:
            data: None | bytes
            if url_path.startswith(("/d/", "/p/")):
                return redirect(base_url + url_path)
            content_type = str(request.headers.get_first(b"content-type") or b"", "latin-1")
            if content_type.startswith("application/json"):
                data = payload["data"] = await request.read()
                if data:
                    result["request"]["payload"]["json"] = loads(data.decode(get_charset(content_type)))
            elif content_type.startswith(("application/xml", "text/xml", "application/x-www-form-urlencoded")):
                data = payload["data"] = await request.read()
                if data:
                    result["request"]["payload"]["text"] = data.decode(get_charset(content_type))
            else:
                payload["data"] = request.stream()
            response = await client.request(
                **payload, 
                allow_redirects=False, 
                raise_for_status=False, 
                timeout=None, 
            )
            response_status  = response.status
            response_headers = [
                (k, proxy_base_url + v[len(base_url):] if k == "location" and v.startswith(base_url) else v)
                for k, v in ((k.lower(), v) for k, v in response.headers.items())
                if k.lower() != "date"
            ]
            result["response"] = {
                "status": response_status, 
                "headers": response_headers, 
            }
            content_type = response.headers.get("content-type", "")
            if content_type.startswith(("application/json", "application/xml", "text/xml")):
                excluded_headers = ("content-encoding", "content-length", "transfer-encoding")
                headers          = [
                    (bytes(k, "latin-1"), bytes(v, "latin-1")) 
                    for k, v in response_headers if k not in excluded_headers
                ]
                content = await response.read()
                if content_type.startswith("application/json"):
                    result["response"]["json"] = loads(content.decode(get_charset(content_type)))
                    if url_path == "/api/fs/get":
                        json = result["response"]["json"]
                        if json["code"] == 200:
                            raw_url = json["data"].get("raw_url") or ""
                            if raw_url.startswith(base_url):
                                json["data"]["raw_url"] = proxy_base_url + raw_url[len(base_url):]
                                content = dumps(json)
                else:
                    result["response"]["text"] = content.decode(get_charset(content_type))
                return Response(response_status, headers, Content(bytes(content_type, "latin-1"), content))
            else:
                headers = [(bytes(k, "latin-1"), bytes(v, "latin-1")) for k, v in response_headers]
                async def reader():
                    async with response:
                        async for chunk in response.content.iter_chunked(COPY_BUFSIZE):
                            yield chunk
                return Response(response_status, headers, StreamedContent(bytes(content_type, "latin-1"), reader))
        except BaseException as e:
            result["exception"] = {
                "reason": f"{type(e).__module__}.{type(e).__qualname__}: {e}", 
                "traceback": format_exc(), 
            }
            raise
        finally:
            task_group.__dict__["collect"](result)

    return app


def make_application_with_fs_events(
    alist_token: str, 
    base_url: str = "http://localhost:5244", 
    collect: None | Callable[[dict], Any] = None, 
    threaded: bool = False, 
) -> Application:
    """只收集和文件系统操作有关的事件

    :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
    :param base_url: alist 的 base_url
    :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
    :param threaded: collect 如果不是 async 函数，就放到单独的线程中运行

    :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    """
    def project(data):
        if "category" in data:
            return data
        if not(response := data.get("response")) or not(200 <= response["status"] < 300):
            return
        payload = data["request"]["payload"]
        url = payload["url"]
        urlp = urlsplit(url)
        path = unquote(urlp.path)
        if path.startswith("/api/fs"):
            if not(200 <= response["json"]["code"] < 300):
                return
            data = {"category": "web", "type": "", "method": basename(urlp.path), "payload": payload.get("json")}
            if result := response["json"]["data"]:
                data["result"] = result
            match data["method"]:
                case "copy":
                    data["type"] = "copy"
                case "form" | "put":
                    file_path = next(v for k, v in payload["headers"] if k == "file-path")
                    data.update(type="upload", payload={"path": unquote(file_path)})
                case "get" | "list" | "search" | "dirs":
                    data["type"] = "find"
                case "mkdir":
                    data["type"] = "mkdir"
                case "move" | "recursive_move":
                    data["type"] = "move"
                case "remove" | "remove_empty_directory":
                    data["type"] = "remove"
                case "rename" | "batch_rename" | "regex_rename":
                    data["type"] = "rename"
                case _:
                    return
            return data
        elif path.startswith("/dav"):
            path = path.removeprefix("/dav")
            data = {
                "category": "dav", 
                "type": "", 
                "method": payload["method"], 
                "payload": {
                    "path": path.rstrip("/"), 
                    "is_dir": path.endswith("/"), 
                }, 
            }
            match data["method"]:
                case "COPY":
                    data["type"] = "copy"
                    destination = next(v for k, v in payload["headers"] if k == "destination")
                    data["payload"]["to_path"] = unquote(urlsplit(destination).path).rstrip("/")
                case "DELETE":
                    data["type"] = "remove"
                case "MKCOL":
                    data["type"] = "mkdir"
                case "MOVE":
                    data["type"] = "move"
                    destination = next(v for k, v in payload["headers"] if k == "destination")
                    data["payload"]["to_path"] = unquote(urlsplit(destination).path).rstrip("/")
                case "PROPFIND":
                    data["type"] = "find"
                    data["result"] = list(islice(
                        ({sel.tag.removeprefix("{DAV:}").removeprefix("{SAR:}").removeprefix("get"): sel.text for sel in el} 
                            for el in fromstring(response["text"]).iterfind(".//{DAV:}prop")
                        ), 2, None, 2
                    ))
                case "PUT":
                    data["type"] = "upload"
                case _:
                    return
            return data

    app = make_application(
        base_url=base_url, 
        collect=collect, 
        project=project, 
        threaded=threaded, 
    )
    app_ns = app.__dict__
    logger = getattr(app, "logger")

    if alist_token:
        client  = AlistClient.from_auth(alist_token, base_url)
        resp    = client.auth_me()
        if resp["code"] != 200:
            raise ValueError(resp)
        elif resp["data"]["id"] != 1:
            raise ValueError("you are not admin of alist")

        def run_worker(tasklist, convert):
            task_group = app.services.resolve(TaskGroup)
            collect: Callable[[dict], None] = task_group.__dict__["collect"]
            list_done, remove = tasklist.list_done, tasklist.remove
            async def work():
                while app_ns["running"]:
                    try:
                        ls = await list_done(async_=True)
                    except BaseException as e:
                        logger.exception(e)
                    else:
                        for task in ls:
                            if task["state"] == 2:
                                try:
                                    collect(convert(task))
                                    await remove(task["id"], async_=True)
                                except BaseException as e:
                                    logger.exception(e)
            task_group.create_task(work())

        @app.after_start
        async def pull_copy_tasklist():
            def convert(task: dict) -> dict:
                src_sto, src_path, dst_sto, dst_dir = CRE_copy_name_extract(task["name"]).groups() # type: ignore
                src_dir, name = splitpath(src_path)
                return {
                    "category": "task", 
                    "type": "copy", 
                    "method": "copy", 
                    "payload": {
                        "src_path": joinpath(src_sto, src_dir, name), 
                        "dst_path": joinpath(dst_sto, dst_dir, name), 
                        "src_storage": src_sto, 
                        "dst_storage": dst_sto, 
                        "src_dir": joinpath(src_sto, src_dir), 
                        "dst_dir": joinpath(dst_sto, dst_dir), 
                        "name": name, 
                        "is_dir": task["status"] != "getting src object", 
                    }
                }
            run_worker(client.copy_tasklist, convert)

        @app.after_start
        async def pull_upload_tasklist():
            def convert(task: dict) -> dict:
                name, dst_sto, dst_dir = CRE_upload_name_extract(task["name"]).groups() # type: ignore
                return {
                    "category": "task", 
                    "type": "upload", 
                    "method": "upload", 
                    "payload": {
                        "path": joinpath(dst_sto, dst_dir, name), 
                        "dst_storage": dst_sto, 
                        "dst_dir": joinpath(dst_sto, dst_dir), 
                        "name": name, 
                        "is_dir": False, 
                    }
                }
            run_worker(client.upload_tasklist, convert)

        @app.after_start
        async def pull_offline_download_transfer_tasklist(app: Application):
            def convert(task: dict) -> dict:
                local_path, dst_dir = CRE_transfer_name_extract(task["name"]).groups() # type: ignore
                name = os_basename(local_path)
                return {
                    "category": "task", 
                    "type": "upload", 
                    "method": "transfer", 
                    "payload": {
                        "path": joinpath(dst_dir, name), 
                        "dst_dir": dst_dir, 
                        "name": name, 
                        "is_dir": False, 
                    }
                }
            run_worker(client.upload_tasklist, convert)

    return app


def make_application_with_fs_event_stream(
    alist_token: str, 
    base_url: str = "http://localhost:5244", 
    redis_host: str = "localhost", 
    redis_port: int = 6379, 
    redis_key: str  = "alist:fs", 
):
    """只收集和文件系统操作有关的事件，存储到 redis streams，并且可以通过 websocket 拉取

    :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
    :param base_url: alist 的 base_url
    :param redis_host: redis 服务所在的主机
    :param redis_port: redis 服务的端口
    :param redis_key: redis streams 的键名

    :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    """
    redis: Any = None

    app = make_application_with_fs_events(
        alist_token=alist_token, 
        base_url=base_url, 
        collect=lambda data: redis.xadd(redis_key, {"data": dumps(data)}), 
    )

    @app.lifespan
    async def register_redis(app: Application):
        nonlocal redis
        async with Redis(host=redis_host, port=redis_port) as redis:
            app.services.register(Redis, instance=redis)
            yield

    @app.router.route("/pull", methods=["GET_WS"])
    async def push(websocket: WebSocket, lastid: str = "", group: str = "", name: str = ""):
        await websocket.accept()
        async with Redis(host=redis_host, port=redis_port) as redis:
            if group:
                try:
                    await redis.xgroup_create(name=redis_key, groupname=group)
                except ResponseError as e:
                    if str(e) != "BUSYGROUP Consumer Group name already exists":
                        raise
                if lastid:
                    last_id = bytes(lastid, "latin-1")
                else:
                    last_id = b">"
                read: Callable = partial(redis.xreadgroup, groupname=group, consumername=name)
            else:
                if lastid:
                    last_id = bytes(lastid, "latin-1")
                else:
                    last_id = b"$"
                read = redis.xread
            while True:
                messages = await read(streams={redis_key: last_id})
                if messages:
                    for last_id, item in messages[0][1]:
                        await websocket.send_bytes(b'{"id": "%s", "data": %s}' % (last_id, item[b"data"]))

    return app

