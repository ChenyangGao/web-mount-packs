#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 9)
__all__ = ["ApplicationWithMethods", "make_application"]

from asyncio import gather
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Sequence
from ipaddress import ip_address
from functools import cached_property, partial
from itertools import chain
from socket import socket, AF_INET, SOCK_DGRAM
from sys import _getframe, maxsize
from typing import overload, Literal, SupportsIndex, TypeVar
from urllib.parse import urlsplit, urlunsplit

from blacksheep import Application, Request, Router, WebSocket
from blacksheep.contents import StreamedContent
from blacksheep.messages import Response
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from blacksheep.server.websocket import WebSocketDisconnectError
from dictattr import AttrDict
from httpx import AsyncClient, Response as HTTPResponse
from websockets import connect as websocket_connect
from websockets.exceptions import ConnectionClosed


T = TypeVar("T")

def __setattr__(self, attr, val, /, _set=Router.__setattr__):
    if attr == "routes":
        if val:
            val = Routers(val)
        else:
            val = Routers()
    return _set(self, attr, val)

setattr(Router, "__setattr__", __setattr__)


def get_local_ip() -> str:
    with socket(AF_INET, SOCK_DGRAM) as sock:
        #sock.connect(("8.8.8.8", 80))
        sock.connect(("192.168.1.1", 80))
        try:
            return sock.getsockname()[0]
        except:
            return ""


def is_localhost(host: str, /) -> bool:
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def is_private(host: str, /) -> bool:
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        return ip_address(host).is_private
    except ValueError:
        return False


class ChainedList(list[T]):

    def __init__(self, iterable: Iterable[T] = (), /, *appendices: Sequence[T]):
        self.appendices = appendices

    def __repr__(self, /) -> str:
        if self.appendices:
            appendices = ", " + ", ".join(map(repr, self.appendices))
        else:
            appendices = ""
        return f"{type(self).__module__}.{type(self).__qualname__}({super().__repr__()}{appendices})"

    def __len__(self, /) -> int:
        return super().__len__() + sum(map(len, self.appendices))

    def __contains__(self, v, /) -> bool:
        return super().__contains__(v) or v in chain.from_iterable(self.appendices)

    def __iter__(self, /) -> Iterator[T]:
        yield from super().__iter__()
        yield from chain.from_iterable(self.appendices)

    @overload
    def __getitem__(self, idx: SupportsIndex, /) -> T: ...
    @overload
    def __getitem__(self, idx: slice, /) -> list[T]: ...
    def __getitem__(self, idx: SupportsIndex | slice, /) -> T | list[T]:
        if isinstance(idx, SupportsIndex):
            if not isinstance(idx, int):
                idx = idx.__index__()
            total_size = len(self)
            if idx < 0:
                idx += total_size
            if idx < 0 or idx >= total_size:
                raise IndexError("list index out of range")
            size = super().__len__()
            if idx < size:
                return super().__getitem__(idx)
            for a in self.appendices:
                size += len(a)
                if idx < size:
                    return a[size-idx]
        elif isinstance(idx, slice):
            return list(self)[idx]
        raise TypeError("list indices must be integers or slices, not str")

    def count(self, v, /) -> int:
        return super().count(v) + sum(a.count(v) for a in self.appendices)

    def index(self, v: T, start: SupportsIndex = 0, stop: SupportsIndex = maxsize, /) -> int:
        if not isinstance(start, int):
            start = start.__index__()
        if not isinstance(stop, int):
            stop = stop.__index__()
        size = len(self)
        if start < 0:
            start += size
        if start < 0:
            start = 0
        if stop < 0:
            stop += size
        if not (start >= stop or start >= size):
            if start == 0 and stop >= size:
                for i, val in enumerate(self):
                    if v is val or v == val:
                        return i
            else:
                size = super().__len__()
                if start < size:
                    try:
                        return super().index(v, start, stop)
                    except ValueError:
                        pass
                if stop > size:
                    for a in self.appendices:
                        if start > size:
                            start -= size
                        else:
                            start = 0
                        stop -= size
                        try:
                            super().index(v, start, stop)
                        except ValueError:
                            pass
                        if stop <= size:
                            break
                        size = len(a)
        raise ValueError(f"{v!r} is not in list")


class Routers(dict):

    def __missing__(self, key, /):
        if key == b"":
            ls = self[key] = []
        else:
            frame = _getframe(1)
            if frame.f_code.co_qualname == "Router.add_route":
                ls = self[key] = ChainedList([], self[b""])
            else:
                ls = self[b""]
        return ls


class ApplicationWithMethods(Application):

    @cached_property
    def methods(self, /) -> AttrDict:
        return AttrDict()

    def add_method(self, func: None | Callable = None, /, name: str = ""):
        if func is None:
            return partial(self.add_method, name=name)
        if not name:
            name = func.__name__
        self.methods[name] = func
        return func

    def __getattr__(self, attr, /):
        try:
            return self.methods[attr]
        except KeyError as e:
            raise AttributeError(attr) from e


def make_application(
    base_url: str = "http://localhost", 
    custom_proxy: bool | Callable = True, 
    ws_mode: None | Literal["", "r", "w", "rw"] = None, 
    resolve_localhost: bool = False, 
    debug: bool = False, 
) -> ApplicationWithMethods:
    """创建一个 blacksheep 应用，用于反向代理 emby，以修改一些数据响应

    :param base_url: 被代理服务的 base_url
    :param custom_proxy: 自定义的代理服务函数

        - 如果为 False，则不绑定路由，之后你自己再绑定实现
        - 如果为 True，则提供一个默认的方法，会被绑定 "/" 和 "/<path:path>" 路由路径到任何请求方法
        - 如果为 Callable，会被绑定 "/" 和 "/<path:path>" 路由路径到任何请求方法

    :param ws_mode: websocket 的读写模式

        - 如果为 None 或 ""，则不代理 websocket
        - 如果为 "r"，则代理为单向 websocket，只进行接收（读）
        - 如果为 "r"，则代理为单向 websocket，只进行发送（写）
        - 如果为 "rw"，则代理为双向 websocket，会进行接收（读）和发送（写）

    :param resolve_localhost: 如果 base_url 为 localhost 地址，是否获取其实际局域网地址
    :param debug: 启用调试，会输出 DEBUG 级别日志，也会产生更详细的报错信息

    :return: 一个 blacksheep 应用，你可以 2 次扩展，并用 uvicorn 运行
    """
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"not a valid http/https base_url: {base_url!r}")
    base_url = base_url.rstrip("/")
    base_urlp = urlsplit(base_url)
    base_url_hostname = base_urlp.hostname or "localhost"
    base_url_is_localhost = is_localhost(base_url_hostname)
    base_url_is_private = base_url_is_localhost or is_private(base_url_hostname)
    if base_url_is_localhost and resolve_localhost:
        base_url_hostname = get_local_ip()
        base_url_port = (base_urlp.netloc or "").removeprefix(base_urlp.hostname or "")
        base_urlp = base_urlp._replace(netloc=base_url_hostname + base_url_port)
        base_url = urlunsplit(base_urlp)

    router = Router()
    app = ApplicationWithMethods(router=router, show_error_details=debug)

    if debug:
        getattr(app, "logger").level = 10

    @app.add_method
    def can_redirect(request: Request, url: str = "") -> bool:
        remote_hostname = urlsplit("http://" + request.host).hostname or "localhost"
        if url:
            url_hostname = urlsplit(url).hostname
            if not url_hostname:
                return True
            url_is_localhost = is_localhost(url_hostname)
            url_is_private = is_private(url_hostname)
        else:
            url_is_localhost = base_url_is_localhost
            url_is_private = base_url_is_private
        if url_is_localhost:
            return is_private(remote_hostname) if resolve_localhost else is_localhost(remote_hostname)
        elif url_is_private:
            return is_private(remote_hostname)
        return True

    @app.add_method
    async def redirect_request(
        request: Request, 
        data: None | bytes | AsyncIterator[bytes] = None, 
        timeout: None | int | float = None, 
    ) -> HTTPResponse:
        proxy_base_url = f"{request.scheme}://{request.host}"
        request_headers = [
            (k, base_url + v[len(proxy_base_url):] if k in ("destination", "origin", "referer") and v.startswith(proxy_base_url) else v)
            for k, v in ((str(k, "latin-1"), str(v, "latin-1")) for k, v in request.headers)
            if k.lower() not in ("host", "x-forwarded-proto")
        ]
        session = app.services.resolve(AsyncClient)
        return await session.send(
            request=session.build_request(
                method=request.method, 
                url=base_url+str(request.url), 
                data=request.stream() if data is None else data, # type: ignore
                headers=request_headers, 
                timeout=timeout, 
            ), 
            follow_redirects=False, 
            stream=True,
        )

    @app.add_method
    async def make_response(
        request: Request, 
        response: HTTPResponse, 
        read_if: None | Callable[[HTTPResponse], bool] = None, 
    ) -> tuple[Response, None | tuple[str, bytes]]:
        content_type = response.headers.get("content-type", "")
        if callable(read_if) and read_if(response):
            chunks = [chunk async for chunk in response.aiter_raw()]
            async def get_content():
                for chunk in chunks:
                    yield chunk
            data = (content_type, b"".join(map(response._get_content_decoder().decode, chunks)))
        else:
            get_content = response.aiter_raw
            data = None
        async def reader():
            try:
                async for chunk in get_content():
                    if await request.is_disconnected():
                        break
                    yield chunk
            finally:
                await response.aclose()
        headers = [
            (
                bytes(k, "latin-1"), 
                bytes(f"{request.scheme}://{request.host}" + v[len(base_url):] if k == "location" and v.startswith(base_url) else v, "latin-1"), 
            )
            for k, v in ((k.lower(), v) for k, v in response.headers.items())
            if k not in ("access-control-allow-methods", "access-control-allow-origin", "date", "content-type", "transfer-encoding")
        ]
        headers.append((b"access-control-allow-methods", b"PUT, GET, HEAD, POST, DELETE, OPTIONS"))
        headers.append((b"access-control-allow-origin", b"*"))
        return (Response(
            status=response.status_code, 
            headers=headers, 
            content=StreamedContent(bytes(content_type, "latin-1"), reader), 
        ), data)

    @app.add_method
    async def redirect(
        request: Request, 
        url: None | str = None, 
        timeout: None | int | float = None, 
        redirect_first: bool = False, 
    ) -> Response:
        if url is None:
            if redirect_first and request.method.upper() in ("GET", "HEAD") and can_redirect(request):
                from blacksheep import redirect
                return redirect(base_url + str(request.url))
            http_resp = await redirect_request(request, timeout=timeout)
            response, _ = await make_response(request, http_resp)
            return response
        session = app.services.resolve(AsyncClient)
        resp = await session.send(
            request=session.build_request(
                method=request.method, 
                url=url, 
                data=request.stream(), # type: ignore
                headers=[
                    (k, v)
                    for k, v in ((str(k, "latin-1"), str(v, "latin-1")) for k, v in request.headers)
                    if k.lower() not in ("host", "x-forwarded-proto")
                ], 
                timeout=timeout, 
            ), 
            stream=True, 
        )
        async def reader():
            try:
                async for chunk in resp.aiter_raw():
                    if await request.is_disconnected():
                        break
                    yield chunk
            finally:
                await resp.aclose()
        content_type = resp.headers.get("content-type") or "application/octent-stream"
        headers = [
            (bytes(k, "latin-1"), bytes(v, "latin-1")) for k, v in resp.headers.items()
            if k not in ("access-control-allow-methods", "access-control-allow-origin", "date", "content-type", "transfer-encoding")
        ]
        headers.append((b"access-control-allow-methods", b"PUT, GET, HEAD, POST, DELETE, OPTIONS"))
        headers.append((b"access-control-allow-origin", b"*"))
        return Response(
            status=resp.status_code, 
            headers=headers, 
            content=StreamedContent(bytes(content_type, "latin-1"), reader), 
        )

    @app.add_method
    async def redirect_websocket(
        request: Request, 
        ws_to: WebSocket, 
        ws_mode: Literal["r", "w", "rw"] = "rw", 
    ):
        await ws_to.accept()
        proxy_base_url = f"{request.scheme.replace('ws', 'http')}://{request.host}"
        async with websocket_connect(
            "ws" + base_url.removeprefix("http") + str(request.url), 
            additional_headers=[
                (k, base_url + v[len(proxy_base_url):] if k in ("destination", "origin", "referer") and v.startswith(proxy_base_url) else v)
                for k, v in ((str(k, "latin-1"), str(v, "latin-1")) for k, v in request.headers)
                if k.lower() not in ("host", "sec-websocket-key", "x-forwarded-proto")
            ], 
        ) as ws_from:
            async def redirect(recv, send):
                try:
                    while True:
                        await send(await recv())
                except Exception as e:
                    exc_cls = (WebSocketDisconnectError, ConnectionClosed)
                    if not (isinstance(e, exc_cls) or isinstance(e.__cause__, exc_cls)):
                        raise
            if ws_mode == "r":
                await redirect(ws_from.recv, ws_to.send_bytes)
            elif ws_mode == "w":
                await redirect(ws_to.receive_bytes, ws_from.send)
            else:
                await gather(
                    redirect(ws_from.recv, ws_to.send_bytes), 
                    redirect(ws_to.receive_bytes, ws_from.send), 
                )

    @app.on_middlewares_configuration
    def configure_forwarded_headers(app: Application):
        app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))

    @app.lifespan
    async def register_http_client(app: Application):
        async with AsyncClient() as session:
            app.services.register(AsyncClient, instance=session)
            yield

    if ws_mode:
        @router.ws("/")
        @router.ws("/<path:path>")
        async def proxy(
            request: Request, 
            ws_to: WebSocket, 
            path: str = "", 
        ):
            await redirect_websocket(request, ws_to, ws_mode)

    if callable(custom_proxy):
        router.route("/", methods=[""])(custom_proxy)
        router.route("/<path:path>", methods=[""])(custom_proxy)
    elif custom_proxy:
        @router.route("/", methods=[""])
        @router.route("/<path:path>", methods=[""])
        async def proxy(request: Request, path: str = ""):
            return await redirect(request)

    return app

# TODO: 再实现一个版本，用 fastapi，因为这个框架更新较频繁，可以在 python 3.13 上稳定运行，也可以在多种设备上编译成功
# TODO: 再实现一个版本，用 emmett
