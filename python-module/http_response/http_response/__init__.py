#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = [
    "headers_get", "get_filename", "get_content_length", "get_length", 
    "get_total_length", "get_range", "is_chunked", "is_range_request", 
]

from collections.abc import Callable, Container, Mapping
from mimetypes import guess_extension, guess_type
from posixpath import basename
from re import compile as re_compile
from typing import Final, Optional
from urllib.parse import parse_qsl, urlsplit, unquote


CRE_CONTENT_RANGE_fullmatch: Final = re_compile(r"bytes\s+(?:\*|(?P<begin>[0-9]+)-(?P<end>[0-9]+))/(?:(?P<size>[0-9]+)|\*)").fullmatch
CRE_HDR_CD_FNAME_search: Final = re_compile("(?<=filename=\")[^\"]+|(?<=filename=')[^']+|(?<=filename=)[^'\"][^;]*").search
CRE_HDR_CD_FNAME_STAR_search: Final = re_compile("(?<=filename\\*=)(?P<charset>[^']*)''(?P<name>[^;]+)").search


def headers_get(response, /, key, default=None, parse=None):
    if hasattr(response, "headers"):
        headers = response.headers
    else:
        headers = response
    try:
        val = headers[key]
    except KeyError:
        return default
    else:
        if parse is None:
            return val
        elif callable(parse):
            return parse(val)
        elif isinstance(parse, (bytes, str)):
            return val == parse
        elif isinstance(parse, Mapping):
            return headers_get(parse, val, default)
        elif isinstance(parse, Container):
            return val in parse
        return val


def get_filename(response, /, default: str = "") -> str:
    # NOTE: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition
    if hdr_cd := headers_get(response, "content-disposition"):
        if match := CRE_HDR_CD_FNAME_STAR_search(hdr_cd):
            return unquote(match["name"], match["charset"] or "utf-8")
        if match := CRE_HDR_CD_FNAME_search(hdr_cd):
            return match[0]
    url = response.url
    if not isinstance(url, (bytearray, bytes, str)):
        url = str(url)
    urlp = urlsplit(url)
    for key, val in parse_qsl(urlp.query):
        if val and key.lower() in ("filename", "file_name"):
            return unquote(val)
    filename = basename(unquote(urlp.path)) or default
    if filename:
        if guess_type(filename)[0]:
            return filename
        if hdr_ct := headers_get(response, "content-type"):
            if idx := hdr_ct.find(";") > -1:
                hdr_ct = hdr_ct[:idx]
            ext = hdr_ct and guess_extension(hdr_ct) or ""
            if ext and not filename.endswith(ext, 1):
                filename += ext
    return filename


def get_content_length(response, /) -> Optional[int]:
    if length := headers_get(response, "content-length"):
        return int(length)
    return None


def get_length(response, /) -> Optional[int]:
    if (length := get_content_length(response)) is not None:
        return length
    if rng := get_range(response):
        return rng[1] - rng[0] + 1
    return None


def get_total_length(response, /) -> Optional[int]:
    if rng := get_range(response):
        return rng[-1]
    return get_content_length(response)


def get_range(response, /) -> Optional[tuple[int, int, int]]:
    hdr_cr = headers_get(response, "content-range")
    if not hdr_cr:
        return None
    if match := CRE_CONTENT_RANGE_fullmatch(hdr_cr):
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
    return headers_get(response, "transfer-encoding", default=False, parse="chunked")


def is_range_request(response, /) -> bool:
    return bool(headers_get(response, "accept-ranges", parse="bytes")
                or headers_get(response, "content-range"))

