#!/usr/bin/env python3
# coding: utf-8

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 1)
__all__ = [
    'ListRegistry', 'SetRegistry', 'DictRegistry', 'AttrDictRegistry', 
    'BareDictAttrRegistry', 'DictAttrRegistry', 'ProxySequenceRegistry', 
    'ProxySetRegistry', 'ProxyMappingRegistry', 'DefaultdictRegistry', 
]

from collections import defaultdict
from functools import partial
from operator import attrgetter
from typing import (
    Callable, Mapping, MutableMapping, MutableSequence, 
    MutableSet, Optional, 
)

from .register import container_register, container_unregister, BaseRegistry


class AttrDict(dict):

    def __delattr__(self, attr, /):
        try:
            del self[attr]
        except KeyError as exc:
            raise AttributeError(attr) from exc

    def __getattr__(self, attr, /):
        try:
            return self[attr]
        except KeyError as exc:
            raise AttributeError(attr) from exc

    def __setattr__(self, attr, value, /):
        self[attr] = value


@MutableMapping.register
class BareDictAttr():

    def __init__(self, /, *args, **attrs):
        for a in args:
            self.__dict__.update(a)
        if attrs:
            self.__dict__.update(attrs)

    def __repr__(self, /):
        return '%s(%r)' % (type(self).__qualname__, self.__dict__)

    def __contains__(self, key):
        return key in self.__dict__

    def __iter__(self, /):
        return iter(self.__dict__)

    def __len__(self, /):
        return len(self.__dict__)

    def __delitem__(self, key, /):
        del self.__dict__[key]

    def __getitem__(self, key, /):
        return self.__dict__[key]

    def __setitem__(self, key, val, /):
        self.__dict__[key] = val


class DictAttr(BareDictAttr, MutableMapping):
    pass


@Mapping.register
class BareMappingAttr:

    def __init__(
        self, 
        container: Optional[Mapping] = None, 
        /, 
        default_factory: Optional[Callable] = None, 
        use_wrap: bool = True, 
    ):
        if isinstance(container, __class__):
            container = container.__container__
        elif container is None:
            container = {}
        self.__dict__['__container__'] = container
        self.__dict__['__default_factory__'] = default_factory
        self.__dict__['__use_wrap__'] = use_wrap

    def __repr__(self, /):
        return '%s(%r)' % (type(self).__qualname__, self.__container__)

    def __contains__(self, key):
        return key in self.__container__

    def __iter__(self, /):
        return iter(self.__container__)

    def __len__(self, /):
        return len(self.__container__)

    def __delitem__(self, key, /):
        del self.__container__[key]

    def __getitem__(self, key, /):
        try:
            val = self.__container__[key]
        except KeyError:
            if (self.__default_factory__ is None or 
                not isinstance(self.__container__, MutableMapping)
            ):
                raise
            val = self.__container__[key] = self.__default_factory__()

        if (self.__use_wrap__ and 
            isinstance(val, Mapping) and 
            not isinstance(val, __class__)
        ):
            val = type(self)(val)
        return val

    def __setitem__(self, key, val, /):
        self.__container__[key] = val

    def __delattr__(self, attr, /):
        if attr in self.__dict__:
            del self.__dict__[attr]
        try:
            del self[attr]
        except KeyError as exc:
            raise AttributeError(attr) from exc

    def __getattr__(self, attr, /):
        try:
            return self[attr]
        except KeyError as exc:
            raise AttributeError(attr) from exc

    def __setattr__(self, attr, val, /):
        try:
            self[attr] = val
        except KeyError:
            super().__setattr__(attr, val)


class MappingAttr(BareMappingAttr, MutableMapping):
    pass


class ListRegistry(BaseRegistry, list):

    def register(self, obj, /):
        self.append(obj)
        return obj

    __call__ = register

    def unregister(self, obj, /):
        self.remove(obj)
        return obj


class SetRegistry(BaseRegistry, set):

    def register(self, obj, /):
        self.add(obj)
        return obj

    __call__ = register

    def unregister(self, obj, /):
        self.remove(obj)
        return obj


class DictRegistry(BaseRegistry, dict):

    def __init__(self, /, key=attrgetter('__name__')):
        if not callable(key):
            key = attrgetter(key)
        self.__dict__['__key__'] = key

    def register(self, obj, /):
        self[self.__key__(obj)] = obj
        return obj

    __call__ = register

    def unregister(self, obj, /):
        del self[self.__key__(obj)]
        return obj


class AttrDictRegistry(DictRegistry, AttrDict):
    pass


class BareDictAttrRegistry(BareDictAttr, DictRegistry):
    __init__ = DictRegistry.__init__


class DictAttrRegistry(DictAttr, DictRegistry):
    __init__ = DictRegistry.__init__


class _ProxyRegistryMixin:

    @property
    def registry(self, /):
        return self.__registry__

    def __repr__(self, /):
        return '<%s(%r) at %s>' % (
                type(self).__qualname__, self.__registry__, hex(id(self)))

    def __getattr__(self, attr: str, /):
        return getattr(self.__registry__, attr)

    def __contains__(self, key, /):
        return key in self.__registry__

    def __iter__(self, /):
        return iter(self.__registry__)

    def __len__(self, /):
        return len(self.__registry__)

    def __call__(self, /, *args, **kwds):
        return self.register(*args, **kwds)


class ProxySequenceRegistry(BaseRegistry, _ProxyRegistryMixin, MutableSequence):

    def __init__(self, /, container: Optional[MutableSequence] = None):
        if container is None:
            container = []

        for attr in ('append', 'insert', 'remove'):
            method = getattr(container, attr, None)
            if callable(method):
                setattr(self, attr, method)

        self.__registry__ = container

    def __delitem__(self, key, /):
        del self.__registry__[key]

    def __getitem__(self, key, /):
        return self.__registry__[key]

    def __setitem__(self, key, val, /):
        self.__registry__[key] = val

    def insert(self, key, val, /):
        return self.__registry__.insert(key, val)

    def register(self, obj, /):
        self.append(obj)
        return obj

    def unregister(self, obj, /):
        self.remove(obj)
        return obj


class ProxySetRegistry(BaseRegistry, _ProxyRegistryMixin, MutableSet):

    def __init__(self, /, container: Optional[MutableSet] = None):
        if container is None:
            container = set()

        for attr in ('add', 'discard', 'remove'):
            method = getattr(container, attr, None)
            if callable(method):
                setattr(self, attr, method)

        self.__registry__ = container

    def add(self, value, /):
        return self.__registry__.add(value)

    def discard(self, value, /):
        return self.__registry__.discard(value)

    def register(self, obj, /):
        self.add(obj)
        return obj

    def unregister(self, obj, /):
        self.remove(obj)
        return obj


class ProxyMappingRegistry(BaseRegistry, _ProxyRegistryMixin, MutableMapping):

    def __init__(
        self, /, 
        container: Optional[MutableMapping] = None, 
        key=attrgetter('__name__'), 
    ):
        if container is None:
            container = {}

        self.__registry__ = container
        self.__key__ = key

    def __delitem__(self, key, /):
        del self.__registry__[key]

    def __getitem__(self, key, /):
        return self.__registry__[key]

    def __setitem__(self, key, val, /):
        self.__registry__[key] = val

    def register(self, obj, /):
        self[self.__key__(obj)] = obj
        return obj

    def unregister(self, obj, /):
        del self[self.__key__(obj)]
        return obj


MISSING = type('MISSING', (), {'__repr__': lambda _: 'MISSING'})()


class DefaultdictRegistry(ProxyMappingRegistry):

    def __init__(
        self, /, 
        default_factory: Callable = list, 
        key = None, 
        bindkey = None, 
    ):
        if isinstance(default_factory, type):
            typ = default_factory
        else:
            typ = type(default_factory())
        self._reg_2nd = container_register.dispatch(typ)
        self._unreg_2nd = container_unregister.dispatch(typ)

        self.__registry__ = defaultdict(default_factory)
        self.__default_factory__ = default_factory
        self.__key__ = key
        self.__bindkey__ = bindkey

    def register(self, obj, key=MISSING, /, *args, **kwds):
        if key is MISSING:
            key = self.__key__
        if callable(key):
            key = key(obj)
        return self._reg_2nd(
            self.__registry__[key], obj, *args, **kwds)

    def unregister(self, obj, key=MISSING, /, *args, **kwds):
        if key is MISSING:
            key = self.__key__
        if callable(key):
            key = key(obj)
        return self._unreg_2nd(
            self.__registry__[key], obj, *args, **kwds)

    def bindto(
        self, obj, key = MISSING, /, 
        pop: bool = True, 
        attr_registry: Optional[str] = 'registry', 
        attr_register: Optional[str] = 'register', 
        attr_unregister: Optional[str] = 'unregister', 
    ):
        if key is MISSING:
            key = self.__bindkey__
        if callable(key):
            key = key(obj)

        key_in = key in self.__registry__
        registry = self.__registry__[key] if key_in else self.__default_factory__()
        if attr_registry is not None:
            setattr(obj, attr_registry, registry)
        if attr_register is not None:
            setattr(obj, attr_register, partial(self._reg_2nd, registry))
        if attr_unregister is not None:
            setattr(obj, attr_unregister, partial(self._unreg_2nd, registry))

        if pop and key_in:
            del self.__registry__[key]

        return obj

