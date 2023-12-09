#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["funcproperty", "lazyproperty", "cacheproperty", "final_cacheproperty"]


class funcproperty:

    def __init__(self, func):
        self.__func__ = func
        self.__name__ = getattr(func, "__name__", None)
        self.__doc__  = getattr(func, "__doc__", None)

    def __repr__(self):
        return f"{type(self).__qualname__}({self.__func__!r})"

    def __set_name__(self, cls, name):
        self.__name__ = name

    def __get__(self, instance, cls):
        if instance is None:
            return self
        return self.__func__(instance)


class lazyproperty(funcproperty):

    def __get__(self, instance, cls):
        if instance is None:
            return self
        try:
            return self.__value__
        except AttributeError:
            val = self.__value__ = self.__func__(instance)
            return val

    def __delete__(self, instance):
        try:
            del self.__value__
        except AttributeError:
            pass


# NOTE: you can use `functools.cached_property` instead
class cacheproperty(funcproperty):

    def __get__(self, instance, cls):
        if instance is None:
            return self
        try:
            name = self.__name__
        except AttributeError:
            return self.__func__(instance)
        try:
            return instance.__dict__[name]
        except KeyError:
            val = self.__func__(instance)
            instance.__dict__[name] = val
            return val


class final_cacheproperty(cacheproperty):

    def __set__(self, instance, value):
        raise TypeError(f"can't set property: {self.__name__!r}")

