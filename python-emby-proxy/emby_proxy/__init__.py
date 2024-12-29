#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__license__ = "GPLv3 <https://www.gnu.org/licenses/gpl-3.0.txt>"
__all__ = ["make_application"]

from contextlib import suppress
from urllib.parse import urlsplit

from blacksheep import redirect, Request, Response
from httpx import AsyncClient, ReadTimeout
from reverse_proxy import make_application as make_application_base, ApplicationWithMethods


def make_application(
    base_url: str = "http://localhost:8096", 
    debug: bool = False, 
) -> ApplicationWithMethods:
    app = make_application_base(base_url, ws_mode="r", resolve_localhost=True, debug=debug)

    @app.middlewares.append
    async def some_path_to_lower_case(request, handler):
        path = request.scope["path"].lower()
        if path.startswith(("/emby/", "/items/", "/audio/", "/videos/", "/sync/")):
            request.scope["path"] = path
        return await handler(request)

    @app.router.route("/items/{item_id}/download", methods=["GET", "HEAD"])
    @app.router.route("/emby/items/{item_id}/download", methods=["GET", "HEAD"])
    @app.router.route("/audio/{item_id}/{name}", methods=["GET", "HEAD"])
    @app.router.route("/emby/audio/{item_id}/{name}", methods=["GET", "HEAD"])
    @app.router.route("/videos/{item_id}/{name}", methods=["GET", "HEAD"])
    @app.router.route("/emby/videos/{item_id}/{name}", methods=["GET", "HEAD"])
    @app.router.route("/sync/jobitems/{item_id}/file", methods=["GET", "HEAD"])
    @app.router.route("/emby/sync/jobitems/{item_id}/file", methods=["GET", "HEAD"])
    async def download(
        request: Request, 
        client: AsyncClient, 
        item_id: str, 
        name: str = "", 
        MediaSourceId: str = "", 
        api_key: str = "", 
    ):
        if not name.endswith(".m3u8"):
            json: None | dict = None
            while json is None:
                if await request.is_disconnected():
                    return
                with suppress(ReadTimeout):
                    resp = await client.post(f"{base_url}/Items/{item_id}/PlaybackInfo?X-Emby-Token={api_key}", timeout=3)
                    json = resp.json()
            for item in json["MediaSources"]:
                url = item["Path"]
                if (
                    (
                        (MediaSourceId and MediaSourceId == item.get("Id")) or 
                        item.get("ItemId") == item_id
                    ) and url.startswith(("http://", "https://"))
                ):
                    if not url.startswith(("http://", "https://")) or app.can_redirect(request, url):
                        return redirect(url)
                    proxy_base_url = f"{request.scheme}://{request.host}"
                    request_headers = [
                        (k, base_url + v[len(proxy_base_url):] if k in ("destination", "origin", "referer") and v.startswith(proxy_base_url) else v)
                        for k, v in ((str(k, "latin-1"), str(v, "latin-1")) for k, v in request.headers)
                        if k.lower() not in ("host", "x-forwarded-proto")
                    ]
                    while True:
                        http_resp = await client.send(
                            request=client.build_request(
                                method="GET", 
                                url=url, 
                                headers=request_headers, 
                                timeout=None, 
                            ), 
                            follow_redirects=False, 
                            stream=True, 
                        )
                        if http_resp.status_code in (301, 302, 303, 307, 308):
                            await http_resp.aclose()
                            url = http_resp.headers["location"]
                            if not url.startswith(("http://", "https://")) or app.can_redirect(request, url):
                                return Response(http_resp.status_code, [(b"Location", bytes(url, "latin-1"))])
                    resp, _ = await app.make_response(request, http_resp)
                    return resp
        return await app.redirect(request, redirect_first=True)

    return app


if __name__ == "__main__":
    from uvicorn import run

    app = make_application(debug=True)
    run(app, host="0.0.0.0", port=8097, proxy_headers=True, forwarded_allow_ips="*")

