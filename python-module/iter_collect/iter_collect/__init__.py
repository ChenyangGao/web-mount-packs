#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = [
    "collect_as_mapping", "group", "uniq", "dups", "iter_dups", "iter_keyed_dups", 
]

from collections.abc import Iterable, Iterator, MutableMapping
from typing import cast, overload, Any, Callable, Literal, Optional, Protocol, TypeVar


K = TypeVar("K")
V = TypeVar("V")


class SupportsLT(Protocol):
    def __lt__(self, o) -> bool:
        ...


@overload
def collect_as_mapping(
    it: Iterable[tuple[K, V]], 
    /, 
    mapping: None = None, 
) -> dict[K, list[V]]:
    ...
@overload
def collect_as_mapping(
    it: Iterable[tuple[K, V]], 
    /, 
    mapping: MutableMapping[K, list[V]], 
) -> MutableMapping[K, list[V]]:
    ...
def collect_as_mapping(
    it: Iterable[tuple[K, V]], 
    /, 
    mapping: Optional[MutableMapping[K, list[V]]] = None, 
) -> MutableMapping[K, list[V]]:
    if mapping is None:
        mapping = {}
    for k, v in it:
        try:
            mapping[k].append(v)
        except KeyError:
            mapping[k] = [v]
    return mapping


@overload
def group(
    it: Iterable[V], 
    /, 
    key: None = None, 
) -> dict[V, list[V]]:
    ...
@overload
def group(
    it: Iterable[tuple[K, V]], 
    /, 
    key: Literal[True] = True, 
) -> dict[K, list[V]]:
    ...
@overload
def group(
    it: Iterable[V], 
    /, 
    key: Callable[[V], K], 
) -> dict[K, list[V]]:
    ...
def group(
    it: Iterable, 
    /, 
    key: None | Literal[True] | Callable = None, 
) -> dict[Any, list]:
    items: Iterable[tuple[Any, Any]]
    if key is None:
        items = ((e, e) for e in it)
    elif key is True:
        items = it
    else:
        items = ((key(e), e) for e in it)
    return collect_as_mapping(items)


@overload
def uniq(
    it: Iterable[V], 
    /, 
    key: None = None, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> dict[V, V]:
    ...
@overload
def uniq(
    it: Iterable[tuple[K, V]], 
    /, 
    key: Literal[True] = True, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> dict[K, V]:
    ...
@overload
def uniq(
    it: Iterable[V], 
    /, 
    key: Callable[[V], K], 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> dict[K, V]:
    ...
def uniq(
    it: Iterable, 
    /, 
    key: None | Literal[True] | Callable = None, 
    keep_first: bool | Callable[..., SupportsLT] = True, 
) -> dict:
    items: Iterable[tuple[Any, Any]]
    if key is None:
        items = ((e, e) for e in it)
    elif key is True:
        items = it
    else:
        items = ((key(e), e) for e in it)
    d: dict = {}
    setitem: Callable
    if keep_first is True:
        setitem = d.setdefault
    elif keep_first is False:
        setitem = d.__setitem__
    else:
        cache: dict[Any, SupportsLT] = {}
        def setitem(k, v):
            cp = keep_first(v)
            if k in cache:
                kp = cache[k]
                if cp < kp:
                    d[k] = v
                else:
                    return
            cache[k] = cp
    for k, v in items:
        setitem(k, v)
    return d


@overload
def dups(
    it: Iterable[V], 
    /, 
    key: None = None, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> MutableMapping[V, list[V]]:
    ...
@overload
def dups(
    it: Iterable[tuple[K, V]], 
    /, 
    key: Literal[True] = True, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> MutableMapping[K, list[V]]:
    ...
@overload
def dups(
    it: Iterable[V], 
    /, 
    key: Callable[[V], K], 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> MutableMapping[K, list[V]]:
    ...
def dups(
    it: Iterable, 
    /, 
    key: None | Literal[True] | Callable = None, 
    keep_first: bool | Callable[..., SupportsLT] = True, 
) -> dict[Any, list]:
    return collect_as_mapping(iter_keyed_dups(it, key, keep_first=keep_first))


@overload
def iter_dups(
    it: Iterable[V], 
    /, 
    key: None = None, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> Iterator[V]:
    ...
@overload
def iter_dups(
    it: Iterable[tuple[K, V]], 
    /, 
    key: Literal[True] = True, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> Iterator[V]:
    ...
@overload
def iter_dups(
    it: Iterable[V], 
    /, 
    key: Callable[[V], K], 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> Iterator[V]:
    ...
def iter_dups(
    it: Iterable, 
    /, 
    key: None | Literal[True] | Callable = None, 
    keep_first: bool | Callable[..., SupportsLT] = True, 
) -> Iterator:
    items: Iterable[tuple[Any, Any]]
    if key is None:
        items = ((e, e) for e in it)
    elif key is True:
        items = it
    else:
        items = ((key(e), e) for e in it)
    if keep_first is True:
        s: set = set()
        add = s.add
        for k, v in items:
            if k in s:
                yield v
            else:
                add(k)
    elif keep_first is False:
        d: dict = {}
        for k, v in items:
            if k in d:
                yield d[k]
            d[k] = v
    else:
        cache: dict[Any, tuple[SupportsLT, Any]] = {}
        for k, v in items:
            cp = keep_first(v)
            if k in cache:
                kp, kv = cache[k]
                if cp < kp:
                    yield kv
                else:
                    yield v
                    continue
            cache[k] = (cp, v)


@overload
def iter_keyed_dups(
    it: Iterable[V], 
    /, 
    key: None = None, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> Iterator[tuple[Any, V]]:
    ...
@overload
def iter_keyed_dups(
    it: Iterable[tuple[K, V]], 
    /, 
    key: Literal[True] = True, 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> Iterator[tuple[Any, V]]:
    ...
@overload
def iter_keyed_dups(
    it: Iterable[V], 
    /, 
    key: Callable[[V], K], 
    keep_first: bool | Callable[[V], SupportsLT] = True, 
) -> Iterator[tuple[Any, V]]:
    ...
def iter_keyed_dups(
    it: Iterable, 
    /, 
    key: None | Literal[True] | Callable = None, 
    keep_first: bool | Callable[..., SupportsLT] = True, 
) -> Iterator:
    items: Iterable[tuple[Any, Any]]
    if key is None:
        items = ((e, e) for e in it)
    elif key is True:
        items = it
    else:
        items = ((key(e), e) for e in it)
    if keep_first is True:
        s: set = set()
        add = s.add
        for k, v in items:
            if k in s:
                yield k, v
            else:
                add(k)
    elif keep_first is False:
        d: dict = {}
        for k, v in items:
            if k in d:
                yield k, d[k]
            d[k] = v
    else:
        cache: dict[Any, tuple[SupportsLT, Any]] = {}
        for k, v in items:
            cp = keep_first(v)
            if k in cache:
                kp, kv = cache[k]
                if cp < kp:
                    yield k, kv
                else:
                    yield k, v
                    continue
                yield k, kv
            cache[k] = (cp, v)

