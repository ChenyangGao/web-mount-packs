#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["retry", "raise_for_value"]

from functools import partial, update_wrapper
from inspect import isawaitable, iscoroutinefunction
from itertools import count
from typing import Any, Callable, Iterable, Optional, TypeVar


T = TypeVar("T")


async def ensure_awaitable(o, /):
    "make an object awaitable"
    if isawaitable(o):
        return await o
    return o


def retry(
    func: Optional[Callable] = None, 
    /, 
    retry_times: int = 0, 
    suppress_exceptions: type[BaseException] | tuple[type[BaseException], ...] = Exception, 
    do_interval: Optional[Callable[[int], Any]] = None, 
    mark_async: bool = False, 
) -> Callable:
    """Decorator to make a function retryable.

    :param func: The function to be decorated.
    :param retry_times: The number of times the decorated function will be retried if it raises an exception. Default is 0, which means no retries.
    :param suppress_exceptions: The type or types of exceptions that should be suppressed during retries.
    :param do_interval: An optional function that can be used to perform a delay between retries. It takes the current retry count as an argument.
    :param mark_async`: A flag to explicitly indicate whether the decorated function is asynchronous. 

    :return: If the `func` argument is provided, it returns a wrapper function that wraps the original function with retry logic. 
             If the `func` argument is not provided, it returns a partial function with the specified arguments for later use as a decorator. 
    """
    if func is None:
        return partial(
            retry, 
            retry_times=retry_times, 
            suppress_exceptions=suppress_exceptions, 
            do_interval=do_interval, 
            mark_async=mark_async, 
        )
    if retry_times == 0:
        return func
    if mark_async or iscoroutinefunction(func):
        async def wrapper(*args, **kwds):
            if retry_times > 0:
                excs: list[BaseException] = []
                add_exc = excs.append
                loops: Iterable[int] = range(retry_times + 1)
            else:
                add_exc = None
                loops = count()
            for i in loops:
                try:
                    if i and do_interval is not None:
                        await ensure_awaitable(do_interval(i))
                    return await ensure_awaitable(func(*args, **kwds))
                except suppress_exceptions as exc:
                    add_exc and add_exc(exc)
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
            for i in loops:
                try:
                    if i and do_interval is not None:
                        do_interval(i)
                    return func(*args, **kwds)
                except suppress_exceptions as exc:
                    add_exc and add_exc(exc)
            raise BaseExceptionGroup("too many retries", tuple(excs))
    return update_wrapper(wrapper, func)


def raise_for_value(
    func: Optional[Callable[..., T]] = None, 
    /, 
    predicate: Callable[[T], bool] = lambda val: val is not None, 
    exception_factory: type[BaseException] | Callable[[T], BaseException] = ValueError, 
    mark_async: bool = False, 
) -> Callable:
    """Wrap a function and ensure that its return value satisfies a given predicate condition.

    :param func: The function to be wrapped. If not provided, return a partial function.
    :param predicate: A callable that takes the return value of `func` and returns a boolean indicating whether the value satisfies a condition. 
    :param exception_factory: The exception type or a callable that creates an exception object to be raised when the return value fails the condition.
    :param mark_async: To mark the wrapped function as asynchronous if True.

    :return: The wrapped function.
    """
    if func is None:
        return partial(
            raise_for_value, 
            predicate=predicate, 
            exception_factory=exception_factory, 
            mark_async=mark_async, 
        )
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
    return update_wrapper(wrapper, func)

