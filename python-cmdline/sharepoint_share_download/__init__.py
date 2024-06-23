#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["read_context", "iterdir"]

from collections.abc import Callable, Iterator
from json import loads
from posixpath import join as joinpath
from re import compile as re_compile
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

try:
    from urllib3_request import request
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "urllib3_request"], check=True)
    from urllib3_request import request


CRE_CONTEXT_INFO_search = re_compile(b'(?<=var _spPageContextInfo=)\{.*?\}(?=;)').search


def read_context(url: str) -> dict:
    with request(url, redirect=False, preload_content=False) as resp:
        durl = resp.headers["location"]
        cookie = resp.headers["Set-Cookie"]
    headers = {"Cookie": cookie}
    with request(durl, headers=headers) as resp:
        match = CRE_CONTEXT_INFO_search(resp.data)
        if match is None:
            raise ValueError(f"wrong url: {url!r}")
        info = loads(match[0])
    list_url = info["listUrl"]
    urlp = urlsplit(durl)
    origin = f"{urlp.scheme}://{urlp.netloc}"
    base_url = f"{origin}{list_url.rsplit('/', 1)[0]}"
    return {
        "url": durl, 
        "headers": headers, 
        "origin": origin, 
        "base_url": base_url, 
        "list_url": list_url, 
        "root": dict(parse_qsl(urlp.query))["id"], 
        "list_api": f"{base_url}/_api/web/GetListUsingPath(DecodedUrl=@a1)/RenderListDataAsStream", 
        "download_api": urljoin(urlunsplit(urlp._replace(query="")), "download.aspx"), 
        "info": info, 
    }


def _iterdir(
    context: dict, 
    dirname: str = "", 
) -> Iterator[dict]:
    headers = context["headers"]
    list_api = context["list_api"]
    download_api = context["download_api"]
    root = context["root"]
    relpath_start = len(root) + 1
    dirname = dirname or root
    params = {
        "RootFolder": dirname, 
        "TryNewExperienceSingle": "TRUE", 
    }
    a1 = "@a1=" + quote(repr(context["list_url"]))
    url = f"{list_api}?{urlencode(params)}&{a1}"
    while True:
        resp = request(url, "POST", headers=headers).json()
        for item in resp["Row"]:
            name = item["name"] = item["FileLeafRef"]
            path = item["path"] = joinpath(dirname, name)
            item["relpath"] = path[relpath_start:]
            item["isdir"] = item["FSObjType"] == "1"
            item["download_url"] = f"{download_api}?SourceUrl={quote(path)}"
            item["headers"] = headers
            yield item
        if "NextHref" not in resp:
            break
        url = f"{list_api}{resp['NextHref']}&{a1}"


def iterdir(
    url: str, 
    dirname: str = "", 
    context: None | dict = None, 
    topdown: bool = True, 
    min_depth: int = 0, 
    max_depth: int = 1, 
    predicate: None | Callable[[dict], bool] = None, 
) -> Iterator[dict]:
    if not max_depth:
        return
    if context is None:
        context = read_context(url)
    if min_depth > 0:
        min_depth -= 1
    if max_depth > 0:
        max_depth -= 1
    yield_me = min_depth <= 0
    for attr in _iterdir(context, joinpath(context["root"], dirname)):
        if yield_me and predicate:
            pred = predicate(attr)
            if pred is None:
                continue
            yield_me = pred
        if yield_me and topdown:
            yield attr
        if attr["isdir"]:
            yield from iterdir(
                url, 
                attr["relpath"], 
                context=context, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
            )
        if yield_me and not topdown:
            yield attr

