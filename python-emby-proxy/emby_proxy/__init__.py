#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__license__ = "GPLv3 <https://www.gnu.org/licenses/gpl-3.0.txt>"
__all__ = ["make_application"]

from contextlib import suppress
from urllib.parse import urlsplit

from blacksheep import redirect, Request
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
                if (
                    (
                        (MediaSourceId and "Id" in item and MediaSourceId == item["Id"]) or 
                        ("ItemId" in item and item["ItemId"] == item_id)
                    ) and item["Path"].startswith(("http://", "https://"))
                ):
                    return redirect(item["Path"])
        return await app.redirect(request, redirect_first=True)

    return app


if __name__ == "__main__":
    from uvicorn import run

    app = make_application(debug=True)
    run(app, host="0.0.0.0", port=8097, proxy_headers=True, forwarded_allow_ips="*")

