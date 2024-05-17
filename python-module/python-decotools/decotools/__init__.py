#!/usr/bin/env python3
# coding: utf-8

"""This module provides some decorators to decorate other 
decorators, in order to simplify some boilerplate code.
"""

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["decorated", "optional", "optional_args", "currying", "partialize"]

from collections.abc import Callable
from functools import partial, reduce, update_wrapper as _update_wrapper
from inspect import signature
from typing import cast, overload, Any, Concatenate, Optional, ParamSpec, TypeVar

from partial import ppartial
from undefined import undefined


Args = ParamSpec("Args")
Args0 = ParamSpec("Args0")
R = TypeVar("R")
T = TypeVar("T")


def update_wrapper(f, g, /, *args, **kwds):
    if f is g:
        return f
    else:
        return _update_wrapper(f, g, *args, **kwds)


def decorated(
    f: Callable[Concatenate[Callable[Args, R], Args], T], 
    /, 
) -> Callable[[Callable[Args, R]], Callable[Args, T]]:
    """Transform the 2-layers decorator into 1-layer.

    @decorated
    def decorator(func, /, *args, **kwds):
        ...
        return func(*args, **kwds)

    Roughly equivalent to:

    import functools

    def decorator(func, /):
        def wrapper(*args, **kwds):
            ...
            return func(*args, **kwds)
        return functools.update_wrapper(wrapper, func)
    """
    return update_wrapper(lambda g, /: update_wrapper(lambda *a, **k: f(g, *a, **k), g), f)


def optional(
    f: Callable[Concatenate[Callable[Args, R], Args0], Callable[Args, T]], 
    /, 
) -> Callable[Concatenate[None, Args0], Callable[[Callable[Args, R]], Callable[Args, T]]] \
    | Callable[Concatenate[Callable[Args, R], Args0], Callable[Args, T]]:
    """This function decorates another decorator that with optional parameters.
    NOTE: Make sure that these optional parameters have default values.

    @optional
    def decorator(func=None, /, *args, **kwds):
        ...
        def wrapper(*args1, **kwds1):
            ...
            return func(*args1, **kwds1)
        return wrapper

    Roughly equivalent to:

    @optional_args
    def decorator(*args, **kwds):
        ...
        def wrapped(func, /, *args1, **kwds1):
            ...
            return func(*args1, **kwds1)
        return wrapped

    Roughly equivalent to:

    import functools

    def decorator(func=None, /, *args, **kwds):
        if func is None:
            return lambda func, /: decorator(func, *args, **kwds)
        ...
        def wrapper(*args1, **kwds1):
            ...
            return func(*args1, **kwds1)
        return functools.update_wrapper(wrapper, func)

    Supposing there is such a decorator:

    >>> @optional
    ... def foo(func, bar="bar", /, baz="baz"):
    ...     def wrapper(*args, **kwds):
    ...         print(bar)
    ...         r = func(*args, **kwds)
    ...         print(baz)
    ...         return r
    ...     return wrapper
    ... 

    example 1::

        >>> @foo 
        ... def baba1(): 
        ...     print("baba1") 
        ... 
        >>> baba1()
        bar
        baba1
        baz

    example 2::

        >>> @foo()
        ... def baba2(): 
        ...     print("baba2") 
        ... 
        >>> baba2()
        bar
        baba2
        baz

    example 3::

        >>> @foo("bar: begin", baz="baz: end") 
        ... def baba3(): 
        ...     print("baba3: process")
        ... 
        >>> baba3()
        bar: begin
        baba3: process
        baz: end

    example 4::

        >>> bar = type("", (), {"__str__": lambda self: "bar: call"})()
        >>> @foo(None, bar, baz='baz: end') 
        ... def baba4(): 
        ...    print("baba4: process")
        ... 
        >>> baba4()
        bar: call
        baba4: process
        baz: end
    """
    def wrapped(func=None, /, *args, **kwds):
        if func is None:
            return ppartial(wrapped, undefined, *args, **kwds)
        elif callable(func):
            return update_wrapper(f(func, *args, **kwds), func)
        else:
            return ppartial(wrapped, undefined, func, *args, **kwds)
    return update_wrapper(wrapped, f)


def optional_args(
    f: Callable[Args0, Callable[Concatenate[Callable[Args, R], Args], T]], 
    /,
) -> Callable[Args0, Callable[[Callable[Args, R]], Callable[Args, T]]] | Callable[Concatenate[Callable[Args, R], Args0], Callable[Args, T]]:
    """This function decorates another decorator that with optional parameters.
    NOTE: Make sure that these optional parameters have default values.

    @optional
    def decorator(func=None, /, *args, **kwds):
        ...
        def wrapper(*args1, **kwds1):
            ...
            return func(*args1, **kwds1)
        return wrapper

    Roughly equivalent to:

    @optional_args
    def decorator(*args, **kwds):
        ...
        def wrapped(func, /, *args1, **kwds1):
            ...
            return func(*args1, **kwds1)
        return wrapped

    Roughly equivalent to:

    import functools

    def decorator(func=None, /, *args, **kwds):
        if func is None:
            return lambda func, /: decorator(func, *args, **kwds)
        ...
        def wrapper(*args1, **kwds1):
            ...
            return func(*args1, **kwds1)
        return functools.update_wrapper(wrapper, func)

    Supposing there is such a decorator:

    >>> @optional_args
    ... def foo(bar="bar", /, baz="baz"):
    ...     def wrapper(func, /, *args, **kwds):
    ...         print(bar)
    ...         r = func(*args, **kwds)
    ...         print(baz)
    ...         return r
    ...     return wrapper
    ... 

    example 1::

        >>> @foo 
        ... def baba1(): 
        ...     print("baba1") 
        ... 
        >>> baba1()
        bar
        baba1
        baz

    example 2::

        >>> @foo()
        ... def baba2(): 
        ...     print("baba2") 
        ... 
        >>> baba2()
        bar
        baba2
        baz

    example 3::

        >>> @foo("bar: begin", baz="baz: end") 
        ... def baba3(): 
        ...     print("baba3: process")
        ... 
        >>> baba3()
        bar: begin
        baba3: process
        baz: end

    example 4::

        >>> bar = type("", (), {"__str__": lambda self: "bar: call"})()
        >>> @foo(None, bar, baz='baz: end') 
        ... def baba4(): 
        ...    print("baba4: process")
        ... 
        >>> baba4()
        bar: call
        baba4: process
        baz: end
    """
    def wrapped(func=None, /, *args, **kwds):
        if func is None:
            return decorated(f(*args, **kwds))
        elif callable(func):
            return decorated(f(*args, **kwds))(func)
        else:
            return decorated(f(func, *args, **kwds))
    return update_wrapper(wrapped, f)


def currying(
    f: Callable[Args, R], 
    /, 
) -> Callable[Args, R]:
    bind = signature(f).bind
    def wrapper(*args, **kwds):
        try:
            bind(*args, **kwds)
        except TypeError as exc:
            if (exc.args 
                and isinstance(exc.args[0], str)
                and exc.args[0].startswith("missing a required")
            ):
                return partial(wrapper, *args, **kwds)
            raise
        return f(*args, **kwds)
    return update_wrapper(wrapper, f)


@overload
def partialize(
    f: None = None, 
    /, 
    sentinel: Any = undefined, 
) -> Callable[[Callable[Args, R]], Callable[Args, R]]:
    ...
@overload
def partialize(
    f: Callable[Args, R], 
    /, 
    sentinel: Any = undefined, 
) -> Callable[Args, R]:
    ...
def partialize(
    f: None | Callable[Args, R] = None, 
    /, 
    sentinel: Any = undefined, 
) -> Callable[Args, R] | Callable[[Callable[Args, R]], Callable[Args, R]]:
    if f is None:
        return cast(
            Callable[[Callable[Args, R]], Callable[Args, R]], 
            partial(partialize, sentinel=sentinel), 
        )
    bind = signature(f).bind
    def wrap(_paix, _pargs, _kargs, /):
        def wrapper(*args, **kwargs):
            pargs = _pargs.copy()
            j = len(pargs)
            for i, e in zip(_paix, args[j:]):
                pargs[i] = e
                j += 1
            pargs.extend(args[j:])
            try:
                bound = bind(*pargs, **kwargs)
            except TypeError as exc:
                if (exc.args 
                    and isinstance(exc.args[0], str)
                    and exc.args[0].startswith("missing a required")
                ):
                    return partial(wrapper, *args, **kwargs)
                raise
            else:
                bound.apply_defaults()
            if sentinel in bound.args or sentinel in bound.kwargs.values():
                return wrap(
                    [i for i, e in enumerate(args) if e is sentinel], 
                    list(args), kwargs)
            return f(*args, **kwargs)
        return partial(update_wrapper(wrapper, f), *_pargs, **_kargs)
    return wrap([], [], {})

