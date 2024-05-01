#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = ['as_is', 'apply', 'call', 'callby', 'pipe', 'compose']


from functools import reduce
from typing import Any, Callable, TypeVar
from .undefined import undefined


T = TypeVar('T')
S = TypeVar('S')


def callby_if(
    x: T, 
    f: Callable[[T], T], 
    pred: Callable[[T], bool], 
) -> T:
    return f(x) if pred(x) else x


def pipe0(*fs: Callable) -> Callable:
    return lambda x: reduce(callby, fs, x)


def compose0(*fs: Callable) -> Callable:
    return pipe0(*reversed(fs))


def pipe(f: Callable, *fs: Callable) -> Callable:
    return lambda *a, **k: \
        reduce(callby, fs, f(*a, **k))


def compose(f: Callable, *fs: Callable) -> Callable:
    return pipe(*reversed(fs), f)


def foreach(func, iterable, *iterables, strict=False):
    if iterables:
        it = zip(iterable, *iterables, strict=strict)
        for args in it: 
            func(*args)
    else:
        for arg in iterable: 
            func(arg)


def mapby(x, fs):
    return (f(x) for f in fs)


def reduce2(function, iterable, /, initial=undefined):
    if initial is undefined:
        return reduce(function, iterable)
    return reduce(function, iterable, initial)

