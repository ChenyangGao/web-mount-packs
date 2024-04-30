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


def as_is(x: T) -> T:
    return x


def is_or_eq(x: Any, y: Any) -> bool:
    return x is y or x == y


def f_not(f):
    return lambda *a, **k: not(f(*a, **k))


def f_and(f, g):
    return lambda *a, **k: f(*a, **k) and g(*a, **k)


def f_or(f, g):
    return lambda *a, **k: f(*a, **k) or g(*a, **k)


def f_all(*fs):
    return lambda *a, **k: all(f(*a, **k) for f in fs)


def f_any(*preds):
    return lambda *a, **k: any(f(*a, **k) for f in fs)


def apply(
    f: Callable[..., T], 
    args: tuple = (), 
    kwargs: dict = {}, 
) -> T:
    return f(*args, **kwargs)


def call(f: Callable[[T], S], x: T) -> S:
    return f(x)


def callby(x: T, f: Callable[[T], S]) -> S:
    return f(x)


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

