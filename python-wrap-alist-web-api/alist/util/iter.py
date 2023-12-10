#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["acc_step", "cut_iter", "posix_glob_translate_iter"]

from fnmatch import translate as wildcard_translate
from functools import partial
from re import compile as re_compile, escape as re_escape
from typing import Iterator, Optional


RESUB_REMOVE_WRAP_BRACKET = partial(re_compile("(?s:\\[(.[^]]*)\\])").sub, "\\1")


def acc_step(end: int, step: int = 1) -> Iterator[tuple[int, int, int]]:
    i = 0
    for j in range(step, end + 1, step):
        yield i, j, step
        i = j
    if (rest := end - i):
        yield i, end, rest


def cut_iter(
    start: int, 
    stop: Optional[int] = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int]]:
    if stop is None:
        start, stop = 0, start
    i = start
    for j in range(start+step, stop, step):
        yield i, j
        i = j    
    yield i, stop


def posix_glob_translate_iter(pattern: str) -> Iterator[tuple[str, str, str]]:
    def is_pat(part: str) -> bool:
        it = enumerate(part)
        try:
            for _, c in it:
                if c in ("*", "?"):
                    return True
                elif c == "[":
                    _, c2 = next(it)
                    if c2 == "]":
                        continue
                    i, c3 = next(it)
                    if c3 == "]":
                        continue
                    if part.find("]", i + 1) > -1:
                        return True
            return False
        except StopIteration:
            return False
    last_type = None
    for part in pattern.split("/"):
        if not part:
            continue
        if part == "*":
            last_type = "star"
            yield "[^/]*", last_type, ""
        elif len(part) >=2 and not part.strip("*"):
            if last_type == "dstar":
                continue
            last_type = "dstar"
            yield "[^/]*(?:/[^/]*)*", last_type, ""
        elif is_pat(part):
            last_type = "pat"
            yield wildcard_translate(part)[4:-3].replace(".*", "[^/]*"), last_type, ""
        else:
            last_type = "orig"
            tidy_part = RESUB_REMOVE_WRAP_BRACKET(part)
            yield re_escape(tidy_part), last_type, tidy_part

