#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "text_to_dict", "dict_to_text", "cookies_str_to_dict", "headers_str_to_dict", "text_within", 
]

from re import compile as re_compile, escape as re_escape, Pattern
from typing import AnyStr, Optional


def text_to_dict(
    s: AnyStr, 
    /, 
    kv_sep: AnyStr | Pattern[AnyStr], 
    entry_sep: AnyStr | Pattern[AnyStr], 
) -> dict[AnyStr, AnyStr]:
    if isinstance(kv_sep, (str, bytes, bytearray)):
        search_kv_sep = re_compile(re_escape(kv_sep)).search
    else:
        search_kv_sep = kv_sep.search
    if isinstance(entry_sep, (str, bytes, bytearray)):
        search_entry_sep = re_compile(re_escape(entry_sep)).search
    else:
        search_entry_sep = entry_sep.search
    d: dict[AnyStr, AnyStr] = {}
    start = 0
    length = len(s)
    while start < length:
        match = search_kv_sep(s, start)
        if match is None:
            break
        l, r = match.span()
        key = s[start:l]
        match = search_entry_sep(s, r)
        if match is None:
            d[key] = s[r:]
            break
        l, start = match.span()
        d[key] = s[r:l]
    return d


def dict_to_text(
    d: dict[AnyStr, AnyStr], 
    /, 
    kv_sep: AnyStr, 
    entry_sep: AnyStr, 
) -> AnyStr:
    return entry_sep.join(k+kv_sep+v for k, v in d.items())


def cookies_str_to_dict(
    cookies: str, 
    /, 
    kv_sep: str | Pattern[str] = re_compile(r"\s*=\s*"), 
    entry_sep: str | Pattern[str] = re_compile(r"\s*;\s*"), 
) -> dict[str, str]:
    return text_to_dict(cookies.strip(), kv_sep, entry_sep)


def headers_str_to_dict(
    headers: str, 
    /, 
    kv_sep: str | Pattern[str] = re_compile(r":\s+"), 
    entry_sep: str | Pattern[str] = re_compile("\n+"), 
) -> dict[str, str]:
    return text_to_dict(headers.strip(), kv_sep, entry_sep)


def text_within(
    text: AnyStr, 
    begin: Optional[AnyStr | Pattern[AnyStr]] = None, 
    end: Optional[AnyStr | Pattern[AnyStr]] = None, 
    start: int = 0, 
    greedy: bool = False, 
    with_begin: bool = False, 
    with_end: bool = False, 
) -> AnyStr:
    empty = text[:0]
    if not begin:
        start0 = start
    elif isinstance(begin, (bytes, bytearray, str)):
        start = text.find(begin, start)
        if start == -1:
            return empty
        start0 = start + len(begin)
        if not with_begin:
            start = start0
    else:
        match = begin.search(text, start)
        if match is None:
            return empty
        start0 = match.end()
        start = match.start() if with_begin else match.end()
    if not end:
        return text[start:]
    elif isinstance(end, (bytes, bytearray, str)):
        if greedy:
            stop = text.rfind(end, start0)
        else:
            stop = text.find(end, start0)
        if stop == -1:
            return empty
        if with_end:
            stop += len(end)
    else:
        if greedy:
            match = None
            for match in end.finditer(text, start0):
                pass
        else:
            match = end.search(text, start0)
        if match is None:
            return empty
        stop = match.end() if with_end else match.start()
    return text[start:stop]

