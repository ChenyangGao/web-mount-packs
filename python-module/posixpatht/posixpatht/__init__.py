#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__all__ = [
    "altsep", "curdir", "extsep", "pardir", "pathsep", "sep", "abspath", "basename", "commonpath", 
    "commonpatht", "commonprefix", "dirname", "isabs", "iter_split", "join", "joinpath", "joins", 
    "normcase", "normpath", "normpatht", "split", "splitdrive", "splitext", "splits", "realpath", 
    "relpath", "escape", "unescape", "path_is_dir_form", 
]

from collections.abc import Callable, Iterable, Iterator, Sequence
from functools import partial
from posixpath import altsep, curdir, extsep, pardir, pathsep, sep, commonprefix, normcase, splitdrive
from re import compile as re_compile, Match
from typing import cast, Final


CRE_DIR_END_search: Final = re_compile(r"(?P<bss>\\*)/\.{0,2}$").search
CRE_PART_finditer: Final = re_compile(r"[^\\/]*(?:\\(?s:.)[^\\/]*)*").finditer


def path_is_dir_form(
    path: str, 
    /, 
    slash_escaped: bool = True, 
) -> bool:
    if path in ("/", "", ".", ".."):
        return True
    if slash_escaped:
        match = CRE_DIR_END_search(path)
        return match is not None and len(match["bss"]) % 2 == 0
    else:
        return path.endswith(("/", "/.", "/.."))


def escape(name: str, /, parse_dots: bool = True) -> str:
    if parse_dots and name in (".", ".."):
        return "\\" + name
    else:
        return name.replace("\\", r"\\").replace("/", r"\/")


def unescape(name: str, /, parse_dots: bool = True) -> str:
    if parse_dots and name in (r"\.", r"\.."):
        name = name[1:]
    return name.replace(r"\/", "/").replace(r"\\", "\\")


def abspath(
    path: str, 
    /, 
    dirname: str = "/", 
) -> str:
    return joinpath(dirname, path)


def basename(
    path: str, 
    /, 
    unescape: None | Callable[[str], str] = unescape, 
    parse_dots: bool = True, 
    slash_escaped: bool = True, 
) -> str:
    return split(
        path, 
        unescape=unescape, 
        parse_dots=parse_dots, 
        slash_escaped=slash_escaped, 
    )[1]


def commonpath(
    pathit: Iterable[str], 
    /, 
    slash_escaped: bool = True, 
) -> str:
    if isinstance(pathit, Sequence):
        paths = pathit
    else:
        paths = tuple(pathit)
    prefix = commonprefix(paths)
    if prefix in ("", "/") or prefix.endswith("/") and path_is_dir_form(prefix, slash_escaped):
        return prefix
    prefix_with_slash = prefix + "/"
    if all(p == prefix or p.startswith(prefix_with_slash) for p in paths):
        return prefix
    return dirname(prefix, parse_dots=False, slash_escaped=slash_escaped)


def commonpatht(
    pathtit: Iterable[Sequence[str]], 
    /, 
) -> list[str]:
    parts: list[str] = []
    add_part = parts.append
    for part, *t_part in zip(*pathtit):
        if any(p != part for p in t_part):
            break
        add_part(part)
    return parts


def dirname(
    path: str, 
    /, 
    parse_dots: bool = True, 
    slash_escaped: bool = True, 
) -> str:
    return split(
        path, 
        unescape=None, 
        parse_dots=parse_dots, 
        slash_escaped=slash_escaped, 
    )[0]


def isabs(path: str, /) -> bool:
    return path.startswith("/")


def iter_split(
    path: str, 
    /, 
    unescape: None | Callable[[str], str] = unescape, 
    parse_dots: bool = True, 
    slash_escaped: bool = True, 
) -> Iterator[tuple[str, str]]:
    if unescape is globals()["unescape"]:
        unescape = partial(unescape, parse_dots=parse_dots) # type: ignore
    skip = 0
    if slash_escaped:
        matches = tuple(CRE_PART_finditer(path))
        for m in reversed(matches):
            p = m[0]
            if not p:
                continue
            if parse_dots:
                if p == ".":
                    continue
                elif p == "..":
                    skip += 1
                    continue
            if skip:
                skip -= 1
                continue
            if unescape is None:
                name = p
            else:
                name = unescape(p)
            index = m.start()
            yield path[:index - 1 if index > 1 else index], name
    else:
        rfind = path.rfind
        stop = len(path)
        while (index := rfind("/", 0, stop)) > -1:
            p = path[index+1:stop]
            if not p:
                continue
            if parse_dots:
                if p == ".":
                    continue
                elif p == "..":
                    skip += 1
                    continue
            if skip:
                skip -= 1
                continue
            if unescape is None:
                name = p
            else:
                name = unescape(p)
            yield path[:index or 1], name
            stop = index


def join(
    path: str, 
    /, 
    *parts: str, 
    escape: None | Callable[[str], str] = escape, 
) -> str:
    if not parts:
        return path
    if not path.endswith("/"):
        path += "/"
    if escape is None:
        parts_: Iterable[str] = parts
    else:
        parts_ = map(escape, parts)
    return path + "/".join(p for p in parts_ if p)


def joinpath(
    dirname: str, 
    /, 
    *paths: str, 
    slash_escaped: bool = True, 
) -> str:
    if not paths:
        return dirname
    path = ""
    for dirname in reversed((dirname, *paths)):
        if not dirname:
            continue
        if not path:
            path = dirname
        elif dirname == "/":
            return dirname + path
        else:
            if not (dirname.endswith("/") and path_is_dir_form(dirname, slash_escaped)):
                dirname += "/"
            path = dirname + path
        if path.startswith("/"):
            break
    return path


def joins(
    patht: Sequence[str], 
    /, 
    parents: int = 0, 
    escape: None | Callable[[str], str] = escape, 
) -> str:
    if parents < 0:
        parents = 0
    if not patht:
        if parents:
            return "/".join(("..",) * parents)
        return ""
    if escape is None:
        path = "/".join(p for p in patht if p)
    else:
        path = "/".join(escape(p) for p in patht if p)
    if not patht[0]:
        path = "/" + path
    elif parents:
        path = "".join(("../",) * parents) + path
    return path


def normpath(
    path: str, 
    /, 
    parse_dots: bool = True, 
    slash_escaped: bool = True, 
) -> str:
    parts, parents = splits(
        path, 
        unescape=None, 
        parse_dots=parse_dots, 
        slash_escaped=slash_escaped, 
    )
    return joins(parts, parents, escape=None)


def normpatht(
    patht: Sequence[str], 
    /, 
) -> list[str]:
    return [patht[0], *filter(None, patht)]


def split(
    path: str, 
    /, 
    unescape: None | Callable[[str], str] = unescape, 
    parse_dots: bool = True, 
    slash_escaped: bool = True, 
) -> tuple[str, str]:
    if not path:
        return "", ""
    elif not path.strip("/"):
        return "/", ""
    return next(iter_split(
        path, 
        unescape=unescape, 
        parse_dots=parse_dots, 
        slash_escaped=slash_escaped, 
    ))


def splitext(
    path: str, 
    /, 
    slash_escaped: bool = True, 
) -> tuple[str, str]:
    if path_is_dir_form(path, slash_escaped):
        return path, ""
    if slash_escaped:
        start = 0
        for m in CRE_PART_finditer(path):
            if m[0]:
                start = m.start()
    else:
        start = path.rfind("/") + 1
    if start == len(path):
        return path, ""
    index = path.rfind(".", start)
    if index == -1 or not path[start:index].strip("."):
        return path, ""
    return path[:index], path[index:]


def splits(
    path: str, 
    /, 
    unescape: None | Callable[[str], str] = unescape, 
    parse_dots: bool = True, 
    slash_escaped: bool = True, 
) -> tuple[list[str], int]:
    if unescape is globals()["unescape"]:
        unescape = partial(unescape, parse_dots=parse_dots) # type: ignore
    parts: list[str] = []
    add_part = parts.append
    is_absolute = path.startswith("/")
    if is_absolute:
        add_part("")
    if slash_escaped:
        part_it = (m[0].replace(r"\/", "/") for m in CRE_PART_finditer(path) if m[0])
    else:
        part_it = (p for p in path.split("/") if p)
    parents = 0
    for p in part_it:
        if p == "." and parse_dots:
            pass
        elif p == ".." and parse_dots:
            if is_absolute:
                if len(parts) > 1:
                    parts.pop()
            elif parts:
                parts.pop()
            else:
                parents += 1
        elif unescape is None:
            add_part(p)
        else:
            add_part(unescape(p))
    return parts, parents


realpath = abspath


def relpath(
    path: str, 
    /, 
    start: None | str = None, 
    dirname: str = "/", 
    parse_dots: bool = True, 
    slash_escaped: bool = True, 
) -> str:
    if not start:
        return path
    patht, parents = splits(path, unescape=None, parse_dots=parse_dots, slash_escaped=slash_escaped)
    start_patht, start_parents = splits(start, unescape=None, parse_dots=parse_dots, slash_escaped=slash_escaped)
    dirname_patht, _ = splits("/" + dirname, unescape=None, parse_dots=parse_dots, slash_escaped=slash_escaped)
    if path.startswith("/") ^ start.startswith("/"):
        if path.startswith("/"):
            start_parents = 0
            start_patht[:0] = dirname_patht[:-parents] if parents else dirname_patht
        else:
            parents = 0
            patht[:0] = dirname_patht[:-parents] if parents else dirname_patht
    len0 = len(dirname_patht)
    len1 = len(patht)
    len2 = len(start_patht)
    if parents:
        if start_parents:
            if parents == start_parents:
                return "."
            elif parents > start_parents:
                return ".." + "/.." * (parents - start_parents - 1)
            else:
                return "/".join(dirname_patht[max(1, len0 + parents - start_parents):])
        return ".." + "/.." * (len2 + parents - 1)
    elif start_parents:
        return "/".join(dirname_patht[max(1, len0 - start_parents):] + patht)
    for i, (p1, p2) in enumerate(zip(patht, start_patht)):
        if p1 != p2:
            return "../" * (len2 - i) + "/".join(patht[i:])
    if len1 == len2:
        return "."
    elif len1 < len2:
        return ".." + "/.." * (len2 - len1 - 1)
    else:
        return "/".join(patht[len2:])

