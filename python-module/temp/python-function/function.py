#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import collections
import functools
import inspect
import types
import traceback
import wrapt



__version__ = '0.1'
__all__ = []
reg = wrapt.register(__all__)


def getfnself():
    f = sys._getframe(1)
    return f.f_globals[f.f_code.co_name]


def bindfunc(obj, func=undefined, /):
    if func is undefined:
        return partial(getfnself(), obj)
    setattr(obj, f.__name__, f)
    return f

@reg
def make_lambda(expr_str, args='x'):
    return eval(f'lambda {args}: {expr_str}')


@reg
def invoke_method(obj, attr, *args, **kwds):
    return getattr(obj, attr)(*args, **kwds)


@reg
def chain_func_with_arg(*functions):
    compound = lambda f, g: g(f)
    return lambda arg: functools.reduce(compound, functions, arg)

@reg
def chain_func(*functions):
    function0 = functions[0]
    def chain_func(*args, **kwds):
        r = function0(*args, **kwds)
        for f in functions[1:]:
            r = f(r)
        else:
            return r
    try:
        chain_func.__signature__ = inspect.signature(function0)
    except ValueError:
        pass
    return chain_func


@reg
@wrapt.decorator
def run_but_return_args(func, *args, **kwds):
    if callable(func):
        func(*args, **kwds)
    if args and kwds:
        return args, kwds
    elif kwds:
        return kwds
    elif args:
        if len(args) == 1:
            return args[0]
        return args

@reg
@wrapt.decorator
def run_by_arg_case(func, arg):
    if type(arg) is tuple:
        if len(arg) == 2:
            args, kwds = arg
            if type(args) is tuple and type(kwds) is dict:
                return func(*args, **kwds)
        return func(*arg)
    elif type(arg) is dict:
        return func(**arg)
    return func(arg)

@reg
@wrapt.decorator
def run_by_arg_type(func, arg):
    if isinstance(arg, collections.abc.Mapping):
        return func(**arg)
    elif isinstance(arg, collections.abc.Iterable):
        return func(*arg)
    else:
        func(arg)


_Args = collections.namedtuple('Args', 'args kwargs')

@reg
@wrapt.decorator
def run_return_args(func, *args, **kwds):
    if callable(func):
        func(*args, **kwds)
    return _Args(args, kwds)

@reg
@wrapt.decorator
def run_by_arg(func, arg):
    assert type(arg) is _Args
    args, kwds = arg
    return func(*args, **kwds)


@reg
@wrapt.optional
def ensure_return(catch_exceptions=Exception):
    @wrapt.decorator
    def wrapper(func, *args, **kwds):
        try:
            return func(*args, **kwds)
        except catch_exceptions:
            if __debug__:
                traceback.print_exc()
            return run_but_return_args(None)(*args, **kwds)
    return wrapper


@reg
class Wrapper:
    def __init__(self, func):
        functools.update_wrapper(self, func)

    def __call__(self, *args, **kwds):
        return self.__wrapped__(*args, **kwds)

    def __get__(self, instance, cls):
        if instance is None:
            return self
        else:
            return types.MethodType(self, instance)

@reg
def key_map(iterable, maps=None, default=lambda x: x, key=lambda x: x):
    if maps is None:
        if callable(default):
            yield from map(default, iterable)
        else:
            for item in iterable:
                yield default
        return
    for item in iterable:
        map_ = maps.get(key(item), default)
        if callable(map_):
            yield map_(item)
        else:
            yield map_

@reg
def type_map(iterable, val_maps=None, type_maps=None, default=lambda x: x):
    for item in iterable:
        try:
            map_ = val_maps[item]
        except (KeyError, TypeError):
            try:
                map_ = type_maps[type(item)]
            except (KeyError, TypeError):
                map_ = default
        if callable(map_):
            yield map_(item)
        else:
            yield map_

