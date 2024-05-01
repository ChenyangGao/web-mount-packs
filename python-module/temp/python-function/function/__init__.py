#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = [
    "argcount", "identity", "is_or_eq", "hash_eq", "apply", "call", "callby", 
    "call_if", "call_if_any", "foreach", "pipe", "compose", "f_and", "f_or", 
    "f_not", "f_all", "f_any", "f_swap_args", "f_select_args", 
]

from collections.abc import Callable, Iterable, Iterator, Mapping
from functools import reduce
from inspect import getfullargspec
from operator import itemgetter
from typing import Any, ParamSpec, TypeVar


Args = ParamSpec("Args")
R = TypeVar("R")
S = TypeVar("S")
T = TypeVar("T")


def argcount(func: Callable) -> int:
    try:
        return func.__code__.co_argcount
    except AttributeError:
        return len(getfullargspec(func).args)


def identity(x: T, /) -> T:
    return x


def is_or_eq(x, y, /) -> bool:
    return x is y or x == y


def hash_eq(x, y, /) -> bool:
    return x == y and hash(x) == hash(y)


def apply(
    func: Callable[..., R], 
    /, 
    args: Iterable = (), 
    kwds: Mapping = {}, 
) -> R:
    return func(*args, **kwds)


def call(func: Callable[Args, R], /, *args: Args.args, **kwds: Args.kwargs) -> R:
    return func(*args, **kwds)


def callby(x: T, f: Callable[[T], R], /) -> R:
    return f(x)


def call_if(f, x, /, predicate = bool):
    return f(x) if predicate(x) else x


def call_if_any(f, x, /):
    return f(x) if callable(f) else x


def foreach(
    func: Callable, 
    iterable: Iterable, 
    /, 
    *iterables: Iterable, 
    callback: None | Callable = None, 
):
    if iterables:
        for args in zip(iterable, *iterables):
            r = func(*args)
            callback and callback(r)
    else:
        for arg in iterable:
            r = func(arg)
            callback and callback(r)


def pipe(f: Callable, /, *fns: Callable) -> Callable:
    if not fns:
        return f
    return lambda *args, **kwds: reduce(callby, fns, f(*args, **kwds))


def compose(*fns: Callable) -> Callable:
    return pipe(*reversed(fns))


def fn_and(f: Callable[Args, R], g: Callable[Args, S], /) -> Callable[Args, R | S]:
    return lambda *args, **kwds: f(*args, **kwds) and g(*args, **kwds)


def fn_or(f: Callable[Args, R], g: Callable[Args, S], /) -> Callable[Args, R | S]:
    return lambda *args, **kwds: f(*args, **kwds) and g(*args, **kwds)


def fn_not(f: Callable, /) -> bool:
    return lambda *args, **kwds: f(*args, **kwds) or g(*args, **kwds)


def fn_all(*fs: Callable[Args, Any]) -> bool:
    return lambda *args, **kwds: all(f(*args, **kwds) for f in fs)


def fn_any(*fs: Callable[Args, Any]) -> bool:
    return lambda *args, **kwds: any(f(*args, **kwds) for f in fs)


def fn_swap_args(f: Callable[[S, T], R], /) -> Callable[[T, S], R]:
    return lambda y, x, /: f(x, y)


def fn_select_args(f, /, *ks: int | str):
    idxs = tuple((k for k in ks if isinstance(k, int)))
    if idxs:
        get_pargs = itemgetter(*idxs)
    keys = tuple(k for k in ks if isinstance(k, str))
    if keys:
        get_kargs = itemgetter(*keys)
    if idxs:
        if keys:
            return lambda *args, **kwds: f(*get_pargs(args), **dict(zip(keys, get_kargs(kwds))))
        else:
            return lambda *args, **kwds: f(*get_pargs(args))
    elif keys:
        return lambda *args, **kwds: f(**dict(zip(keys, get_kargs(kwds))))
    else:
        return lambda *args, **kwds: f()

