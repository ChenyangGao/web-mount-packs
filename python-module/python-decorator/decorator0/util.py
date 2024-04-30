#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["suppressed", "threaded", "timethis", "with_lock"]

from _thread import start_new_thread
from asyncio import Lock as AsyncLock
from concurrent.futures import Future
from inspect import isawaitable, iscoroutinefunction
from threading import Lock
from time import perf_counter

from undefined import undefined
from . import decorated, optional


@optional
def suppressed(
    func, 
    /, 
    default=undefined, 
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = Exception, 
):
    if iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            try:
                return await func(*args, **kwds)
            except exceptions as e:
                if default is undefined:
                    return e
                else:
                    return default
    else:
        def wrapper(*args, **kwds):
            try:
                return func(*args, **kwds)
            except exceptions as e:
                if default is undefined:
                    return e
                else:
                    return default
    return wrapper


@decorated
def threaded(func, /, *args, **kwds) -> Future:
    def start_future():
        try: 
            fu.set_result(func(*args, **kwds))
        except BaseException as e:
            fu.set_exception(e)
    fu: Future = Future()
    start_new_thread(start_future, ())
    return fu


@optional
def timethis(func, /, output=lambda t: print(f"cost time: {t} s")):
    if iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            start = perf_counter()
            result = await func(*args, **kwds)
            resp = output(perf_counter() - start)
            if isawaitable(resp):
                await resp
            return result
    else:
        def wrapper(*args, **kwds):
            start = perf_counter()
            result = func(*args, **kwds)
            output(perf_counter() - start)
            return result
    return wrapper


@optional
def with_lock(func, /, lock=None):
    if iscoroutinefunction(func):
        if lock is None:
            lock = AsyncLock()
        async def wrapper(*args, **kwds):
            async with lock:
                return await func(*args, **kwds)
    else:
        if lock is None:
            lock = Lock()
        async def wrapper(*args, **kwds):
            with lock:
                return func(*args, **kwds)
    return wrapper

