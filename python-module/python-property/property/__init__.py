#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = ["funcproperty", "lazyproperty", "cacheproperty", "final_cacheproperty"]

from collections.abc import Callable
from threading import Lock
from types import GenericAlias, MethodType
from typing import Any


class funcproperty:
    __slots__ = ("__func__", "__name__", "__doc__", "__is_method__")

    def __init__(self, func: Callable, /):
        self.__func__ = func
        self.__name__ = getattr(func, "__name__", "")
        self.__doc__ = getattr(func, "__doc__", None)
        self.__is_method__ = isinstance(func, (staticmethod, classmethod, MethodType))

    def __repr__(self, /):
        return f"{type(self).__qualname__}({self.__func__!r})"

    def __set_name__(self, cls, name: str, /):
        self.__name__ = name

    def __get__(self, instance, cls, /):
        if instance is None:
            return self
        if self.__is_method__:
            return self.__func__()
        else:
            return self.__func__(instance)

    __class_getitem__: classmethod = classmethod(GenericAlias)


class lazyproperty(funcproperty):

    def __get__(self, instance, cls, /):
        if instance is None:
            return self
        key = "__value__" if self.__is_method__ else instance
        try:
            return self.__dict__[key]
        except KeyError:
            val = self.__dict__[key] = self.__func__() if self.__is_method__ else self.__func__(instance)
            return val

    def __delete__(self, instance, /):
        self.__dict__.pop("__value__" if self.__is_method__ else instance, None)


class cacheproperty(funcproperty):
    __slots__ = ("__func__", "__name__", "__doc__", "__is_method__")

    def __get__(self, instance, cls, /):
        if instance is None:
            return self
        name = self.__name__
        try:
            return instance.__dict__[name]
        except KeyError:
            val = instance.__dict__[name] = self.__func__() if self.__is_method__ else self.__func__(instance)
            return val


class locked_cacheproperty(cacheproperty):

    def __get__(self, instance, cls, /):
        with self.__dict__.setdefault(instance, Lock()):
            return super().__get__(instance, cls)


class final_cacheproperty(cacheproperty):
    __slots__ = ("__func__", "__name__", "__doc__", "__is_method__")

    def __set__(self, instance, value, /):
        raise TypeError(f"can't set property: {self.__name__:r}")

    def __delete__(self, instance, /):
        raise TypeError(f"can't delete attribute: {self.__name__:r}")

