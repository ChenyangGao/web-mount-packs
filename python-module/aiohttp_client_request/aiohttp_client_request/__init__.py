#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["request"]

from asyncio import get_running_loop, run, run_coroutine_threadsafe
from collections.abc import Callable
from inspect import isawaitable
from json import loads

from argtools import argcount
from aiohttp import ClientSession, ClientResponse

def _async_session_del(self, /):
    if not self.closed:
        try:
            try:
                loop = get_running_loop()
            except RuntimeError:
                run(self.close())
            else:
                run_coroutine_threadsafe(self.close(), loop)
        except Exception:
            pass
    _async_session_del_next(self)

_async_session_del_next = ClientSession.__del__
setattr(ClientSession, "__del__", _async_session_del)

def _async_response_del(self, /):
    if not self.closed:
        self.close()
    _async_response_del_next(self)

_async_response_del_next = ClientResponse.__del__
setattr(ClientResponse, "__del__", _async_response_del)


async def request(
    url: str, 
    method: str = "GET", 
    parse: None | bool | Callable = None, 
    raise_for_status: bool = True, 
    session: None | ClientSession = None, 
    **request_kwargs, 
):
    if session is None:
        async with ClientSession() as session:
            return await request(
                url, 
                method, 
                parse=parse, 
                raise_for_status=raise_for_status, 
                session=session, 
                **request_kwargs, 
            )
    request_kwargs.pop("stream", None)
    resp = await session.request(method, url, **request_kwargs)
    if raise_for_status:
        resp.raise_for_status()
    if parse is None:
        return resp
    elif parse is False:
        return await resp.read()
    elif parse is True:
        content_type = resp.headers.get("Content-Type", "")
        if content_type == "application/json":
            return await resp.json()
        elif content_type.startswith("application/json;"):
            return loads(await resp.text())
        elif content_type.startswith("text/"):
            return await resp.text()
        return await resp.read()
    else:
        ac = argcount(parse)
        if ac == 1:
            ret = parse(resp)
        else:
            ret = parse(resp, (await resp.read()))
        if isawaitable(ret):
            ret = await ret
        return ret

