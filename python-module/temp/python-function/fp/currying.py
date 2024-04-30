#!/usr/bin/env python3
# coding: utf-8

"""
4 decorators (as below) are provided to implement `currying` for Python functions:
    - currying 👍
    - partial_currying
    - fast_currying
    - Currying 👍
"""

__author__  = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = ["currying", "partial_currying", "fast_currying", "Args", "Currying"]

import inspect

from functools import partial, update_wrapper
from inspect import signature
from types import MappingProxyType


def currying(func, /):
    bind = signature(func).bind
    attrs = [(attr, getattr(func, attr))
             for attr in ("__module__", "__name__", "__qualname__", 
                          "__doc__", "__annotations__")
             if hasattr(func, attr)]

    def wrap(_pf, /):
        def wrapper(*args, **kwargs):
            args = _pf.args + args
            kwargs = {**_pf.keywords, **kwargs}
            try:
                bind(*args, **kwargs)
            except TypeError as exc:
                if (exc.args 
                    and isinstance(exc.args[0], str)
                    and exc.args[0].startswith("missing a required argument:")
                ):
                    return wrap(partial(func, *args, **kwargs))
                raise
            else:
                return func(*args, **kwargs)

        _pf.__dict__.update(attrs)
        wrapper.args = _pf.args
        wrapper.kwargs = _pf.keywords
        wrapper.keywords = _pf.keywords

        return update_wrapper(wrapper, _pf)

    return wrap(partial(func))


def partial_currying(func, /):
    bind = signature(func).bind

    def wrapper(*args, **kwargs):
        try:
            bind(*args, **kwargs)
        except TypeError as exc:
            if (exc.args 
                and isinstance(exc.args[0], str)
                and exc.args[0].startswith("missing a required argument:")
            ):
                return partial(wrapper, *args, **kwargs)
            raise

        return func(*args, **kwargs)

    return update_wrapper(wrapper, func)


def fast_currying(func, /, _args=(), _kwargs={}, _idfn=None):
    if _idfn is None:
        _sig_str = str(inspect.Signature([
            p.replace(annotation=inspect._empty) 
            for p in signature(func).parameters.values()
        ]))[1:-1]
        _idfn = eval(f"lambda %s: None" % _sig_str)

    def wrapper(*args, **kwargs):
        args = _args + args
        kwargs = {**_kwargs, **kwargs}

        try:
            _idfn(*args, **kwargs)
        except TypeError as exc:
            if (exc.args 
                and isinstance(exc.args[0], str)
                and exc.args[0].startswith("<lambda>() missing ")
            ):
                return fast_currying(func, args, kwargs, _idfn)
            raise
        else:
            return func(*args, **kwargs)

    wrapper.args = _args
    wrapper.kwargs = _kwargs
    wrapper.keywords = _kwargs

    return update_wrapper(wrapper, func)


class Args:

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwds = MappingProxyType(kwargs)

    @property
    def args(self):
        return self._args

    @property
    def kwargs(self):
        return self._kwds

    @property
    def keywords(self):
        return self._kwds

    def __call__(self, func, /):
        return func(*self._args, **self._kwds)


class Currying:

    def __init__(self, func, args=(), kwargs={}):
        if isinstance(func, Currying):
            args = func._args + args
            kwargs = {**func._kwds, **kwargs}
            func = func._func
            self.__dict__.update(func.__dict__)
        else:
            self.__dict__.update(
                (attr, getattr(func, attr))
                for attr in ("__module__", "__name__", "__qualname__", 
                             "__doc__", "__annotations__")
                if hasattr(func, attr)
            )

        self._func = func
        self._args = args
        self._kwds = MappingProxyType(kwargs)
        self._signature = signature(partial(func, *args, **kwargs))

    @property
    def signature(self):
        return self._signature

    @property
    def func(self):
        return self._func

    @property
    def args(self):
        return self._args

    @property
    def kwargs(self):
        return self._kwds

    @property
    def keywords(self):
        return self._kwds

    def __repr__(self):
        return self._func.__qualname__ + str(self._signature)

    def __call__(self, *args, **kwargs):
        try:
            self._signature.bind(*args, **kwargs)
        except TypeError as exc:
            if (exc.args
                and isinstance(exc.args[0], str)
                and exc.args[0].startswith("missing a required argument:")
            ):
                return type(self)(self, args, kwargs)
            raise
        args = self._args + args
        kwargs = {**self._kwds, **kwargs}
        return self._func(*args, **kwargs)

    def __lshift__(self, arg):
        if type(arg) is Args:
            return arg(self)
        else:
            return self(arg)

    __add__ = __radd__ = __rrshift__ = __lshift__

    def __mul__(self, arg):
        arg_type = type(arg)
        if arg_type is tuple:
            return self(*arg)
        elif arg_type is dict:
            return self(**arg)
        elif arg_type is Args:
            return arg(self)
        else:
            return self(arg)

    __rmul__ = __mul__

