#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__licence__ = "GPLv3 <https://www.gnu.org/licenses/gpl-3.0.txt>"

from asyncio import get_running_loop, run_coroutine_threadsafe, to_thread, BaseEventLoop, Lock
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, MutableMapping, Sequence
from contextlib import closing, suppress
from datetime import datetime
from functools import partial
from io import BytesIO
from itertools import cycle
from pathlib import Path
from posixpath import split as splitpath, splitext
from queue import SimpleQueue
from os import environ, remove
from sqlite3 import connect, register_adapter, register_converter, PARSE_DECLTYPES, Connection
from _thread import start_new_thread
from typing import cast
from urllib.parse import quote, urlsplit
from weakref import WeakValueDictionary

from a2wsgi import WSGIMiddleware
from blacksheep import redirect, text, Application, Router
from blacksheep.contents import Content, StreamedContent
from blacksheep.messages import Request, Response
from blacksheep.server.compression import use_gzip_compression
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from blacksheep.server.rendering.jinja2 import JinjaRenderer
from blacksheep.server.responses import view_async
from blacksheep.settings.html import html_settings
from blacksheep.settings.json import json_settings
from cachetools import LRUCache, TTLCache
from dictattr import AttrDict
from encode_uri import encode_uri, encode_uri_component_loose
# NOTE: 其它可用模块
# - https://pypi.org/project/user-agents/
# - https://github.com/faisalman/ua-parser-js
from httpagentparser import detect as detect_ua
from orjson import dumps as json_dumps, loads as json_loads
from p115client import check_response, CLASS_TO_TYPE, SUFFIX_TO_TYPE, P115Client, P115URL
from p115client.exception import AuthenticationError, BusyOSError
from p115client.tool import get_id_to_path, get_id_to_pickcode, get_id_to_sha1, share_iterdir, P115ID
from path_predicate import MappingPath
from posixpatht import path_is_dir_form, splits
from property import locked_cacheproperty
from pysubs2 import SSAFile
from wsgidav.wsgidav_app import WsgiDAVApp # type: ignore
from wsgidav.dav_error import DAVError # type: ignore
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider # type: ignore


register_adapter(dict, json_dumps)
register_adapter(list, json_dumps)
register_converter("JSON", json_loads)


def format_size(
    n: int, 
    /, 
    unit: str = "", 
    precision: int = 2, 
) -> str:
    "scale bytes to its proper byte format"
    if unit == "B" or not unit and n < 1024:
        return f"{n} B"
    b = 1
    b2 = 1024
    for u in ["K", "M", "G", "T", "P", "E", "Z", "Y"]:
        b, b2 = b2, b2 << 10
        if u == unit if unit else n < b2:
            break
    return f"%.{precision}f {u}B" % (n / b)


def format_timestamp(ts: int | float, /) -> str:
    return str(datetime.fromtimestamp(ts))


if __name__ == "__main__":
    import sys
    sys.path[0] = str(Path(__file__).parents[1])

environ["APP_JINJA_PACKAGE_NAME"] = "p115dav"
html_settings.use(JinjaRenderer(enable_async=True))
json_settings.use(loads=json_loads)
jinja2_filters = html_settings.renderer.env.filters
jinja2_filters["format_size"] = format_size
jinja2_filters["encode_uri"] = encode_uri
jinja2_filters["json_dumps"] = lambda data: json_dumps(data).decode("utf-8").replace("'", "&apos;")
jinja2_filters["format_timestamp"] = format_timestamp


def get_origin(request: Request) -> str:
    return f"{request.scheme}://{request.host}"


def get_status_code(e: BaseException, /) -> None | int:
    status = (
        getattr(e, "status", None) or 
        getattr(e, "code", None) or 
        getattr(e, "status_code", None)
    )
    if status is None and hasattr(e, "response"):
        response = e.response
        status = (
            getattr(response, "status", None) or 
            getattr(response, "code", None) or 
            getattr(response, "status_code", None)
        )
    return status


def reduce_image_url_layers(url: str, /) -> str:
    if not url.startswith(("http://thumb.115.com/", "https://thumb.115.com/")):
        return url
    urlp = urlsplit(url)
    sha1 = urlp.path.rsplit("/")[-1].split("_")[0]
    return f"https://imgjump.115.com/?sha1={sha1}&{urlp.query}"


def make_application(
    cookies_path: str | Path = "", 
    dbfile: str | Path = "", 
    strm_origin: str = "", 
    predicate = None, 
    strm_predicate = None, 
    load_libass: bool = False, 
    debug: bool = False, 
) -> Application:
    if cookies_path:
        cookies_path = Path(cookies_path)
    else:
        cookies_path = Path("115-cookies.txt")

    app = Application(router=Router(), show_error_details=debug)
    use_gzip_compression(app)
    app.serve_files(
        Path(__file__).with_name("static"), 
        root_path="/%3Cpic", 
        fallback_document="index.html", 
    )

    # NOTE: 缓存图片的 CDN 直链，缓存 59 分钟
    IMAGE_URL_CACHE: MutableMapping[str | tuple[str, int], None | P115URL] = TTLCache(65536, ttl=60*59)
    # NOTE: 限制请求频率，以一组请求信息为 key，0.5 秒内相同的 key 只放行一个
    URL_COOLDOWN: MutableMapping[tuple, None] = TTLCache(1024, ttl=0.5)
    # NOTE: 下载链接缓存，以减少接口调用频率，只需缓存很短时间
    URL_CACHE: MutableMapping[tuple, P115URL] = TTLCache(64, ttl=1)
    # NOTE: 缓存文件列表数据
    CACHE_ID_TO_LIST: MutableMapping[int, dict] = LRUCache(64)
    # NOTE: 缓存文件信息数据
    CACHE_ID_TO_ATTR: MutableMapping[int, AttrDict] = LRUCache(1024)
    # NOTE: 缓存文件信息数据，但是弱引用
    ID_TO_ATTR: MutableMapping[int, AttrDict] = WeakValueDictionary()
    # NOTE: 获取文件列表数据时加锁，实现了对任何 1 个目录 id，只允许同时运行 1 个拉取
    ID_TO_LIST_LOCK: MutableMapping[int, Lock] = WeakValueDictionary()
    # NOTE: 缓存 115 分享链接的提取码到接收码（密码）的映射
    SHARE_FS_MAP: dict[str, dict] = {}
    # NOTE: 后台任务队列
    QUEUE: SimpleQueue[tuple] = SimpleQueue()
    # NOTE: webdav 的文件对象缓存
    DAV_FILE_CACHE: MutableMapping[str, DAVNonCollection] = LRUCache(65536)

    put_task = QUEUE.put_nowait
    client: P115Client = None
    con: Connection = None
    loop: BaseEventLoop = None

    def queue_execute(flag):
        get = QUEUE.get
        with closing(con.cursor()) as cur:
            execute = cur.execute
            executemany = cur.executemany
            while flag:
                try:
                    sql, params = get(0.01)
                except TimeoutError:
                    continue
                if params is None:
                    execute(sql)
                elif isinstance(params, (tuple, Mapping)):
                    execute(sql, params)
                elif isinstance(params, list):
                    executemany(sql, params)
                else:
                    execute(sql, (params,))

    def query(sql, params=None, default=None):
        with closing(con.cursor()) as cur:
            if params is None:
                cur.execute(sql)
            elif isinstance(params, (tuple, Mapping)):
                cur.execute(sql, params)
            elif isinstance(params, list):
                cur.executemany(sql, params)
            else:
                cur.execute(sql, (params,))
            record = cur.fetchone()
        if record is None:
            return default
        return record[0]

    def query_all(sql, params):
        with closing(con.cursor()) as cur:
            if params is None:
                cur.execute(sql)
            elif isinstance(params, (tuple, Mapping)):
                cur.execute(sql, params)
            elif isinstance(params, list):
                cur.executemany(sql, params)
            else:
                cur.execute(sql, (params,))
            return cur.fetchall()

    async def get_id_from_db(pickcode: str = "", sha1: str = "") -> int:
        if id:
            return await to_thread(query, "SELECT id FROM data WHERE pickcode=? LIMIT 1;", pickcode, default=0)
        elif sha1:
            return await to_thread(query, "SELECT id FROM data WHERE sha1=? LIMIT 1;", sha1, default=0)
        return 0

    async def get_pickcode_from_db(id: int = 0, sha1: str = "") -> str:
        if id:
            return await to_thread(query, "SELECT pickcode FROM data WHERE id=? LIMIT 1;", id, default="")
        elif sha1:
            return await to_thread(query, "SELECT pickcode FROM data WHERE sha1=? LIMIT 1;", sha1, default="")
        return ""

    async def get_sha1_from_db(id: int = 0, pickcode: str = "") -> str:
        if id:
            return await to_thread(query, "SELECT sha1 FROM data WHERE id=? LIMIT 1;", id, default="")
        elif sha1:
            return await to_thread(query, "SELECT sha1 FROM data WHERE pickcode=? LIMIT 1;", pickcode, default="")
        return ""

    async def get_ancestors_from_db(id: int = 0) -> list[dict]:
        ancestors = [{"id": "0", "parent_id": 0, "name": ""}]
        ls = await to_thread(query_all, """\
WITH RECURSIVE t AS (
    SELECT data.id, data.parent_id, data.name FROM data WHERE id = ?
    UNION ALL
    SELECT data.id, data.parent_id, data.name FROM t JOIN data ON (t.parent_id = data.id)
)
SELECT * FROM t;""", id)
        if ls:
            ancestors.extend(dict(zip(("id", "parent_id", "name"), map(str, record))) for record in reversed(ls))
        return ancestors

    async def get_children(id: int = 0) -> None | list[dict]:
        return await to_thread(query, "SELECT data FROM list WHERE id=? LIMIT 1", id)

    def info_to_path_gen(
        path: str | Sequence[str], 
        ensure_file: None | bool = None, 
        /, 
    ) -> Iterator[P115ID]:
        fields = ("id", "parent_id", "name", "pickcode", "sha1", "is_dir")
        if isinstance(path, str):
            patht, _ = splits("/" + path)
        else:
            patht = path
        if len(patht) == 1:
            yield P115ID.of(0, {"id": 0, "parent_id": 0, "name": "", "pickcode": "", "sha1": "", "is_dir": 1})
            return
        with closing(con.cursor()) as cur:
            execute = cur.execute
            parent_id = 0
            if len(patht) > 2:
                sql = "SELECT id FROM data WHERE parent_id = ? AND is_dir AND name = ? LIMIT 1"
                for name in patht[1:-1]:
                    val = execute(sql, (parent_id, name)).fetchone()
                    if val is None:
                        return
                    parent_id, = val
            sql = "SELECT id, parent_id, name, pickcode, sha1, is_dir FROM data WHERE parent_id = ? AND name = ?"
            if ensure_file is None:
                sql += " ORDER BY is_dir DESC"
            elif ensure_file:
                sql += " AND NOT is_dir"
            else:
                sql += " AND is_dir LIMIT 1"
            for record in execute(sql, (parent_id, patht[-1])):
                yield P115ID.of(record[0], dict(zip(fields, record)))

    def info_to_path(
        path: str | Sequence[str], 
        ensure_file: None | bool = None, 
        /, 
    ) -> None | P115ID:
        return next(info_to_path_gen(path, ensure_file), None)

    def normalize_attr(info: Mapping, /) -> AttrDict:
        def typeof(attr):
            if attr["is_dir"]:
                return 0
            if int(info.get("iv", info.get("isv", 0))):
                return 4
            if "muc" in info:
                return 3
            if fclass := info.get("class", ""):
                if type := CLASS_TO_TYPE.get(fclass):
                    return type
                else:
                    return 99
            if type := SUFFIX_TO_TYPE.get(splitext(attr["name"])[1].lower()):
                return type
            elif "play_long" in info:
                return 4
            return 99
        if "share_code" in info:
            share_code = info["share_code"]
            receive_code = info.get("receive_code", "")
            sha1 = info.get("sha", "")
            is_dir = not sha1
            attr = AttrDict({
                "share_code": share_code, 
                "receive_code": receive_code, 
                "is_dir": is_dir, 
                "id": info["cid"] if is_dir else info["fid"], 
                "parent_id": info["pid"] if is_dir else info["cid"], 
                "name": info["n"], 
                "sha1": sha1, 
                "mtime": int(info["t"]), 
                "size": int(info.get("s", 0)), 
                "is_collect": int(info.get("c", 0)) == 1, 
                "thumb": info.get("u", ""), 
            })
        elif "fn" in info:
            sha1 = info.get("sha1", "")
            is_dir = not sha1
            attr = AttrDict({
                "is_dir": is_dir, 
                "id": info["fid"], 
                "parent_id": info["pid"], 
                "pickcode": info["pc"], 
                "name": info["fn"], 
                "sha1": sha1, 
                "mtime": int(info["upt"]), 
                "size": int(info.get("fs", 0)), 
                "is_collect": int(info.get("ic", 0)) == 1, 
                "thumb": info.get("thumb", ""), 
            })
        elif "n" in info:
            sha1 = info.get("sha", "")
            is_dir = not sha1
            attr = AttrDict({
                "is_dir": is_dir, 
                "id": info["cid"] if is_dir else info["fid"], 
                "parent_id": info["pid"] if is_dir else info["cid"], 
                "pickcode": info["pc"], 
                "name": info["n"], 
                "sha1": sha1, 
                "mtime": int(info["te"]), 
                "size": int(info.get("s", 0)), 
                "is_collect": int(info.get("c", 0)) == 1, 
                "thumb": info.get("u", ""), 
            })
        else:
            raise ValueError(f"can't process: {info!r}")
        id = int(attr["id"])
        if "share_code" in attr:
            key = (share_code, id)
            url = f"/?share_code={share_code}&receive_code={receive_code}&id={id}"
        else:
            pickcode = cast(str, attr["pickcode"])
            key = pickcode
            if is_dir:
                url = "/%s?id=%d" % (encode_uri_component_loose(attr["name"]), id)
            else:
                url = "/%s?pickcode=%s" % (encode_uri_component_loose(attr["name"]), pickcode)
        file_type = attr["type"] = typeof(attr)
        if is_dir:
            url += "&file=false"
        else:
            url += "&file=true"
            if attr["is_collect"] and attr["size"] < 1024 * 1024 * 115:
                url += "&web=true"
        if file_type == 3 and attr["size"] < 200 * 1024 * 1024:
            url += "&music=true"
        attr["url"] = url
        if is_dir:
            attr["ico"] = "folder"
        else:
            attr["ico"] = splitext(attr["name"])[1][1:].lower()
        if thumb := attr["thumb"]:
            if thumb.startswith("?"):
                thumb = f"https://imgjump.115.com{thumb}&sha1={attr['sha1']}"
            else:
                thumb = reduce_image_url_layers(thumb)
            if thumb.startswith("https://imgjump.115.com"):
                attr["thumb"] = thumb + "&size=200"
                thumb += "&size=0"
                cached_thumb = IMAGE_URL_CACHE.get(key, "")
                if isinstance(cached_thumb, P115URL):
                    cached_thumb = cached_thumb["thumb"]
                if thumb != cached_thumb:
                    IMAGE_URL_CACHE[key] = thumb
            else:
                attr["thumb"] = thumb
        elif thumb := info.get("muc"):
            attr["thumb"] = thumb
        return attr

    # TODO: 用多个接口进行分流
    async def get_file_list(
        cid: int, 
        /, 
        page_size: int = 10_000, 
    ) -> AsyncIterator[dict]:
        """获取目录中的文件信息迭代器
        """
        file_list = CACHE_ID_TO_LIST.get(cid)
        if file_list is None:
            children = await get_children(cid)
            if children is not None:
                children = list(map(AttrDict, children))
                ancestors = await get_ancestors_from_db(cid)
                file_list = {"ancestors": ancestors, "children": children}
                ID_TO_ATTR.update((int(attr["id"]), attr) for attr in children)
                CACHE_ID_TO_LIST[cid] = file_list
        # TODO: 实现一种增量更新合并机制
        # TODO: 如果元素被删除，则把它的 parent_id 变成 NULL
        if file_list is not None:
            return file_list
        payload = {
            "asc": 0, "cid": cid, "cur": 1, "custom_order": 1, "fc_mix": 1, "limit": page_size, 
            "o": "user_utime", "offset": 0, "show_dir": 1, 
        }
        children: list[dict] = []
        while True:
            resp = await client.fs_files_app(payload, app="android", async_=True)
            check_response(resp)
            if cid and int(resp["path"][-1]["cid"]) != cid:
                raise FileNotFoundError(resp)
            ancestors = [{"id": "0", "parent_id": "0", "name": ""}]
            ancestors.extend({"id": a["cid"], "parent_id": a["pid"], "name": a["name"]} for a in resp["path"][1:])
            children.extend(map(normalize_attr, resp["data"]))
            payload["offset"] += len(resp["data"])
            if payload["offset"] >= resp["count"]:
                break
        # TODO: 首先从缓存读取一下，如果不在缓存中，或者在缓存中，但图片快要失效，则重新拉取，否则直接返回缓存数据
        # earliest_thumb_ts = min((int(attr["thumb"].rsplit("=", 1)[1]) for attr in children if not attr["is_dir"] and attr.get("thumb")), default=0)
        # # TODO: 按更新时间排序进行强制更新
        # if earliest_thumb_ts and earliest_thumb_ts - time() < 600:
        #     children = await get_file_list(client, id)
        # TODO: 只对增删进行更新
        children.sort(key=lambda a: (not a["is_dir"], a["name"]))
        update_cache(ancestors[1:])
        update_cache(children)
        update_list_cache(cid, children)
        return {"ancestors": ancestors, "children": children}

    async def get_file_url(
        pickcode: str, 
        /, 
        user_agent: str = "", 
        use_web_api: bool = False, 
    ) -> P115URL:
        return await client.download_url(
            pickcode, 
            headers={"User-Agent": user_agent}, 
            use_web_api=use_web_api, 
            async_=True, 
        )

    async def get_image_url(pickcode: str, /) -> str:
        if not (url := IMAGE_URL_CACHE.get(pickcode, "")):
            resp = await client.fs_image(pickcode, base_url=True, async_=True)
            resp = check_response(resp)
            data = resp["data"]
            url = IMAGE_URL_CACHE[pickcode] = cast(str, data["origin_url"])
        return url

    def update_cache(attr: dict | list[dict]):
        params = attr
        if isinstance(params, list):
            if not params:
                return
            attr = params[0]
        keys = tuple(attr.keys() & frozenset(("id", "parent_id", "name", "pickcode", "sha1", "is_dir")))
        fields = ",".join(keys)
        vars = ",".join(map(":".__add__, keys))
        repls = ",".join(f"{k}=excluded.{k}" for k in keys if k != "id")
        put_task((f"INSERT INTO data ({fields}) VALUES ({vars}) ON CONFLICT(id) DO UPDATE SET {repls}", params))

    def update_list_cache(id: int, children: list[dict]):
        put_task(("INSERT OR REPLACE INTO list(id, data) VALUES (?, ?)", (id, children)))

    def update_cache_for_p115id[T: int](p115id: T) -> T:
        if isinstance(p115id, P115ID):
            match p115id.get("about"):
                case "path":
                    attr = p115id["attr"] = normalize_attr(p115id.__dict__)
                    update_cache(attr)
                    return p115id
                case "sha1":
                    update_cache({
                        "id": int(p115id["file_id"]), 
                        "pickcode": p115id["pick_code"], 
                        "sha1": p115id["file_sha1"], 
                        "parent_id": int(p115id["category_id"]), 
                        "name": p115id["file_name"], 
                        "is_dir": False, 
                    })
                case "pickcode":
                    update_cache({
                        "id": int(p115id["file_id"]), 
                        "pickcode": p115id["pickcode"], 
                        "name": p115id["file_name"], 
                        "is_dir": p115id["is_dir"], 
                    })
        return p115id

    @app.on_middlewares_configuration
    def configure_forwarded_headers(app: Application):
        app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))

    @app.on_start
    async def get_loop(app: Application):
        nonlocal loop
        loop = get_running_loop()

    @app.lifespan
    async def register_client(app: Application):
        nonlocal client
        client = P115Client(
            cookies_path, 
            app="alipaymini", 
            check_for_relogin=True, 
        )
        async with client.async_session:
            app.services.register(P115Client, instance=client)
            yield

    @app.lifespan
    async def register_connection(app: Application):
        nonlocal con
        remove_done = False
        path = dbfile
        if not path:
            from uuid import uuid4
            from tempfile import mktemp
            path = mktemp(prefix=str(uuid4()) + "-", suffix=".db")
            remove_done = True
        try:
            with connect(
                path, 
                autocommit=True, 
                check_same_thread=False, 
                detect_types=PARSE_DECLTYPES, 
                uri=isinstance(path, str) and path.startswith("file:"), 
            ) as con:
                app.services.register(Connection, instance=con)
                con.executescript("""\
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS data ( -- 用于缓存数据
    id INTEGER NOT NULL PRIMARY KEY,   -- 文件或目录的 id
    parent_id INTEGER,                 -- 上级目录的 id
    pickcode TEXT NOT NULL DEFAULT '', -- 提取码，下载时需要用到
    sha1 TEXT NOT NULL DEFAULT '',     -- 文件的 sha1 散列值
    name TEXT NOT NULL DEFAULT '',     -- 名字
    is_dir BOOLEAN NOT NULL DEFAULT TRUE  -- 是否目录
);
CREATE TABLE IF NOT EXISTS share_data ( -- 用于缓存分享链接数据
    share_code TEXT NOT NULL DEFAULT '',  -- 分享码
    id INTEGER NOT NULL,                  -- 文件或目录的 id
    parent_id INTEGER,                    -- 上级目录的 id
    sha1 TEXT NOT NULL DEFAULT '',        -- 文件的 sha1 散列值
    name TEXT NOT NULL DEFAULT '',        -- 名字
    path TEXT NOT NULL DEFAULT '',        -- 路径
    is_dir BOOLEAN NOT NULL DEFAULT TRUE  -- 是否目录
);
CREATE TABLE IF NOT EXISTS list ( -- 用于缓存文件列表数据
    id INTEGER NOT NULL PRIMARY KEY,   -- 目录的 id
    data JSON NOT NULL                 -- 二进制数据
);
CREATE TABLE IF NOT EXISTS share_list ( -- 用于缓存分享链接的文件列表数据
    share_code TEXT NOT NULL DEFAULT '', -- 分享码
    id INTEGER NOT NULL,                 -- 目录的 id
    data JSON NOT NULL                   -- 二进制数据
);
CREATE TABLE IF NOT EXISTS share_list_loaded ( -- 用于标记分享链接的文件列表是否已经加载完
    share_code TEXT NOT NULL PRIMARY KEY, -- 分享码
    loaded BOOLEAN NOT NULL DEFAULT TRUE  -- 分享链接的文件列表是否已经加载完
);
CREATE INDEX IF NOT EXISTS idx_data_pid ON data(parent_id);
CREATE INDEX IF NOT EXISTS idx_data_pc ON data(pickcode);
CREATE INDEX IF NOT EXISTS idx_data_sha1 ON data(sha1);
CREATE INDEX IF NOT EXISTS idx_data_name ON data(name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sdata_code_id ON share_data(share_code, id);
CREATE INDEX IF NOT EXISTS idx_sdata_pid ON share_data(parent_id);
CREATE INDEX IF NOT EXISTS idx_sdata_sha1 ON share_data(sha1);
CREATE INDEX IF NOT EXISTS idx_sdata_name ON share_data(name);
CREATE INDEX IF NOT EXISTS idx_sdata_path ON share_data(path);
CREATE UNIQUE INDEX IF NOT EXISTS idx_slist_code_id ON share_list(share_code, id);
""")
                yield
        finally:
            if remove_done:
                with suppress(OSError):
                    remove(path)
                with suppress(OSError):
                    remove(path+"-shm")
                with suppress(OSError):
                    remove(path+"-wal")

    @app.lifespan
    async def start_tasks(app: Application):
        running = True
        start_new_thread(
            queue_execute, 
            (type("", (), {"__bool__": staticmethod(lambda: running)})(),), 
        )
        try:
            yield
        finally:
            running = False

    def make_response_for_exception(
        exc: BaseException, 
        status_code: int = 500, 
    ) -> Response:
        if (len(exc.args) == 1 and isinstance(exc.args[0], (dict, list, tuple)) or 
            isinstance(exc, OSError) and len(exc.args) == 2 and isinstance(exc.args[1], (dict, list, tuple))
        ):
            return Response(
                status_code, 
                None, 
                Content(b"application/json", json_dumps(exc.args[-1])), 
            )
        return text(str(exc), status_code)

    if not debug:
        @app.exception_handler(BaseException)
        async def redirect_exception_response(
            self, 
            request: Request, 
            exc: BaseException, 
        ) -> Response:
            code = get_status_code(exc)
            if code is not None:
                return make_response_for_exception(exc, code)
            elif isinstance(exc, ValueError):
                return make_response_for_exception(exc, 400) # Bad Request
            elif isinstance(exc, AuthenticationError):
                return make_response_for_exception(exc, 401) # Unauthorized
            elif isinstance(exc, PermissionError):
                return make_response_for_exception(exc, 403) # Forbidden
            elif isinstance(exc, FileNotFoundError):
                return make_response_for_exception(exc, 404) # Not Found
            elif isinstance(exc, (IsADirectoryError, NotADirectoryError)):
                return make_response_for_exception(exc, 406) # Not Acceptable
            elif isinstance(exc, BusyOSError):
                return make_response_for_exception(exc, 429) # Too Many Requests
            elif isinstance(exc, OSError):
                return make_response_for_exception(exc, 500) # Internal Server Error
            else:
                return make_response_for_exception(exc, 503) # Service Unavailable

    @app.router.get("/%3Cid")
    async def get_id(
        id: int = -1, 
        pickcode: str = "", 
        sha1: str = "", 
        path: str = "", 
    ) -> int:
        if pickcode:
            if (fid := await get_id_from_db(pickcode=pickcode.lower())) is not None:
                return fid
            else:
                return update_cache_for_p115id(await get_id_to_pickcode(client, pickcode, async_=True))
        elif id >= 0:
            return id
        elif sha1:
            if (fid := await get_id_from_db(sha1=sha1.upper())) is not None:
                return fid
            else:
                return update_cache_for_p115id(await get_id_to_sha1(client, sha1, async_=True))
        else:
            if not path:
                return 0
            ensure_file = False if path_is_dir_form(path) else None
            ret = await to_thread(info_to_path, path, ensure_file)
            if ret is not None:
                return ret
            id_to_dirnode = {}
            try:
                return update_cache_for_p115id(await get_id_to_path(
                    client, 
                    path, 
                    ensure_file=ensure_file, 
                    id_to_dirnode=id_to_dirnode, 
                    app="android", 
                    async_=True, 
                ))
            finally:
                if id_to_dirnode:
                    update_cache([
                        {"id": id, "name": name, "parent_id": pid} 
                        for id, (name, pid) in id_to_dirnode.items()
                    ])

    @app.router.get("/%3Cpickcode")
    async def get_pickcode(
        id: int = -1, 
        pickcode: str = "", 
        sha1: str = "", 
        path: str = "", 
    ) -> str | Response:
        if pickcode:
            if not 17 <= len(pickcode) <= 18 or not pickcode.isalnum():
                raise ValueError(f"bad pickcode: {pickcode!r}")
            return pickcode
        elif id >= 0:
            if pickcode := await get_pickcode_from_db(id=id):
                return pickcode
        elif sha1:
            if pickcode := await get_pickcode_from_db(sha1=sha1):
                return pickcode
            id = await get_id(sha1=sha1)
            if isinstance(id, P115ID):
                return p115id["pick_code"]
        else:
            if not path:
                raise ValueError("root directory has no pickcode")
            ensure_file = False if path_is_dir_form(path) else None
            id = await get_id(path=path)
            if isinstance(id, P115ID):
                return p115id.get("pc") or p115id.get("pickcode", "")
        if id == 0:
            raise ValueError("the root directory does not have pickcode")
        resp = await client.fs_file_skim(id, base_url=True, async_=True)
        check_response(resp)
        data = resp["data"][0]
        pickcode = data["pick_code"]
        sha1 = data["sha1"]
        update_cache({
            "id": int(data["file_id"]), 
            "pickcode": pickcode, 
            "sha1": sha1, 
            "name": data["file_name"], 
            "is_dir": not sha1, 
        })
        return pickcode

    _get_attr_g = cycle([True, False]).__next__

    @app.router.get("/%3Cattr")
    async def get_attr(
        id: int = -1, 
        pickcode: str = "", 
        sha1: str = "", 
        path: str = "", 
    ) -> dict:
        id = await get_id(id=id, pickcode=pickcode, sha1=sha1, path=path)
        if isinstance(id, P115ID) and id.get("about") == "path":
            return id["attr"]
        id = int(id)
        if id == 0:
            return {"id": 0, "parent_id": 0, "is_dir": True, "name": ""}
        if attr := ID_TO_ATTR.get(id):
            return attr
        else:
            resp = await client.fs_file(id, base_url=_get_attr_g(), async_=True)
            check_response(resp)
            attr = normalize_attr(resp["data"][0])
            CACHE_ID_TO_ATTR[id] = attr
            update_cache(attr)
            return attr

    @app.router.get("/%3Clist")
    async def get_list(
        id: int = -1, 
        pickcode: str = "", 
        sha1: str = "", 
        path: str = "", 
    ) -> list[dict]:
        id = await get_id(id=id, pickcode=pickcode, sha1=sha1, path=path)
        async with ID_TO_LIST_LOCK.setdefault(int(id), Lock()):
            return await get_file_list(id)

    @app.router.get("/%3Cm3u8")
    async def get_m3u8(pickcode: str = ""):
        """获取 m3u8 文件链接
        """
        resp = await client.fs_video_app(pickcode, async_=True)
        if data := resp.get("data"):
            update_cache({
                "id": int(data["file_id"]), 
                "pickcode": data["pick_code"], 
                "sha1": data["file_sha1"], 
                "name": data["file_name"], 
                "parent_id": int(data["parent_id"]), 
                "is_dir": False, 
            })
        check_response(resp)
        return data["video_url"]

    @app.router.get("/%3Csubtitles")
    async def get_subtitles(pickcode: str):
        """获取字幕（随便提供此文件夹内的任何一个文件的提取码即可）
        """
        resp = await client.fs_video_subtitle(pickcode, base_url=True, async_=True)
        data = check_response(resp).get("data")
        if data:
            update_cache([
                {
                    "id": int(a["file_id"]), 
                    "pickcode": a["pick_code"], 
                    "sha1": a["sha1"], 
                    "name": a["file_name"], 
                    "is_dir": False, 
                } 
                for a in data["list"] if "file_id" in a
            ])
        return data

    @app.router.get("/%3Curl")
    async def get_url(
        request: Request, 
        pickcode: str, 
        image: bool = False, 
        music: bool = False, 
        web: bool = False, 
    ) -> dict:
        """获取下载链接

        :param pickcode: 文件的 pickcode
        :param image: 是否为图片，优先级高于 `music`
        :param music: 是否为音乐，优先级高于 `web`
        :param web: 是否使用 web 接口
        """
        if image:
            return {"type": "image", "url": await get_image_url(pickcode)}
        user_agent = (request.get_first_header(b"User-agent") or b"").decode("latin-1")
        bytes_range = (request.get_first_header(b"Range") or b"").decode("latin-1")
        url: None | P115URL
        if not music and bytes_range and not user_agent.lower().startswith(("vlc/", "oplayer/", "lavf/")):
            remote_addr = request.original_client_ip
            cooldown_key = (pickcode, remote_addr, user_agent, bytes_range)
            if cooldown_key in URL_COOLDOWN:
                raise BusyOSError(f"too many requests: {pickcode}")
            URL_COOLDOWN[cooldown_key] = None
            key = (pickcode, remote_addr, user_agent, web)
            if not (url := URL_CACHE.get(key)):
                URL_CACHE[key] = url = await get_file_url(pickcode, user_agent=user_agent, use_web_api=web)
        else:
            url = await get_file_url(pickcode, user_agent=user_agent, use_web_api=web)
        return {"type": "file", "url": url, "headers": url["headers"]}

    @app.router.route("/", methods=["GET", "HEAD"])
    @app.router.route("/<path:path2>", methods=["GET", "HEAD"])
    async def get_page(
        request: Request, 
        id: int = -1, 
        pickcode: str = "", 
        sha1: str = "", 
        path: str = "", 
        path2: str = "", 
        file: None | bool = None, 
        image: bool = False, 
        music: bool = False, 
        web: bool = False, 
    ) -> Response:
        """根据实际情况分流到具体接口

        :param path2: 文件或目录的 path，优先级最低
        :param id: 文件或目录的 id，优先级高于 `sha1`
        :param pickcode: 文件或目录的 pickcode，优先级高于 `id`，为最高
        :param sha1: 文件的 sha1，优先级高于 `path`
        :param path: 文件或目录的 path，优先级高于 `path2`
        :param file: 是否为文件，如果为 None，则需要进一步确定
        :param image: 是否为图片
        :param music: 是否为音乐
        :param web: 是否使用 web 接口
        """
        if file is None:
            attr = await get_attr(
                id=id, 
                pickcode=pickcode, 
                sha1=sha1, 
                path=path or path2, 
            )
            is_dir = attr["is_dir"]
            if is_dir:
                id = int(attr["id"])
            else:
                pickcode = attr["pickcode"]
        elif file:
            is_dir = False
            pickcode = await get_pickcode(
                id=id, 
                pickcode=pickcode, 
                sha1=sha1, 
                path=path or path2, 
            )
        else:
            is_dir = True
            id = await get_id(
                id=id, 
                pickcode=pickcode, 
                sha1=sha1, 
                path=path or path2, 
            )
        if not is_dir:
            resp = await get_url(
                request, 
                pickcode=pickcode, 
                image=image, 
                music=music, 
                web=web, 
            )
            url: P115URL = resp["url"]
            if web:
                cookie = resp["headers"]["Cookie"]
                return Response(
                    302, 
                    headers=[
                        (b"Location", bytes(f"/<download/{quote(url['name'])}?url={quote(url)}", "latin-1")), 
                        (b"Set-Cookie", bytes(cookie[:cookie.find(";")], "latin-1")), 
                    ], 
                )
            else:
                return redirect(url)
        file_list = await get_list(id=id)
        ancestors = file_list["ancestors"]
        children  = file_list["children"]
        return await view_async(
            "list", 
            ancestors=ancestors, 
            children=children, 
            origin=get_origin(request), 
            load_libass=load_libass, 
            user_agent=detect_ua((request.get_first_header(b"User-agent") or b"").decode("latin-1")), 
            IMAGE_URL_CACHE=IMAGE_URL_CACHE, 
        )

    async def list_shares() -> list[dict]:
        "获取分享列表"
        get_share_list = client.share_list
        shares: list[dict] = []
        add_share = shares.append
        payload = {"offset": 0, "limit": 1150}
        while True:
            resp = await get_share_list(payload, base_url=True, async_=True)
            check_response(resp)
            for share in resp["list"]:
                SHARE_FS_MAP[share["share_code"]] = share
                add_share(share)
            payload["offset"] += len(resp["list"])
            if payload["offset"] >= resp["count"]:
                break
        return shares

    async def get_share_info(share_code: str, /) -> dict:
        "获取分享链接的接收码（必须是你自己的分享）"
        share_code = share_code.lower()
        try:
            return SHARE_FS_MAP[share_code]
        except KeyError:
            resp = await client.share_info(share_code, base_url=True, async_=True)
            check_response(resp)
            share_info = SHARE_FS_MAP[share["share_code"]] = resp["data"]
            return share_info

    async def get_share_file_url(
        share_code: str, 
        receive_code: str, 
        id: int | str, 
        /, 
        use_web_api: bool = False, 
    ) -> P115URL:
        """获取分享链接中文件的下载链接
        """
        return await client.share_download_url(
            {"share_code": share_code, "receive_code": receive_code, "file_id": id}, 
            use_web_api=use_web_api, 
            async_=True, 
        )

    async def get_share_image_url(
        share_code: str, 
        receive_code: str, 
        id: int, 
    ) -> str:
        if url := IMAGE_URL_CACHE.get((share_code, id), ""):
            return url
        attr = await get_share_attr(share_code, id=id, receive_code=receive_code)
        try:
            return attr["thumb"]
        except KeyError:
            raise ValueError("has no thumb picture")

    @app.router.get("/%3Cshare/%3Curl")
    async def get_share_url(
        request: Request, 
        share_code: str, 
        id: int, 
        receive_code: str = "", 
        image: bool = False, 
        music: bool = False, 
        web: bool = False, 
    ):
        if not receive_code:
            share_info = await get_share_info(share_code)
            receive_code = share_info["receive_code"]
        if image:
            return {
                "type": "image", 
                "url": await get_share_image_url(share_code, receive_code, id), 
            }
        user_agent = (request.get_first_header(b"User-agent") or b"").decode("latin-1")
        bytes_range = (request.get_first_header(b"Range") or b"").decode("latin-1")
        url: None | P115URL
        if not music and bytes_range and not user_agent.lower().startswith(("vlc/", "oplayer/", "lavf/")):
            remote_addr = request.original_client_ip
            cooldown_key = (share_code, id, remote_addr, user_agent, bytes_range)
            if cooldown_key in URL_COOLDOWN:
                raise BusyOSError(f"too many requests: share_code={share_code}&id={id}")
            URL_COOLDOWN[cooldown_key] = None
            key = (share_code, id, remote_addr, user_agent, web)
            if not (url := URL_CACHE.get(key)):
                URL_CACHE[key] = url = await get_share_file_url(share_code, receive_code, id=id, use_web_api=web)
        else:
            url = await get_share_file_url(share_code, receive_code, id=id, use_web_api=web)
        return {"type": "file", "url": url, "headers": url.get("headers")}

    # TODO: ...
    @app.router.get("/%3Cshare/%3Cid")
    async def get_share_id(
        share_code: str, 
        id: int = -1, 
        sha1: str = "", 
        path: str = "", 
        receive_code: str = "", 
    ):
        if id >= 0:
            return id
        elif sha1:
            return await share_get_id(client, sha1=sha1)
        else:
            return await share_get_id(client, path=path)

    # TODO: ...
    @app.router.get("/%3Cshare/%3Cattr")
    async def get_share_attr(
        share_code: str, 
        id: int = -1, 
        sha1: str = "", 
        path: str = "", 
        receive_code: str = "", 
    ):
        if not share_code:
            return {"is_dir": True, "id": "0"}
        if id < 0:
            id = await get_share_id(
                share_code=share_code, 
                sha1=sha1, 
                path=path, 
                receive_code=receive_code, 
            )
        if id == 0:
            return await get_share_info(share_code)
        if not receive_code:
            share_info = await get_share_info(share_code)
            receive_code = share_info["receive_code"]
        #attr = get_share_attr(id)
        #return normalize_attr(attr)

    # TODO: ...
    @app.router.get("/%3Cshare/%3Clist")
    async def get_share_list(
        share_code: str = "", 
        id: int = -1, 
        sha1: str = "", 
        path: str = "", 
        receive_code: str = "", 
    ):
        if not share_code:
            shares = await list_shares()
            return {
                "ancestors": [{"id": "0", "parent_id": "0", "name": ""}], 
                "children": [{
                    "id": "0", 
                    "parent_id": "0", 
                    "is_dir": True, 
                    "time": int(s["create_time"]), 
                    "size": int(s["file_size"]), 
                    "name": s["share_title"], 
                    "ico": "folder", 
                    "share_code": s["share_code"], 
                    "url": f"/<share?share_code={s['share_code']}&id=0", 
                } for s in shares], 
            }
        if not receive_code:
            share_info = await get_share_info(share_code)
            receive_code = share_info["receive_code"]
        # TODO: ...
        if id < 0:
            id = await share_get_id_to_path(client, path, async_=True)
            
        children = fs.listdir_attr(id_or_path, page_size=10_000)
        if children:
            earliest_thumb_ts = min((int(attr["thumb"].rsplit("=", 1)[1]) for attr in children if not attr["is_dir"] and attr.get("thumb")), default=0)
            if earliest_thumb_ts and earliest_thumb_ts - time() < 600:
                children = fs.listdir_attr(id_or_path, page_size=10_000, refresh=True)
        origin = get_origin()
        return [normalize_attr(attr, origin) for attr in children]

    @app.router.route("/%3Cshare", methods=["GET", "HEAD"])
    @app.router.route("/%3Cshare/<path:path2>", methods=["GET", "HEAD"])
    async def get_share_page(
        request: Request, 
        share_code: str = "", 
        receive_code: str = "", 
        id: int = -1, 
        sha1: str = "", 
        path: str = "", 
        path2: str = "", 
        file: None | bool = None, 
        image: bool = False, 
        music: bool = False, 
        web: bool = False, 
    ):
        if file is None:
            attr = await get_share_attr(
                share_code, 
                id=id, 
                sha1=sha1, 
                path=path or path2, 
                receive_code=receive_code, 
            )
            is_dir = attr["is_dir"]
            id = int(attr["id"])
        else:
            is_dir = not file
            id = await get_share_id(
                share_code, 
                id=id, 
                sha1=sha1, 
                path=path or path2, 
                receive_code=receive_code, 
            )
        if not is_dir:
            resp = await get_share_url(
                request, 
                share_code, 
                id=id, 
                image=image, 
                music=music, 
                web=web, 
                receive_code=receive_code, 
            )
            url: P115URL = resp["url"]
            if web:
                cookie = resp["headers"]["Cookie"]
                return Response(
                    302, 
                    headers=[
                        (b"Location", bytes(f"/<download/{quote(url['name'])}?url={quote(url)}", "latin-1")), 
                        (b"Set-Cookie", bytes(cookie[:cookie.find(";")], "latin-1")), 
                    ], 
                )
            else:
                return redirect(url)
        file_list = await get_share_list(share_code, id=id, receive_code=receive_code)
        ancestors = file_list["ancestors"]
        children  = file_list["children"]
        return await view_async(
            "share_list", 
            share_code=share_code, 
            ancestors=ancestors, 
            children=children, 
            origin=get_origin(request), 
            load_libass=load_libass, 
            user_agent=detect_ua((request.get_first_header(b"User-agent") or b"").decode("latin-1")), 
            IMAGE_URL_CACHE=IMAGE_URL_CACHE, 
        )

    @app.router.route("/%3Cdownload", methods=["GET", "HEAD", "POST"])
    @app.router.route("/%3Cdownload/<path:name>", methods=["GET", "HEAD", "POST"])
    async def do_download(
        request: Request, 
        url: str, 
        name: str = "", 
    ) -> Response:
        """打开某个下载链接后，对数据流进行转发

        :param url: 下载链接
        """
        if urlsplit(url).hostname.endswith(".115.com"):
            headers = {
                str(k, "latin-1").title(): str(v, "latin-1") 
                for k, v in request.headers 
                if k.lower() in (b"user-agent", b"cookie")
            }
        else:
            headers = {str(k, "latin-1"): str(v, "latin-1") for k, v in request.headers}
        resp = await client.request(
            url, 
            method=request.method, 
            data=request.stream(), 
            headers=headers, 
            follow_redirects=True, 
            raise_for_status=False, 
            parse=False, 
            async_=True, 
        )
        async def stream():
            stream = resp.aiter_raw()
            try:
                async for chunk in stream:
                    if await request.is_disconnected():
                        break
                    yield chunk
            finally:
                await stream.aclose()
        headers = resp.headers
        content_type = headers.get("content-type") or "application/octent-stream"
        return Response(
            status=resp.status_code, 
            headers=[(bytes(k, "latin-1"), bytes(v, "latin-1")) 
                     for K, v in headers.items() 
                     if (k := K.lower()) not in ("date", "content-type")], 
            content=StreamedContent(bytes(content_type, "latin-1"), stream), 
        )

    @app.router.route("/%3Credirect", methods=["GET", "HEAD", "POST"])
    @app.router.route("/%3Credirect/<path:name>", methods=["GET", "HEAD", "POST"])
    async def do_redirect(url: str, name: str = "") -> Response:
        """对给定的链接进行 302 重定向，可用于某些通过链接中的路径部分来进行判断，但原来的链接缺乏必要信息的情况

        :param url: 下载链接
        """
        return redirect(url)

    @app.router.route("/%3Csub2ass", methods=["GET", "HEAD", "POST"])
    @app.router.route("/%3Csub2ass/<path:name>", methods=["GET", "HEAD", "POST"])
    async def sub2ass(
        request: Request, 
        url: str, 
        format: str = "srt", 
        name: str = "", 
    ) -> str:
        """把字幕转换为 ASS 格式

        :param url: 下载链接
        :param format: 源文件的字幕格式，默认为 "srt"

        :return: 转换后的字幕文本
        """
        if urlsplit(url).hostname.endswith(".115.com"):
            headers = {
                str(k, "latin-1").title(): str(v, "latin-1") 
                for k, v in request.headers 
                if k.lower() in (b"user-agent", b"cookie")
            }
        else:
            headers = {str(k, "latin-1"): str(v, "latin-1") for k, v in request.headers}
        resp = await client.request(
            url, 
            method=request.method, 
            data=request.stream(), 
            headers=headers, 
            follow_redirects=True, 
            parse=False, 
            async_=True, 
        )
        content = await client.request(url, parse=False, follow_redirects=True, async_=True)
        return SSAFile.from_string(content.decode("utf-8"), format_=format).to_string("ass")

    class DavPathBase:

        def __getattr__(self, attr: str, /):
            try:
                return self.attr[attr]
            except KeyError as e:
                raise AttributeError(attr) from e

        @locked_cacheproperty
        def mtime(self, /) -> float:
            attr = self.attr
            return attr.get("mtime") or attr.get("time") or 0

        @locked_cacheproperty
        def name(self, /) -> str:
            return self.attr["name"]

        def get_display_name(self, /) -> str:
            return self.name

        def get_etag(self, /) -> str:
            return "%s-%s-%s" % (
                self.attr["id"], 
                self.mtime, 
                self.size, 
            )

        def get_last_modified(self, /) -> float:
            return self.mtime

        def is_link(self, /) -> bool:
            return False

        def support_etag(self, /) -> bool:
            return True

        def support_modified(self, /) -> bool:
            return True

    class FileResource(DavPathBase, DAVNonCollection):

        def __init__(
            self, 
            /, 
            path: str, 
            environ: dict, 
            attr: Mapping, 
            is_strm: bool = False, 
        ):
            super().__init__(path, environ)
            self.attr = attr
            self.is_strm = is_strm
            DAV_FILE_CACHE[path] = self

        if strm_origin:
            origin = strm_origin
        else:
            @locked_cacheproperty
            def origin(self, /) -> str:
                if origin := self.environ.get("STRM_ORIGIN"):
                    return origin
                return f"{self.environ['wsgi.url_scheme']}://{self.environ['HTTP_HOST']}"

        @locked_cacheproperty
        def size(self, /) -> int:
            if self.is_strm:
                return len(self.strm_data)
            return self.attr["size"]

        @locked_cacheproperty
        def strm_data(self, /) -> bytes:
            attr = self.attr
            name = encode_uri_component_loose(attr["name"])
            if share_code := attr.get("share_code"):
                url = f"{self.origin}/<share/{name}?file=true&share_code={share_code}&id={attr['id']}"
            else:
                url = f"{self.origin}/{name}?file=true&pickcode={attr['pickcode']}&id={attr['id']}&sha1={attr['sha1']}"
            return bytes(url, "utf-8")

        @locked_cacheproperty
        def url(self, /) -> str:
            attr = self.attr
            if share_code := attr.get("share_code"):
                return f"{self.origin}/<share?file=true&share_code={share_code}&id={attr['id']}"
            else:
                return f"{self.origin}/?file=true&pickcode={attr['pickcode']}"

        def get_content(self, /):
            if self.is_strm:
                return BytesIO(self.strm_data)
            raise DAVError(302, add_headers=[("Location", self.url)])

        def get_content_length(self, /) -> int:
            return self.size

        def support_content_length(self, /) -> bool:
            return True

        def support_ranges(self, /) -> bool:
            return True

    class FolderResource(DavPathBase, DAVCollection):

        def __init__(
            self, 
            /, 
            path: str, 
            environ: dict, 
            attr: Mapping, 
        ):
            super().__init__(path, environ)
            self.attr = attr

        @locked_cacheproperty
        def children(self, /) -> dict[str, FileResource | FolderResource]:
            children: dict[str, FileResource | FolderResource] = {}
            environ = self.environ
            dir_ = self.path
            if dir_ != "/":
                dir_ += "/"
            if dir_ == "/<share/":
                shares = run_coroutine_threadsafe(list_shares(), loop).result()
                for share in shares:
                    share_code = share["share_code"]
                    children[share["share_code"]] = FolderResource(
                        "/<share/" + share_code, 
                        environ, 
                        {
                            "id": 0, 
                            "parent_id": 0, 
                            "is_dir": True, 
                            "time": int(share["create_time"]), 
                            "size": int(share["file_size"]), 
                            "name": share["share_title"], 
                            "ico": "folder", 
                            "share_code": share_code, 
                        }, 
                    )
            else:
                is_root = False
                if dir_.startswith("/<share/"):
                    share_code = self.attr["share_code"]
                    coro = get_share_list(share_code=share_code, path=dir_)
                else:
                    is_root = dir_ == "/"
                    coro = get_list(path=dir_)
                try:
                    file_list = run_coroutine_threadsafe(coro, loop).result()
                except FileNotFoundError:
                    raise DAVError(404, dir_)
                for attr in file_list["children"]:
                    name = attr["name"]
                    is_strm = False
                    is_dir = attr["is_dir"]
                    if not is_dir and strm_predicate and strm_predicate(MappingPath(attr)):
                        is_strm = True
                        name = splitext(name)[0] + ".strm"
                        path = dir_ + name
                    elif predicate and not predicate(MappingPath(attr)):
                        continue
                    else:
                        path = dir_ + name
                    if is_dir:
                        children[name] = FolderResource(path, environ, attr)
                    else:
                        children[name] = FileResource(path, environ, attr, is_strm=is_strm)
                if is_root:
                    children["<share"] = FolderResource("/<share", environ, {"id": 0, "name": "<share", "size": 0})
            return children

        def get_member(self, /, name: str) -> FileResource | FolderResource:
            if not (attr := self.children.get(name)):
                raise DAVError(404, self.path + "/" + name)
            return attr

        def get_member_list(self, /) -> list[FileResource | FolderResource]:
            return list(map(self.get_member, self.get_member_names()))

        def get_member_names(self, /) -> list[str]:
            return list(self.children)

        def get_property_value(self, /, name: str):
            if name == "{DAV:}getcontentlength":
                return 0
            elif name == "{DAV:}iscollection":
                return True
            return super().get_property_value(name)

    class P115FileSystemProvider(DAVProvider):

        def get_resource_inst(
            self, 
            /, 
            path: str, 
            environ: dict, 
        ) -> FolderResource | FileResource:
            is_dir = path.endswith("/")
            path = "/" + path.strip("/")
            if not strm_origin:
                origin = environ["STRM_ORIGIN"] = f"{environ['wsgi.url_scheme']}://{environ['HTTP_HOST']}"
            if not is_dir:
                if inst := DAV_FILE_CACHE.get(path):
                    if not strm_origin and origin != inst.origin:
                        inst = FileResource(path, environ, inst.attr, is_strm=inst.is_strm)
                    return inst
                if path.endswith(".strm"):
                    dir_, name = splitpath(path)
                    inst = self.get_resource_inst(dir_, environ)
                    if not isinstance(inst, FolderResource):
                        raise DAVError(404, path)
                    return inst.get_member(name)
            if path == "/<share":
                return FolderResource("/<share", environ, {"id": 0, "name": "<share", "size": 0})
            else:
                if path.startswith("/<share/"):
                    share_code, _, share_path = path[8:].partition("/")
                    coro = get_share_attr(share_code=share_code, path=share_path)
                else:
                    coro = get_attr(path=path)
                try:
                    attr = run_coroutine_threadsafe(coro, loop).result()
                except FileNotFoundError:
                    raise DAVError(404, path)
                is_strm = False
                is_dir = attr["is_dir"]
                if not is_dir and strm_predicate and strm_predicate(MappingPath(attr)):
                    is_strm = True
                    path = splitext(path)[0] + ".strm"
                elif predicate and not predicate(MappingPath(attr)):
                    raise DAVError(404, path)
                if is_dir:
                    return FolderResource(path, environ, attr)
                else:
                    return FileResource(path, environ, attr, is_strm=is_strm)

        def is_readonly(self, /) -> bool:
            return True

    WSGIDAV_CONFIG = {
        "host": "0.0.0.0", 
        "port": 0, 
        "mount_path": "/<dav", 
        "provider_mapping": {"/": P115FileSystemProvider()}, 
        "simple_dc": {"user_mapping": {"*": True}}, 
    }

    wsgidav_app = WsgiDAVApp(WSGIDAV_CONFIG)
    app.mount("/%3Cdav", WSGIMiddleware(wsgidav_app, workers=128, send_queue_size=256))

    return app

# 当不存在缓存时，用两套进行分流：1. aps 接口 2. app 接口（android）
# 当存在缓存时，则只用 app 接口

# TODO: 这个可以缓存相对路径
# TODO: 某个 id 是否存在可以尝试通过 share_download_url 判断，个人建议用网页版接口，anxia
# TODO: 如果某个有缩略图，但缩略图快失效，则父目录重新拉

if __name__ == "__main__":
    import uvicorn

    app = make_application(debug=True, load_libass=True, dbfile="test.db")
    try:
        uvicorn.run(app)
    finally:
        with suppress(OSError):
            remove("test.db")
        with suppress(OSError):
            remove("test.db-shm")
        with suppress(OSError):
            remove("test.db-wal")

# TODO: 完整的 wsgidav 配置文件支持
# TODO: 更完整信息的支持，类似 xattr
# TODO: 虽然115分享的图片也能获去cdn图片，但是并不能单独获取某个文件的属性，因此并不能给图片更新，除非这张图片被转存了，然后缓存转存后的pickcode，以后就可以反复更新了
# TODO: 加上搜索框和分页，加上图库浏览功能
# TODO: 播放器实现，播放列表，字幕或歌词绑定，弹幕、封面、元数据等功能
# TODO: 网页版支持播放 m3u8，自动绑定字幕等，这样可以避免那种没有声音的情况，默认使用最高画质，如果没有m3u8，则会退到原始视频
# TODO: 使用115接口保存播放进度
# TODO: 使用 aplayer 播放音乐
# TODO: 在线播放：播放列表、字幕列表（自动执行绑定视频）、多码率列表
# TODO: 支持自定义转换规则，把 srt 转换为 ass 时，添加样式和字体，或者添加一个在线的样式选择框，就像 115
# TODO: 直接用 m3u8 实现播放列表和各种附加，这样一切都是流媒体
# TODO: 数据库支持 mongodb
# TODO: 允许使用多种序列化模块：orjson, pickcle, marshal, msgspec 等，默认为 orjson

# NOTE: https://wsgidav.readthedocs.io/en/latest/user_guide_configure.html

# TODO: 实现一个 share_iterdir，可以从某个 id 开始，获取整个子树
