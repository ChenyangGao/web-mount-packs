#!/usr/bin/env python3
# coding: utf-8

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 0)
__all__ = ['re_find_slice', 're_sub_slice', 're_sub_with_index']

from itertools import islice
from re import finditer as re_find, sub as re_sub

from .getitems import getitems


def re_find_slice(pattern, string, pos=None, flags=0):
    matches = re_find(pattern, string, flags)
    if pos is not None:
        matches = getitems(matches, pos)
    return matches


def re_sub_slice(pattern, repl, string, pos=None, flags=0):
    if pos is None:
        return re_sub(pattern, repl, string, flags=flags)
    elif isinstance(pos, int):
        match = re_find_slice(pattern, string, pos, flags=flags)
        if match is None:
            return string
        repl_s = repl(match) if callable(repl) else repl
        if repl_s is None:
            return string
        b, d = match.span()
        return string[:b] + repl_s + string[d:]
    elif isinstance(pos, slice):
        matches = re_find_slice(pattern, string, pos, flags=flags)
        if not matches:
            return string
        if pos.step and pos.step < 0:
            matches = reversed(matches)
        ls = []
        add = ls.append
        last = 0
        is_c_repl = callable(repl)
        for m in matches:
            repl_s = repl(m) if is_c_repl else repl
            if repl_s is None:
                continue
            b, d = m.span()
            add(string[last:b])
            add(repl_s)
            last = d
        else:
            if not ls:
                return string
            add(string[last:])
        return "".join(ls)
    else:
        raise TypeError


def re_sub_with_index(pattern, repl_with_index, string, count=0, flags=0):
    index = -1
    def repl(m):
        nonlocal index
        index += 1
        r = repl_with_index(m, index)
        if r is None:
            return m[0]
        return r
    return re_sub(pattern, repl, string, count=count, flags=flags)

