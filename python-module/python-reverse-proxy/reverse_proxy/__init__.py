#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = ["make_application"]

from collections.abc import Callable, Iterable, Iterator, Sequence
from itertools import chain
from sys import _getframe, maxsize
from typing import overload, SupportsIndex, TypeVar

from blacksheep import Application, Request, Response, Router
from blacksheep.contents import Content, StreamedContent
from blacksheep.server.remotes.forwarding import ForwardedHeadersMiddleware
from httpx import AsyncClient


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


def make_application(
    base_url: str = "http://localhost", 
    custom_proxy: bool | Callable = True, 
) -> Application:
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
    app = Application(router=router)

    @app.on_middlewares_configuration
    def configure_forwarded_headers(app: Application):
        app.middlewares.insert(0, ForwardedHeadersMiddleware(accept_only_proxied_requests=False))

    @app.lifespan
    async def register_http_client(app: Application):
        async with AsyncClient() as session:
            app.services.register(AsyncClient, instance=session)
            yield

    if callable(custom_proxy):
        router.route("/", methods=[""])(custom_proxy)
        router.route("/<path:path>", methods=[""])(custom_proxy)
    else:
        @router.route("/", methods=[""])
        @router.route("/<path:path>", methods=[""])
        async def proxy(
            request: Request, 
            session: AsyncClient, 
            path: str = "", 
        ):
            proxy_base_url = f"{request.scheme}://{request.host}"
            request_headers = [
                (k, base_url + v[len(proxy_base_url):] if k == "destination" and v.startswith(proxy_base_url) else v)
                for k, v in ((str(k.lower(), "latin-1"), str(v, "latin-1")) for k, v in request.headers)
                if k != "host"
            ]
            response = await session.send(
                request=session.build_request(
                    method=request.method, 
                    url=base_url+str(request.url), 
                    data=request.stream(), # type: ignore
                    headers=request_headers, 
                    timeout=None, 
                ), 
                follow_redirects=False, 
                stream=True,
            )
            content_type = response.headers.get("content-type", "")
            response_headers = [
                (
                    bytes(k, "latin-1"), 
                    bytes(proxy_base_url + v[len(base_url):] if k == "location" and v.startswith(base_url) else v, "latin-1"), 
                )
                for k, v in ((k.lower(), v) for k, v in response.headers.items())
                if k.lower() not in ("date", "content-type")
            ]
            async def reader():
                try:
                    async for chunk in response.aiter_raw():
                        if await request.is_disconnected():
                            break
                        yield chunk
                finally:
                    await response.aclose()
            return Response(
                response.status_code, 
                response_headers, 
                StreamedContent(bytes(content_type, "latin-1"), reader), 
            )

    return app

