from collections.abc import Iterable, Reversible
from functools import reduce
from inspect import CO_VARARGS


def argcount(fn):
    return fn.__code__.co_argcount

def apply(fn, args, kwargs={}, /):
    return fn(*args, **kwargs)

def call(fn, *args, **kwargs):
    return fn(*args, **kwargs)

def compose(fns):
    return lambda arg: reduce(lambda x, f: f(x), fns, arg)

def all_p(predicate=None, /):
    if predicate is None:
        return all
    else:
        return lambda xs: all(map(predicate, xs))

def any_p(predicate=None, /):
    if predicate is None:
        return any
    else:
        return lambda xs: any(map(predicate, xs))

def all_pm(predicates, /):
    return lambda x: all(map_m(predicates, x))

def any_pm(predicates, /):
    return lambda x: any(map_m(predicates, x))

def find(fn=None, it=(), /, default=None):
    return next(filter(fn, it), default)

def find_index(fn=bool, it=(), /):
    for i, n in enumerate(it):
        if fn(n): return i
    return -1

def find_last(fn=None, it=(), /, default=None):
    try:
        it = reversed(it)
    except TypeError:
        n = default
        for n in filter(fn, it): pass
        return n
    else:
        return find(fn, it, default)

def find_last_index(fn=bool, it=(), /):
    l = -1
    for i, n in enumerate(it):
        if fn(n): l = i
    return l

def flatten(items, ignore_types=(str, bytes)):
    for i in items:
        if isinstance(i, Iterable) and not isinstance(i, ignore_types):
            yield from flatten(i)
        else:
            yield i

def foreach(iterable, fn, /):
    argcount = fn.__code__.co_argcount
    if argcount >= 3:
        for i, e in enumerate(iterable):
            fn(e, i, iterable)
    elif argcount == 2:
        for i, e in enumerate(iterable):
            fn(e, i)
    elif argcount == 1:
        for e in iterable:
            fn(e)
    else:
        for e in iterable:
            fn()

def invoke(fn, /, *args, **kwargs):
    return fn(args, **kwargs)

def js_apply(fn, args, /, *, default=None):
    args = tuple(args)
    code = fn.__code__
    argcount = code.co_argcount
    default_argcount = len(fn.__defaults__)
    lack_argcount = argcount - default_argcount - len(args)
    if len(args) > argcount:
        if not code.co_flags & CO_VARARGS:
            args = args[:argcount]
    elif lack_argcount > 0:
        args += (default,) * lack_argcount
    return fn(*args)

def js_call(fn, /, *args, default=None):
    return js_apply(fn, args, default=default)

def map_m(fns, x, /):
    return (f(x) for f in fns)

def mapping_foreach(mapping, fn, /):
    argcount = fn.__code__.co_argcount
    if argcount >= 3:
        for k in mapping:
            fn(mapping[k], k, mapping)
    elif argcount == 2:
        for k in mapping:
            fn(mapping[k], k)
    elif argcount == 1:
        for k in mapping:
            fn(mapping[k])
    else:
        for k in mapping:
            fn()

def pipe(fns):
    if isinstance(fns, Reversible):
        fns = tuple(fns)
    return compose(reversed(fns))

def zip_in_turn(iterables):
    its = dict.fromkeys(map(iter, iterables))
    while its:
        itl = []
        for it in its:
            try:
                yield next(it)
            except StopIteration:
                itl.append(it)
        for it in itl:
            del its[it]








