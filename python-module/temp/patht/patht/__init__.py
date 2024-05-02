#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "escape", "unescape", "joins", "splits", "normpath", "normpatht", 
    "split", "join", "basename", "dirname", "commonpath", "commonpatht", 
]

from re import compile as re_compile, Match
from typing import cast, Iterable, Sequence


CRE_PART_match = re_compile(r"[^\\/]*(?:\\(?s:.)[^\\/]*)*/").match
CRE_PART = re_compile(r"[^\\/]*(?:\\(?s:.)[^\\/]*)*$")


def escape(name: str, /) -> str:
    return "\\" + name if name in (".", "..") else name.replace("\\", r"\\").replace("/", r"\/")


def unescape(name: str, /) -> str:
    if name.startswith(r"\."):
        name = name[1:]
    return name.replace(r"\/", "/").replace(r"\\", "\\")


def joins(patht: Sequence[str], parents: int = 0, /) -> str:
    assert parents >= 0
    if not patht:
        if parents:
            return "/".join(("..",) * parents)
        return ""
    path = "/".join(escape(p) for p in patht if p)
    if not patht[0]:
        path = "/" + path
    elif parents:
        path = "".join(("../",) * parents) + path
    return path


def splits(
    path: str, 
    /, 
    parse_dots: bool = True, 
    do_unescape: bool = True, 
) -> tuple[list[str], int]:
    parts: list[str] = []
    add_part = parts.append
    if path.startswith("/"):
        add_part("")
        l = 1
        is_absolute = True
    else:
        l = 0
        is_absolute = False
    parents = 0
    while (m := CRE_PART_match(path, l)):
        p = m[0][:-1]
        if p:
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
            elif do_unescape:
                add_part(unescape(p))
            else:
                add_part(p)
        l = m.end()
    if l < len(path):
        p = path[l:]
        if p:
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
            elif do_unescape:
                add_part(unescape(p))
            else:
                add_part(p)
    return parts, parents


def normpath(path: str, /) -> str:
    return joins(*splits(path))


def normpatht(patht: Sequence[str], /) -> list[str]:
    return [patht[0], *filter(None, patht)]


def split(path: str, /) -> tuple[str, str]:
    stop = len(path)
    if stop <= 1:
        if path == "/":
            return "/", ""
        return "", path
    parents = 0
    while True:
        match = cast(Match, CRE_PART.search(path, 0, stop))
        idx = match.start()
        value = path[idx:stop]
        if value in ("", "."):
            pass
        elif value == "..":
            parents += 1
        elif parents:
            parents -= 1
        else:
            value = unescape(value)
            if idx == 0:
                return "", value
            elif idx == 1:
                return path[:idx], value
            else:
                return path[:idx-1], value
        if idx == 0:
            if path.startswith("/"):
                return "/", ""
            else:
                return "", ""
        stop = idx - 1


def join(path: str, /, *parts: str) -> str:
    if not parts:
        return path
    return "/".join((path, *map(escape, parts)))


def basename(path: str, /) -> str:
    return split(path)[1]


def dirname(path: str, /) -> str:
    return split(path)[0]


def commonpath(pathit: Iterable[str], /) -> str:
    ls = tuple(map(splits, pathit))
    if not ls:
        return ""
    m = min(t[1] for t in ls)
    M = max(t[1] for t in ls)
    if m:
        prefix = "/".join(("..",) * m)
    else:
        prefix = ""
    if m != M:
        return prefix
    cm = commonpatht((t[0] for t in ls))
    if not cm:
        return prefix
    path = joins(cm)
    if prefix:
        path = prefix + "/" + path
    return path


def commonpatht(pathtit: Iterable[Sequence[str]], /) -> list[str]:
    ls = []
    for n1, n2 in zip(*pathtit):
        if n1 != n2:
            break
        ls.append(n1)
    return ls

# TODO
# commonprefix
# splitext
# samefile
# sameopenfile
# samestat
# stat
# 另外参考 posixpath
