#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 8)
__all__ = ["request"]

from collections.abc import Buffer, Callable, ItemsView, Iterable, Mapping, Sequence
from http.cookiejar import CookieJar
from http.cookies import SimpleCookie
from re import compile as re_compile
from types import EllipsisType
from typing import cast, runtime_checkable, Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request

from argtools import argcount
from cookietools import extract_cookies, cookies_dict_to_str, cookies_str_to_dict
from urllib3 import HTTPHeaderDict, Retry, Timeout
from urllib3.exceptions import MaxRetryError
from urllib3.poolmanager import PoolManager
from urllib3.response import HTTPResponse
from urllib3.util.url import _normalize_host as normalize_host

try:
    from orjson import loads
except ImportError:
    from json import loads


if "__del__" not in PoolManager.__dict__:
    setattr(PoolManager, "__del__", PoolManager.clear)

CRE_search_charset = re_compile(r"\bcharset=(?P<charset>[^ ;]+)").search


@runtime_checkable
class SupportsGeturl[AnyStr: (str, bytes)](Protocol):
    def geturl(self, /) -> AnyStr: ...


def str_url(url: Any, /) -> str:
    if not isinstance(url, str):
        if isinstance(url, SupportsGeturl):
            url = url.geturl()
        if isinstance(url, Buffer):
            url = str(url, "utf-8")
        else:
            url = str(url)
    return url


def origin_tuple(url: str, /) -> tuple[str, str, int]:
    urlp   = urlsplit(url)
    scheme = urlp.scheme or "http"
    host   = normalize_host(urlp.hostname or "", scheme) or ""
    port   = urlp.port or (443 if scheme == "https" else 80)
    return (scheme, host, port)


def is_same_origin(url1: str, url2: str, /) -> bool:
    if url2.startswith("/"):
        return True
    elif url1.startswith("/"):
        return False
    return origin_tuple(url1) == origin_tuple(url2)


def get_charset(content_type: str, default="utf-8") -> str:
    match = CRE_search_charset(content_type)
    if match is None:
        return "utf-8"
    return match["charset"]


def parse_response(
    response: HTTPResponse, 
    parse: None | EllipsisType | bool | Callable = None, 
):
    if parse is None:
        return response
    elif parse is ...:
        response.close()
        return response
    with response:
        if isinstance(parse, bool):
            content = response.read()
            if parse:
                content_type = response.headers.get("Content-Type") or ""
                if content_type == "application/json":
                    return response.json()
                elif content_type.startswith("application/json;"):
                    return loads(content.decode(get_charset(content_type)))
                elif content_type.startswith("text/"):
                    return content.decode(get_charset(content_type))
            return content
        else:
            ac = argcount(parse)
            with response:
                if ac == 1:
                    return parse(response)
                else:
                    return parse(response, response.read())


def request(
    url: Any, 
    method: str = "GET", 
    params: None | str | Mapping | Sequence[tuple[Any, Any]] = None, 
    data: None | Buffer | str | Mapping | Sequence[tuple[Any, Any]] | Iterable[Buffer] = None, 
    headers: None | Mapping[str, str] | Iterable[tuple[str, str]] = None, 
    cookies: None | CookieJar | SimpleCookie = None, 
    parse: None | EllipsisType | bool | Callable = None, 
    redirect: bool = True, 
    timeout: None | float | Timeout = Timeout(connect=5, read=60), 
    raise_for_status: bool = True, 
    pool: PoolManager = PoolManager(128), 
    retries: None | int | Retry = Retry(connect=5, read=5), 
    stream: bool = True, 
    **request_kwargs, 
):
    url = str_url(url)
    if params:
        if not isinstance(params, (Buffer, str)):
            params = urlencode(params)
        if params:
            if isinstance(params, Buffer):
                params = str(params, "utf-8")
            urlp = urlsplit(url)
            if query := urlp.query:
                query += "&" + params
            else:
                query = params
            url = urlunsplit(urlp._replace(query=query))
    if data is None:
        pass
    elif isinstance(data, Buffer):
        request_kwargs["body"] = data
    elif isinstance(data, (Mapping, Sequence)):
        request_kwargs["fields"] = data
    elif isinstance(data, Iterable):
        request_kwargs["body"] = data
    if retries and isinstance(retries, int):
        retries = Retry.from_int(retries, redirect=redirect)
    if headers:
        if isinstance(headers, Mapping):
            headers = ItemsView(headers)
        headers = {k.lower(): v for k, v in headers}
    else:
        headers = {}
    if cookies is None:
        cookies = getattr(pool, "cookies", None)
    if cookies:
        netloc_endswith = urlsplit(url).netloc.endswith
        cookies_dict = cookies_str_to_dict(headers.get("cookie", ""))
        if isinstance(cookies, CookieJar):
            cookies_dict.update(
                (cookie.name, val)
                for cookie in cookies 
                if (val := cookie.value) and (domain := cookie.domain) and not netloc_endswith(domain)
            )
        else:
            cookies_dict.update(
                (name, val)
                for name, morsel in cookies.items()
                if (val := morsel.value) and (not (domain := morsel.get("domain", "")) or netloc_endswith(domain))
            )
        if cookies_dict:
            headers["cookie"] = cookies_dict_to_str(cookies_dict)
    elif cookies is None:
        cookies = CookieJar()
    response = cast(HTTPResponse, pool.request(
        method=method, 
        url=url, 
        headers=headers, 
        preload_content=not stream, 
        redirect=False, 
        retries=retries, 
        timeout=timeout, 
        **request_kwargs, 
    ))
    setattr(response, "cookies", cookies)
    extract_cookies(cookies, url, response) # type: ignore
    if raise_for_status and response.status >= 400:
        raise HTTPError(url, response.status, response.reason, response.headers, response) # type: ignore
    redirect_location = redirect and response.get_redirect_location()
    if not redirect_location:
        return parse_response(response, parse)
    redirect_location = redirect_location
    redirect_location = cast(str, urljoin(url, redirect_location))
    if response.status == 303:
        method = "GET"
        request_kwargs["body"] = None
        headers = HTTPHeaderDict(headers)._prepare_for_method_change()
    if retries:
        if (rm_headers := retries.remove_headers_on_redirect) and not is_same_origin(url, redirect_location):
            headers = {k: v for k, v in headers.items() if k not in rm_headers}
        try:
            retries = retries.increment(method, url, response=response)
        except MaxRetryError:
            if retries.raise_on_redirect:
                response.drain_conn()
                raise
            return parse_response(response, parse)
    response.drain_conn()
    return request(
        redirect_location, 
        method, 
        headers=headers, 
        cookies=cookies, 
        timeout=timeout, 
        raise_for_status=raise_for_status, 
        pool=pool, 
        retries=retries, 
        stream=stream, 
        **request_kwargs, 
    )

