#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = ["FIFODict", "LRUDict", "LFUDict", "TTLDict", "TLRUDict"]

from collections.abc import Callable, ItemsView, Mapping
from heapq import nlargest, nsmallest
from math import inf, isinf, isnan
from operator import itemgetter
from time import time
from typing import overload, Literal

from undefined import undefined


class FIFODict[K, V](dict[K, V]):
    __slots__ = ("maxsize", "auto_clean")

    def __init__(
        self, 
        /, 
        maxsize: int = 0, 
        auto_clean: bool = True, 
    ):
        self.maxsize = maxsize
        self.auto_clean = auto_clean

    def __repr__(self, /) -> str:
        return super().__repr__()

    def __setitem__(self, key: K, value: V, /):
        super().pop(key, None)
        super().__setitem__(key, value)
        if self.auto_clean:
            self.clean()

    def clean(self, /):
        if self and (maxsize := self.maxsize) > 0:
            keys = super().keys()
            pop = super().pop
            while len(keys) > maxsize:
                try:
                    pop(next(iter(keys)), None)
                except RuntimeError:
                    pass
                except StopIteration:
                    break

    def popitem(self, /) -> tuple[K, V]:
        try:
            keys = super().keys()
            while keys:
                try:
                    key = next(iter(keys))
                    val = super().pop(key)
                    return key, val
                except (KeyError, RuntimeError):
                    pass
        except StopIteration:
            pass
        raise KeyError(f"{self!r} is empty")

    def setdefault(self, key: K, default: V, /) -> V:
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


class LRUDict[K, V](FIFODict[K, V]):
    __slots__ = ("maxsize", "auto_clean")

    def __getitem__(self, key: K, /) -> V:
        value = super().pop(key)
        super().__setitem__(key, value)
        return value

    @overload
    def get(self, key: K, /) -> None | V:
        ...
    @overload
    def get[T](self, key: K, default: V | T, /) -> V | T:
        ...
    def get(self, key: K, default = None, /):
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: K, default: V, /) -> V:
        value = super().pop(key, default)
        super().__setitem__(key, value)
        if self.auto_clean:
            self.clean()
        return value


class Counter[K](dict[K, int]):

    def __missing__(self, key: K, /) -> Literal[0]:
        return 0

    def max(self, /) -> tuple[K, int]:
        try:
            return max(self.items(), key=itemgetter(1))
        except ValueError as e:
            raise KeyError("dictionary is empty") from e

    def min(self, /) -> tuple[K, int]:
        try:
            return min(self.items(), key=itemgetter(1))
        except ValueError as e:
            raise KeyError("dictionary is empty") from e

    def most_common(
        self, 
        n: None | int = None, 
        /, 
        largest: bool = True, 
    ) -> list[tuple[K, int]]:
        if n is None:
            return sorted(self.items(), key=itemgetter(1), reverse=largest)
        if largest:
            return nlargest(n, self.items(), key=itemgetter(1))
        else:
            return nsmallest(n, self.items(), key=itemgetter(1))


class LFUDict[K, V](dict[K, V]):
    __slots__ = ("maxsize", "auto_clean")

    def __init__(
        self, 
        /, 
        maxsize: int = 0, 
        auto_clean: bool = True, 
    ):
        self.maxsize = maxsize
        self.auto_clean = auto_clean
        self._counter: Counter[K] = Counter()

    def __delitem__(self, key: K, /):
        super().__delitem__(key)
        self._counter.pop(key, None)

    def __getitem__(self, key: K, /) -> V:
        value = super().__getitem__(key)
        self._counter[key] += 1
        return value

    def __repr__(self, /) -> str:
        return super().__repr__()

    def __setitem__(self, key: K, value: V, /):
        super().__setitem__(key, value)
        self._counter[key] += 1
        if self.auto_clean:
            self.clean()

    def clean(self, /):
        if self and (maxsize := self.maxsize) > 0:
            keys = super().keys()
            pop = self.pop
            most_common = self._counter.most_common
            while (diff := len(keys) - maxsize) > 0:
                try:
                    for key, _ in most_common(diff, largest=False):
                        pop(key, None)
                except RuntimeError:
                    pass

    @overload
    def get(self, key: K, /) -> None | V:
        ...
    @overload
    def get[T](self, key: K, default: V | T, /) -> V | T:
        ...
    def get(self, key: K, default = None, /):
        try:
            return self[key]
        except KeyError:
            return default

    @overload
    def pop(self, key: K, /) -> V:
        ...
    @overload
    def pop(self, key: K, default: V, /) -> V:
        ...
    @overload
    def pop[T](self, key: K, default: T, /) -> V | T:
        ...
    def pop(self, key: K, default = undefined, /):
        value = super().pop(key, default)
        self._counter.pop(key, None)
        if value is undefined:
            raise KeyError(key)
        return value

    def popitem(self, /) -> tuple[K, V]:
        get_min = self._counter.min
        pop = self.pop
        while self:
            key, _ = get_min()
            try:
                return key, pop(key)
            except KeyError:
                pass
        raise KeyError(f"{self!r} is empty")

    def setdefault(self, key: K, default: V) -> V:
        value = super().setdefault(key, default)
        self._counter[key] += 1
        if self.auto_clean:
            self.clean()
        return value

    def update(self, /, *args, **pairs):
        setitem = super().__setitem__
        counter = self._counter
        for arg in args:
            if isinstance(arg, Mapping):
                try:
                    arg = arg.items()
                except (AttributeError, TypeError):
                    arg = ItemsView(arg)
            for key, val in arg:
                setitem(key, val)
                counter[key] += 1
        if pairs:
            for key, val in pairs.items():
                setitem(key, val)
                counter[key] += 1
        if self.auto_clean:
            self.clean()


class TTLDict[K, V](dict[K, V]):
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

    def __delitem__(self, key: K, /):
        super().__delitem__(key)
        self._ttl_cache.pop(key, None)

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
        if not self:
            return
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

    @overload
    def get(self, key: K, /) -> None | V:
        ...
    @overload
    def get[T](self, key: K, default: V | T, /) -> V | T:
        ...
    def get(self, key: K, default = None, /):
        try:
            return self[key]
        except KeyError:
            return default

    @overload
    def pop(self, key: K, /) -> V:
        ...
    @overload
    def pop(self, key: K, default: V, /) -> V:
        ...
    @overload
    def pop[T](self, key: K, default: T, /) -> V | T:
        ...
    def pop(self, key: K, default = undefined, /):
        value = super().pop(key, default)
        self._ttl_cache.pop(key, None)
        if value is undefined:
            raise KeyError(key)
        return value

    def popitem(self, /) -> tuple[K, V]:
        try:
            keys = super().keys()
            while keys:
                try:
                    key = next(iter(keys))
                    val = super().pop(key)
                    return key, val
                except (KeyError, RuntimeError):
                    pass
        except StopIteration:
            pass
        raise KeyError(f"{self!r} is empty")

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


class TLRUDict[K, V](LRUDict[K, tuple[int, V]]):

    __slots__ = ("maxsize", "auto_clean")

    def __contains__(self, key, /) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __getitem__(self, key: K) -> tuple[int, V]:
        value = expire_ts, _ = super().__getitem__(key)
        if time() >= expire_ts:
            self.pop(key, None)
            raise KeyError(key)
        return value

    def setdefault(self, key: K, default: tuple[int, V], /) -> tuple[int, V]:
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

# TODO: 参考 cachetools 和 diskcache 等第三方模块，再添加几种缓存类型
