#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["LRUDict", "TTLDict"]

from collections.abc import Callable, ItemsView, Mapping
from math import inf, isinf, isnan
from time import time


class LRUDict[K, V](dict):
    __slots__ = ("maxsize", "auto_clean")

    def __init__(
        self, 
        /, 
        maxsize: int = 0, 
        auto_clean: bool = True, 
    ):
        self.maxsize = maxsize
        self.auto_clean = auto_clean

    def __setitem__(self, key: K, value: V, /):
        super().pop(key, None)
        super().__setitem__(key, value)
        if self.auto_clean:
            self.clean()

    def clean(self, /):
        if (maxsize := self.maxsize) > 0:
            keys = super().keys()
            pop = super().pop
            while len(keys) > maxsize:
                try:
                    pop(next(iter(keys)), None)
                except RuntimeError:
                    pass
                except StopIteration:
                    break

    def setdefault(self, key: K, default: V) -> V: # type: ignore
        value = super().setdefault(key, default)
        if self.auto_clean:
            self.clean()
        return value

    def update(self, /, *args, **pairs):
        pop = super().pop
        setitem = super().__setitem__
        for arg in args:
            if isinstance(arg, Mapping):
                try:
                    arg = arg.items()
                except (AttributeError, TypeError):
                    arg = ItemsView(arg)
            for key, val in arg:
                pop(key, None)
                setitem(key, val)
        if pairs:
            for key, val in pairs.items():
                pop(key, None)
                setitem(key, val)
        if self.auto_clean:
            self.clean()


class TTLDict[K, V](dict):
    __slots__ = ("maxsize", "ttl", "timer", "auto_clean", "_ttl_cache")

    def __init__(
        self, 
        /, 
        maxsize: int = 0, 
        ttl: int | float = inf, 
        timer: Callable[[], int | float] = time, 
        auto_clean: bool = True, 
    ):
        self.maxsize = maxsize
        self.ttl = ttl
        self.timer = timer
        self.auto_clean = auto_clean
        self._ttl_cache: dict[K, int | float] = {}

    def __contains__(self, key, /) -> bool:
        if self.auto_clean:
            self.clean()
        return super().__contains__(key)

    def __getitem__(self, key: K, /) -> V:
        value = super().__getitem__(key)
        ttl = self.ttl
        if isinf(ttl) or isnan(ttl) or ttl <= 0:
            return value
        ttl_cache = self._ttl_cache
        start = ttl_cache[key]
        diff = ttl + start - self.timer()
        if diff <= 0:
            super().pop(key, None)
            ttl_cache.pop(key, None)
            if diff:
                raise KeyError(key)
        return value

    def __repr__(self, /) -> str:
        if self.auto_clean:
            self.clean()
        return super().__repr__()

    def __setitem__(self, key: K, value: V, /):
        ttl_cache = self._ttl_cache
        super().__setitem__(key, value)
        ttl_cache.pop(key, None)
        ttl_cache[key] = self.timer()
        if self.auto_clean:
            self.clean()

    def clean(self, /):
        ttl_cache = self._ttl_cache
        t_pop = ttl_cache.pop
        pop = super().pop
        if (maxsize := self.maxsize) > 0:
            keys = ttl_cache.keys()
            while len(keys) > maxsize:
                try:
                    key = next(iter(keys))
                    pop(key, None)
                    t_pop(key, None)
                except RuntimeError:
                    pass
                except StopIteration:
                    break
        ttl = self.ttl
        if isinf(ttl) or isnan(ttl) or ttl <= 0:
            return
        thres = self.timer() - ttl
        items = ttl_cache.items()
        while True:
            try:
                key, val = next(iter(items))
                if val > thres:
                    break
                pop(key, None)
                t_pop(key, None)
            except StopIteration:
                break
            except RuntimeError:
                pass

    def setdefault(self, key: K, default: V, /) -> V: # type: ignore
        value = super().setdefault(key, default)
        self._ttl_cache.setdefault(key, self.timer())
        if self.auto_clean:
            self.clean()
        return value

    def update(self, *args, **pairs):
        ttl_cache = self._ttl_cache
        t_pop = ttl_cache.pop
        t_set = ttl_cache.__setitem__
        timer = self.timer
        setitem = super().__setitem__
        for arg in args:
            if isinstance(arg, Mapping):
                try:
                    arg = arg.items()
                except (AttributeError, TypeError):
                    arg = ItemsView(arg)
            for key, val in arg:
                setitem(key, val)
                t_pop(key, None)
                t_set(key, timer())
        if pairs:
            for key, val in pairs.items():
                setitem(key, val)
                t_pop(key, None)
                t_set(key, timer())
        if self.auto_clean:
            self.clean()

