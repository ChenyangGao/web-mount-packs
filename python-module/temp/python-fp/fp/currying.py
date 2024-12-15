#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["currying", "fast_currying", "partialize"]

from functools import partial, update_wrapper
from inspect import _empty as empty, signature
from typing import Any

def make_idfn(func, /):
    last_kind = -1
    ls: list[str] = []
    ns: dict[str, Any] = {}
    add = ls.append
    for name, param in signature(func).parameters.items():
        kind = param.kind
        default = param.default
        if kind != last_kind:
            if last_kind == 0:
                add("/")
            if kind == 3 and last_kind != 2:
                add("*")
        if kind == 2:
            add("*"+name)
        elif kind == 4:
            add("**"+name)
        elif default is empty:
            add(name)
        else:
            ns[name] = default
            add(f"{name}={name}")
        last_kind = kind
    idfn = eval("lambda %s: None" % ", ".join(ls), ns)
    if isinstance(func, partial):
        func = func.func
    if name := getattr(func, "__qualname__", ""):
        idfn.__qualname__ = name
    return idfn

def update_partialed_wrapper(wrapper, wrapped):
    if isinstance(wrapped, partial):
        update_wrapper(wrapper, wrapped.func)
        wrapper.__wrapped__ = wrapped
        return wrapper
    else:
        return update_wrapper(wrapper, wrapped)

def currying(func, /, *args, **kwargs):
    pf = partial(func, *args, **kwargs)
    def wrap(pf, /):
        idfn = make_idfn(pf)
        sentinel = idfn.__qualname__ + "() missing "
        def wrapper(*args, **kwargs):
            try:
                idfn(*args, **kwargs)
            except TypeError as exc:
                if (exc.args and isinstance(exc.args[0], str)
                    and exc.args[0].startswith(sentinel)
                ):
                    if not args and not kwargs:
                        return wrapper
                    return wrap(partial(pf, *args, **kwargs))
                raise
            return pf(*args, **kwargs)
        return update_partialed_wrapper(wrapper, pf)
    return wrap(pf)

def fast_currying(func, /, *args, **kwargs):
    pf = partial(func, *args, **kwargs)
    name = pf.func.__qualname__
    sentinel = (f"{name}() missing ", f"{name} expected ", f"{name}() must have ")
    def wrapper(*args, **kwargs):
        args = pf.args + args
        kwargs = {**pf.keywords, **kwargs}
        try:
            return func(*args, **kwargs)
        except TypeError as exc:
            if (exc.args and isinstance(exc.args[0], str)
                and exc.args[0].startswith(sentinel)
            ):
                if not args and not kwargs:
                    return wrapper
                return fast_currying(func, *args, **kwargs)
            raise
    return update_partialed_wrapper(wrapper, pf)

def partialize(func, /, *args, **kwargs):
    idfn = make_idfn(func)
    sentinel = f"{idfn.__qualname__}() missing "
    def wrapper(*args, **kwargs):
        try:
            idfn(*args, **kwargs)
        except TypeError as exc:
            if (exc.args and isinstance(exc.args[0], str)
                and exc.args[0].startswith(sentinel)
            ):
                return partial(wrapper, *args, **kwargs)
            raise 
        return func(*args, **kwargs)
    update_partialed_wrapper(wrapper, func)
    return partial(wrapper, *args, **kwargs)


class Args:

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwds = kwargs

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

