#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["get_files_config", "iterdir"]

from collections.abc import Callable, Iterator
from json import load
from posixpath import join as joinpath
from re import compile as re_compile
from typing import Final, Optional
from urllib.parse import urlparse, parse_qsl

try:
    from .util.urlopen import urlopen
except ImportError:
    from util.urlopen import urlopen # type: ignore


FILES_CONFIG_search: Final = re_compile(br"(?<=\bFilesConfig=)[^;]+").search


def get_files_config(url: str) -> dict:
    with urlopen(url, headers={}) as resp:
        return eval(FILES_CONFIG_search(resp.read())[0]) # type: ignore


def _iterdir(
    rid_or_url: str, 
    /, 
    params: dict = {}, 
    relpath: str = "", 
) -> Iterator[dict]:
    if rid_or_url.startswith(("http://", "https://")):
        url = rid_or_url
        urlp = urlparse(url)
        if urlp.hostname == "1drv.ms":
            url = urlopen(url, headers={}, method="HEAD").url
            urlp = urlparse(url)
        query_dict = dict(parse_qsl(urlp.query))
        resid = query_dict.get("resid") or query_dict["id"]
        dirver, id = resid.rsplit("!", maxsplit=1)
        authkey = query_dict.get("authkey", "")
        api = f"https://api.onedrive.com/v1.0/drives/{dirver}/items/{dirver}!{id}/children"
        params = {
            "$top": 100, 
            "orderby": "folder,fileSystemInfo/lastModifiedDateTime desc", 
            "$expand": "thumbnails,lenses,tags", 
            "select": "*,ocr,webDavUrl,sharepointIds,isRestricted,commentSettings,specialFolder,containingDrivePolicyScenarioViewpoint", 
            "ump": 1, 
            **params, 
            "authKey": authkey, 
        }
    else:
        dirver, id = rid_or_url.rsplit("!", maxsplit=1)
        api = f"https://api.onedrive.com/v1.0/drives/{dirver}/items/{dirver}!{id}/children"
    resp = load(urlopen(api, params=params, headers={}))
    for attr in resp["value"]:
        attr["isdir"] = "@content.downloadUrl" not in attr
        attr["relpath"] = joinpath(relpath, attr["name"])
        yield attr
    while (next_link := resp.get("@odata.nextLink")):
        resp = load(urlopen(next_link, headers={}))
        for attr in resp["value"]:
            attr["isdir"] = "@content.downloadUrl" in attr
            attr["relpath"] = joinpath(relpath, attr["name"])
            yield attr


def iterdir(
    rid_or_url: str, 
    /, 
    params: dict = {}, 
    topdown: bool = True, 
    min_depth: int = 0, 
    max_depth: int = 1, 
    predicate: Optional[Callable[[dict], bool]] = None, 
    relpath: str = "", 
) -> Iterator[dict]:
    if not max_depth:
        return
    if rid_or_url.startswith(("http://", "https://")):
        url = rid_or_url
        urlp = urlparse(url)
        if urlp.hostname == "1drv.ms":
            url = urlopen(url, headers={}, method="HEAD").url
            urlp = urlparse(url)
        query_dict = dict(parse_qsl(urlp.query))
        rid_or_url = query_dict.get("resid") or query_dict["id"]
        params = {**params, "authKey": query_dict.get("authkey", "")}
    if min_depth > 0:
        min_depth -= 1
    if max_depth > 0:
        max_depth -= 1
    yield_me = min_depth <= 0
    for attr in _iterdir(rid_or_url, params, relpath=relpath):
        if yield_me and predicate:
            pred = predicate(attr)
            if pred is None:
                continue
            yield_me = pred
        if yield_me and topdown:
            yield attr
        if attr["isdir"]:
            yield from iterdir(
                attr["id"], 
                params=params, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                predicate=predicate, 
                relpath=joinpath(relpath, attr["name"]), 
            )
        if yield_me and not topdown:
            yield attr

