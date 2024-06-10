#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 8)
__all__ = ["request", "request_sync", "request_async"]

from asyncio import create_task, get_running_loop, run, run_coroutine_threadsafe
from collections.abc import Awaitable, Callable
from contextlib import aclosing, closing
from inspect import isawaitable
from json import loads
from typing import cast, overload, Any, Literal, TypeVar

from argtools import argcount
from httpx import AsyncHTTPTransport, HTTPTransport
from httpx._types import AuthTypes, CertTypes, ProxyTypes, ProxiesTypes, SyncByteStream, URLTypes, VerifyTypes
from httpx._client import AsyncClient, Client, Response, UseClientDefault, USE_CLIENT_DEFAULT


if "__del__" not in Client.__dict__:
    setattr(Client, "__del__", Client.close)

if "__del__" not in AsyncClient.__dict__:
    def __del__(self, /):
        try:
            try:
                loop = get_running_loop()
            except RuntimeError:
                run(self.aclose())
            else:
                run_coroutine_threadsafe(self.aclose(), loop)
        except Exception:
            pass
    setattr(Client, "__del__", __del__)

if "__del__" not in Response.__dict__:
    def __del__(self, /):
        if self.is_closed:
            return
        if isinstance(self.stream, SyncByteStream):
            self.close()
        else:
            try:
                try:
                    loop = get_running_loop()
                except RuntimeError:
                    run(self.aclose())
                else:
                    run_coroutine_threadsafe(self.aclose(), loop)
            except Exception:
                pass
    setattr(Response, "__del__", __del__)


def request_sync(
    url: URLTypes, 
    method: str = "GET", 
    # determine how to parse response data
    parse: None | bool | Callable = None, 
    # raise for status
    raise_for_status: bool = True, 
    # pass in a custom session instance
    session: None | Client = None, 
    # Client.send params
    auth: None | AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT, 
    follow_redirects: bool | UseClientDefault = True, 
    # use Client.stream xor Client.request
    stream: bool = True, 
    # Client.__init__ params
    cert: None | CertTypes = None, 
    proxy: None | ProxyTypes = None, 
    proxies: None | ProxiesTypes = None, 
    trust_env: bool = True, 
    verify: VerifyTypes = True, 
    # Client.request params
    **request_kwargs, 
):
    if session is None:
        session = Client(
            cert=cert, 
            proxy=proxy, 
            proxies=proxies, 
            trust_env=trust_env, 
            verify=verify, 
            transport=HTTPTransport(http2=True, retries=5), 
        )
    request = session.build_request(
        method=method, 
        url=url, 
        **request_kwargs, 
    )
    resp = session.send(
        request=request, 
        auth=auth, 
        follow_redirects=follow_redirects, 
        stream=stream, 
    )
    if raise_for_status:
        resp.raise_for_status()
    if parse is None:
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
    parse: None | bool | Callable = None, 
    # raise for status
    raise_for_status: bool = True, 
    # pass in a custom session instance
    session: None | AsyncClient = None, 
    # AsyncClient.send params
    auth: None | AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT, 
    follow_redirects: bool | UseClientDefault = True, 
    # use AsyncClient.stream xor AsyncClient.request
    stream: bool = True, 
    # Client.__init__ params
    cert: None | CertTypes = None, 
    proxy: None | ProxyTypes = None, 
    proxies: None | ProxiesTypes = None, 
    trust_env: bool = True, 
    verify: VerifyTypes = True, 
    **request_kwargs, 
):
    if session is None:
        session = AsyncClient(
            cert=cert, 
            proxy=proxy, 
            proxies=proxies, 
            trust_env=trust_env, 
            verify=verify, 
            transport=AsyncHTTPTransport(http2=True, retries=5), 
        )
    request = session.build_request(
        method=method, 
        url=url, 
        **request_kwargs, 
    )
    resp = await session.send(
        request=request, 
        auth=auth, 
        follow_redirects=follow_redirects, 
        stream=stream, 
    )
    if raise_for_status:
        resp.raise_for_status()
    if parse is None:
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
    parse: None | bool | Callable = None, 
    raise_for_status: bool = True, 
    session: None | Client | AsyncClient = None, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Any:
    ...
@overload
def request(
    url: URLTypes, 
    method: str, 
    parse: None | bool | Callable, 
    raise_for_status: bool, 
    session: None | AsyncClient, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Awaitable[Any]:
    ...
def request(
    url: URLTypes, 
    method: str = "GET", 
    parse: None | bool | Callable = None, 
    raise_for_status: bool = True, 
    session: None | Client | AsyncClient = None, 
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

