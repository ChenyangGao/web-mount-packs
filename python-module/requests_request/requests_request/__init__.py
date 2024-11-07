#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 6)
__all__ = ["request"]

from collections.abc import Callable
from json import loads
from types import EllipsisType
from typing import Literal

from argtools import argcount
from requests import adapters
from requests.models import Response
from requests.sessions import Session

if "__del__" not in Response.__dict__:
    setattr(Response, "__del__", Response.close)

if "__del__" not in Session.__dict__:
    setattr(Session, "__del__", Session.close)

adapters.DEFAULT_RETRIES = 5


def request(
    url: str, 
    method: str = "GET", 
    parse: None | EllipsisType | bool | Callable = None, 
    raise_for_status: bool = True, 
    session: None | Session = None, 
    stream: bool = True, 
    timeout: None | float | tuple[float, float] = (5, 60), 
    **request_kwargs, 
):
    if session is None:
        session = Session()
    resp = session.request(
        method=method, 
        url=url, 
        stream=stream, 
        timeout=timeout, 
        **request_kwargs, 
    )
    if raise_for_status:
        resp.raise_for_status()
    if parse is None:
        return resp
    elif parse is ...:
        resp.close()
        return resp
    with resp:
        if parse is False:
            return resp.content
        elif parse is True:
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
            with resp:
                if ac == 1:
                    return parse(resp)
                else:
                    return parse(resp, resp.content)

