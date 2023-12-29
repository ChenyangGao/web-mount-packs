#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "get_header", "get_filename", "get_content_length", "get_length", "get_total_length", "get_range", 
    "is_chunked", "is_range_request", 
]

from mimetypes import guess_extension, guess_type
from posixpath import basename
from re import compile as re_compile
from typing import Optional
from urllib.parse import urlsplit, unquote


CRE_CONTENT_RANGE = re_compile(r"bytes\s+(?:\*|(?P<begin>[0-9]+)-(?P<end>[0-9]+))/(?:(?P<size>[0-9]+)|\*)")


def get_header(response, /, name: str) -> Optional[str]:
    get = response.headers.get
    return get(name.title()) or get(name.lower())


def get_filename(response, /, default: str = "") -> str:
    hdr_cd = get_header(response, "Content-Disposition")
    if hdr_cd and hdr_cd.startswith("attachment; filename="):
        return unquote(hdr_cd.rstrip()[22:-1])
    urlp = urlsplit(unquote(response.url))
    filename = basename(urlp.path) or default
    if filename:
        if guess_type(filename)[0]:
            return filename
        hdr_ct = get_header(response, "Content-Type")
        if hdr_ct and (idx := hdr_ct.find(";")) > -1:
            hdr_ct = hdr_ct[:idx]
        ext = hdr_ct and guess_extension(hdr_ct) or ""
        if ext and not filename.endswith(ext, 1):
            filename += ext
    return filename


def get_content_length(response, /) -> Optional[int]:
    length = get_header(response, "Content-Length")
    if length:
        return int(length)
    return None


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
    hdr_cr = get_header(response, "Content-Range")
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


def is_chunked(response, /) -> bool:
    return get_header(response, "Transfer-Encoding") == "chunked"


def is_range_request(response, /) -> bool:
    return get_header(response, "Accept-Ranges") == "bytes"

