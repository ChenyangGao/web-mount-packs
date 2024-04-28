#!/usr/bin/env python3
# coding: utf-8

"""This module provides some decorators to decorate other 
decorators, in order to simplify some boilerplate code.
"""

# Reference:
# - [decorator](https://pypi.org/project/decorator/)

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = [
    "as_decorator", "partial_decorator", "optional", 
    "optional_decorator", "optional_decorator_2", 
    "currying", "partialize", 
]

from functools import partial, update_wrapper as _update_wrapper
from inspect import signature
from typing import overload, Callable, Optional, TypeVar, Union


T = TypeVar('T')


def update_wrapper(f, g):
    if f is g:
        return f
    return _update_wrapper(f, g)


@overload
def as_decorator(
    f: Callable[..., T], 
    g: None, 
    /, 
) -> Callable[[Callable], Callable]:
    ...
@overload
def as_decorator(
    f: Callable[..., T], 
    g: Callable, 
    /, 
) -> Callable[[Callable], T]:
    ...
def as_decorator(f, g=None, /):
    '''This helper function is used to simplify the 
        boilerplate code when creating a decorator.

    :param f: decorator which is decorated by `as_decorator`.
    :param g: callable which is decorated by `f`.
    :return: a decorated callable, `f` is the decorator and
        g is the callable.

    Example::

        @as_decorator
        def foo(bar: Callable, /, *args, **kwargs):
            ...

        # Roughly equivalent to:

        from functools import update_wrapper

        def foo(bar: Callable, /):
            def wrapper(*args, **kwargs):
                ...
            return update_wrapper(wrapper, bar)
    '''
    fn = lambda g, /: update_wrapper(
        lambda *a, **k: f(g, *a, **k), g)
    if g is None:
        return update_wrapper(fn, f)
    return fn(g)


@overload
def partial_decorator(
    f: Callable[..., T], 
    g: None, 
    /, 
) -> Callable[[Callable], Callable]:
    ...
@overload
def partial_decorator(
    f: Callable[..., T], 
    g: Callable, 
    /, 
) -> Callable[[Callable], T]:
    ...
def partial_decorator(f, g=None, /):
    '''This helper function is used to simplify the 
        boilerplate code when creating a decorator.

    :param f: decorator which is decorated by `as_decorator`.
    :param g: callable which is decorated by `f`.
    :return: a decorated callable, `f` is the decorator and
        g is the callable.

    Example::

    @partial_decorator
    def foo(bar: Callable, /, *args, **kwargs):
        ...

    Roughly equivalent to:

    from functools import update_wrapper

    def foo(bar: Callable, /):
        def wrapper(*args, **kwargs):
            ...
        return update_wrapper(wrapper, bar)
    '''
    if g is None:
        return partial(partial_decorator, f)
    return partial(f, g)


@as_decorator
def optional(
    f: Callable[..., Callable], 
    g: Optional[Callable] = None, 
    /, 
    *args, 
    **kwargs, 
) -> Callable:
    '''
    This helper function decorates another decorator that having 
        optional parameters. Make sure that these optional 
        parameters have default values.

    Example1::

    Supposing there is such a decorator:

    >>> @optional
    def foo(bar, baz='baz'):
        def wrapped(fn, /, *args, **kwargs):
            print(bar)
            r = fn(*args, **kwargs)
            print(baz)
            return r
        return as_decorator(wrapped)
    ...

    - Use case 1:

    >>> @foo
    def baba1():
        print('baba1')
    
    Traceback (most recent call last):
        ...
    TypeError: foo() missing 1 required positional argument: 'bar'

    - Use case 2:

    >>> @foo('bar')
    def baba2():
        print('baba2')
    
    >>> baba2()
    bar
    baba2
    baz

    - Use case 3:

    >>> @foo(bar='bar')
    def baba3():
        print('baba3')
    
    >>> baba3()
    bar
    baba3
    baz

    Example2::

    Supposing there is such a decorator:

    >>> @optional
    def foo2(bar='bar', *, baz='baz'):
        def wrapped(fn, /, *args, **kwargs):
            print(bar)
            r = fn(*args, **kwargs)
            print(baz)
            return r
        return as_decorator(wrapped)

    - Use case 4:

    >>> @foo2
    def baba4(): 
        print('baba4') 
    
    >>> baba4()
    bar
    baba4
    baz

    - Use case 5:

    >>> @foo2()
    def baba5(): 
        print('baba5') 
    
    >>> baba5()
    bar
    baba5
    baz

    - Use case 6:

    >>> @foo2(None, 'bar: begin', baz='baz: end') 
    def baba6(): 
        print('baba6: process')
    
    >>> baba6()
    bar: begin
    baba6: process
    baz: end

    - Use case 7:

    >>> @foo2('bar: begin', baz='baz: end') 
    def baba7(): 
        print('baba7: process')
    
    >>> baba7()
    bar: begin
    baba7: process
    baz: end
    '''
    if g is None:
        return f(*args, **kwargs)
    elif callable(g):
        return f(*args, **kwargs)(g)
    else:
        return f(g, *args, **kwargs)


def optional_decorator(
    f: Callable[..., Callable], /
) -> Callable:
    """This helper function is used to simplify the 
        boilerplate code when creating a decorator.

    Example::

    @optional_decorator
    def foo(bar, /, *args, **kwds):
        ...
        def wrapper(*args2, **kwds2)
            ...
        return wrapper

    Roughly equivalent to:

    from functools import update_wrapper

    @optional
    def foo(*args, **kwds):
        def wrapped(bar, /):
            ...
            def wrapper(*args2, **kwds2):
                ...
            return update_wrapper(wrapper, bar)
        return wrapped
    """
    def wrapped(
        g: Optional[Callable] = None, 
        /, 
        *args, 
        **kwds, 
    ) -> Callable:
        if g is None:
            return lambda g: \
                update_wrapper(f(g, *args, **kwds), g)
        return update_wrapper(f(g, *args, **kwds), g)
    return update_wrapper(wrapped, f)


def optional_decorator_2(
    f: Callable[..., Callable], 
    g: Optional[Callable] = None, 
    /, 
    *args, 
    **kwds, 
) -> Callable:
    """This helper function is used to simplify the 
        boilerplate code when creating a decorator.

    Example::

    @optional_decorator_2
    def foo(bar, /, *args, **kwds):
        ...
        def wrapper(*args2, **kwds2)
            ...
        return wrapper

    Roughly equivalent to:

    from functools import update_wrapper

    @optional
    def foo(*args, **kwds):
        def wrapped(bar, /):
            ...
            def wrapper(*args2, **kwds2):
                ...
            return update_wrapper(wrapper, bar)
        return wrapped
    """
    fn = lambda g, a, k, /: update_wrapper(f(g, *a, **k), g)
    if g is None:
        def wrapped(g=None, /, *a, **k):
            a, k = (*args, *a), {**kwds, **k}
            return (lambda g: fn(g, a, k)) \
                if g is None else fn(g, a, k)
        return update_wrapper(wrapped, f)
    return fn(g, args, kwds)


def currying(
    f: Callable[..., T], /
) -> Callable[..., Union[Callable, T]]:
    """
    """
    bind = signature(f).bind
    def wrapper(*args, **kwargs):
        try:
            bind(*args, **kwargs)
        except TypeError as exc:
            if (exc.args 
                and isinstance(exc.args[0], str)
                and exc.args[0].startswith('missing a required argument:')
            ):
                return partial(wrapper, *args, **kwargs)
            raise
        else:
            return f(*args, **kwargs)
    return update_wrapper(wrapper, f)


def partialize(
    f: Optional[Callable[..., T]] = None, 
    /, 
    sentinel=None, 
) -> Callable[..., Union[Callable, T]]:
    """
    """
    if f is None:
        return partial(partialize, sentinel=sentinel)
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
                    and exc.args[0].startswith('missing a required argument:')
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


if __name__ == "__main__":
    import doctest
    print(doctest.testmod())

