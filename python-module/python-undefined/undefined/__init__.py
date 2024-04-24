#!/usr/bin/env python3
# coding: utf-8

from __future__ import annotations

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["Undefined", "undefined"]

from typing import final, Never


@final
class Undefined:
    __slots__: tuple[str, ...] = ()
    __instance__: Undefined

    def __new__(cls, /) -> Undefined:
        try:
            return cls.__instance__
        except AttributeError:
            inst = cls.__instance__ = super().__new__(cls)
            return inst

    def __init_subclass__(cls, /, **kwargs) -> Never:
        raise TypeError("Subclassing is not allowed")

    __bool__ = staticmethod(lambda: False) # type: ignore
    __eq__ = lambda self, other, /: self is other
    __hash__ = staticmethod(lambda: 0) # type: ignore
    __repr__ = staticmethod(lambda: "undefined") # type: ignore


undefined = Undefined()

