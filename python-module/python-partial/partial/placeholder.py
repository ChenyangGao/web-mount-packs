#!/usr/bin/env python3
# coding: utf-8

from __future__ import annotations

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["Placeholder", "_"]

from typing import final, Never


@final
class Placeholder:
    __slots__ = ()
    __instance__: Placeholder

    def __new__(cls, /) -> Placeholder:
        try:
            return cls.__instance__
        except AttributeError:
            inst = cls.__instance__ = super().__new__(cls)
            return inst

    def __init_subclass__(cls, /, **kwargs) -> Never:
        raise TypeError("Subclassing is not allowed")

    __bool__ = staticmethod(lambda: False)
    __eq__ = lambda self, other, /: self is other
    __hash__ = staticmethod(lambda: 0) # type: ignore
    __repr__ = staticmethod(lambda: "_") # type: ignore


_ = Placeholder()

