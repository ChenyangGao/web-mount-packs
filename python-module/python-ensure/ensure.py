#!/usr/bin/env python3
# coding: utf-8

"""这个模块提供了一些与 确保返回值的类型 有关的工具函数
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 2)
__all__ = [
    "ensure_awaitable", "ensure_cm", "ensure_acm", "ensure_enum", 
    "ensure_str", "ensure_bytes", "ensure_functype", 
]

from contextlib import asynccontextmanager, contextmanager
from functools import update_wrapper
from inspect import isawaitable
from sys import byteorder
from typing import AsyncContextManager, ContextManager
from types import FunctionType

from .type import is_buffer
from undefined import undefined


async def ensure_awaitable(o, /):
    if isawaitable(o):
        return await o
    return o


@contextmanager
def _cm(yield_=None, /):
    yield yield_


def ensure_cm(
    o, /, default=undefined
) -> ContextManager:
    if isinstance(o, ContextManager):
        return o
    elif default is undefined:
        default = o
    return _cm(o)


@asynccontextmanager
async def _acm(yield_=None, /):
    yield yield_


def ensure_acm(
    o, /, default=undefined
) -> AsyncContextManager:
    if isinstance(o, AsyncContextManager):
        return o
    elif default is undefined:
        default = o
    return _acm(o)


def ensure_enum(cls, val):
    if isinstance(val, cls):
        return val
    try:
        if isinstance(val, str):
            return cls[val]
    except KeyError:
        pass
    return cls(val)


def ensure_str(obj) -> str:
    if isinstance(obj, str):
        return obj
    elif is_buffer(obj):
        return str(obj, "utf-8")
    return str(obj)


def ensure_bytes(obj) -> bytes:
    if isinstance(obj, str):
        return bytes(obj, "utf-8")
    elif isinstance(obj, int):
        return obj.to_bytes((obj.bit_length()+7)//8, byteorder)
    return bytes(obj)


def ensure_functype(f, /):
    if isinstance(f, FunctionType):
        return f
    elif callable(f):
        return update_wrapper(
            lambda *args, **kwds: f(*args, **kwds), f)
    raise TypeError

