#!/usr/bin/env python3
# coding: utf-8

from __future__ import annotations

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = ["Undefined", "undefined"]

from typing import final, Never, Self


class Undefined:
    """Just like `None` and `NoneType`, which are used to mark missing values.
    """
    __slots__: tuple[str, ...] = ()
    __instance__: Self

    def __new__(cls, /) -> Self:
        try:
            return cls.__dict__["__instance__"]
        except KeyError:
            inst = cls.__instance__ = super().__new__(cls)
            return inst

    __bool__ = staticmethod(lambda: False)
    __eq__ = lambda self, other, /: self is other or NotImplemented
    __hash__ = staticmethod(lambda: 0) # type: ignore
    __repr__ = staticmethod(lambda: "undefined") # type: ignore


undefined = Undefined()

