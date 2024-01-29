#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["set_global_origin", "get_download_url", "iterdir"]

from collections.abc import Callable, Iterator
from datetime import datetime
from itertools import count
from json import load
from posixpath import basename, join as joinpath
from re import compile as re_compile, Match
from time import sleep
from typing import cast, Final, Optional
from urllib.parse import unquote, urlsplit

try:
    from .util.response import get_filename
    from .util.urlopen import urlopen
except ImportError:
    from util.response import get_filename # type: ignore
    from util.urlopen import urlopen # type: ignore


ORIGIN: str = "https://lanzoui.com"
CRE_PAYLOAD_search: Final = re_compile(br'(?<=\sdata :)(?s:.*?\})').search
CRE_DOWNLOAD_search: Final = re_compile(br'<iframe[^>]+?name="(?P<name>[^"]+)"[^>]+?src="(?P<link>/fn\?[^"]{64,})').search
CRE_SUBDIR_finditer: Final = re_compile(br'(?:folderlink|mbxfolder)"[^>]*><a [^>]*?\bhref="/(?P<fid>[^"]+)"[^>]*>(?P<name>[^<]+)').finditer
CRE_BEFORE_SQUOT_match : Final = re_compile(br"[^']*").match


def set_global_origin(origin: str):
    "设置全局变量 ORIGIN，它是各个函数省略 origin 参数时的默认值"
    global ORIGIN
    ORIGIN = origin


def extract_payload(
    content: bytes, 
    /, 
    start: int = 0, 
) -> Optional[dict]:
    "从包含 javascript 代码的文本中，提取请求参数"
    def __getitem__(key: str):
        matches = re_compile(br"\b%s\s*=\s*([^;]+)" % key.encode("ascii")).search(content)
        if matches is not None:
            try:
                return eval(matches[1])
            except:
                pass
        return ""
    ns = type("", (), {"__getitem__": staticmethod(__getitem__)})()
    payload_code = CRE_PAYLOAD_search(content, start)
    if payload_code is None:
        return None
    return eval(payload_code[0], None, ns)


def extract_single_link_payload(content: bytes) -> tuple[str, dict]:
    "提取单个文件获取信息所需的：请求链接 和 请求数据"
    idx = content.index(b"/ajaxm.php?")
    return (
        CRE_BEFORE_SQUOT_match(content, idx)[0].decode("ascii"), # type: ignore
        cast(dict, extract_payload(content, start=idx)), 
    )


def get_single_item(
    id_or_url: str, 
    password: str = "", 
    origin: Optional[str] = None, 
) -> dict:
    "获取文件信息"
    origin = origin or ORIGIN
    if id_or_url.startswith(("http://", "https://")):
        url = id_or_url
    else:
        url = "%s/%s" % (origin, id_or_url)
    content = urlopen(url, origin=origin).read()
    # NOTE: 这种情况意味着单文件分享
    if b"/ajaxm.php?" in content:
        try:
            link, payload = extract_single_link_payload(content)
        except TypeError as e:
            raise ValueError(f"invalid id or url: {id_or_url!r}")
        if password:
            payload["p"] = password
    else:
        match = CRE_DOWNLOAD_search(content)
        if match is None:
            raise ValueError(f"can't find download link for: {id_or_url}")
        fid = match["name"].decode("ascii")
        link = match["link"].decode("ascii")
        content = urlopen(link, origin=origin).read()
        payload = cast(dict, extract_payload(content))
        link = "/ajaxm.php?file=%s" % fid
    return load(urlopen(link, data=payload, headers={"Referer": url, "User-agent": ""}, method="POST", origin=origin))


def get_download_url(
    id_or_url: str, 
    password: str = "", 
    origin: Optional[str] = None, 
) -> str:
    "获取文件的下载链接"
    json = get_single_item(id_or_url, password, origin)
    return json["dom"] + "/file/" + json["url"]


def attr_from_download_url(
    url: str, 
    origin: Optional[str] = None, 
) -> dict:
    "请求下载链接，获取文件信息"
    resp = urlopen(url, headers={"Accept-language": "zh-CN"}, method="HEAD", origin=origin or ORIGIN)
    headers = resp.headers
    date = datetime.strptime(headers["date"], "%a, %d %b %Y %H:%M:%S %Z")
    if "last-modified" in headers:
        last_modified = datetime.strptime(headers["last-modified"], "%a, %d %b %Y %H:%M:%S %Z")
    else:
        last_modified = date
    return {
        "filename": get_filename(resp), 
        "size": int(headers["content-length"]), 
        "created_time": date, 
        "modified_time": last_modified, 
        "access_time": last_modified, 
        "download_url": resp.url, 
    }


def iterdir(
    id_or_url: str, 
    password: str = "", 
    predicate: Optional[Callable] = None, 
    files_only: Optional[bool] = None, 
    show_download: bool = False, 
    show_detail: bool = False, 
    relpath: str = "", 
    origin: Optional[str] = None, 
) -> Iterator[dict]:
    "获取分享链接中的条目信息，迭代器"
    if id_or_url.startswith(("http://", "https://")):
        urlp = urlsplit(id_or_url)
        fid = basename(unquote(urlp.path).rstrip("/"))
        if not origin and urlp.scheme:
            origin = "%s://%s" % (urlp.scheme, urlp.netloc)
    else:
        fid = id_or_url
    origin = origin or ORIGIN
    # 这种情况意味着单文件分享
    if fid.startswith("i"):
        if files_only != False:
            item = get_single_item(fid, password, origin)
            name = item["inf"]
            attr = {
                "id": fid, 
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
    if files_only != False:
        api = "%s/filemoreajax.php" % origin
        content = urlopen(id_or_url, origin=origin).read()
        payload = extract_payload(content)
        if payload is None:
            raise ValueError("wrong id or url: %r" % id_or_url)
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
                elif show_download:
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

