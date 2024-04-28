#!/usr/bin/env python3
# coding: utf-8

# TODO:
# 参考 statistics.__all__
# 参考 numpy.*
# 参考 pandas.core.generic.NDFrame.*
# 参考 pandas.core.frame.DataFrame.*

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 1)
__all__ = [
    'aggregate_if', 'aggregate_map', 'all', 'any', 'concat', 'count', 
    'sum', 'prod', 'mean', 'arithmetic_mean', 'geometric_mean', 
    'power_mean', 'harmonic_mean', 'quadratic_mean', 'pvar', 'var', 
    'pstdev', 'stdev', 'mode', 'multimode', 'INTERPOLATION', 'median', 
    'median_low', 'median_high', 'quantile', 'quantiles', 
]


from builtins import all as _all, any as _any, sum as _sum
from enum import Enum, EnumMeta
from heapq import nsmallest
from math import prod as _prod, nan, sqrt, isinf 
from typing import AnyStr, Callable, Final, Iterable, Optional, Sized, Union


INTERPOLATION: Final[EnumMeta] = Enum('INTERPOLATION', 
    ('linear', 'lower', 'higher', 'nearest', 'midpoint', 'bothsides'))


def _ensure_interpolation(val):
    if type(val) is INTERPOLATION:
        return val
    elif isinstance(val, str):
        try:
            return INTERPOLATION[val]
        except KeyError:
            pass
    return INTERPOLATION(val)


def aggregate_if(
    iterable: Iterable, /, 
    predicate: Optional[Callable] = None, 
    aggfunc: Callable = _sum, 
):
    if predicate is not None:
        iterable = filter(predicate, iterable)
    return aggfunc(iterable)


def aggregate_map(
    iterable: Iterable, /, 
    mapfunc: Optional[Callable] = None, 
    aggfunc: Callable = _sum, 
):
    if mapfunc is not None:
        iterable = map(mapfunc, iterable)
    return aggfunc(iterable)


def all(
    iterable: Iterable, /, 
    predicate: Optional[Callable] = None, 
) -> bool:
    if predicate is not None:
        iterable = filter(predicate, iterable)
    return _all(iterable)


def any(
    iterable: Iterable, /, 
    predicate: Optional[Callable] = None, 
) -> bool:
    if predicate is not None:
        iterable = filter(predicate, iterable)
    return _any(iterable)


def concat(
    iterable: Iterable[AnyStr], /, 
    sep: AnyStr = '', 
    to_str: AnyStr = str, 
) -> AnyStr:
    return sep.join(map(to_str, iterable))


def count(
    iterable: Iterable, /, 
    predicate: Optional[Callable] = None, 
):
    if predicate is not None:
        iterable = filter(predicate, iterable)
    if isinstance(iterable, Sized):
        return len(iterable)
    else:
        return _sum(1 for _ in iterable)


def sum(
    iterable: Iterable, /, 
    start=0, 
    predicate: Optional[Callable] = None, 
):
    if predicate is not None:
        iterable = filter(predicate, iterable)
    return _sum(iterable, start=start)


def prod(
    iterable: Iterable, /, 
    start=1, 
    predicate: Optional[Callable] = None, 
):
    if predicate is not None:
        iterable = filter(predicate, iterable)
    return _prod(iterable, start=start)


def mean(iterable: Iterable, /):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 1:
            return next(iter(iterable))
        elif count_ > 1:
            sum_ = _sum(iterable)
    else:
        count_ = sum_ = 0
        for count_, i in enumerate(iterable, 1):
            sum_ += i
    if count_ == 0:
        return nan
    return sum_ / count_

arithmetic_mean = mean


def geometric_mean(iterable: Iterable, /):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 1:
            return next(iter(iterable))
        elif count_ > 1:
            prod_ = _prod(iterable)
    else:
        count_ = 0
        prod_ = 1
        for count_, i in enumerate(iterable, 1):
            prod_ *= i
    if count_ == 0:
        return nan
    return prod_ **  (1 / count_)


def power_mean(
    iterable: Iterable, /, 
    n: Union[int, float] = 2, 
):
    if n == 0:
        return geometric_mean(iterable)
    elif n == 1:
        return mean(iterable)
    elif isinf(n):
        if n > 0:
            return max(iterable)
        else:
            return min(iterable)
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 1:
            return next(iter(iterable))
        elif count_ > 1:
            sum_ = 0
            for i in iterable:
                sum_ += i ** n
    else:
        count_ = sum_ = 0
        for count_, i in enumerate(iterable, 1):
            sum_ += i ** n
    if count_ == 0:
        return nan
    return (sum_ / count_) ** (1 / n)


def harmonic_mean(iterable: Iterable, /):
    return power_mean(iterable, -1)


def quadratic_mean(iterable: Iterable, /):
    return power_mean(iterable, 2)


def pvar(iterable: Iterable, /):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ > 1:
            sum_ = sum_quad = 0
            for i in iterable:
                sum_ += i
                sum_quad += i ** 2
    else:
        count_ = sum_ = sum_quad = 0
        for count_, i in enumerate(iterable, 1):
            sum_ += i
            sum_quad += i ** 2
    if count_ == 0:
        return nan
    elif count_ == 1:
        return 0
    return sum_quad / count_ - (sum_ / count_) ** 2


def var(iterable: Iterable, /):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ > 1:
            sum_ = sum_quad = 0
            for i in iterable:
                sum_ += i
                sum_quad += i ** 2
    else:
        count_ = sum_ = sum_quad = 0
        for count_, i in enumerate(iterable, 1):
            sum_ += i
            sum_quad += i ** 2
    if count_ <= 1:
        return nan
    return (sum_quad - sum_ ** 2 / count_) / (count_ - 1)


def pstdev(iterable: Iterable, /):
    return sqrt(pvar(iterable))


def stdev(iterable: Iterable, /):
    return sqrt(var(iterable))


def mode(iterable: Iterable, /):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 0:
            return nan
        elif count_ == 1 or isinstance(iterable, (dict, set)):
            return next(iter(iterable))
    d = {}
    for i in iterable:
        if i in d:
            d[i] += 1
        else:
            d[i] = 1
    if not d:
        return nan
    return max(d, key=lambda k: d[k])


def multimode(iterable: Iterable, /):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 0:
            return []
        elif count_ == 1 or isinstance(iterable, (dict, set)):
            return list(iterable)
    d = {}
    for i in iterable:
        if i in d:
            d[i] += 1
        else:
            d[i] = 1
    if not d:
        return []
    m = max(d.values())
    return [k for k, v in d.items() if v == m]


def median(
    iterable: Iterable, /, 
    interpolation: Union[int, str, INTERPOLATION] = INTERPOLATION.midpoint, 
    key: Optional[Callable] = None, 
):
    interpolation = _ensure_interpolation(interpolation)
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 1:
            return next(iter(iterable))
        elif count_ > 1:
            data = nsmallest(count_ // 2 + 1, iterable, key=key)
    else:
        data = sorted(iterable, key=key)
        count_ = len(data)
    if count_ == 0:
        return nan
    if interpolation is INTERPOLATION.linear:
        return (data[0] + data[-1]) * 0.5
    i, r = divmod(count_, 2)
    if r or interpolation is INTERPOLATION.higher:
        return data[i]
    elif interpolation is INTERPOLATION.lower:
        return data[i - 1]
    elif interpolation is INTERPOLATION.nearest:
        return data[round(count_ / 2)]
    elif interpolation is INTERPOLATION.midpoint:
        return (data[i - 1] + data[i]) / 2
    elif interpolation is INTERPOLATION.bothsides:
        return (data[i - 1], data[i])


def median_low(
    iterable: Iterable, /, 
    key: Optional[Callable] = None, 
):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 1:
            return next(iter(iterable))
        elif count_ > 1:
            data = nsmallest((count_ + 1) // 2, iterable, key=key)
    else:
        data = sorted(iterable, key=key)
        count_ = len(data)
    if count_ == 0:
        return nan
    i, r = divmod(count_, 2)
    if r:
        return data[i]
    else:
        return data[i - 1]


def median_high(
    iterable: Iterable, /, 
    key: Optional[Callable] = None, 
):
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 1:
            return next(iter(iterable))
        elif count_ > 1:
            data = nsmallest(count_ // 2 + 1, iterable, key=key)
    else:
        data = sorted(iterable, key=key)
        count_ = len(data)
    if count_ == 0:
        return nan
    return data[count_ // 2]


def quantile(
    iterable: Iterable, /, 
    q: float = 0.5, 
    interpolation: Union[int, str, INTERPOLATION] = INTERPOLATION.linear, 
    key: Optional[Callable] = None, 
):
    interpolation = _ensure_interpolation(interpolation)
    if isinstance(iterable, Sized):
        count_ = len(iterable)
        if count_ == 0:
            return nan
        elif count_ == 1:
            return next(iter(iterable))
        data = sorted(iterable, key=key)
    else:
        data = sorted(iterable, key=key)
        count_ = len(data)
        if count_ == 0:
            return nan
        elif count_ == 1:
            return data[0]
    if q <= 0:
        return data[0]
    elif q >= 1:
        return data[-1]
    if interpolation is INTERPOLATION.linear:
        m , M = data[0], data[-1]
        return m + (M - m) * q
    idx = (count_ - 1) * q
    if idx.is_integer() or interpolation is INTERPOLATION.lower:
        return data[int(idx)]
    elif interpolation is INTERPOLATION.higher:
        return data[int(idx) + 1]
    elif interpolation is INTERPOLATION.nearest:
        return data[round(idx)]
    elif interpolation is INTERPOLATION.midpoint:
        i = int(idx)
        return (data[i] + data[i + 1]) / 2
    elif interpolation is INTERPOLATION.bothsides:
        i = int(idx)
        return (data[i], data[i + 1])


def quantiles(
    iterable: Iterable, /, 
    n: int = 4, 
    inclusive: bool = True, 
    key: Optional[Callable] = None, 
):
    '''Divide *iterable* into *n* continuous intervals with equal probability.
    Returns a list of (n - 1) cut points separating the intervals (in to equal sized groups).
    '''
    if n <= 0:
        raise nan
    data = sorted(iterable, key=key)
    ld = len(data)
    if ld < 2:
        raise nan
    if inclusive:
        m = ld - 1
        func = lambda i: divmod(i * m, n)
    else:
        m = ld + 1
        def func(i):
            j = i * m // n                               # rescale i to m/n
            j = 1 if j < 1 else ld-1 if j > ld-1 else j  # clamp to 1 .. ld-1
            delta = i*m - j*n                            # exact integer math
            return j - 1, delta
    return [
        (data[j] * (n - delta) + data[j + 1] * delta) / n
        for j, delta in map(func, range(1, n))
    ]

