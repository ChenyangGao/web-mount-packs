#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["LRUDict"]

from collections.abc import ItemsView, Mapping


class LRUDict(dict):

    def __init__(self, /, maxsize: int = 0):
        self.maxsize = maxsize

    def __setitem__(self, key, value, /):
        self.pop(key, None)
        super().__setitem__(key, value)
        self.clean()

    def clean(self, /):
        if (maxsize := self.maxsize) > 0:
            pop = self.pop
            while len(self) > maxsize:
                try:
                    pop(next(iter(self)), None)
                except RuntimeError:
                    pass

    def setdefault(self, key, default=None, /):
        value = super().setdefault(key, default)
        self.clean()
        return value

    def update(self, iterable=None, /, **pairs):
        pop = self.pop
        setitem = self.__setitem__
        if iterable:
            if isinstance(iterable, Mapping):
                try:
                    iterable = iterable.items()
                except (AttributeError, TypeError):
                    iterable = ItemsView(iterable)
            for key, val in iterable:
                pop(key, None)
                setitem(key, val)
        if pairs:
            for key, val in pairs.items():
                pop(key, None)
                setitem(key, val)
        self.clean()

