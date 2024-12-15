#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__all__ = [
    "create_cookie", "create_morsel", "cookie_to_morsel", "morsel_to_cookie", 
    "extract_cookies", "update_cookies", "cookies_str_to_dict", "cookies_dict_to_str", 
]

from calendar import timegm
from collections.abc import ItemsView, Iterable, Mapping, ValuesView
from copy import copy
from datetime import datetime
from http.client import HTTPMessage
from http.cookiejar import Cookie, CookieJar
from http.cookies import Morsel, SimpleCookie
from re import compile as re_compile
from time import gmtime, strftime, strptime, time
from typing import cast, Any, Protocol
from urllib.request import Request


CRE_COOKIE_SEP_split = re_compile(r";\s*").split


class HasHeaders[AnyStr: (bytes, str)](Protocol):
    @property
    def headers(self, /) -> HTTPMessage | Mapping[AnyStr, AnyStr] | Iterable[tuple[AnyStr, AnyStr]]:
        ...


def create_cookie(
    name: str, 
    value: str | Cookie | Morsel | Mapping, 
    **kwargs, 
) -> Cookie:
    if isinstance(value, str):
        pass
    elif isinstance(value, Cookie):
        if not kwargs:
            cookie = copy(value)
            if name:
                cookie.name = name
            return cookie
        kwargs = {**value.__dict__, **kwargs}
        kwargs.setdefault("rest", kwargs.pop("_rest", {"HttpOnly": None}))
        value = kwargs["value"]
    elif isinstance(value, Morsel):
        kwargs = {
            "comment": value["comment"], 
            "discard": False, 
            "domain": value["domain"], 
            "path": value["path"], 
            "rest": {
                "HttpOnly": value["httponly"], 
                "SameSite": value["samesite"], 
            }, 
            "secure": bool(value["secure"]), 
            "version": value["version"] or 0, 
            **kwargs, 
        }
        value = value.value
    else:
        kwargs = {**value, **kwargs}
        value = kwargs.get("value", "")
    if not name:
        name = kwargs.get("name", "")
    expires = kwargs.get("expires")
    max_age = kwargs.get("max-age")
    if expires:
        if isinstance(expires, int):
            pass
        elif isinstance(expires, datetime):
            expires = expires.timestamp()
        else:
            if len(expires) == 27:
                fmt = "%a, %d-%b-%y %H:%M:%S GMT"
            else:
                fmt = "%a, %d-%b-%Y %H:%M:%S GMT"
            expires = timegm(strptime(expires, fmt))
    elif max_age:
        try:
            expires = int(time()) + int(max_age)
        except ValueError:
            raise TypeError(f"max-age: {max_age} must be integer")
    result: dict[str, Any] = {
        "version": 0, 
        "name": name, 
        "value": value, 
        "port": None, 
        "domain": "", 
        "path": "/", 
        "secure": False, 
        "expires": None, 
        "discard": True, 
        "comment": None, 
        "comment_url": None, 
        "rest": {"HttpOnly": None}, 
        "rfc2109": False, 
    }
    result.update(
        (key, val)
        for key, val in kwargs.items()
        if key in result
    )
    result["comment_url"] = bool(result["comment"])
    result["port_specified"] = bool(result["port"])
    result["domain_specified"] = bool(result["domain"])
    result["domain_initial_dot"] = result["domain"].startswith(".")
    result["path_specified"] = bool(result["path"])
    return Cookie(**result)


def create_morsel(
    name: str, 
    value: str | Cookie | Morsel | Mapping, 
    **kwargs, 
) -> Morsel:
    morsel: Morsel
    if isinstance(value, str):
        morsel = Morsel()
        morsel.set(name, value, value)
    elif isinstance(value, Cookie):
        kwargs = {**value.__dict__, **kwargs}
        kwargs.setdefault("rest", kwargs.pop("_rest", {"HttpOnly": None}))
        if not name:
            name = kwargs.get("name", "")
        value = cast(str, kwargs["value"])
        morsel = Morsel()
        morsel.set(name, value, value)
    elif isinstance(value, Morsel):
        morsel = copy(value)
        if name:
            setattr(morsel, "_key", name)
        if not kwargs:
            return morsel
    else:
        kwargs = {**value, **kwargs}
        if not name:
            name = kwargs.get("name", "")
        value = cast(str, kwargs.get("value", ""))
        morsel = Morsel()
        morsel.set(name, value, value)
    expires = kwargs.get("expires")
    if expires:
        if isinstance(expires, datetime):
            morsel["expires"] = expires.strftime("%a, %d-%b-%Y %H:%M:%S GMT")
        else:
            morsel["expires"] = strftime("%a, %d-%b-%Y %H:%M:%S GMT", gmtime(expires))
    if "path" in kwargs or morsel["path"] in ("", None):
        morsel["path"] = kwargs.get("path", "/")
    if "comment" in kwargs:
        morsel["comment"] = kwargs["comment"]
    if "domain" in kwargs:
        morsel["domain"] = kwargs["domain"]
    if "secure" in kwargs or morsel["secure"] in ("", None):
        morsel["secure"] = kwargs.get("secure", False)
    if "version" in kwargs or morsel["version"] in ("", None):
        morsel["version"] = kwargs.get("version", 0)
    rest = kwargs.get("rest")
    if rest:
        if "HttpOnly" in rest:
            morsel["httponly"] = rest["HttpOnly"]
        if "Max-Age" in rest:
            morsel["max-age"]  = rest["Max-Age"]
        if "SameSite" in rest:
            morsel["samesite"] = rest["SameSite"]
    return morsel


def cookie_to_morsel(cookie: Cookie, /) -> Morsel:
    morsel: Morsel = Morsel()
    value = cookie.value or ""
    morsel.set(cookie.name, value, value)
    expires: Any = cookie.expires
    if expires:
        if isinstance(expires, datetime):
            expires = expires.strftime("%a, %d-%b-%Y %H:%M:%S GMT")
        else:
            expires = strftime("%a, %d-%b-%Y %H:%M:%S GMT", gmtime(expires))
    rest = getattr(cookie, "_rest", {})
    morsel.update({
        "expires": expires, 
        "path": cookie.path, 
        "comment": getattr(cookie, "comment", "") or "", 
        "domain": cookie.domain, 
        "max-age": getattr(cookie, "max_age", ""), 
        "secure": getattr(cookie, "secure", ""), 
        "httponly": getattr(cookie, "http_only", "") or rest.get("HttpOnly", ""), 
        "version": getattr(cookie, "version", ""), 
        "samesite": getattr(cookie, "same_site", "") or rest.get("SameSite", ""), 
    })
    return morsel


def morsel_to_cookie(cookie: Morsel, /) -> Cookie:
    expires = cookie["expires"] or None
    max_age = cookie["max-age"] or None
    if expires:
        if len(expires) == 27:
            fmt = "%a, %d-%b-%y %H:%M:%S GMT"
        else:
            fmt = "%a, %d-%b-%Y %H:%M:%S GMT"
        expires = timegm(strptime(expires, fmt))
    elif max_age:
        try:
            expires = int(time()) + int(max_age)
        except ValueError:
            raise TypeError(f"max-age: {max_age} must be integer")
    return create_cookie(
        comment=cookie["comment"], 
        comment_url=bool(cookie["comment"]), 
        discard=False, 
        domain=cookie["domain"], 
        expires=expires, 
        name=cookie.key, 
        path=cookie["path"], 
        rest={
            "HttpOnly": cookie["httponly"], 
            "SameSite": cookie["samesite"], 
        }, 
        secure=bool(cookie["secure"]), 
        value=cookie.value, 
        version=cookie["version"] or 0, 
    )


def extract_cookies[Cookies: (CookieJar, SimpleCookie)](
    cookies: Cookies, 
    url: str, 
    response: HasHeaders, 
) -> Cookies:
    if not hasattr(response, "info"):
        headers = response.headers
        if not isinstance(headers, HTTPMessage):
            headers_old = headers
            headers = HTTPMessage()
            if isinstance(headers_old, Mapping):
                headers_old = ItemsView(headers_old)
            for k, v in headers_old:
                if isinstance(k, bytes):
                    k = str(k, "latin-1")
                if isinstance(v, bytes):
                    v = str(v, "latin-1")
                headers.add_header(k, v)
        setattr(response, "info", lambda: headers)
    if isinstance(cookies, SimpleCookie):
        cookiejar = CookieJar()
        cookiejar.extract_cookies(response, Request(url)) # type: ignore
        cookies.update((cookie.name, cookie_to_morsel(cookie)) for cookie in cookiejar)
    else:
        cookies.extract_cookies(response, Request(url)) # type: ignore
    return cookies


def update_cookies[Cookies: (CookieJar, SimpleCookie)](
    cookies1: Cookies, 
    cookies2: CookieJar | SimpleCookie, 
    /, 
) -> Cookies:
    if isinstance(cookies1, CookieJar):
        if isinstance(cookies2, SimpleCookie):
            cookies: Iterable[Cookie | Morsel] = cookies2.values()
        elif isinstance(cookies2, Mapping):
            cookies = ValuesView(cookies2)
        else:
            cookies = cookies2
        set_cookie = cookies1.set_cookie
        for cookie in cookies:
            if isinstance(cookie, Morsel):
                cookie = morsel_to_cookie(cookie)
            set_cookie(cookie)
    else:
        if isinstance(cookies2, SimpleCookie):
            morsels: Iterable[tuple[str, Morsel]] = cookies2.items()
        elif isinstance(cookies2, Mapping):
            morsels = ((k, v if isinstance(v, Morsel) else cookie_to_morsel(v)) for k, v in ItemsView(cookies2))
        else:
            morsels = ((c.key, c) for c in (c if isinstance(c, Morsel) else cookie_to_morsel(c) for c in cookies2))
        cookies1.update(morsels)
    return cookies1


def cookies_str_to_dict(cookies: str, /) -> dict[str, str]:
    return dict(cookie.split("=", 1) for cookie in CRE_COOKIE_SEP_split(cookies) if cookie)


def cookies_dict_to_str(cookies: Mapping[str, str], /) -> str:
    return "; ".join(f"{key}={cookies[key]}" for key in cookies)

