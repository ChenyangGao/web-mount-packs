#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["request"]

from collections.abc import Callable
from json import loads

from argtools import argcount
from requests.models import Response
from requests.sessions import Session

if "__del__" not in Response.__dict__:
    setattr(Response, "__del__", Response.close)

if "__del__" not in Session.__dict__:
    setattr(Session, "__del__", Session.close)


def request(
    url: str, 
    method: str = "GET", 
    parse: None | bool | Callable = None, 
    raise_for_status: bool = True, 
    session: None | Session = None, 
    **request_kwargs, 
):
    if session is None:
        with Session() as session:
            return request(
                url, 
                method, 
                parse=parse, 
                raise_for_status=raise_for_status, 
                session=session, 
                **request_kwargs, 
            )
    request_kwargs.setdefault("stream", True)
    resp = session.request(method, url, **request_kwargs)
    if raise_for_status:
        resp.raise_for_status()
    if parse is None:
        return resp
    elif parse is False:
        return resp.content
    elif parse is True:
        with resp:
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

