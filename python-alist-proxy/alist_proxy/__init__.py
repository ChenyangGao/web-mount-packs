#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 8)
__all__ = ["make_application", "make_application_with_fs_events", "make_application_with_fs_event_stream"]

import logging

from asyncio import get_running_loop, sleep as async_sleep, to_thread, Lock, TaskGroup
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from inspect import isawaitable, iscoroutinefunction
from ipaddress import ip_address
from itertools import islice
from os.path import basename as os_basename
from posixpath import basename, join as joinpath, split as splitpath
from shutil import COPY_BUFSIZE # type: ignore
from re import compile as re_compile
from traceback import format_exc
from typing import cast, Any
from urllib.parse import unquote, urlsplit
from weakref import WeakValueDictionary
from xml.etree.ElementTree import fromstring

from aiohttp import ClientSession
from alist import AlistClient
from blacksheep import redirect, Application, Request, Response, Router, WebSocket
from blacksheep.contents import Content, StreamedContent
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from cookietools import cookies_str_to_dict
from orjson import dumps, loads
from yarl import URL


# NOTE: 115 的 ssoent 对应的 app，与扫码登录有关
SSOENT_TO_APP = {
    "A1": "web",
    "A2": "android",
    "A3": "ios",
    "A4": "115ipad",
    "B1": "android",
    "D1": "ios",
    "D2": "ios",
    "D3": "115ios",
    "F1": "android",
    "F2": "android",
    "F3": "115android",
    "H1": "115ipad",
    "H2": "115ipad",
    "H3": "115ipad",
    "I1": "tv",
    "M1": "qandroid",
    "N1": "ios",
    "P1": "windows",
    "P2": "mac",
    "P3": "linux",
    "R1": "wechatmini",
    "R2": "alipaymini",
    "S1": "harmony",
}
DEFAULT_METHODS = [
    "GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", 
    "TRACE", "PATCH", "MKCOL", "COPY", "MOVE", "PROPFIND", 
    "PROPPATCH", "LOCK", "UNLOCK", "REPORT", "ACL", 
]
RELOGIN_115_LOCK_STORE: WeakValueDictionary[str, Lock] = WeakValueDictionary()
CRE_charset_search = re_compile(r"\bcharset=(?P<charset>[^ ;]+)").search
CRE_copy_name_extract = re_compile(r"^copy \[(.*?)\]\(/(.*?)\) to \[(.*?)\]\(/(.*)\)$").fullmatch
CRE_upload_name_extract = re_compile(r"^upload (.*?) to \[(.*?)\]\(/(.*)\)$").fullmatch
CRE_transfer_name_extract = re_compile(r"^transfer (.*?) to \[(.*)\]$").fullmatch
logging.basicConfig(format="[\x1b[1m%(asctime)s\x1b[0m] (\x1b[1;36m%(levelname)s\x1b[0m) "
                            "\x1b[0m\x1b[1;35malist-proxy\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s")


def get_charset(content_type: str, default: str = "utf-8") -> str:
    """从 content-type 请求头，获取编码信息
    """
    match = CRE_charset_search(content_type)
    if match is None:
        return "utf-8"
    return match["charset"]


def is_private(host: str, /) -> bool:
    """判断一个主机是不是局域网的
    """
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        return ip_address(host).is_private
    except ValueError:
        return False


async def storage_of(client: AlistClient, path: str) -> None | dict:
    """从 alist 获取某个路径所属的存储
    """
    path = path.rstrip("/")
    resp = await client.admin_storage_list(async_=True)
    storages = resp["data"]["content"]
    selected_storage = None
    for storage in storages:
        if storage["mount_path"] == path:
            return storage
        elif path.startswith(storage["mount_path"] + "/"):
            if not selected_storage or len(selected_storage["mount_path"]) < storage["mount_path"]:
                selected_storage = storage
    return selected_storage


async def relogin_115(session: ClientSession, cookies: str) -> None | str:
    """115 网盘，用一个被 405 风控的 cookies，获取一个新的 cookies
    """
    ssoent = cookies_str_to_dict(cookies)["UID"].split("_")[1]
    app = SSOENT_TO_APP.get(ssoent, "harmony")

    request = session.request

    async def urlopen(url, method="GET", **request_kwargs):
        async with request(method=method, url=url, **request_kwargs) as resp:
            json = loads(await resp.read())
            if not json["state"]:
                raise OSError(json)
            return json

    qrcode_token_api = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
    resp = await urlopen(qrcode_token_api)
    uid = resp["data"]["uid"]

    qrcode_scan_api = f"https://qrcodeapi.115.com/api/2.0/prompt.php?uid={uid}"
    await urlopen(qrcode_scan_api, headers={"Cookie": cookies})

    qrcode_confirm_api = "https://hnqrcodeapi.115.com/api/2.0/slogin.php"
    await urlopen(qrcode_confirm_api, params={"key": uid, "uid": uid, "client": 0}, headers={"Cookie": cookies})

    qrcode_result_api = f"https://passportapi.115.com/app/1.0/{app}/1.0/login/qrcode/"
    resp = await urlopen(qrcode_result_api, "POST", data={"account": uid})

    return "; ".join(f"{k}={v}" for k, v in resp["data"]["cookie"].items())


async def update_115_cookies(client: AlistClient, path: str, session: ClientSession):
    """115 网盘，更新某个路径所对应存储的 cookies，必须仅是被 405 风控
    """
    storage = await storage_of(client, path)
    if not storage or storage["driver"] != "115 Cloud":
        return
    addition = loads(storage["addition"])
    cookies = addition["cookie"]
    async with RELOGIN_115_LOCK_STORE.setdefault(storage["mount_path"], Lock()):
        if cookies == addition["cookie"]:
            addition["cookie"] = await relogin_115(session, addition["cookie"])
            storage["addition"] = dumps(addition).decode("utf-8")
            client.admin_storage_update(storage)


def make_application(
    alist_token: str = "", 
    base_url: str = "http://localhost:5244", 
    collect: None | Callable[[dict], Any] = None, 
    webhooks: None | Sequence[str] = None, 
    project: None | Callable[[dict], None | dict] = None, 
    methods: list[str] = DEFAULT_METHODS, 
    threaded: bool = False, 
) -> Application:
    """创建一个 blacksheep 应用，用于反向代理 alist，并持续收集每个请求事件的消息

    :param alist_token: alist 的 token，提供此参数可在 115 网盘遭受 405 风控时自动扫码刷新 cookies
    :param base_url: alist 的 base_url
    :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
    :param webhooks: 一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}
    :param project: 调用以对请求事件的消息进行映射处理，如果结果为 None，则丢弃此消息
    :param methods: 需要监听的 HTTP 方法集
    :param threaded: collect 和 project，如果不是 async 函数，就放到单独的线程中运行

    :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    """
    app = Application(router=Router())
    app_ns = app.__dict__
    logger = getattr(app, "logger")
    logger.level = 20
    base_url_is_private = is_private(URL(base_url).host or "")

    if collect is None and not webhooks:
        collect = cast(
            Callable[[dict], Any], 
            lambda data, *, log=logger.info: log(dumps(data).decode("utf-8"))
        )
    if threaded:
        if not iscoroutinefunction(collect):
            collect = partial(to_thread, collect) # type: ignore
        if project is not None and not iscoroutinefunction(project):
            project = partial(to_thread, project) # type: ignore
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

    if alist_token:
        client = AlistClient.from_auth(alist_token, base_url)
        resp = client.auth_me()
        if resp["code"] != 200:
            raise ValueError(resp)
        elif resp["data"]["id"] != 1:
            raise ValueError("you are not admin of alist")

    @app.on_middlewares_configuration
    def configure_forwarded_headers(app: Application):
        app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))

    @app.on_start
    async def on_start(app: Application):
        app_ns["running"] = True

    @app.lifespan
    async def register_http_client(app: Application):
        async with ClientSession() as session:
            app.services.register(ClientSession, instance=session)
            yield

    @app.lifespan
    async def register_task_group(app: Application):
        session = app.services.resolve(ClientSession)
        async def work(result: dict):
            try:
                task: None | dict = result
                if project is not None:
                    if isawaitable(task := project(cast(dict, task))):
                        task = await task
                if task is None:
                    return
            except BaseException as e:
                logger.exception(f"can't project data: {result!r}")
                return
            if collect is not None:
                try:
                    if isawaitable(ret := collect(task)):
                        await ret
                except BaseException as e:
                    logger.exception(f"can't collect data: {result!r}")
            if webhooks:
                try:
                    data = dumps(task)
                    async with TaskGroup() as task_group:
                        create_task = task_group.create_task
                        for webhook in webhooks:
                            create_task(session.post(webhook, data=data, headers={"Content-Type": "application/json; charset=utf-8"}))
                except BaseException as e:
                    logger.exception(f"webhook sending failed: {e!r}")
                    pass
        async with TaskGroup() as task_group:
            app.services.register(TaskGroup, instance=task_group)
            create_task = task_group.create_task
            task_group.__dict__["collect"] = lambda result: create_task(work(result))
            yield
            app_ns["running"] = False

    @app.router.route("/", methods=methods)  
    @app.router.route("/<path:path>", methods=methods)
    async def proxy(
        request: Request, 
        session: ClientSession, 
        task_group: TaskGroup, 
        path: str = "", 
    ):
        proxy_base_url = f"{request.scheme}://{request.host}"
        request_headers = [
            (k, base_url + v[len(proxy_base_url):] if k == "destination" and v.startswith(proxy_base_url) else v)
            for k, v in ((str(k.lower(), "latin-1"), str(v, "latin-1")) for k, v in request.headers)
            if k != "host"
        ]
        method = request.method.upper()
        url_path = unquote(str(request.url))
        payload: dict = dict(
            method  = method, 
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
            if method == "GET" and (url_path == "/favicon.ico" or url_path.startswith(("/d/", "/p/", "/dav/", "/images/"))):
                if not base_url_is_private or is_private(URL(proxy_base_url).host or ""):
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

            while True:
                response = await session.request(
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
                if method == "PROPFIND" and response_status == 404 and alist_token:
                    path = url_path.removeprefix("/dav")
                    try:
                        resp = await client.fs_list({"path": path}, async_=True)
                        if resp["code"] == 500 and "<title>405</title>" in resp["message"]:
                            await update_115_cookies(client, path, session)
                            continue
                    except Exception:
                        pass
                content_type = response.headers.get("content-type", "")
                if content_type.startswith(("text/plain", "application/json", "application/xml", "text/xml")):
                    excluded_headers = ("content-encoding", "content-length", "transfer-encoding")
                    headers          = [
                        (bytes(k, "latin-1"), bytes(v, "latin-1")) 
                        for k, v in response_headers if k not in excluded_headers
                    ]
                    content = await response.read()
                    if content_type.startswith("application/json"):
                        json = result["response"]["json"] = loads(content.decode(get_charset(content_type)))
                        if url_path == "/api/fs/list":
                            if (
                                alist_token and
                                json["code"] == 500 and
                                "<title>405</title>" in json["message"]
                            ):
                                try:
                                    await update_115_cookies(
                                        client, 
                                        result["request"]["payload"]["json"]["path"], 
                                        session, 
                                    )
                                    continue
                                except Exception:
                                    pass
                        elif url_path == "/api/fs/get":
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
                                if await request.is_disconnected():
                                    break
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
    alist_token: str = "", 
    base_url: str = "http://localhost:5244", 
    collect: None | Callable[[dict], Any] = None, 
    webhooks: None | Sequence[str] = None, 
    threaded: bool = False, 
) -> Application:
    """只收集和文件系统操作有关的事件

    :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
    :param base_url: alist 的 base_url
    :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
    :param webhooks: 一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}
    :param threaded: collect 如果不是 async 函数，就放到单独的线程中运行

    :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    """
    async def project(data):
        if "category" in data:
            data.setdefault("datetime", datetime.now().isoformat())
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
            data = {"datetime": datetime.now().isoformat(), "category": "web", "type": "", "method": basename(urlp.path), "payload": payload.get("json")}
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
                "datetime": datetime.now().isoformat(), 
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
        alist_token=alist_token, 
        base_url=base_url, 
        collect=collect, 
        webhooks=webhooks, 
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
                    "datetime": datetime.now().isoformat(), 
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
                    "datetime": datetime.now().isoformat(), 
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
                    "datetime": datetime.now().isoformat(), 
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
            run_worker(client.offline_download_transfer_tasklist, convert)

    return app


def make_application_with_fs_event_stream(
    alist_token: str, 
    base_url: str = "http://localhost:5244", 
    db_uri: str = "sqlite", 
    webhooks: None | Sequence[str] = None, 
):
    """只收集和文件系统操作有关的事件，存储到 redis streams，并且可以通过 websocket 拉取

    :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
    :param base_url: alist 的 base_url
    :param db_uri: 数据库连接的 URI，格式为 "{dbtype}://{host}:{port}/{path}

        - dbtype: 数据库类型，目前仅支持 "sqlite"、"mongodb" 和 "redis"
        - host: （非 "sqlite"）ip 或 hostname，如果忽略，则用 "localhost"
        - port: （非 "sqlite"）端口号，如果忽略，则自动使用此数据库的默认端口号
        - path: （限 "sqlite"）文件路径，如果忽略，则为 ""（会使用一个临时文件）

        如果你只输入 dbtype 的名字，则视为 "{dbtype}://"
        如果你输入了值，但不能被视为 dbtype，则自动视为 path，即 "sqlite:///{path}"
    :param webhooks: 一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}

    :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    """
    if not db_uri:
        return make_application_with_fs_events(
            alist_token=alist_token, 
            base_url=base_url, 
            webhooks=webhooks, 
        )

    match db_uri:
        case "sqlite":
            scheme = "sqlite"
            path = ""
        case "redis":
            scheme = "redis"
            host = "localhost"
            port = 6379
        case "mongodb":
            scheme = "mongodb"
            host = "localhost"
            port = 27017
        case _:
            urip = URL(db_uri)
            match urip.scheme:
                case "sqlite":
                    scheme = "sqlite"
                    path = urip.path.removeprefix("/")
                case "redis":
                    scheme = "redis"
                    host = urip.host or "localhost"
                    port = int(urip.port or 0) or 6379
                case "mongodb":
                    scheme = "mongodb"
                    host = urip.host or "localhost"
                    port = int(urip.port or 0) or 27017
                case _:
                    scheme = "sqlite"
                    path = db_uri

    if scheme == "redis":
        from redis.asyncio import Redis
        from redis.exceptions import ResponseError

        redis: Any = None

        app = make_application_with_fs_events(
            alist_token=alist_token, 
            base_url=base_url, 
            collect=lambda data: redis.xadd("alist:fs", {"data": dumps(data)}), 
            webhooks=webhooks, 
        )
        app_ns = app.__dict__

        @app.lifespan
        async def register_redis(app: Application):
            nonlocal redis
            async with Redis(host=host, port=port) as redis:
                app.services.register(Redis, instance=redis)
                yield

        @app.router.route("/pull", methods=["GET_WS"])
        async def push(websocket: WebSocket, lastid: str = "", group: str = "", name: str = ""):
            await websocket.accept()
            async with Redis(host=host, port=port) as redis:
                if group:
                    try:
                        await redis.xgroup_create(name="alist:fs", groupname=group)
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
                while app_ns["running"]:
                    messages = await read(streams={"alist:fs": last_id}, block=1000)
                    if messages:
                        for last_id, item in messages[0][1]:
                            await websocket.send_bytes(b'{"id": "%s", "data": %s}' % (last_id, item[b"data"]))
    elif scheme == "mongodb":
        from bson import ObjectId
        from dateutil.parser import parse as parse_date
        from motor.motor_asyncio import AsyncIOMotorClient

        app = make_application_with_fs_events(
            alist_token=alist_token, 
            base_url=base_url, 
            collect=lambda data: mongo_col.insert_one({"data": data}), 
            webhooks=webhooks, 
        )
        app_ns = app.__dict__

        db_uri = f"mongodb://{host}:{port}"
        mongo_col: Any = None

        @app.lifespan
        async def register_mongodb(app: Application):
            nonlocal mongo_col
            try:
                mongo: AsyncIOMotorClient = AsyncIOMotorClient(db_uri)
                mongo_col = mongo["alist"]["alist:fs"]
                app.services.register(AsyncIOMotorClient, instance=mongo)
                yield
            finally:
                mongo.close()

        @app.router.route("/pull", methods=["GET_WS"])
        async def push(websocket: WebSocket, lastid: str = "", from_datetime: str = ""):
            await websocket.accept()
            predicate: dict = {}
            if lastid:
                predicate = {"_id": {"$gt": ObjectId(lastid)}}
            elif from_datetime:
                predicate = {"_id": {"$gt": ObjectId.from_datetime(parse_date(from_datetime))}}
            else:
                last_doc = await anext(mongo_col.find().sort("_id", -1).limit(1), None)
                if last_doc:
                    predicate = {"_id": {"$gt": last_doc["_id"]}}
            if (await mongo_col.database.command("isMaster"))["ismaster"]:
                while app_ns["running"]:
                    item = None
                    async for item in mongo_col.find(predicate).sort("_id"):
                        await websocket.send_bytes(dumps({"id": str(item["_id"]), "data": item["data"]}))
                    if item:
                        predicate = {"_id": {"$gt": item["_id"]}}
                    await async_sleep(0.01)
            else:
                async with mongo_col.watch() as stream:
                    if predicate:
                        async for item in mongo_col.find(predicate).sort("_id"):
                            await websocket.send_bytes(dumps({"id": str(item["_id"]), "data": item["data"]}))
                    async for item in stream:
                        if not app_ns["running"]:
                            break
                    await websocket.send_bytes(dumps({"id": str(item["_id"]), "data": item["data"]}))
    else:
        from dateutil.parser import parse as parse_date
        from aiosqlite import connect, Connection

        async def collect(item, /):
            try:
                await sqlite.execute('INSERT INTO "alist:fs"(data) VALUES (?)', (dumps(item),))
                await sqlite.commit()
            except BaseException as e:
                await sqlite.rollback()
                raise

        app = make_application_with_fs_events(
            alist_token=alist_token, 
            base_url=base_url, 
            collect=collect, 
            webhooks=webhooks, 
        )
        app_ns = app.__dict__
        sqlite: Any = None

        @app.lifespan
        async def register_sqlite(app: Application):
            nonlocal path, sqlite
            if path:
                remove: None | Callable = None
            else:
                from tempfile import mktemp
                from uuid import uuid4
                from os import remove
                path = mktemp(prefix=str(uuid4()), suffix=".db")
            try:
                async with connect(path) as sqlite:
                    await sqlite.executescript("""\
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS "alist:fs" (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    data JSON NOT NULL, 
    datetime DATETIME GENERATED ALWAYS AS (data->'datetime') STORED
);
CREATE INDEX IF NOT EXISTS "idx_alist:fs_datetime" ON "alist:fs"(datetime);
""")
                    app.services.register(Connection, instance=sqlite)
                    yield
            finally:
                if remove is not None:
                    remove(path)

        @app.router.route("/pull", methods=["GET_WS"])
        async def push(websocket: WebSocket, lastid: str = "", from_datetime: str = ""):
            await websocket.accept()
            last_id = 0
            if lastid:
                last_id = int(lastid)
            elif from_datetime:
                async with sqlite.execute(
                    'SELECT COALESCE(MIN(id), 0) FROM "alist:fs" WHERE datetime > ?', 
                    (parse_date(from_datetime).isoformat(),)
                ) as cursor:
                    last_id = (await cursor.fetchone())[0]
            else:
                async with sqlite.execute('SELECT COALESCE(MAX(id), 0) FROM "alist:fs"') as cursor:
                    last_id = (await cursor.fetchone())[0]
            while app_ns["running"]:
                async with sqlite.execute('SELECT id, data FROM "alist:fs" WHERE id > ?', (last_id,)) as cursor:
                    async for last_id, data in cursor:
                        await websocket.send_bytes(b'{"id": %d, "data": %s}' % (last_id, data))
                    await async_sleep(0.01)
    return app

