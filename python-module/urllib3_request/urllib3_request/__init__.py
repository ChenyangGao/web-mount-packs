#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["request"]

from collections.abc import Callable, Iterable, Mapping, Sequence
from json import loads
from re import compile as re_compile
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, urlunparse

from argtools import argcount
from urllib3 import _DEFAULT_POOL # type: ignore
from urllib3 import Retry, Timeout
from urllib3.poolmanager import PoolManager


if "__del__" not in PoolManager.__dict__:
    setattr(PoolManager, "__del__", PoolManager.clear)

CRE_search_charset = re_compile(r"\bcharset=(?P<charset>[^ ;]+)").search


def get_charset(content_type: str, default="utf-8") -> str:
    match = CRE_search_charset(content_type)
    if match is None:
        return "utf-8"
    return match["charset"]


def request(
    url: str, 
    method: str = "GET", 
    parse: None | bool | Callable = None, 
    params: None | str | Mapping | Sequence[tuple[Any, Any]] = None, 
    data: None | bytes | str | Mapping | Sequence[tuple[Any, Any]] | Iterable[bytes] = None, 
    timeout: None | float | Timeout = Timeout(connect=5, read=60), 
    raise_for_status: bool = True, 
    pool: PoolManager = _DEFAULT_POOL, 
    retries: None | int | Retry = Retry(connect=5, read=5), 
    stream: bool = True, 
    **request_kwargs, 
):
    if params:
        if not isinstance(params, str):
            params = urlencode(params)
        if params:
            urlp = urlparse(url)
            if urlp.query:
                query = urlp.query + "&" + params
            else:
                query = params
            url = urlunparse(urlp._replace(query=query))
    if data is None:
        pass
    elif isinstance(data, (bytes, bytearray, memoryview)):
        request_kwargs["body"] = data
    elif isinstance(data, (Mapping, Sequence)):
        request_kwargs["fields"] = data
    elif isinstance(data, Iterable):
        request_kwargs["body"] = data
    request_kwargs["preload_content"] = not stream
    if retries:
        if isinstance(retries, int):
            retries = Retry(retries)
        request_kwargs["retries"] = retries
    resp = pool.request(
        method=method, 
        url=url, 
        timeout=timeout, 
        **request_kwargs, 
    )
    if raise_for_status and resp.status >= 400:
        raise HTTPError(resp.url, resp.status, resp.reason, resp.headers, resp)
    if parse is None:
        return resp
    with resp:
        if isinstance(parse, bool):
            content = resp.read()
            if parse:
                content_type = resp.headers.get("Content-Type") or ""
                if content_type == "application/json":
                    return resp.json()
                elif content_type.startswith("application/json;"):
                    return loads(content.decode(get_charset(content_type)))
                elif content_type.startswith("text/"):
                    return content.decode(get_charset(content_type))
            return content
        else:
            ac = argcount(parse)
            with resp:
                if ac == 1:
                    return parse(resp)
                else:
                    return parse(resp, resp.read())

