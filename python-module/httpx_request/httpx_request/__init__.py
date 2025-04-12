#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 1, 4)
__all__ = ["request", "request_sync", "request_async"]

from collections.abc import Awaitable, Callable
from contextlib import aclosing, closing
from inspect import isawaitable, signature
from json import loads
from types import EllipsisType
from typing import cast, overload, Any, Literal

from asynctools import run_async
from argtools import argcount
from httpx import AsyncHTTPTransport, HTTPTransport
from httpx._types import AuthTypes, SyncByteStream, URLTypes
from httpx._client import AsyncClient, Client, Response, UseClientDefault, USE_CLIENT_DEFAULT


_BUILD_REQUEST_KWARGS = signature(Client.build_request).parameters.keys() - {"self"}
_CLIENT_INIT_KWARGS = signature(Client).parameters.keys() - _BUILD_REQUEST_KWARGS

if "__del__" not in Client.__dict__:
    setattr(Client, "__del__", Client.close)
if "close" not in AsyncClient.__dict__:
    def close(self, /):
        return run_async(self.aclose())
    setattr(AsyncClient, "close", close)
if "__del__" not in AsyncClient.__dict__:
    setattr(AsyncClient, "__del__", getattr(AsyncClient, "close"))
if "__del__" not in Response.__dict__:
    def __del__(self, /):
        if self.is_closed:
            return
        if isinstance(self.stream, SyncByteStream):
            self.close()
        else:
            return run_async(self.aclose())
    setattr(Response, "__del__", __del__)


def request_sync(
    url: URLTypes, 
    method: str = "GET", 
    # determine how to parse response data
    parse: None | bool | EllipsisType | Callable = None, 
    # raise for status
    raise_for_status: bool = True, 
    # pass in a Client instance
    session: None | Client = None, 
    # Client.send params
    auth: None | AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT, 
    follow_redirects: bool | UseClientDefault = True, 
    stream: bool = True, 
    # Client.request params
    **request_kwargs, 
):
    if session is None:
        init_kwargs = {k: v for k, v in request_kwargs.items() if k in _CLIENT_INIT_KWARGS}
        if "transport" not in init_kwargs:
            init_kwargs["transport"] = HTTPTransport(http2=True, retries=5)
        session = Client(**init_kwargs)
    resp = session.send(
        request=session.build_request(
            method=method, 
            url=url, 
            **{k: v for k, v in request_kwargs.items() if k in _BUILD_REQUEST_KWARGS}, 
        ), 
        auth=auth, 
        follow_redirects=follow_redirects, 
        stream=stream, 
    )
    # NOTE: keep ref to prevent gc
    setattr(resp, "session", session)
    if resp.status_code >= 400 and raise_for_status:
        resp.raise_for_status()
    if parse is None:
        return resp
    elif parse is ...:
        resp.close()
        return resp
    with closing(resp):
        if parse is False:
            return resp.read()
        elif parse is True:
            resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if content_type == "application/json":
                return resp.json()
            elif content_type.startswith("application/json;"):
                return loads(resp.text)
            elif content_type.startswith("text/"):
                return resp.text
            return resp.content
        else:
            ac = argcount(parse)
            if ac == 1:
                return parse(resp)
            else:
                return parse(resp, resp.read())


async def request_async(
    url: URLTypes, 
    method: str = "GET", 
    # determine how to parse response data
    parse: None | bool | EllipsisType | Callable = None, 
    # raise for status
    raise_for_status: bool = True, 
    # pass in an AsyncClient instance
    session: None | AsyncClient = None, 
    # AsyncClient.send params
    auth: None | AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT, 
    follow_redirects: bool | UseClientDefault = True, 
    stream: bool = True, 
    **request_kwargs, 
):
    if session is None:
        init_kwargs = {k: v for k, v in request_kwargs.items() if k in _CLIENT_INIT_KWARGS}
        if "transport" not in init_kwargs:
            init_kwargs["transport"] = AsyncHTTPTransport(http2=True, retries=5)
        session = AsyncClient(**init_kwargs)
    resp = await session.send(
            request=session.build_request(
            method=method, 
            url=url, 
            **{k: v for k, v in request_kwargs.items() if k in _BUILD_REQUEST_KWARGS}, 
        ), 
        auth=auth, 
        follow_redirects=follow_redirects, 
        stream=stream, 
    )
    setattr(resp, "session", session)
    if resp.status_code >= 400 and raise_for_status:
        resp.raise_for_status()
    if parse is None:
        return resp
    elif parse is ...:
        await resp.aclose()
        return resp
    async with aclosing(resp):
        if parse is False:
            return await resp.aread()
        elif parse is True:
            await resp.aread()
            content_type = resp.headers.get("Content-Type", "")
            if content_type == "application/json":
                return resp.json()
            elif content_type.startswith("application/json;"):
                return loads(resp.text)
            elif content_type.startswith("text/"):
                return resp.text
            return resp.content
        else:
            ac = argcount(parse)
            if ac == 1:
                ret = parse(resp)
            else:
                ret = parse(resp, await resp.aread())
            if isawaitable(ret):
                ret = await ret
            return ret


@overload
def request(
    url: URLTypes, 
    method: str = "GET", 
    parse: None | bool | EllipsisType | Callable = None, 
    raise_for_status: bool = True, 
    session: None | Client = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Any:
    ...
@overload
def request(
    url: URLTypes, 
    method: str = "GET", 
    parse: None | bool | EllipsisType | Callable = None, 
    raise_for_status: bool = True, 
    session: None | AsyncClient = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Awaitable[Any]:
    ...
def request(
    url: URLTypes, 
    method: str = "GET", 
    parse: None | bool | EllipsisType | Callable = None, 
    raise_for_status: bool = True, 
    session: None | Client | AsyncClient = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    if async_:
        return request_async(
            url=url, 
            method=method, 
            parse=parse, 
            raise_for_status=raise_for_status, 
            session=cast(None | AsyncClient, session), 
            **request_kwargs, 
        )
    else:
        return request_sync(
            url=url, 
            method=method, 
            parse=parse, 
            raise_for_status=raise_for_status, 
            session=cast(None | Client, session), 
            **request_kwargs, 
        )

