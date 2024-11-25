#!/usr/bin/env python3
# coding: utf-8

from __future__ import annotations

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["Placeholder", "_"]

from typing import final, Never

from undefined import Undefined, undefined


@final
class Placeholder(Undefined):
    __slots__: tuple[str, ...] = ()

    def __init_subclass__(cls, /, **kwargs) -> Never:
        raise TypeError("Subclassing is not allowed")

    __eq__ = lambda self, other, /: self is other or other is undefined # type: ignore
    __repr__ = staticmethod(lambda: "_") # type: ignore


_ = Placeholder()

