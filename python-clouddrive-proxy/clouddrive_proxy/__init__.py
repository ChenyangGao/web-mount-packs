#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__license__ = "GPLv3 <https://www.gnu.org/licenses/gpl-3.0.txt>"
__all__ = ["make_application"]

from glob import iglob
from os.path import exists, isfile
from posixpath import split as splitpath
from sqlite3 import connect, Connection

from blacksheep import redirect, Request, Response
from clouddrive import CloudDriveClient
from google.protobuf.json_format import MessageToDict
from httpx import AsyncClient
from reverse_proxy import make_application as make_application_base
from sqlitetools import find


def make_application(
    username: str, 
    password: str, 
    base_url: str = "http://localhost:19798", 
    base_url_115: str = "http://localhost:8000", 
    dbfile: str = "", 
    debug: bool = False, 
):
    client = CloudDriveClient(origin=base_url, username=username, password=password)
    app = make_application_base(
        base_url, 
        ws_mode="rw", 
        resolve_localhost=True, 
        debug=debug, 
    )
    con: None | Connection = None

    if dbfile:
        if exists(dbfile):
            if not isfile(dbfile):
                dbfile = next(iglob(f"{dbfile}/**/dir_cache.sqlite", recursive=True), "")
        if dbfile:
            @app.lifespan
            async def register_connection(app):
                nonlocal con
                with connect(dbfile) as con:
                    app.services.register(Connection, instance=con)
                    yield

    if base_url_115:
        @app.router.get("/static/http/{host}/False/{path}")
        @app.router.get("/dav/{path:path}")
        async def download(request: Request, session: AsyncClient, path: str = ""):
            if request.path.startswith("/dav"):
                path = "/" + path
            url = ""
            if con:
                dir_, name = splitpath(path)
                pid = find(con, "SELECT id FROM cached_item WHERE path = ? LIMIT 1", dir_)
                if pid:
                    resp = find(con, "SELECT api_name = '115', api_user, custom_data FROM files WHERE parent_id = ? AND name = ? LIMIT 1", (pid, name))
                    if resp and resp[0]:
                        url = f"{base_url_115}?user_id=%s&pickcode=%s" % resp[1:]
            if not url:
                attr = MessageToDict(await client.FindFileByPath(path, async_=True))
                if attr["CloudAPI"]["name"] == "115":
                    user_id = int(attr["CloudAPI"]["userName"])
                    file_id = int(attr["id"])
                    if con:
                        pickcode = find(con, "SELECT custom_data FROM files WHERE id = ? LIMIT 1", file_id)
                        if pickcode:
                            url = f"{base_url_115}?user_id={user_id}&pickcode={pickcode}"
                    if not url:
                        url = f"{base_url_115}?user_id={user_id}&id={file_id}"
            if url:
                if app.can_redirect(request, url):
                    return redirect(url)
                proxy_base_url = f"{request.scheme}://{request.host}"
                request_headers = [
                    (k, base_url + v[len(proxy_base_url):] if k in ("destination", "origin", "referer") and v.startswith(proxy_base_url) else v)
                    for k, v in ((str(k, "latin-1"), str(v, "latin-1")) for k, v in request.headers)
                    if k.lower() not in ("host", "x-forwarded-proto")
                ]
                try:
                    while True:
                        http_resp = await session.send(
                            request=session.build_request(
                                method="GET", 
                                url=url, 
                                headers=request_headers, 
                                timeout=None, 
                            ), 
                            follow_redirects=False, 
                            stream=True, 
                        )
                        if http_resp.status_code >= 400:
                            raise
                        if http_resp.status_code in (301, 302, 303, 307, 308):
                            await http_resp.aclose()
                            url = http_resp.headers["location"]
                            if not url.startswith(("http://", "https://")) or app.can_redirect(request, url):
                                return Response(http_resp.status_code, [(b"Location", bytes(url, "latin-1"))])
                    resp, _ = await app.make_response(request, http_resp)
                    return resp
                except Exception:
                    pass
            return await app.redirect(request, redirect_first=True)

    return app

