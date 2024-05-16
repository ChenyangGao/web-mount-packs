#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["iterable", "mapf", "map_prod", "unzip"]

from collections.abc import AsyncIterable, Callable, Iterable, Iterator
from itertools import product
from typing import Any, TypeVar


T = TypeVar("T")


def mapf(it: Iterable[T], /, *fns: Callable[[T], Any]) -> Iterator[tuple]:
    return (tuple(f(v) for f in fns) for v in it)


def map_prod(f, /, *its, ignore_types=(bytes, str)):
    if not its:
        return f()
    for args in product(*(it if isinstance(it, Iterable) and not isinstance(it, ignore_types) else (it,) for it in its)):
        yield f(*args)


def unzip(iterable):
    return zip(*iterable)

