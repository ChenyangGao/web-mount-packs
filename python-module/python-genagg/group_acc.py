#!/usr/bin/env python3
# coding: utf-8

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 1)
__all__ = [
    'gen_startup', 'joint', 'iter_accumulate', 'iter_group_accumulate', 
    'iteracc', 'groupacc', 'groupagg', 
]


from functools import update_wrapper
from inspect import isgeneratorfunction
from typing import Any, Callable, Generator, Iterable, Optional, Tuple


def gen_startup(
    fn: Callable[..., Generator], /
) -> Callable[..., Generator]:
    def wrapper(*args, **kwds) -> Generator:
        r = fn(*args, **kwds)
        next(r)
        return r
    return update_wrapper(wrapper, fn)


def joint(
    *accumulator_factories: Callable, 
    calc: Optional[Callable] = None, 
) -> Callable[[], Generator]:
    def wrapper():
        factories = [
            gen_startup(f)().send if isgeneratorfunction(f) else f()
            for f in accumulator_factories
        ]
        i = yield
        if calc is None:
            while True:
                i = yield [f(i) for f in factories]
        else:
            while True:
                i = yield calc(*(f(i) for f in factories))
    return wrapper


def iter_accumulate(
    accumulator_factory: Callable, /
) -> Generator:
    f = accumulator_factory()
    if isgeneratorfunction(accumulator_factory):
        i = yield next(f)
        f = f.send
    else:
        i = yield None
    while True:
        i = yield f(i)


def iter_group_accumulate(
    accumulator_factory: Callable, 
    /, 
    key: Callable, 
) -> Generator:
    if isgeneratorfunction(accumulator_factory):
        accumulator_factory = \
            lambda _f=accumulator_factory: gen_startup(_f)().send
    macc: dict = {}
    mdata: dict = {}
    while True:
        i = yield mdata
        k = key(i)
        try:
            f = macc[k]
        except KeyError:
            f = macc[k] = accumulator_factory()
        mdata[k] = f(i)


def iteracc(
    accumulator_factory: Callable, 
    /, 
    key: Optional[Callable] = None, 
) -> Generator:
    if key is None:
        return iter_accumulate(accumulator_factory)
    else:
        return iter_group_accumulate(accumulator_factory, key=key)


def groupacc(
    accumulator_factory: Callable, 
    /, 
    key: Optional[Callable] = None, 
    value: Optional[Callable] = None, 
) -> Tuple[Any, Callable]:
    acc = iteracc(accumulator_factory, key=key)
    if value is None:
        return next(acc), acc.send
    else:
        return next(acc), lambda x, _send=acc.send, /: _send(value(x))


def groupagg(
    iterable: Iterable, 
    accumulator_factory: Callable, 
    /, 
    key: Optional[Callable] = None, 
    value: Optional[Callable] = None, 
):
    r, facc = groupacc(accumulator_factory, key=key)
    if value is not None:
        iterable = map(value, iterable)
    for r in map(facc, iterable): pass
    return r

