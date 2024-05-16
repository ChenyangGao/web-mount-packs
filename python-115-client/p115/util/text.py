#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "to_base64", "text_to_dict", "dict_to_text", "cookies_str_to_dict", "headers_str_to_dict", 
    "unicode_unescape", "extract_origin", "complete_base_url", "posix_glob_translate_iter", 
    "text_within", 
]

from base64 import b64encode
from collections.abc import Iterator
from codecs import decode
from fnmatch import translate as wildcard_translate
from functools import partial
from re import compile as re_compile, escape as re_escape, Pattern
from typing import AnyStr, Final, Optional
from urllib.parse import urlsplit, urlunsplit

from .path import splits


CRE_URL_SCHEME = re_compile(r"^(?i:[a-z][a-z0-9.+-]*)://")
REFIND_BRACKET: Final = re_compile("\[[^]]+\]").finditer
RESUB_DOT: Final = re_compile("((?:^|(?<=[^\\\\]))(?s:\\\\.)*)\\.").sub
RESUB_REMOVE_WRAP_BRACKET: Final = partial(re_compile("(?s:\\[(.[^]]*)(?<![?*])\\])").sub, "\\1")


def to_base64(s: bytes | str, /) -> str:
    if isinstance(s, str):
        s = bytes(s, "utf-8")
    return str(b64encode(s), "ascii")


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


def unicode_unescape(s: str, /) -> str:
    return decode(s, "unicode_escape")


def extract_origin(url: str, /) -> str:
    if url.startswith("://"):
        url = "http" + url
    elif CRE_URL_SCHEME.match(url) is None:
        url = "http://" + url
    urlp = urlsplit(url)
    scheme, netloc = urlp.scheme, urlp.netloc
    if not netloc:
        netloc = "localhost"
    return f"{scheme}://{netloc}"


def complete_base_url(url: str, /) -> str:
    if url.startswith("://"):
        url = "http" + url
    elif CRE_URL_SCHEME.match(url) is None:
        url = "http://" + url
    urlp = urlsplit(url)
    repl = {"query": "", "fragment": ""}
    if not urlp.netloc:
        repl["path"] = "localhost"
    return urlunsplit(urlp._replace(**repl)).rstrip("/")


def _glob_is_pat(part: str, /) -> bool:
    it = enumerate(part)
    try:
        for _, c in it:
            if c in ("?", "*"):
                return True
            elif c == "[":
                _, c2 = next(it)
                if c2 == "]":
                    continue
                i, c3 = next(it)
                if c3 == "]":
                    if c2 in ("?", "*"):
                        return True
                    continue
                if part.find("]", i + 1) > -1:
                    return True
        return False
    except StopIteration:
        return False


def _glob_replace_dots(pat: str, /) -> str:
    if "." not in pat:
        return pat
    def iter(pat):
        last = 0
        for m in REFIND_BRACKET(pat):
            start, stop = m.span()
            yield pat[last:start].replace(".", "[^/]")
            yield m[0]
            last = stop
        yield RESUB_DOT("\g<1>[^/]", pat[last:])
    return "".join(iter(pat))


def posix_glob_translate_iter(
    pattern: str, 
    /, 
    allow_escaped_slash: bool = False, 
) -> Iterator[tuple[str, str, str]]:
    last_type = ""
    if allow_escaped_slash:
        ls, _ = splits(pattern, parse_dots=False, do_unescape=False)
    else:
        ls = pattern.split("/")
    for part in ls:
        if not part:
            continue
        orig_part = ""
        if part == "*":
            pattern = "[^/]*"
            last_type = "star"
        elif len(part) >=2 and not part.strip("*"):
            if last_type == "dstar":
                continue
            pattern = "[^/]*(?:/[^/]*)*"
            last_type = "dstar"
        elif _glob_is_pat(part):
            pattern = _glob_replace_dots(wildcard_translate(part)[4:-3])
            last_type = "pat"
        else:
            orig_part = RESUB_REMOVE_WRAP_BRACKET(part)
            pattern = re_escape(orig_part)
            last_type = "orig"
        yield pattern, last_type, orig_part


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

