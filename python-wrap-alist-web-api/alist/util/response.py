#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["get_filename", "get_length", "get_range", "get_header", "is_chunked", "is_range_request"]

from mimetypes import guess_extension, guess_type
from posixpath import basename
from re import compile as re_compile
from typing import Optional
from urllib.parse import urlsplit, unquote


CRE_CONTENT_RANGE = re_compile(r"bytes\s+(?:\*|(?P<begin>[0-9]+)-(?P<end>[0-9]+))/(?:(?P<size>[0-9]+)|\*)")


def get_filename(response, /, default: str = "") -> str:
    get = response.headers.get
    hdr_cd = get("Content-Disposition") or get("content-disposition")
    if hdr_cd and hdr_cd.startswith("attachment; filename="):
        return hdr_cd[21:]
    urlp = urlsplit(unquote(response.url))
    filename = basename(urlp.path) or default
    if filename:
        if guess_type(filename)[0]:
            return filename
        hdr_ct = get("Content-Type") or get("content-type")
        if (idx := hdr_ct.find(";")) > -1:
            hdr_ct = hdr_ct[:idx]
        ext = hdr_ct and guess_extension(hdr_ct) or ""
        if ext and not filename.endswith(ext, 1):
            filename += ext
    return filename


def get_length(response, /) -> Optional[int]:
    get = response.headers.get
    hdr_cl = get("Content-Length") or get("content-length")
    if hdr_cl:
        return int(hdr_cl)
    rng = get_range(response)
    if rng:
        return rng[1] - rng[0] + 1
    return None


def get_range(response, /) -> Optional[tuple[int, int, int]]:
    get = response.headers.get
    hdr_cr = get("Content-Range") or get("content-range")
    if not hdr_cr:
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


def get_header(response, /, name) -> Optional[str]:
    get = response.headers.get
    return get(name.title()) or get(name.lower())


def is_chunked(response, /) -> bool:
    get = response.headers.get
    hdr_te = get("Transfer-Encoding") or get("transfer-encoding")
    return hdr_te == "chunked"


def is_range_request(response, /) -> bool:
    get = response.headers.get
    hdr_te = get("Accept-Ranges") or get("accept-ranges")
    return hdr_te == "bytes"

