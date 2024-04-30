#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = ["is_nominal_subclass", "inst_hasattr", "is_buffer"]


def is_nominal_subclass(cls, class_or_tuple, /):
    if isinstance(class_or_tuple, tuple):
        return cls in class_or_tuple.__mro__
    else:
        return any(cls in b.__mro__ for b in class_or_tuple)


def inst_hasattr(obj, attr):
    if isinstance(obj, type):
        return (
            attr == "__dict__" or 
            any(attr in b.__dict__ for b in obj.__mro__)
        )
    if attr == "__dict__":
        return hasattr(obj, "__dict__")
    if hasattr(obj, "__dict__"):
        return attr in obj.__dict__
    if hasattr(obj, "__slots__"):
        return attr in obj.__slots__
    return False


def is_buffer(obj):
    try:
        return (
            isinstance(obj, (bytes, bytearray, memoryview)) or 
            (
                inst_hasattr(type(obj), '__getitem__') and 
                inst_hasattr(type(obj), '__len__') and 
                hasattr(obj, 'tobytes')
            )
        )
    except TypeError:
        return False

