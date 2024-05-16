#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["callback", "suppressed", "threaded", "asynced", "timethis", "with_cm", "with_lock"]

from _thread import start_new_thread
from asyncio import Lock as AsyncLock, to_thread
from concurrent.futures import Future
from inspect import isawaitable, iscoroutinefunction
from threading import Lock
from time import perf_counter
from typing import ContextManager, AsyncContextManager

from undefined import undefined
from . import decorated, optional


async def callasync(func, /, *args, **kwds):
    r = func(*args, **kwds)
    if isawaitable(r):
        r = await r
    return r


@optional
def callback(func, /, callok=None, callfail=None):
    good_callok = callable(callok)
    good_callfail = callable(callfail)
    if not (good_callok or good_callfail):
        return func
    if iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            try:
                r = await func(*args, **kwds)
            except BaseException as e:
                good_callfail and callasync(callfail, e)
                raise
            else:
                good_callok and callasync(callok, r)
                return r
    else:
        def wrapper(*args, **kwds):
            try:
                r = func(*args, **kwds)
            except BaseException as e:
                good_callfail and callfail(e)
                raise
            else:
                good_callok and callok(r)
                return r
    return wrapper


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


@decorated
def asynced(func, /, *args, **kwds):
    return to_thread(func, *args, **kwds)


@optional
def timethis(func, /, output=lambda t: print(f"cost time: {t} s")):
    if iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            start = perf_counter()
            result = await func(*args, **kwds)
            callasync(output, perf_counter() - start)
            return result
    else:
        def wrapper(*args, **kwds):
            start = perf_counter()
            result = func(*args, **kwds)
            output(perf_counter() - start)
            return result
    return wrapper


@optional
def with_cm(func, /, cm=None):
    if cm is None:
        return func
    if iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            if isinstance(cm, (ContextManager, AsyncContextManager)):
                ctx = cm
            else:
                ctx = cm(*args, **kwds)
            if isinstance(ctx, AsyncContextManager):
                async with ctx:
                    return await func(*args, **kwds)
            else:
                with ctx:
                    return await func(*args, **kwds)
    else:
        def wrapper(*args, **kwds):
            if isinstance(cm, ContextManager):
                ctx = cm
            else:
                ctx = cm(*args, **kwds)
            with ctx:
                return func(*args, **kwds)
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
        def wrapper(*args, **kwds):
            with lock:
                return func(*args, **kwds)
    return wrapper

