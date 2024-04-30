#!/usr/bin/env python3
# coding: utf-8

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 1)
__all__ = [
    "BaseRegistry", "multi_register", "register", "register_with_args", 
    "register_with_convert", "container_register", "seq_register", 
    "set_register", "map_register", "registry_register", "attr_register", 
    "container_unregister", "seq_unregister", "set_unregister", 
    "map_unregister", "registry_unregister", "attr_unregister", 
    "bind_mutmap_registry", "bind_mutmap_fn_registry", 
    "bind_dispatched_registry", 
]


from abc import abstractmethod, ABC
from collections.abc import MutableMapping, MutableSequence, MutableSet
from functools import partial, singledispatch
from operator import attrgetter
from typing import Any, Callable, Generic, Union, TypeVar

from .exceptions import AggregationException
from .undefined import undefined


K = TypeVar("K")
V = TypeVar("V")


class BaseRegistry(ABC, Generic[V]):

    @property
    @abstractmethod
    def registry(self):
        return NotImplemented

    @abstractmethod
    def register(self, obj: V) -> V:
        raise NotImplementedError

    @abstractmethod
    def unregister(self, obj: V) -> V:
        raise NotImplementedError


def multi_register(
    *regs: Callable[[V], Any], 
    exceptions: Union[BaseException, tuple[BaseException, ...]] = Exception, 
) -> Callable[[V], V]:
    def register(obj: V) -> V:
        excs: list[BaseException] = []
        for reg in regs:
            try:
                reg(obj)
            except exceptions as exc:
                excs.append((reg, exc))
        if excs:
            raise AggregationException(excs)
        return obj
    return register


# NOTE: `reg` can be register or unregister
def register(reg: Callable[[V], Any], obj: V, /) -> V:
    reg(obj)
    return obj


def register_with_args(
    reg: Callable[[V], Any], 
    obj: V, 
    /, *args, **kwds
) -> V:
    reg(obj, *args, **kwds)
    return obj


def register_with_convert(
    reg: Callable[[K], Any], 
    obj: V, 
    /, 
    convert: Callable[[V], K], 
) -> V:
    reg(convert(obj))
    return obj


@singledispatch
def container_register(container: Any, obj: V, /) -> V:
    return obj


@container_register.register(MutableSequence)
def seq_register(container: MutableSequence[V], obj: V, /) -> V:
    # Roughly equivalent to:
    # return register(container.append, obj)
    container.append(obj)
    return obj


@container_register.register(MutableSet)
def set_register(container: MutableSet[V], obj: V, /) -> V:
    # Roughly equivalent to:
    # return register(container.add, obj)
    container.add(obj)
    return obj


@container_register.register(MutableMapping)
def map_register(
    container: MutableMapping[K, V], 
    obj: V, 
    /, *, 
    key: Callable[[V], K] = id, 
) -> V:
    # Roughly equivalent to:
    # return register(lambda o: operator.setitem(container, 
    #   key(o) if callable(key) else key, o), obj) 
    container[key(obj) if callable(key) else key] = obj
    return obj


@container_register.register(BaseRegistry)
def registry_register(container: BaseRegistry[V], obj: V, /) -> V:
    # Roughly equivalent to:
    # return register(o.register, obj)
    container.register(obj)
    return obj


@container_register.register
def attr_register(
    container: object, 
    obj: V, 
    /, *, 
    attr: Callable[[V], str] = lambda o: hex(id(o)), 
) -> V:
    # Roughly equivalent to:
    # return register(lambda o: setattr(container, 
    #   attr(o) if callable(attr) else attr, o), obj)
    setattr(container, attr(obj) if callable(attr) else attr, obj)
    return obj


@singledispatch
def container_unregister(container: Any, obj: V, /) -> V:
    return obj


@container_unregister.register(MutableSequence)
def seq_unregister(container: MutableSequence[V], obj: V, /) -> V:
    try:
        container.remove(obj)
    except AttributeError:
        MutableSequence.remove(container, obj)
    return obj


@container_unregister.register(MutableSet)
def set_unregister(container: MutableSet[V], obj: V, /) -> V:
    try:
        container.remove(obj)
    except AttributeError:
        MutableSet.remove(container, obj)
    return obj


@container_unregister.register(MutableMapping)
def map_unregister(
    container: MutableMapping[K, V], 
    obj: V, 
    /, *, 
    key: Callable[[V], K] = id, 
) -> V:
    del container[key(obj) if callable(key) else key]
    return obj


@container_unregister.register(BaseRegistry)
def registry_unregister(container: BaseRegistry[V], obj: V, /) -> V:
    container.unregister(obj)
    return obj


@container_unregister.register
def attr_unregister(
    container: object, 
    obj: V, 
    /, *, 
    attr: Callable[[V], str] = lambda o: hex(id(o)), 
) -> V:
    delattr(container, attr(obj) if callable(attr) else attr)
    return obj


# "mutmap" stands for "mutable mapping"
def bind_mutmap_registry(
    mm: MutableMapping, /
) -> Callable:
    def register(obj=undefined, /, key=attrgetter("__name__")):
        if obj is undefined:
            return partial(register, key=key)
        mm[key(obj) if callable(key) else key] = obj
        return obj
    return register


# "mutmap" stands for "mutable mapping"
# "fn" stands for "function"
def bind_mutmap_fn_registry(
    mm: MutableMapping, /
) -> Callable:
    def register(
        fn=None, /, key=undefined
    ):
        if not callable(fn):
            return partial(
                register, key=fn if key is undefined else key)
        if key is undefined:
            key = attrgetter("__name__")
        mm[key(fn) if callable(key) else key] = fn
        return fn
    return register


def bind_dispatched_registry(
    mm: MutableMapping, /
) -> Callable:
    def register(key, obj=undefined):
        if obj is undefined:
            return partial(register, key)
        k = key(obj) if callable(key) else key
        try:
            mm[k].append(obj)
        except KeyError:
            mm[k] = [obj]
        return obj
    return register

