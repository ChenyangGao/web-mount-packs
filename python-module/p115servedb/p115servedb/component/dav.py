#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["make_application"]

from collections.abc import Callable
from functools import partial
from inspect import getsource
from io import BytesIO
from os import fsdecode, PathLike
from pathlib import Path
from posixpath import dirname, splitext, split as splitpath
from sqlite3 import connect, Connection, OperationalError
from threading import Lock
from typing import Literal
from urllib.parse import quote

from a2wsgi import WSGIMiddleware
from blacksheep import redirect, Application, Request
from blacksheep.client import ClientSession
from blacksheep.server import asgi
from blacksheep.server.compression import use_gzip_compression
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from blacksheep_client_request import request as blacksheep_request
from encode_uri import encode_uri_component_loose
from p115client import P115Client
from path_predicate import MappingPath
from property import locked_cacheproperty
from urllib3.poolmanager import PoolManager
from wsgidav.wsgidav_app import WsgiDAVApp # type: ignore
from wsgidav.dav_error import DAVError # type: ignore
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider # type: ignore
from yaml import load, Loader

from .lrudict import LRUDict


get_request_url_from_scope = asgi.get_request_url_from_scope
source = getsource(get_request_url_from_scope)
repl_code = '        host, port = scope["server"]'
if repl_code in source:
    exec(getsource(get_request_url_from_scope).replace(repl_code, """\
        for key, val in scope["headers"]:
            if key.lower() in (b"host", b"x-forwarded-host", b"x-original-host"):
                host = val.decode("latin-1")
                port = 80 if protocol == "http" else 443
                break
        else:
            host, port = scope["server"]"""), asgi.__dict__)
    get_request_url_from_scope.__code__ = asgi.get_request_url_from_scope.__code__


def make_application(
    dbfile: bytes | str | PathLike, 
    config_path: str | Path = "", 
    cookies_path: str | Path = "", 
    strm_origin: bytes | str = "", 
    predicate: None | Callable[[MappingPath], bool] = None, 
    strm_predicate: None | Callable[[MappingPath], bool] = None, 
) -> Application:
    if isinstance(strm_origin, str):
        strm_origin_bytes = strm_origin.encode("utf-8")
    else:
        strm_origin_bytes = strm_origin
        strm_origin = strm_origin_bytes.decode("utf-8")
    if config_path:
        config = load(open(config_path, encoding="utf-8"), Loader=Loader)
    else:
        config = {"simple_dc": {"user_mapping": {"*": True}}}
    if cookies_path:
        cookies_path = Path(cookies_path)
    else:
        cookies_path = Path("115-cookies.txt")
        if not cookies_path.exists():
            cookies_path = ""
    client = P115Client(cookies_path, app="alipaymini", check_for_relogin=True) if cookies_path else None
    urlopen = partial(PoolManager(num_pools=128).request, "GET", preload_content=False)

    CON: Connection
    CON_FILE: Connection
    FIELDS = ("id", "name", "path", "ctime", "mtime", "sha1", "size", "pickcode", "is_dir")
    ROOT = {"id": 0, "name": "", "path": "/", "ctime": 0, "mtime": 0, "size": 0, "pickcode": "", "is_dir": 1}
    if strm_predicate:
        STRM_CACHE: LRUDict = LRUDict(65536)
    WRITE_LOCK = Lock()

    class DavPathBase:

        def __getattr__(self, attr, /):
            try:
                return self.attr[attr]
            except KeyError as e:
                raise AttributeError(attr) from e

        @locked_cacheproperty
        def creationdate(self, /) -> float:
            return self.ctime

        @locked_cacheproperty
        def ctime(self, /) -> float:
            return self.attr["ctime"]

        @locked_cacheproperty
        def mtime(self, /) -> float:
            return self.attr["mtime"]

        @locked_cacheproperty
        def name(self, /) -> str:
            return self.attr["name"]

        def get_creation_date(self, /) -> float:
            return self.ctime

        def get_display_name(self, /) -> str:
            return self.name

        def get_etag(self, /) -> str:
            return "%s-%s-%s" % (
                self.attr["pickcode"], 
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
            attr: dict, 
            is_strm: bool = False, 
        ):
            super().__init__(path, environ)
            self.attr = attr
            self.is_strm = is_strm
            if is_strm:
                STRM_CACHE[path] = self

        if strm_origin:
            origin = strm_origin_bytes # type: ignore
        else:
            @property
            def origin(self, /) -> bytes:
                return f"{self.environ['wsgi.url_scheme']}://{self.environ['HTTP_HOST']}".encode("utf-8")

        @property
        def size(self, /) -> int:
            if self.is_strm:
                return len(self.origin) + len(self.strm_data)
            return self.attr["size"]

        @locked_cacheproperty
        def strm_data(self, /) -> bytes:
            attr = self.attr
            name = encode_uri_component_loose(attr["name"])
            return bytes(f"/{name}?pickcode={attr['pickcode']}&id={attr['id']}&sha1={attr['sha1']}&size={attr['size']}", "utf-8")

        @property
        def url(self, /) -> str:
            scheme = self.environ["wsgi.url_scheme"]
            host = self.environ["HTTP_HOST"]
            return f"{scheme}://{host}?pickcode={self.attr['pickcode']}"

        def get_content(self, /):
            if self.is_strm:
                return BytesIO(self.origin + self.strm_data)
            fid = self.attr["id"]
            try:
                return CON_FILE.blobopen("data", "data", fid, readonly=True)
            except (OperationalError, SystemError):
                pass
            if self.attr["size"] >= 1024 * 64:
                raise DAVError(302, add_headers=[("Location", self.url)])
            CON_FILE.execute("""\
INSERT INTO data(id, data) VALUES(?, zeroblob(?)) 
ON CONFLICT(id) DO UPDATE SET data=excluded.data;""", (fid, self.attr["size"]))
            CON_FILE.commit()
            try:
                data = urlopen(self.url).read()
                with WRITE_LOCK:
                    with CON_FILE.blobopen("data", "data", fid) as fdst:
                        fdst.write(data)
                return CON_FILE.blobopen("data", "data", fid, readonly=True)
            except:
                CON_FILE.execute("DELETE FROM data WHERE id=?", (fid,))
                CON_FILE.commit()
                raise

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
            attr: dict, 
        ):
            if not path.endswith("/"):
                path += "/"
            super().__init__(path, environ)
            self.attr = attr

        @locked_cacheproperty
        def children(self, /) -> dict[str, FileResource | FolderResource]:
            sql = """\
SELECT id, name, path, ctime, mtime, sha1, size, pickcode, is_dir
FROM data
WHERE parent_id = :id AND name NOT IN ('', '.', '..') AND name NOT LIKE '%/%';
"""
            children: dict[str, FileResource | FolderResource] = {}
            environ = self.environ
            for r in CON.execute(sql, self.attr):
                attr = dict(zip(FIELDS, r))
                is_strm = False
                name = attr["name"]
                path = attr["path"]
                if not attr["is_dir"] and strm_predicate and strm_predicate(MappingPath(attr)):
                    name = splitext(name)[0] + ".strm"
                    path = splitext(path)[0] + ".strm"
                    is_strm = True
                elif predicate and not predicate(MappingPath(attr)):
                    continue
                if attr["is_dir"]:
                    children[name] = FolderResource(path, environ, attr)
                else:
                    children[name] = FileResource(path, environ, attr, is_strm=is_strm)
            return children

        def get_descendants(
            self, 
            /, 
            collections: bool = True, 
            resources: bool = True, 
            depth_first: bool = False, 
            depth: Literal["0", "1", "infinity"] = "infinity", 
            add_self: bool = False, 
        ) -> list[FileResource | FolderResource]:
            descendants: list[FileResource | FolderResource] = []
            push = descendants.append
            if collections and add_self:
                push(self)
            if depth == "0":
                return descendants
            elif depth == "1":
                for item in self.children.values():
                    if item.attr["is_dir"]:
                        if collections:
                            push(item)
                    elif resources:
                        push(item)
                return descendants
            sql = """\
SELECT id, name, path, ctime, mtime, sha1, size, pickcode, is_dir
FROM data
WHERE path LIKE ? || '%' AND name NOT IN ('', '.', '..') AND name NOT LIKE '%/%'"""
            if collections and resources:
                pass
            elif collections:
                sql += " AND is_dir"
            elif resources:
                sql += " AND NOT is_dir"
            else:
                return descendants
            if depth_first:
                sql += "\nORDER BY path"
            else:
                sql += "\nORDER BY dirname(path)"
            environ = self.environ
            for r in CON.execute(sql, (self.path,)):
                attr = dict(zip(FIELDS, r))
                is_strm = False
                path = attr["path"]
                if not attr["is_dir"] and strm_predicate and strm_predicate(MappingPath(attr)):
                    path = splitext(path)[0] + ".strm"
                    is_strm = True
                elif predicate and not predicate(MappingPath(attr)):
                    continue
                if attr["is_dir"]:
                    push(FolderResource(path, environ, attr))
                else:
                    push(FileResource(path, environ, attr, is_strm=is_strm))
            return descendants

        def get_member(self, /, name: str) -> FileResource | FolderResource:
            if res := self.children.get(name):
                return res
            raise DAVError(404, self.path + name)

        def get_member_list(self, /) -> list[FileResource | FolderResource]:
            return list(self.children.values())

        def get_member_names(self, /) -> list[str]:
            return list(self.children.keys())

        def get_property_value(self, /, name: str):
            if name == "{DAV:}getcontentlength":
                return 0
            elif name == "{DAV:}iscollection":
                return True
            return super().get_property_value(name)

    class ServeDBProvider(DAVProvider):

        def __init__(self, /, dbfile: bytes | str | PathLike):
            nonlocal CON, CON_FILE
            CON = connect("file:%s?mode=ro" % quote(fsdecode(dbfile)), uri=True, check_same_thread=False)
            CON.create_function("dirname", 1, dirname)
            dbpath = CON.execute("SELECT file FROM pragma_database_list() WHERE name='main';").fetchone()[0]
            CON_FILE = connect("%s-file%s" % splitext(dbpath), check_same_thread=False)
            CON_FILE.execute("PRAGMA journal_mode = WAL;")
            CON_FILE.execute("""\
CREATE TABLE IF NOT EXISTS data (
    id INTEGER NOT NULL PRIMARY KEY,
    data BLOB,
    temp_path TEXT
);""")

        def __del__(self, /):
            try:
                CON.close()
            except:
                pass
            try:
                CON_FILE.close()
            except:
                pass

        def get_resource_inst(
            self, 
            /, 
            path: str, 
            environ: dict, 
        ) -> FolderResource | FileResource:
            is_dir = path.endswith("/")
            path = "/" + path.strip("/")
            if strm_predicate:
                if strm := STRM_CACHE.get(path):
                    return strm
                if path.endswith(".strm") and not is_dir:
                    dir_, name = splitpath(path)
                    inst = self.get_resource_inst(dir_, environ)
                    if not isinstance(inst, FolderResource):
                        raise DAVError(404, path)
                    return inst.get_member(name)
            if path == "/":
                return FolderResource("/", environ, ROOT)
            sql = "SELECT id, name, path, ctime, mtime, sha1, size, pickcode, is_dir FROM data WHERE path = ? LIMIT 1"
            record = CON.execute(sql, (path,)).fetchone()
            if not record:
                if path.endswith(".strm"):
                    sql = "SELECT id, name, path, ctime, mtime, sha1, size, pickcode, is_dir FROM data WHERE path LIKE ? || '.%' AND NOT is_dir LIMIT 1"
                    record = CON.execute(sql, (path[:-5],)).fetchone()
                    if record:
                        attr = dict(zip(FIELDS, record))
                        attr["path"] = path
                        return FileResource(path, environ, attr, is_strm=True)
                raise DAVError(404, path)
            attr = dict(zip(FIELDS, record))
            is_strm = False
            if not attr["is_dir"] and strm_predicate and strm_predicate(MappingPath(attr)):
                is_strm = True
                path = splitext(path)[0] + ".strm"
            elif predicate and not predicate(MappingPath(attr)):
                raise DAVError(404, path)
            if attr["is_dir"]:
                return FolderResource(path, environ, attr)
            else:
                return FileResource(path, environ, attr, is_strm=is_strm)

        def is_readonly(self, /) -> bool:
            return True

    app = Application()
    use_gzip_compression(app)

    @app.on_middlewares_configuration
    def configure_forwarded_headers(app: Application):
        app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))

    @app.lifespan
    async def register_client(app: Application):
        async with ClientSession(follow_redirects=False) as client:
            app.services.register(ClientSession, instance=client)
            yield

    @app.router.route("/", methods=["GET", "HEAD"])
    async def index(request: Request, session: ClientSession, pickcode: str = ""):
        if pickcode:
            user_agent = (request.get_first_header(b"User-agent") or b"").decode("latin-1")
            if client:
                resp = await client.download_url_app(
                    pickcode, 
                    headers={"User-Agent": user_agent}, 
                    request=blacksheep_request, 
                    session=session, 
                    async_=True, 
                )
                if not resp["state"]:
                    return resp, 500
                for fid, info in resp["data"].items():
                    if not info["url"]:
                        return resp, 404
                    return redirect(info["url"]["url"])
            else:
                return redirect(f"{strm_origin}?pickcode={pickcode}")
        else:
            return redirect("/d")

    @app.router.route("/", methods=[
        "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", 
        "TRACE", "PATCH", "MKCOL", "COPY", "MOVE", "PROPFIND", 
        "PROPPATCH", "LOCK", "UNLOCK", "REPORT", "ACL", 
    ])
    async def redirect_to_dav():
        return redirect("/d")

    @app.router.route("/<path:path>", methods=["GET", "HEAD"])
    async def resolve_path(request: Request, session: ClientSession, pickcode: str = "", path: str = ""):
        if pickcode:
            return redirect(f"/?pickcode={pickcode}")
        else:
            return redirect(f"/d/{path}")

    @app.router.route("/<path:path>", methods=[
        "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", 
        "TRACE", "PATCH", "MKCOL", "COPY", "MOVE", "PROPFIND", 
        "PROPPATCH", "LOCK", "UNLOCK", "REPORT", "ACL", 
    ])
    async def resolve_path_to_dav(path: str):
        return redirect(f"/d/{path}")

    config.update({
        "host": "0.0.0.0", 
        "host": 0, 
        "mount_path": "/d", 
        "provider_mapping": {"/": ServeDBProvider(dbfile)}, 
    })
    wsgidav_app = WsgiDAVApp(config)
    app.mount("/d", WSGIMiddleware(wsgidav_app, workers=128, send_queue_size=256))
    return app

# TODO: wsgidav 速度比较一般，我需要自己实现一个 webdav
# TODO: 目前 webdav 是只读的，之后需要支持写入和删除，写入小文件不会上传，因此需要一个本地的 id，如果路径上原来有记录，则替换掉此记录（删除记录，生成本地 id 的数据，插入数据）
# TODO: 如果需要写入文件，会先把数据存入临时文件，等到关闭文件，再自动写入数据库。如果文件未被修改，则忽略，如果修改了，就用我本地的id替代原来的数据
# TODO: 文件可以被 append 写，这时打开时，会先把数据库的数据写到硬盘，然后打开这个临时文件
# TODO: 实现自动排除空目录而不展示
# TODO: 和 p115dav 的思路一致，主要是 webdav 方面，使得支持的基本相同（除了不能写）
# TODO: 目前 p115dav 的进度更靠前，需要进行追进
# TODO: logging 对象可能需要初始化，从 log 模块进行
# TODO: 使用 sha1 和 size 对数据进行缓存
