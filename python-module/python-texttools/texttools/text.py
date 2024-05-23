#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "unicode_escape", "unicode_unescape", "replace", "replace_index", "translate", 
    "text_within", "text_to_dict", "dict_to_text", 
]

from collections.abc import Iterable, Iterator, Mapping
from codecs import decode, encode
from itertools import chain, repeat
from re import compile as re_compile, escape as re_escape, Pattern
from typing import AnyStr


def unicode_escape(s: str, /) -> str:
    return str(encode(s, "unicode_escape"), "ascii")


def unicode_unescape(s: str, /) -> str:
    return decode(s, "unicode_escape")


def replace(
    s: AnyStr, 
    olds: AnyStr | Iterable[AnyStr] | Pattern[AnyStr], 
    new: None | AnyStr = None, 
    /, 
    count: int = -1, 
) -> AnyStr:
    if count == 0:
        return s
    if new is None:
        new = "" if isinstance(s, str) else b""
    if isinstance(olds, (bytes, str)):
        return s.replace(olds, new, count)
    def repl(m) -> AnyStr:
        return new
    if isinstance(olds, Pattern):
        pat = olds
    else:
        sep: AnyStr = "|" if isinstance(s, str) else b"|"
        pat = re_compile(sep.join(map(re_escape, olds)))
    return pat.sub(repl, s, count)


def replace_index(
    s: AnyStr, 
    olds: AnyStr | Iterable[AnyStr] | Pattern[AnyStr], 
    new: None | AnyStr = None, 
    /, 
    index: int = 0, 
    count: int = -1, 
) -> AnyStr:
    if count == 0:
        return s
    if new is None:
        new = "" if isinstance(s, str) else b""
    start = index
    index = -1
    if count < 0:
        def repl(m):
            nonlocal index
            index += 1
            if index >= start:
                return new
            else:
                return m[0]
    else:
        stop = start + count
        def repl(m):
            nonlocal index
            index += 1
            if start <= index < stop:
                return new
            else:
                return m[0]
    if isinstance(olds, Pattern):
        pat = olds
    elif isinstance(olds, (bytes, str)):
        pat = re_compile(re_escape(olds))
    else:
        sep: AnyStr = "|" if isinstance(s, str) else b"|"
        pat = re_compile(sep.join(map(re_escape, olds)))
    return pat.sub(repl, s, count)


def text_within(
    text: AnyStr, 
    prefix: None | AnyStr | Pattern[AnyStr] = None, 
    suffix: None | AnyStr | Pattern[AnyStr] = None, 
    start: int = 0, 
    greedy: bool = False, 
    with_prefix: bool = False, 
    with_suffix: bool = False, 
) -> AnyStr:
    empty = text[:0]
    if not prefix:
        start0 = start
    elif isinstance(prefix, (bytes, bytearray, str)):
        start = text.find(prefix, start)
        if start == -1:
            return empty
        start0 = start + len(prefix)
        if not with_prefix:
            start = start0
    else:
        match = prefix.search(text, start)
        if match is None:
            return empty
        start0 = match.end()
        start = match.start() if with_prefix else match.end()
    if not suffix:
        return text[start:]
    elif isinstance(suffix, (bytes, bytearray, str)):
        if greedy:
            stop = text.rfind(suffix, start0)
        else:
            stop = text.find(suffix, start0)
        if stop == -1:
            return empty
        if with_suffix:
            stop += len(suffix)
    else:
        if greedy:
            match = None
            for match in suffix.finditer(text, start0):
                pass
        else:
            match = suffix.search(text, start0)
        if match is None:
            return empty
        stop = match.end() if with_suffix else match.start()
    return text[start:stop]


def translate(
    s: str, 
    from_str: str | Mapping, 
    to_str: None | str = None, 
    /, 
) -> str:
    if isinstance(from_str, Mapping):
        return str.translate(s, from_str)
    ts: Iterator[None | int]
    if to_str is None:
        ts = repeat(None)
    else:
        ts = chain(map(ord, to_str), repeat(None))
    transtab = dict(zip(map(ord, from_str), ts))
    return str.translate(s, transtab)


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

