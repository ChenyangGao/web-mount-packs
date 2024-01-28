#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["get_download_url", "iterdir"]

from collections.abc import Callable, Iterator
from copy import copy
from datetime import datetime
from itertools import count
from json import load
from posixpath import join as joinpath
from re import compile as re_compile
from time import sleep
from typing import cast, Optional
from urllib.parse import urlsplit

from util.text import text_within
from util.urlopen import urlopen, download


ORIGIN = "https://lanzoui.com"
CRE_DOWNLOAD_search = re_compile(br'<iframe[^>]+?name="(?P<name>[^"]+)"[^>]+?src="(?P<link>/fn\?[^"]{64,})').search
CRE_SUBDIR_finditer = re_compile(br'(?:folderlink|mbxfolder)"[^>]*><a [^>]*?\bhref="/(?P<fid>[^"]+)"[^>]*>(?P<name>[^<]+)').finditer


def extract_payload(content: bytes, start: int = 0) -> Optional[dict]:
    "从包含 javascript 代码的文本中，提取请求参数"
    def __getitem__(key):
        match = re_compile(br"\b%s\s*=\s*([^;]+)" % key.encode("ascii")).search(content)
        if match is not None:
            try:
                return eval(match[1])
            except:
                pass
        return ""
    ns = type("", (), {"__getitem__": staticmethod(__getitem__)})()
    payload_text = text_within(content, re_compile(br'\sdata :'), b'}', start=start, with_end=True)
    if not payload_text:
        return None
    return eval(payload_text, None, ns)


def extract_single_item(content: bytes) -> tuple[str, dict]:
    idx = content.index(b"/ajaxm.php?")
    return (
        text_within(content, end=b"'", with_begin=True, start=idx).decode("ascii"), 
        cast(dict, extract_payload(content, start=idx)), 
    )


def get_single_item(
    id_or_url: str, 
    password: str = "", 
    origin: Optional[str] = None, 
) -> dict:
    if id_or_url.startswith(("http://", "https://")):
        url = id_or_url
    else:
        url = "%s/%s" % (origin or ORIGIN, id_or_url)
    content = urlopen(url).read()
    # NOTE: 这种情况意味着单文件分享
    if b"/ajaxm.php?" in content:
        link, payload = extract_single_item(content)
        if password:
            payload["p"] = password
    else:
        match = CRE_DOWNLOAD_search(content)
        if match is None:
            raise ValueError(f"can't find download link for: {id_or_url}")
        fid = match["name"].decode("ascii")
        link = match["link"].decode("ascii")
        content = urlopen(link, origin=origin).read()
        payload = extract_payload(content)
        link = "/ajaxm.php?file=%s" % fid
    return load(urlopen(link, data=payload, headers={"Referer": url, "User-agent": ""}, method="POST", origin=origin))


def get_download_url(
    id_or_url: str, 
    password: str = "", 
    origin: Optional[str] = None, 
) -> str:
    "获取下载链接"
    json = get_single_item(id_or_url, password, origin)
    return json["dom"] + "/file/" + json["url"]


def get_name_from_content_disposition(value):
    value = value.removeprefix("attachment; filename=")
    if value.startswith('"'):
        return value[1:-1]
    elif value.startswith(" "):
        return value[1:]
    return value


def attr_from_download_url(
    url: str, 
    origin: Optional[str] = None, 
) -> dict:
    resp = urlopen(url, headers={"Accept-language": "zh-CN"}, method="HEAD", origin=origin)
    headers = resp.headers
    last_modified = datetime.strptime(headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z")
    return {
        "filename": get_name_from_content_disposition(headers["Content-Disposition"]), 
        "size": int(headers["Content-Length"]), 
        "created_time": datetime.strptime(headers["Date"], "%a, %d %b %Y %H:%M:%S %Z"), 
        "modified_time": last_modified, 
        "access_time": last_modified, 
        "download_url": resp.url, 
    }


def iterdir(
    url: str, 
    password: str = "", 
    show_detail: bool = False, 
    for_download: bool = False, 
    predicate: Optional[Callable] = None, 
    files_only: Optional[bool] = None, 
    origin: Optional[str] = None, 
    relpath: str = "", 
) -> Iterator[dict]:
    "获取分享链接中的条目信息，迭代器"
    urlp = urlsplit(url)
    fid = urlp.path.strip("/")
    # 这种情况意味着单文件分享
    if fid.startswith("i"):
        if files_only != False:
            item = get_single_item(url, password, origin)
            name = item["inf"]
            attr = {
                "id": urlsplit(url).path.strip("/"), 
                "name": name, 
                "relpath": joinpath(relpath, name), 
                "isdir": False, 
                "download_url": item["dom"] + "/file/" + item["url"], 
            }
            if show_detail:
                attr.update(attr_from_download_url(attr["download_url"], origin=origin))
            try:
                if not predicate or predicate(attr):
                    yield attr
            except:
                pass
        return
    if origin is None:
        if urlp.scheme:
            origin = "%s://%s" % (urlp.scheme, urlp.netloc)
        else:
            origin = ORIGIN
    if files_only != False:
        api = "%s/filemoreajax.php" % origin
        content = urlopen(url, origin=origin).read()
        payload = extract_payload(content)
        if payload is None:
            raise ValueError("wrong url: %r" % url)
        payload["pwd"] = password
        for i in count(1):
            payload["pg"] = i
            data = load(urlopen(api, data=payload, method="POST", origin=origin))
            while data["zt"] == 4:
                sleep(1)
                data = load(urlopen(api, data=payload, method="POST", origin=origin))
            if data["zt"] != 1:
                raise ValueError(data)
            for item in data["text"]:
                name = item["name_all"]
                attr = {
                    "id": item["id"], 
                    "short_id": item["duan"], 
                    "name": name, 
                    "relpath": joinpath(relpath, name), 
                    "isdir": False, 
                    "icon": item["icon"], 
                }
                if show_detail:
                    attr.update(attr_from_download_url(get_download_url(attr["id"], origin)))
                elif for_download:
                    attr["download_url"] = get_download_url(attr["id"], origin)
                try:
                    if not predicate or predicate(attr):
                        yield attr
                except:
                    pass
            if len(data["text"]) < 50:
                break
    for match in CRE_SUBDIR_finditer(content):
        name = match["name"].decode("utf-8")
        attr = {
            "id": match["id"].decode("ascii"), 
            "name": name, 
            "relpath": joinpath(relpath, name), 
            "isdir": True, 
        }
        try:
            if files_only != True and (not predicate or predicate(attr)):
                yield attr
            else:
                continue
        except:
            continue
        yield from iterdir(
            attr["id"], 
            show_detail=show_detail, 
            predicate=predicate, 
            files_only=files_only, 
            origin=origin, 
            relpath=attr["relpath"], 
        )

