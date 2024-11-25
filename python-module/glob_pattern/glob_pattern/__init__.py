#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["translate_iter", "translate"]

from collections.abc import Iterator
from fnmatch import translate as wildcard_translate
from functools import partial
from re import compile as re_compile, escape as re_escape
from typing import Final

from posixpatht import splits


REFIND_BRACKET: Final = re_compile(r"\[[^]]+\]").finditer
RESUB_DOT: Final = re_compile(r"((?:^|(?<=[^\\]))(?s:\\.)*)\.").sub
RESUB_REMOVE_WRAP_BRACKET: Final = partial(re_compile(r"(?s:\[(.[^]]*)(?<![?*])\])").sub, r"\1")


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
        yield RESUB_DOT(r"\g<1>[^/]", pat[last:])
    return "".join(iter(pat))


def translate_iter(
    pattern: str, 
    /, 
    allow_escaped_slash: bool = False, 
) -> Iterator[tuple[str, str, str]]:
    last_type = ""
    if allow_escaped_slash:
        ls, _ = splits(pattern, parse_dots=False, unescape=None)
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


def translate(
    pattern: str, 
    /, 
    allow_escaped_slash: bool = False, 
) -> str:
    return "/".join(part for part, *_ in translate_iter(pattern, allow_escaped_slash))

# TODO: support for ntpath, etc.
