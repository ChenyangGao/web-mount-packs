#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__requirements__ = ["urlopen"]

from copy import copy
from http.client import HTTPResponse
from typing import cast, Any, Callable, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import urlopen as _urlopen, Request


def urlopen(
    url: str | Request, 
    data=None, 
    /, 
    params:  str | Mapping | Sequence[tuple[Any, Any]] = "", 
    headers: Optional[Mapping] = None, 
    origin_req_host: Optional[str] = None, 
    unverifiable: Optional[bool] = None, 
    method: Optional[str] = None, 
    urlopen: Callable = _urlopen, 
    **urlopen_kwargs, 
) -> HTTPResponse:
    req_args: dict[str, Any] = {k: v for k, v, p in [
        ("origin_req_host", origin_req_host, origin_req_host), 
        ("unverifiable", unverifiable, unverifiable is not None), 
        ("method", method, method), 
    ] if p}
    if params:
        if not isinstance(params, str):
            params = urlencode(params)
    params = cast(str, params)
    if isinstance(url, Request):
        if params or data or headers or req_args:
            url = copy(url)
            if params:
                urlp = urlparse(url.full_url)
                if urlp.query:
                    params = urlp.query + "&" + params
                url.full_url = urlunparse(urlp._replace(query=params))
            if data:
                url.data = data
            if headers:
                for key in headers:
                    url.add_header(key, headers[key])
            if req_args:
                url.__dict__.update(req_args)
    elif params or data or headers or req_args:
        if params:
            urlp = urlparse(url)
            if urlp.query:
                params = urlp.query + "&" + params
            url = urlunparse(urlp._replace(query=params))
        if headers:
            req_args["headers"] = headers
        if data:
            req_args["data"] = data
        url = Request(url, **req_args)
    return _urlopen(url, **urlopen_kwargs)

