__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 2)
__all__ = ['as_thread', 'as_threads', 'timethis', 'with_lock', 
           'context', 'suppressed']

from concurrent.futures import Future
from threading import current_thread, Lock, Thread
from time import perf_counter
from typing import (
    overload, Callable, List, Optional, Type, TypeVar, Tuple, Union
)

from .decorator import optional_decorate


@optional
def threaded(f: Callable = None, /, **init_thread_kwargs) -> Callable[..., Future]:
    init_thread_kwargs.setdefault("daemon", True)
    def wrapper(*args, **kwds) -> Future:
        fu = Future()
        def asfuture():
            try:
                fu.set_result(f(*args, **kwds))
            except BaseException as exc:
                fu.set_exception(exc)
        Thread(target=asfuture, **init_thread_kwargs).start()
        return fu
    return wrapper


@optional
def timethis(f: Callable = None, /, log: Callable = print) -> Callable:
    def wrapper(*args, **kwds):
        start_ts = perf_counter()
        try:
            return f(*args, **kwds)
        finally:
            cost = perf_counter() - start_ts
            name = getattr(f, "__qualname__", None) or getattr(f, "__name__", None) or repr(f)
            args_str = ", ".join((
                *map(repr, args), 
                *map("%s=%r".__mod__, kwargs.items()), 
            ))
            print(f"{name}({args_str}) consumed {cost} seconds")
    return wrapper


@optional
def with_lock(fn: Callable, /, lock=Lock()) -> Callable:
    def wrapper(*args, **kwds):
        with lock:
            return fn(*args, **kwds)
    return wrapper


@optional
def context(
    fn: Callable, 
    /, 
    onenter: Optional[Callable] = None,
    onexit: Optional[Callable] = None,
) -> Callable:
    def wrapper(*args, **kwds):
        if onenter:
            onenter()
        try:
            return fn(*args, **kwds)
        finally:
            if onexit: onexit()
    return wrapper


@overload
def suppressed(
    fn: Callable[..., T], 
    /, 
    default: None = ..., 
    exceptions: Union[
        Type[BaseException], 
        Tuple[Type[BaseException], ...]
    ] = ..., 
) -> Callable[..., Optional[T]]:
    ...
@overload
def suppressed(
    fn: Callable[..., T], 
    /, 
    default: T = ..., 
    exceptions: Union[
        Type[BaseException], 
        Tuple[Type[BaseException], ...]
    ] = ..., 
) -> Callable[..., T]:
    ...
@optional
def suppressed(fn, /, default=None, exceptions=Exception):
    def wrapper(*args, **kwds):
        try:
            return fn(*args, **kwds)
        except exceptions:
            return default
    return wrapper

