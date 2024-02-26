#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "get_filename", "get_content_length", "get_length", "get_total_length", "get_range", 
    "is_chunked", "is_range_request", 
]

from mimetypes import guess_extension, guess_type
from posixpath import basename
from re import compile as re_compile
from typing import Optional
from urllib.parse import urlsplit, unquote


CRE_CONTENT_RANGE = re_compile(r"bytes\s+(?:\*|(?P<begin>[0-9]+)-(?P<end>[0-9]+))/(?:(?P<size>[0-9]+)|\*)")


def get_filename(response, /, default: str = "") -> str:
    try:
        hdr_cd = response.headers["content-disposition"]
    except KeyError:
        hdr_cd = None
    if hdr_cd and hdr_cd.startswith("attachment; filename="):
        filename = hdr_cd[21:]
        if filename.startswith(("'", '"')):
            filename = filename[1:-1]
        elif filename.startswith(" "):
            filename = filename[1:]
        return unquote(filename)
    urlp = urlsplit(response.url)
    filename = basename(unquote(urlp.path)) or default
    if filename:
        if guess_type(filename)[0]:
            return filename
        try:
            hdr_ct = response.headers["content-type"]
        except KeyError:
            hdr_ct = None
        if hdr_ct and (idx := hdr_ct.find(";")) > -1:
            hdr_ct = hdr_ct[:idx]
        ext = hdr_ct and guess_extension(hdr_ct) or ""
        if ext and not filename.endswith(ext, 1):
            filename += ext
    return filename


def get_content_length(response, /) -> Optional[int]:
    try:
        length = response.headers["content-length"]
        if not length:
            return None
    except KeyError:
        return None
    return int(length)


def get_length(response, /) -> Optional[int]:
    if (length := get_content_length(response)) is not None:
        return length
    rng = get_range(response)
    if rng:
        return rng[1] - rng[0] + 1
    return None


def get_total_length(response, /) -> Optional[int]:
    rng = get_range(response)
    if rng:
        return rng[-1]
    return get_content_length(response)


def get_range(response, /) -> Optional[tuple[int, int, int]]:
    try:
        hdr_cr = response.headers["content-range"]
        if not hdr_cr:
            return None
    except KeyError:
        return None
    match = CRE_CONTENT_RANGE.fullmatch(hdr_cr)
    if match is None:
        return None
    begin, end, size = match.groups()
    if begin:
        begin = int(begin)
        end = int(end)
        if size:
            size = int(size)
        else:
            size = end + 1
        return begin, end, size
    elif size:
        size = int(size)
        if size == 0:
            return 0, 0, 0
        return 0, size - 1, size
    return None


def is_chunked(response, /) -> bool:
    try:
        return response.headers["transfer-encoding"] == "chunked"
    except KeyError:
        return False


def is_range_request(response, /) -> bool:
    headers = response.headers
    try:
        return "accept-ranges" in headers and headers["accept-ranges"] == "bytes" or headers["content-range"]
    except KeyError:
        return False

