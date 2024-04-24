#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["identity", "foreach", "callby", "pipe", "compose", "mapf"]

from collections.abc import Callable, Iterable, Iterator
from functools import reduce
from typing import Any, TypeVar


R = TypeVar("R")
T = TypeVar("T")


def identity(x: T, /) -> T:
    return x


def foreach(
    func: Callable, 
    iterable: Iterable, 
    /, 
    *iterables: Iterable, 
):
    if iterables:
        for args in zip(iterable, *iterables):
            func(*args)
    else:
        for arg in iterable:
            func(arg)


def callby(x: T, f: Callable[[T], R], /) -> R:
    return f(x)


def pipe(f: Callable, /, *fns: Callable) -> Callable:
    if not fns:
        return f
    return lambda *args, **kwds: reduce(callby, fns, f(*args, **kwds))


def compose(*fns: Callable) -> Callable:
    return pipe(*reversed(fns))


def mapf(it: Iterable[T], /, *fns: Callable[[T], Any]) -> Iterator[tuple]:
    return (tuple(f(v) for f in fns) for v in it)

