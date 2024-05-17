#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = [
    "iterable", "async_iterable", "foreach", "async_foreach", "through", "async_through", 
    "wrap_iter", "wrap_aiter", "acc_step", "cut_iter", 
]

from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable, Iterator
from typing import Any, TypeVar

from asynctools import async_zip, ensure_async, ensure_aiter


T = TypeVar("T")


def iterable(it, /) -> bool:
    try:
        return isinstance(iter(it), Iterable)
    except TypeError:
        return False


def async_iterable(it, /) -> bool:
    try:
        return isinstance(iter(it), AsyncIterable)
    except TypeError:
        return False


def foreach(func: Callable, iterable, /, *iterables):
    if iterables:
        for args in zip(iterable, *iterables):
            func(*args)
    else:
        for arg in iterable:
            func(arg)


async def async_foreach(func: Callable, iterable, /, *iterables, threaded: bool = True):
    func = ensure_async(func, threaded=threaded)
    if iterables:
        async for args in async_zip(iterable, *iterables, threaded=threaded):
            await func(*args)
    else:
        async for arg in ensure_aiter(iterable, threaded=threaded):
            await func(arg)


def through(it: Iterable, /):
    for _ in it:
        pass


async def async_through(
    it: Iterable | AsyncIterable, 
    /, 
    threaded: bool = True, 
):
    async for _ in ensure_aiter(it, threaded=threaded):
        pass


def wrap_iter(
    it: Iterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None,  
) -> Iterator[T]:
    if not callable(callprev):
        callprev = None
    if not callable(callnext):
        callnext = None
    for e in it:
        if callprev:
            callprev(e)
        yield e
        if callnext:
            callnext(e)


async def wrap_aiter(
    it: Iterable[T] | AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None,  
    threaded: bool = True, 
) -> AsyncIterator[T]:
    callprev = ensure_async(callprev) if callable(callprev) else None
    callnext = ensure_async(callnext) if callable(callnext) else None
    async for e in ensure_aiter(it, threaded=threaded):
        if callprev:
            await callprev(e)
        yield e
        if callnext:
            await callnext(e)


def acc_step(
    start: int, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int, int]]:
    if stop is None:
        start, stop = 0, start
    for i in range(start + step, stop, step):
        yield start, (start := i), step
    if start != stop:
        yield start, stop, stop - start


def cut_iter(
    start: int, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int]]:
    if stop is None:
        start, stop = 0, start
    for start in range(start + step, stop, step):
        yield start, step
    if start != stop:
        yield stop, stop - start

