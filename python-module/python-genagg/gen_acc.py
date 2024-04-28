#!/usr/bin/env python3
# coding: utf-8

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 2)
__all__ = [
    'gen_exit_value', 'joint', 'gen_acc', 'gen_group_acc', 'gen_acc0', 
    'gen_group_acc0', 'gen_acc1', 'gen_group_acc1', 'gen_concat', 
    'gen_collect', 'gen_max', 'gen_min', 'gen_count', 'gen_count_uniques', 
    'gen_count_uniques_2', 'gen_sum', 'gen_sum_pow', 'gen_prod', 'gen_mean', 
    'gen_geometric_mean', 'gen_power_mean', 'gen_pvar', 'gen_var', 'gen_pstdev', 
    'gen_stdev', 'gen_count_uniques_with_cache', 'gen_count_pvuv_with_cache', 
]

from itertools import chain, repeat
from math import isinf, nan, sqrt
from typing import (
    Tuple, cast, overload, Any, Callable, Dict, Generator, Optional, 
    TypeVar, Union, 
)


K = TypeVar('K')
V = TypeVar('V')
V2 = TypeVar('V2')
T = TypeVar('T')


def gen_exit_value(gen: Generator, /):
    'The return value after a `GeneratorExit` is thrown'
    frame = gen.gi_frame
    if frame is None:
        raise RuntimeError('Process on a stopped generator')
    if frame.f_lasti == -1:
        next(gen)
    try:
        gen.throw(GeneratorExit)
    except StopIteration as exc:
        if exc.args is not None:
            return exc.args[0]


def joint(
    *genfs, 
    init: Optional[Tuple[Optional[tuple], ...]] = None, 
    calc: Optional[Callable] = None, 
):
    def wrapper():
        if init is None:
            fs = [f() for f in genfs]
        else:
            fs = [
                f() if args is None else f(*args)
                for f, args in zip(genfs, chain(init, repeat(None)))
            ]
        try:
            i = yield [next(f.__self__) for f in fs]
            if calc is None:
                while True:
                    i = yield [f(i) for f in fs]
            else:
                while True:
                    i = yield calc(*(f(i) for f in fs))
        except GeneratorExit:
            return tuple(gen_exit_value(f.__self__) for f in fs)
    return wrapper


def gen_acc(
    genf: Callable[..., Generator[T, V, tuple]], 
    init: Optional[tuple] = None, 
    /, 
) -> Generator[T, V, tuple]:
    'Accumulation generator'
    if init is None:
        acc = genf()
    else:
        acc = genf(*init)
    send = acc.send
    try:
        i = yield next(acc)
        while True:
            i = yield send(i)
    except GeneratorExit:
        return genf, gen_exit_value(acc)


@overload
def gen_group_acc(
    genf: Callable[[T], Generator[T, V, Any]], 
    /, 
    key: Callable[[V], K], 
    value: None = ..., 
    init: Optional[Dict[K, tuple]] = ..., 
) -> Generator[Dict[K, T], V, tuple]:
    ...
@overload
def gen_group_acc(
    genf: Callable[[T], Generator[T, V2, Any]], 
    /, 
    key: Callable[[V], K] = ..., 
    value: Optional[Callable[[V], V2]] = ..., 
    init: Optional[Dict[K, tuple]] = ..., 
) -> Generator[Dict[K, T], V, tuple]:
    ...
def gen_group_acc(
    genf, 
    /, 
    key=lambda x: x, 
    value=None, 
    init=None, 
):
    'Group accumulation generator'
    if init is None:
        init = {}
    as_is = value is None
    fcache: dict = {}
    out: dict = {}
    try:
        while True:
            i = yield out
            try:
                k = key(i)
                v = i if as_is else value(i)
            except:
                continue
            try:
                f = fcache[k]
            except KeyError:
                if k in init:
                    f = fcache[k] = genf(*init).send
                else:
                    f = fcache[k] = genf().send
                next(f.__self__)
            out[k] = f(v)
    except GeneratorExit:
        init2 = dict(init)
        init2.update((k, gen_exit_value(v.__self__)) for k, v in fcache.items())
        return genf, key, value, init2


def gen_acc0(
    genf: Callable[[T], Generator[T, V, Any]], 
    out: T, 
    /, 
) -> Generator[T, V, tuple]:
    'Accumulation generator'
    acc = genf(out)
    send = acc.send
    try:
        while True:
            out = send((yield out))
    except GeneratorExit:
        return genf, out


@overload
def gen_group_acc0(
    genf: Callable[[T], Generator[T, V, Any]], 
    /, 
    key: Callable[[V], K] = ..., 
    value: None = ..., 
    init: Union[None, T, Callable[[], T]] = ..., 
    out: Optional[Dict[K, T]] = ..., 
) -> Generator[Dict[K, T], V, tuple]:
    ...
@overload
def gen_group_acc0(
    genf: Callable[[T], Generator[T, V2, Any]], 
    /, 
    key: Callable[[V], K], 
    value: Optional[Callable[[V], V2]] = ..., 
    init: Union[None, T, Callable[[], T]] = ..., 
    out: Optional[Dict[K, T]] = ..., 
) -> Generator[Dict[K, T], V, tuple]:
    ...
def gen_group_acc0(
    genf, 
    /, 
    key=lambda x: x, 
    value=None, 
    init=None, 
    out=None, 
):
    'Group accumulation generator'
    if not callable(init):
        init = cast(Callable[[], T], lambda _=init: _)
    if out is None:
        out = {}
    as_is = value is None
    fcache: dict = {}
    try:
        while True:
            i = yield out
            k = key(i)
            try:
                f = fcache[k]
            except KeyError:
                f = fcache[k] = genf(out[k] if k in out else init()).send
                next(f.__self__)
            out[k] = f(i if as_is else value(i))
    except GeneratorExit:
        return genf, key, value, init, out


def gen_acc1(
    func: Callable[[T, V], T], 
    out: T, 
    /, 
) -> Generator[T, V, tuple]:
    'Accumulation generator'
    try:
        while True:
            out = func(out, (yield out))
    except GeneratorExit:
        return func, out


@overload
def gen_group_acc1(
    func: Callable[[T, V], T], 
    /, 
    key: Callable[[V], K], 
    value: None = ..., 
    init: Union[None, T, Callable[[], T]] = ..., 
    out: Optional[Dict[K, T]] = ..., 
) -> Generator[Dict[K, T], V, tuple]:
    ...
@overload
def gen_group_acc1(
    func: Callable[[T, V2], T], 
    /, 
    key: Callable[[V], K], 
    value: Callable[[V], V2] = ..., 
    init: Union[None, T, Callable[[], T]] = ..., 
    out: Optional[Dict[K, T]] = ..., 
) -> Generator[Dict[K, T], V, tuple]:
    ...
def gen_group_acc1(
    func, 
    /, 
    key=lambda x: x, 
    value=None, 
    init=None, 
    out=None, 
):
    'Group accumulation generator'
    if not callable(init):
        init = cast(Callable[[], T], lambda _=init: _)
    if out is None:
        out = {}
    as_is = value is None
    try:
        while True:
            i = yield out
            k = key(i)
            if k in out:
                out[k] = func(out[k], i if as_is else value(i))
            else:
                out[k] = func(init(), i if as_is else value(i))
    except GeneratorExit:
        return func, key, value, init, out


def gen_concat(
    s: str = '', /
) -> Generator[str, Any, tuple]:
    'String concatenation'
    try:
        while True:
            s += str((yield s))
    except GeneratorExit:
        return s, 


def gen_collect(
    ls: Optional[list] = None, /
) -> Generator[list, Any, tuple]:
    'Collect into list'
    try:
        if ls is None:
            ls = []
        push = ls.append
        while True:
            push((yield ls))
    except GeneratorExit:
        return ls, 


def gen_max(
    m=None, /
) -> Generator:
    'Maximum'
    try:
        if m is None:
            m = yield
        while True:
            i = yield m
            if i > m:
                m = i
    except GeneratorExit:
        return m, 


def gen_min(
    m=None, /
) -> Generator:
    'Minimum'
    try:
        if m is None:
            m = yield
        while True:
            i = yield m
            if i < m:
                m = i
    except GeneratorExit:
        return m, 


def gen_count(
    n=0, /
) -> Generator:
    'Count'
    try:
        while True:
            yield n
            n += 1
    except GeneratorExit:
        return n, 


def gen_count_uniques(
    cache: Optional[set] = None, /
) -> Generator:
    'Deduplication count'
    try:
        if cache is None:
            cache = set()
        add = cache.add
        while True:
            add((yield len(cache)))
    except GeneratorExit:
        return cache, 


def gen_count_uniques_2(
    hcache: Optional[set] = None, 
    idcache: Optional[set] = None, 
    /, 
) -> Generator:
    'Deduplication count'
    try:
        if hcache is None:
            hcache = set()
        if idcache is None:
            idcache = set()
        hadd, iadd = hcache.add, idcache.add
        hlen = ilen = 0
        while True:
            i = yield hlen + ilen
            try:
                hadd(i)
                hlen = len(hcache)
            except TypeError:
                iadd(id(i))
                ilen = len(idcache)
    except GeneratorExit:
        return hcache, idcache


def gen_sum(
    sum_=0, /
) -> Generator:
    'Sum'
    try:
        while True:
            sum_ += yield sum_
    except GeneratorExit:
        return sum_, 


def gen_sum_pow(exp=1, sum_=0, /):
    'Sum of exponents of input values'
    try:
        while True:
            if exp == 0:
                acc = gen_count(sum_)
            elif exp == 1:
                acc = gen_sum(sum_)
            else:
                break
            send = acc.send
            i = yield next(acc)
            while True:
                i = yield send(i)
    except GeneratorExit:
        return exp, *gen_exit_value(acc)
    try:
        while True:
            sum_ += (yield sum_) ** exp
    except GeneratorExit:
        return exp, sum_


def gen_prod(
    prod=1, /
) -> Generator:
    'Production'
    try:
        while True:
            prod *= yield prod
    except GeneratorExit:
        return prod, 


def gen_mean(
    count_=0, sum_=0, /
) -> Generator:
    'Mean'
    assert count_ >= 0
    try:
        if count_ == 0:
            i = yield nan
        else:
            i = yield sum_ / count_
        while True:
            sum_ += i
            count_ += 1
            i = yield sum_ / count_
    except GeneratorExit:
        return count_, sum_


def gen_geometric_mean(count_=0, prod=1, /):
    'Geometric mean'
    assert count_ >= 0
    try:
        if count_ == 0:
            prod *= yield nan
            count_ += 1
        while True:
            prod *= yield prod ** (1 / count_)
            count_ += 1
    except GeneratorExit:
        return count_, prod


def gen_power_mean(exp=1, count_=0, sum_=None, /) -> Generator:
    'Exponential mean'
    try:
        while True:
            if exp == 0:
                if sum_ is None: sum_ = 1
                acc = gen_geometric_mean(count_, sum_)
            elif exp == 1:
                if sum_ is None: sum_ = 0
                acc = gen_mean(count_, sum_)
            elif isinf(exp):
                if exp > 0:
                    acc = gen_max(sum_)
                else:
                    acc = gen_min(sum_)
            else:
                break
            send = acc.send
            i = yield next(acc)
            while True:
                i = yield send(i)
    except GeneratorExit:
        if isinf(exp):
            return exp, count_, *gen_exit_value(acc)
        return exp, *gen_exit_value(acc)
    assert count_ >= 0
    if sum_ is None: sum_ = 0
    _1_div_exp = 1 / exp
    try:
        if count_ == 0:
            sum_ += (yield nan) ** exp
            count_ += 1
        while True:
            sum_ += (yield (sum_ / count_) ** _1_div_exp) ** exp
            count_ += 1
    except GeneratorExit:
        return exp, count_, sum_


def gen_pvar(
    count_=0, sum_=0, sum_quad=0, /
) -> Generator:
    'Population variance'
    assert count_ >= 0
    try:
        if count_ == 0:
            i = yield nan
        else:
            i = yield sum_quad / count_ - (sum_ / count_) ** 2
        while True:
            count_ += 1
            sum_ += i
            sum_quad += i * i
            i = yield sum_quad / count_ - (sum_ / count_) ** 2
    except GeneratorExit:
        return count_, sum_, sum_quad


def gen_var(
    count_=0, sum_=0, sum_quad=0, /
) -> Generator:
    'Sample variance'
    assert count_ >= 0
    try:
        for _ in range(2-count_):
            i = yield nan
            count_ += 1
            sum_ += i
            sum_quad += i * i
        while True:
            i = yield (sum_quad - sum_ ** 2 / count_) / (count_ - 1)
            count_ += 1
            sum_ += i
            sum_quad += i * i
    except GeneratorExit:
        return count_, sum_, sum_quad


def gen_pstdev(
    count_=0, sum_=0, sum_quad=0, /
) -> Generator:
    'Population standard deviation'
    acc = gen_pvar(count_, sum_, sum_quad)
    facc = acc.send
    try:
        i = None
        while True:
            i = yield sqrt(facc(i))
    except GeneratorExit:
        return gen_exit_value(acc)


def gen_stdev(
    count_=0, sum_=0, sum_quad=0, /
) -> Generator:
    'Sample standard deviation'
    acc = gen_var(count_, sum_, sum_quad)
    facc = acc.send
    try:
        i = None
        while True:
            i = yield sqrt(facc(i))
    except GeneratorExit:
        return gen_exit_value(acc)


def gen_count_uniques_with_cache(out=None):
    'Deduplication count (with intermediate results)'
    try:
        if out is None:
            out = [0, set()]
        s = out[1]
        add = s.add
        while True:
            i = yield out
            if i not in s:
                out[0] += 1
                add(i)
    except GeneratorExit:
        return out


def gen_count_pvuv_with_cache(out=None):
    'Count and deduplication count (with intermediate results)'
    try:
        if out is None:
            out = [0, 0, set()]
        s = out[2]
        add = s.add
        while True:
            i = yield out
            out[0] += 1
            if i not in s:
                out[1] += 1
                add(i)
    except GeneratorExit:
        return out

