#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__all__ = [
    "iterable", "async_iterable", "foreach", "async_foreach", "through", "async_through", 
    "wrap_iter", "wrap_aiter", "acc_step", "cut_iter", "run_gen_step", 
]

from asyncio import to_thread
from collections.abc import (
    AsyncIterable, AsyncIterator, Awaitable, Callable, Generator, Iterable, Iterator, 
)
from inspect import isawaitable
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
    callenter: None | Callable[[Iterable[T]], Any] = None, 
    callexit: None | Callable[[Iterable[T], None | BaseException], Any] = None, 
) -> Iterator[T]:
    if not callable(callprev):
        callprev = None
    if not callable(callnext):
        callnext = None
    try:
        if callable(callenter):
            callenter(it)
        for e in it:
            if callprev:
                try:
                    callprev(e)
                except (StopIteration, GeneratorExit):
                    break
            yield e
            if callnext:
                try:
                    callnext(e)
                except (StopIteration, GeneratorExit):
                    break
    except BaseException as e:
        if callable(callexit):
            if not callexit(it, e):
                raise
        else:
            raise
    finally:
        if callable(callexit):
            callexit(it, None)


async def wrap_aiter(
    it: Iterable[T] | AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
    callenter: None | Callable[[Iterable[T] | AsyncIterable[T]], Any] = None, 
    callexit: None | Callable[[Iterable[T] | AsyncIterable[T], None | BaseException], Any] = None, 
    threaded: bool = True, 
) -> AsyncIterator[T]:
    callprev = ensure_async(callprev, threaded=threaded) if callable(callprev) else None
    callnext = ensure_async(callnext, threaded=threaded) if callable(callnext) else None
    try:
        async for e in ensure_aiter(it, threaded=threaded):
            if callprev:
                try:
                    await callprev(e)
                except (StopAsyncIteration, GeneratorExit):
                    break
            yield e
            if callnext:
                try:
                    await callnext(e)
                except (StopAsyncIteration, GeneratorExit):
                    break
    except BaseException as e:
        if callable(callexit):
            if not await ensure_async(callexit, threaded=threaded)(it, e):
                raise
        else:
            raise
    finally:
        if callable(callexit):
            await ensure_async(callexit, threaded=threaded)(it, None)


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


def run_gen_step(
    gen_step: Generator[Any, Any, T] | Callable[[], Generator[Any, Any, T]], 
    *, 
    async_: bool = False, 
    threaded: bool = False, 
    as_iter: bool = False, 
) -> T:
    if callable(gen_step):
        gen = gen_step()
        close = gen.close
    else:
        gen = gen_step
        close = None
    send = gen.send
    throw = gen.throw
    if async_:
        async def process():
            try:
                if threaded:
                    func = await to_thread(send, None)
                else:
                    func = send(None)
                while True:
                    try:
                        if isawaitable(func):
                            ret = await func
                        elif callable(func):
                            ret = func()
                            if isawaitable(ret):
                                ret = await ret
                        else:
                            ret = func
                    except BaseException as e:
                        if threaded:
                            func = await to_thread(throw, e)
                        else:
                            func = throw(e)
                    else:
                        if threaded:
                            func = await to_thread(send, ret)
                        else:
                            func = send(ret)
            except StopIteration as e:
                return e.value
            finally:
                if close is not None:
                    if threaded:
                        await to_thread(close)
                    else:
                        close()
        result = process()
        if as_iter:
            async def wrap(result):
                it = await result
                try:
                    it = aiter(it)
                except TypeError:
                    for val in iter(it):
                        if isawaitable(val):
                            val = await val
                        yield val
                else:
                    async for val in it:
                        yield val
            result = wrap(result)
        return result
    else:
        try:
            func = send(None)
            while True:
                try:
                    ret = func() if callable(func) else ret
                except BaseException as e:
                    func = throw(e)
                else:
                    func = send(ret)
        except StopIteration as e:
            result = e.value
            if as_iter:
                result = iter(result)
            return result
        finally:
            if close is not None:
                close()

