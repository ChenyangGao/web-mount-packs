#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["request"]

from asyncio import get_running_loop, run, run_coroutine_threadsafe
from collections.abc import Callable
from json import loads

from argtools import argcount
from httpx._types import AuthTypes, SyncByteStream, URLTypes
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
    parse: None | bool | Callable = None, 
    raise_for_status: bool = False, 
    session: None | Client = None, 
    auth: None | AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT, 
    follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT, 
    stream: bool = True, 
    **request_kwargs, 
):
    if session is None:
        session = Client()
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
    elif parse is False:
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
    parse: None | bool | Callable = None, 
    raise_for_status: bool = False, 
    session: None | AsyncClient = None, 
    auth: None | AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT, 
    follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT, 
    stream: bool = True, 
    **request_kwargs, 
):
    if session is None:
        session = AsyncClient()
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
    elif parse is False:
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
            return parse(resp)
        else:
            return parse(resp, await resp.aread())


def request(
    url: URLTypes, 
    method: str = "GET", 
    parse: None | bool | Callable = None, 
    raise_for_status: bool = False, 
    session: None | Client | AsyncClient = None, 
    async_: bool = False, 
    **request_kwargs, 
):
    if session is not None:
        async_ = isinstance(session, AsyncClient)
    request = request_async if async_ else request_sync
    return request( # type: ignore
        url, 
        method, 
        parse=parse, 
        raise_for_status=raise_for_status, 
        session=session, 
        **request_kwargs, 
    )

