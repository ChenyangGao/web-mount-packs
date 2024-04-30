#!/usr/bin/env python3
# -*- coding: utf-8 -*-


__author__ = 'ChenyangGao'
__version__ = '0.1'


import functools
import inspect
import operator

from collections.abc import MutableSequence, MutableSet, MutableMapping
from collections import defaultdict


def multi_register(*registers, ignore_errors=False):
    '''
    '''
    def register(func):
        for reg in registers:
            try:
                try:
                    reg.register(func)
                except AttributeError:
                    reg(func)
            except:
                if ignore_errors:
                    continue
                raise
        return func
    return register


def sequence_register(container, f=None):
    '''
    '''
    if f is None:
        return lambda f: sequence_register(container, f)
    container.append(f)
    return f


def set_register(container, f=None):
    '''
    '''
    if f is None:
        return lambda f: set_register(container, f)
    container.add(f)
    return f


def mapping_register(container, f=None, name=None):
    '''
    '''
    if f is None:
        if name is not None:
            return lambda f: mapping_register(container, f, name)
        return lambda f, name=None: mapping_register(container, f, name)
    container[name or f.__name__] = f
    return f


def method_register(obj, f=None, name=None, prepare=None):
    '''
    '''
    if f is None:
        if prepare is not None:
            return lambda f, name=None: method_register(obj, f, name, prepare)
        return lambda f, name=None, prepare=None: method_register\
                    (obj, f, name, prepare)
    setattr(obj, name or f.__name__, prepare(f) if prepare else f)
    return f


class CommonRegister:
    def __init__(self, default_factory=list, pop_when_bind=True):
        self.cache = defaultdict(default_factory)
        self.pop_when_bind = pop_when_bind

    def attach(self, mark, container):
        assert isinstance(container, self.cache.default_factory)
        self.cache[mark] = container
        return container

    def detach(self, mark):
        return self.cache[mark].pop(mark, None)

    def register(self, f=None, *, mark=None):
        if f is None:
            return lambda f: self.register(f, mark=mark)
        return push(self.cache[mark], f)

    def __call__(self, *args, **kwds):
        return self.register(*args, **kwds)

    def bind(self, f=None, *, mark=None, bind_attr='registry'):
        if f is None:
            return lambda f: self.bind(f, mark=mark, bind_attr=bind_attr)
        if self.pop_when_bind:
            setattr(f, bind_attr, self.cache.pop(mark))
        else:
            setattr(f, bind_attr, self.cache[mark])
        return f


class ListRegister(CommonRegister):
    def __init__(self, pop_when_bind=True):
        self.cache = defaultdict(list)
        self.pop_when_bind = pop_when_bind

    def register(self, f=None, *, mark=None):
        if f is None:
            return lambda f: self.register(f, mark=mark)
        self.cache[mark].append(f)
        return f


class SetRegister(CommonRegister):
    def __init__(self, pop_when_bind=True):
        self.cache = defaultdict(set)
        self.pop_when_bind = pop_when_bind

    def register(self, f=None, *, mark=None):
        if f is None:
            return lambda f: self.register(f, mark=mark)
        self.cache[mark].add(f)
        return f


class MappingRegister(CommonRegister):
    def __init__(self, pop_when_bind=True):
        self.cache = defaultdict(dict)
        self.pop_when_bind = pop_when_bind

    def register(self, f=None, *, mark=None, name=None):
        if f is None:
            return lambda f: self.register(f, mark=mark, name=name)
        self.cache[mark][name or f.__name__] = f
        return f


@functools.singledispatch
def push(container, f):
    return f

@push.register(MutableSequence)
def _(container, f):
    container.append(f)
    return f

@push.register(MutableSet)
def _(container, f):
    container.add(f)
    return f

@push.register(MutableMapping)
def _(container, f, mark=operator.attrgetter('__name__')):
    if callable(mark):
        mark = mark(f)
    container[mark] = f
    return f


class CacheAutoRegister:
    def __init__(self, default_factory=list, pop_when_bind=True):
        self.cache = defaultdict(default_factory)
        self.pop_when_bind = pop_when_bind

    def bind(self, obj, key):
        try:
            namespace = obj.__dict__
            has_attr = lambda x: x in namespace
        except AttributeError:
            has_attr = lambda x: hasattr(obj, x)
        cache = self.cache
        if has_attr('register'):
            qualname = '%s.%s' % (obj.__qualname__, 'register')
            if inspect.isclass(obj):
                @classmethod
                def register(cls, f):
                    return push(cls.registry, f)
                register.__func__.__qualname__ = qualname
            else:
                def register(f):
                    return push(obj.registry, f)
                register.__qualname__ = qualname
            setattr(obj, 'register', register)
        if has_attr('registry'):
            if self.pop_when_bind:
                try:
                    setattr(obj, 'registry', cache.pop(key))
                except KeyError:
                    setattr(obj, 'registry', cache.default_factory())
            else:
                setattr(obj, 'registry', cache[key])

    def __call__(self, f=None, *, key=None, cache=None, bind=None):
        '''
        '''
        if f is None:
            return lambda f: self(f, key=key, cache=cache, bind=bind)
        # module = inspect.getmodule(func)
        module = getattr(f, '__module__', None)
        qualname = getattr(f, '__qualname__', None)
        if module is None or qualname is None:
            return f
        if cache is None: # cache为None时则由预设的规则自动确定是True还是False
            if '.' in qualname: # 默认会对嵌入另一函数或类的元素进行缓存
                cache = True
        if bind is None: # bind为None时则由预设的规则自动确定是True还是False
            if inspect.isclass(f): # 默认会对是类的元素进行绑定
                bind = True
        key = (module, qualname.rsplit('.', 1)[0])
        if cache:
            push(self.cache[key], f)
        if bind:
            self.bind(f, key)
        return f


class CacheMethodRegister:
    def __init__(self, default_factory=list, pop_when_bind=True):
        self.cache = defaultdict(default_factory)
        self.pop_when_bind = pop_when_bind

    def bind(self, obj=None, key=None):
        if obj is None:
            return lambda obj: self.bind(obj, key=key)
        namespace = obj.__dict__
        cache = self.cache
        if 'register' not in namespace:
            def register(cls, _f=None, **kwds):
                if _f is None:
                    return lambda _f: cls.register(_f, **kwds)
                _f.__dict__.update(kwds)
                return push(cls.registery, _f)
            register.__qualname__ = '%s.%s' % (obj.__qualname__, 'register')
            obj.register = classmethod(register)
        if 'registry' not in namespace:
            if key is None:
                try:
                    key = namespace['_field']
                except KeyError:
                    key = (obj.__module__, obj.__qualname__)
            if self.pop_when_bind:
                if key in cache:
                    obj.registry = cache.pop(key)
                else:
                    obj.registry = cache.default_factory()
            else:
                obj.registry = cache[key]

    def __call__(self, _field=None, **kwds):
        if callable(_field):
            self.bind(_field)
            return _field
        def decorate(f):
            nonlocal _field
            if _field is None:
                last_dot = f.__qualname__.rfind('.')
                if last_dot is -1:
                    _field = f.__module__
                else:
                    _field = f.__module__, f.__qualname__[:last_dot]
            f.__dict__.update(kwds)
            return push(self.cache[_field], f)
        return decorate

