#!/usr/bin/env python3
# encoding: utf-8


__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["escape", "translate", "parse", "read_file", "read_str", "predicate"]

from fnmatch import translate as wildcard_translate
from glob import escape
from mimetypes import guess_type
from operator import methodcaller
from os import PathLike
from re import compile as re_compile, escape as re_escape, IGNORECASE
from typing import Callable, Final, Iterable, Optional, TextIO

from .text import posix_glob_translate_iter


CRE_PAT_IN_STR: Final = re_compile(r"[^\\ ]*(?:\\(?s:.)[^\\ ]*)*")


def translate(pattern: str, /) -> str:
    s = "".join(t[0] for t in posix_glob_translate_iter(pattern))
    use_basename = "/" not in pattern[:-1]
    s = (("(?:^|/)" if use_basename else "^/?")) + s
    if pattern.endswith("/"):
        return s + ("/" if use_basename else "/$")
    elif use_basename:
        return s + "(?:/|$)"
    else:
        return s + "/?$"


def extended_pattern_translate(pattern: str, /) -> str:
    if len(pattern) <= 1:
        return ""
    first, rest = pattern[0], pattern[1:]
    match first:
        case "=":
            return f"^{re_escape(rest)}$"
        case "^":
            return f"^{re_escape(rest)}"
        case "$":
            return f"{re_escape(rest)}$"
        case ":":
            return re_escape(rest)
        case ";":
            return f"(?:^|(?<=\s)){re_escape(rest)}(?:$|(?=\s))"
        case ",":
            return f"(?:^|(?<=,)){re_escape(rest)}(?:$|(?=,))"
        case "<":
            return f"\\b{re_escape(rest)}"
        case ">":
            return f"{re_escape(rest)}\\b"
        case "|":
            return f"\\b{re_escape(rest)}\\b"
        case "~":
            return rest
        case "-":
            return f"^{rest}$"
        case "%":
            return f"^{wildcard_translate(rest)}"
        case _:
            return f"^{re_escape(pattern)}$"


def parse(
    patterns: Iterable[str], 
    /, 
    ignore_case: bool = False, 
    check_mimetype: bool = False, 
) -> Optional[Callable[[str], bool]]:
    shows: list[str] = []
    show_all: bool = False
    ignores: list[str] = []
    ignore_all: bool = False
    if check_mimetype:
        mimetype_shows: list[str] = []
        mimetype_ignores: list[str] = []
    for pattern in patterns:
        if not pattern:
            continue
        if pattern.startswith("\\"):
            if ignore_all:
                continue
            pattern = pattern[1:]
            if pattern:
                if pattern == "*":
                    ignore_all = True
                else:
                    ignores.append(pattern)
        elif check_mimetype and pattern.removeprefix("!").startswith(
            ("=", "^", "$", ":", ";", ",", "<", ">", "|", "~", "-", "%")
        ):
            pat = extended_pattern_translate(pattern.removeprefix("!"))
            if pat:
                if pattern.startswith("!"):
                    mimetype_shows.append(pat)
                else:
                    mimetype_ignores.append(pat)
        elif pattern.startswith("!"):
            if show_all:
                continue
            pattern = pattern[1:]
            if pattern:
                if pattern == "*":
                    show_all = True
                else:
                    shows.append(pattern)
        else:
            if ignore_all:
                continue
            if pattern == "*":
                ignore_all = True
            else:
                ignores.append(pattern)
    if show_all:
        return None
    flags = IGNORECASE if ignore_case else 0
    preds: list[Callable] = []
    ignore_preds: list[Callable] = []
    if check_mimetype:
        if mimetype_shows:
            show_mime_search = re_compile("|".join(mimetype_shows), flags).search
            def predicate(path: str, /) -> bool:
                if path.endswith("/"):
                    return True
                mime = guess_type(path)[0] or "application/octet-stream"
                return show_mime_search(mime) is None
            preds.append(predicate)
        if mimetype_ignores:
            ignore_mime_search = re_compile("|".join(mimetype_ignores), flags).search
            def predicate(path: str, /) -> bool:
                if path.endswith("/"):
                    return False
                mime = guess_type(path)[0] or "application/octet-stream"
                return ignore_mime_search(mime) is not None
            ignore_preds.append(predicate)
    if shows:
        show = re_compile("|".join(map(translate, shows)), flags).search
        preds.append(lambda path, /: show(path) is None)
    if ignore_all:
        ignore_preds.append(lambda _: True)
    elif ignores:
        ignore = re_compile("|".join(map(translate, ignores)), flags).search
        ignore_preds.append(lambda path, /: ignore(path) is not None)
    if ignore_preds:
        preds.append(lambda path: any(p(path) for p in ignore_preds))
    if not preds:
        return None
    elif len(preds) == 1:
        return preds[0]
    return lambda path: all(p(path) for p in preds)


def read_file(file: bytes | str | PathLike | TextIO, /) -> list[str]:
    if isinstance(file, (bytes, str, PathLike)):
        file = open(file, encoding="utf-8")
    return [p for l in file if not l.startswith("#") and (p := l.removesuffix("\n"))]


def read_str(s: str, /) -> list[str]:
    return [p.replace(r"\ ", " ") for p in CRE_PAT_IN_STR.findall(s) if p]


def predicate(
    pats: str | Iterable[str], 
    path: str, 
    ignore_case: bool = False, 
    check_mimetype: bool = False, 
) -> bool:
    """
    Description:
        See: https://git-scm.com/docs/gitignore#_pattern_format

    Examples::
        # test str cases
        >>> predicate("hello.*", "hello.py")
        True
        >>> predicate("hello.*", "foo/hello.py")
        True
        >>> predicate("/hello.*", "hello.py")
        True
        >>> predicate("!/hello.*", "foo/hello.py")
        True
        >>> predicate("!foo/", "foo")
        True
        >>> predicate("foo/", "foo/")
        True
        >>> predicate("foo/", "bar/foo/")
        True
        >>> predicate("!foo/", "bar/foo")
        True
        >>> predicate("foo/", "bar/foo/baz")
        True
        >>> predicate("/foo/", "foo/")
        True
        >>> predicate("!/foo/", "bar/foo/")
        True
        >>> predicate("foo/*", "foo/hello.py")
        True
        >>> predicate("!foo/*", "bar/foo/hello.py")
        True
        >>> predicate("foo/**/bar/hello.py", "foo/bar/hello.py")
        True
        >>> predicate("foo/**/bar/hello.py", "foo/fop/foq/bar/hello.py")
        True
        >>> predicate("h?llo.py", "hello.py")
        True
        >>> predicate("h[a-g]llo.py", "hello.py")
        True
        >>> not predicate("h[!a-g]llo.py", "hello.py")
        True
        >>> predicate("!h[!a-g]llo.py", "hello.py")
        True
        >>> not predicate("!hello.py", "hello.py")
        True
    """
    if isinstance(pats, str):
        pats = pats,
    predicate = parse(pats, ignore_case=ignore_case, check_mimetype=check_mimetype)
    if predicate is None:
        return False
    return predicate(path)


if __name__ == "__main__":
    import doctest
    doctest.testmod()

