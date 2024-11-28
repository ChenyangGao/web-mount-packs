#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 6)
__all__ = ["ApplicationWithMethods", "make_application"]

from collections.abc import Callable, Iterable, Iterator, Sequence
from functools import cached_property, partial
from itertools import chain
from sys import _getframe, maxsize
from typing import overload, SupportsIndex, TypeVar

from blacksheep import Application, Request, Router
from blacksheep.contents import StreamedContent
from blacksheep.messages import Response
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from dictattr import AttrDict
from httpx import AsyncClient, Response as HTTPResponse


T = TypeVar("T")

def __setattr__(self, attr, val, /, _set=Router.__setattr__):
    if attr == "routes":
        if val:
            val = Routers(val)
        else:
            val = Routers()
    return _set(self, attr, val)

setattr(Router, "__setattr__", __setattr__)


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
) -> ApplicationWithMethods:
    """创建一个 blacksheep 应用，用于反向代理 emby，以修改一些数据响应

    :param base_url: 被代理服务的 base_url
    :param custom_proxy: 自定义的代理服务函数

        - 如果为 False，则不绑定路由，之后你自己再绑定实现
        - 如果为 True，则提供一个默认的方法，会被绑定 "/" 和 "/<path:path>" 路由路径到任何请求方法
        - 如果为 Callable，会被绑定 "/" 和 "/<path:path>" 路由路径到任何请求方法

    :return: 一个 blacksheep 应用，你可以 2 次扩展，并用 uvicorn 运行
    """
    base_url = base_url.rstrip("/")
    router = Router()
    app = ApplicationWithMethods(router=router)

    @app.add_method
    async def redirect_request(request: Request, data=None) -> HTTPResponse:
        proxy_base_url = f"{request.scheme}://{request.host}"
        request_headers = [
            (k, base_url + v[len(proxy_base_url):] if k in ("destination", "origin", "referer") and v.startswith(proxy_base_url) else v)
            for k, v in ((str(k, "latin-1"), str(v, "latin-1")) for k, v in request.headers)
            if k.lower() != "host"
        ]
        session = app.services.resolve(AsyncClient)
        return await session.send(
            request=session.build_request(
                method=request.method, 
                url=base_url+str(request.url), 
                data=request.stream() if data is None else data, # type: ignore
                headers=request_headers, 
                timeout=None, 
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

    @app.on_middlewares_configuration
    def configure_forwarded_headers(app: Application):
        app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))

    @app.lifespan
    async def register_http_client(app: Application):
        async with AsyncClient() as session:
            app.services.register(AsyncClient, instance=session)
            yield

    @router.route("/_redirect", methods=[""])
    async def redirect(
        request: Request, 
        session: AsyncClient, 
        url: str, 
        timeout: None | float = None, 
    ):
        resp = await session.send(
            request=session.build_request(
                method=request.method, 
                url=url, 
                data=request.stream(), # type: ignore
                headers=[
                    (k, v)
                    for k, v in ((str(k, "latin-1"), str(v, "latin-1")) for k, v in request.headers)
                    if k.lower() != "host"
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
        content_type = resp.headers.get("content-type", "")
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

    if callable(custom_proxy):
        router.route("/", methods=[""])(custom_proxy)
        router.route("/<path:path>", methods=[""])(custom_proxy)
    elif custom_proxy:
        @router.route("/", methods=[""])
        @router.route("/<path:path>", methods=[""])
        async def proxy(
            request: Request, 
            session: AsyncClient, 
            path: str = "", 
        ):
            http_resp = await redirect_request(request)
            response, _ = await make_response(request, http_resp)
            return response

    return app

