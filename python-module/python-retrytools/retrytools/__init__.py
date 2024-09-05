#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["retry", "raise_for_value"]

from collections.abc import Callable, Iterable
from asyncio import sleep as asleep
from inspect import isawaitable, iscoroutinefunction
from itertools import count
from time import sleep
from typing import Any, ParamSpec, TypeVar

from decotools import optional


Args = ParamSpec("Args")
T = TypeVar("T")


async def ensure_awaitable(o, /):
    "Make an object awaitable."
    if isawaitable(o):
        return await o
    return o


@optional
def retry(
    func: Callable[Args, T], 
    /, 
    retry_times: int = 0, 
    exceptions: type[BaseException] | tuple[type[BaseException], ...] | Callable[[BaseException], bool] = Exception, 
    do_interval: None | Callable[[int], Any] | int | float = None, 
    mark_async: bool = False, 
) -> Callable[Args, T]:
    """Decorator to make a function retryable.

    :param func: The function to be decorated.
    :param retry_times: The number of times the decorated function will be retried if it raises an exception. Default is 0, which means no retries.
                        It will run at least once. If it is less than 0, it will run infinitely. Otherwise, it will run `retry_times`+1 times.
    :param exceptions: The exception type or tuple of exception types or callable for check exception that should be suppressed during retries.
    :param do_interval: An optional number or function that can be used to perform a delay between retries. 
                        If None (the default), no delay will be performed.
                        If a number is provided, it represents the number of seconds to sleep before each retry. 
                        If a function is provided, it takes the current retry count as an argument, and can dynamically determine the sleep duration if a number is returned. 
    :param mark_async`: A flag to explicitly indicate whether the decorated function is asynchronous. 

    :return: If the `func` argument is provided, it returns a wrapper function that wraps the original function with retry logic. 
             If the `func` argument is not provided, it returns a partial function with the specified arguments for later use as a decorator. 
    """
    if retry_times == 0:
        return func
    if isinstance(exceptions, (type, tuple)):
        check = lambda e: isinstance(e, exceptions)
    else:
        check = exceptions
    if mark_async or iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            if retry_times > 0:
                excs: list[BaseException] = []
                add_exc = excs.append
                loops: Iterable[int] = range(retry_times + 1)
            else:
                add_exc = None
                loops = count()
            prev_exc = None
            for i in loops:
                try:
                    if i and do_interval is not None:
                        if callable(do_interval):
                            sleep_secs = do_interval(i)
                            if isawaitable(sleep_secs):
                                sleep_secs = await sleep_secs
                        else:
                            sleep_secs = do_interval
                        if isinstance(sleep_secs, (int, float)) and sleep_secs > 0:
                            await asleep(sleep_secs)
                    return await ensure_awaitable(func(*args, **kwds))
                except BaseException as exc:
                    add_exc and add_exc(exc)
                    res = check(exc)
                    if isawaitable(res):
                        res = await res
                    if res:
                        setattr(exc, "__prev__", prev_exc)
                    else:
                        raise
                    prev_exc = exc
            raise BaseExceptionGroup("too many retries", tuple(excs))
    else:
        def wrapper(*args, **kwds):
            if retry_times > 0:
                excs: list[BaseException] = []
                add_exc = excs.append
                loops: Iterable[int] = range(retry_times + 1)
            else:
                add_exc = None
                loops = count()
            prev_exc = None
            for i in loops:
                try:
                    if i and do_interval is not None:
                        if callable(do_interval):
                            sleep_secs = do_interval(i)
                        else:
                            sleep_secs = do_interval
                        if isinstance(sleep_secs, (int, float)) and sleep_secs > 0:
                            sleep(sleep_secs)
                    return func(*args, **kwds)
                except BaseException as exc:
                    if check(exc):
                        add_exc and add_exc(exc)
                        setattr(exc, "__prev__", prev_exc)
                    else:
                        raise
                    prev_exc = exc
            raise BaseExceptionGroup("too many retries", tuple(excs))
    return wrapper


@optional
def raise_for_value(
    func: Callable[Args, T], 
    /, 
    predicate: Callable[[T], bool] = lambda val: val is not None, 
    exception_factory: type[BaseException] | Callable[[T], BaseException] = ValueError, 
    mark_async: bool = False, 
) -> Callable[Args, T]:
    """Wrap a function and ensure that its return value satisfies a given predicate condition.

    :param func: The function to be wrapped. If not provided, return a partial function.
    :param predicate: A callable that takes the return value of `func` and returns a boolean indicating whether the value satisfies a condition. 
    :param exception_factory: The exception type or a callable that creates an exception object to be raised when the return value fails the condition.
    :param mark_async: To mark the wrapped function as asynchronous if True.

    :return: The wrapped function.
    """
    def check(val: T) -> T:
        if predicate(val):
            return val
        raise exception_factory(val)
    if mark_async or iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            return check(await ensure_awaitable(func(*args, **kwds)))
    else: 
        def wrapper(*args, **kwds):
            return check(func(*args, **kwds))
    return wrapper

