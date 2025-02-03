#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 10)
__all__ = [
    "run_async", "as_thread", "ensure_async", "ensure_await", "ensure_coroutine", 
    "ensure_aiter", "async_map", "async_filter", "async_filterfalse", "async_reduce", 
    "async_zip", "async_chain", "async_all", "async_any", "async_compress", "async_cycle", 
    "async_accumulate", "async_enumerate", "async_islice", "async_takewhile", "async_dropwhile", 
    "async_batched", "async_groupby", "async_pairwise", "async_starmap", "async_count", 
    "async_repeat", "async_zip_longest", "async_tee", "call_as_aiter", "to_list", "collect", 
]

from asyncio import create_task, get_running_loop, run, to_thread
from collections.abc import (
    Awaitable, AsyncIterable, AsyncIterator, Callable, Collection, Coroutine, 
    ItemsView, Iterable, Iterator, Mapping, MutableMapping, MutableSequence, 
    MutableSet, Sequence, 
)
from inspect import isawaitable, iscoroutine, iscoroutinefunction, isgenerator
from itertools import pairwise
from typing import cast, overload, Any, Self

from decotools import decorated
from undefined import undefined, Undefined


def run_async(obj, /):
    if isawaitable(obj):
        coro = ensure_coroutine(obj)
        try:
            get_running_loop()
            return create_task(coro)
        except RuntimeError:
            return run(coro)
    else:
        return obj


@decorated
def as_thread[**Args, T](
    function: Callable[Args, T], 
    /, 
    *args: Args.args, 
    **kwds: Args.kwargs, 
) -> Awaitable[T]:
    def wrapfunc(*args, **kwds):
        try:
            return function(*args, **kwds)
        except StopIteration as e:
            raise StopAsyncIteration from e
    return to_thread(wrapfunc, *args, **kwds)


def ensure_async[**Args, T](
    function: Callable[Args, T] | Callable[Args, Awaitable[T]], 
    /, 
    threaded: bool = False, 
) -> Callable[Args, Awaitable[T]]:
    if iscoroutinefunction(function):
        return function
    function = cast(Callable[Args, T], function)
    if threaded:
        function = as_thread(function)
        async def wrapper(*args, **kwds):
            ret = await function(*args, **kwds)
            if isawaitable(ret):
                try:
                    return await ret
                except StopIteration as e:
                    raise StopAsyncIteration from e
            return ret
    else:
        async def wrapper(*args, **kwds):
            try:
                ret = function(*args, **kwds)
                if isawaitable(ret):
                    return await ret
                return ret
            except StopIteration as e:
                raise StopAsyncIteration from e
    return wrapper


def ensure_await(o, /) -> Awaitable:
    if isawaitable(o):
        return o
    async def wrapper():
        return o
    return wrapper()


def ensure_coroutine(o, /) -> Coroutine:
    if iscoroutine(o):
        return o
    async def wrapper():
        if isawaitable(o):
            return await o
        return o
    return wrapper()


def ensure_aiter[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    if isinstance(iterable, AsyncIterable):
        return aiter(iterable)
    if isinstance(iterable, Sequence):
        async def it():
            for e in iterable:
                yield e
        return it()
    elif isgenerator(iterable):
        if threaded:
            send = as_thread(iterable.send)
            async def wrapper():
                e: Any = None
                try:
                    while True:
                        e = yield await send(e)
                except StopAsyncIteration:
                    pass
        else:
            send = iterable.send
            async def wrapper():
                e: Any = None
                try:
                    while True:
                        e = yield send(e)
                except StopIteration:
                    pass
    else:
        if threaded:
            get = as_thread(iter(iterable).__next__)
            async def wrapper():
                try:
                    while True:
                        yield await get()
                except StopAsyncIteration:
                    pass
        else:
            async def wrapper():
                for e in iterable:
                    yield e
    return wrapper()


async def async_map[T](
    function: Callable[..., T] | Callable[..., Awaitable[T]], 
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    func = ensure_async(function, threaded=threaded)
    if iterables:
        async for args in async_zip(iterable, *iterables, threaded=threaded):
            yield await func(*args)
    else:
        async for arg in ensure_aiter(iterable, threaded=threaded):
            yield await func(arg)


async def async_filter[T](
    function: None | Callable[[T], bool] | Callable[[T], Awaitable[bool]], 
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    if function is None or function is bool:
        async for arg in ensure_aiter(iterable, threaded=threaded):
            if arg:
                yield arg
    else:
        fn = ensure_async(function, threaded=threaded)
        async for arg in ensure_aiter(iterable, threaded=threaded):
            if await fn(arg):
                yield arg


async def async_filterfalse[T](
    function: None | Callable[[T], bool] | Callable[[T], Awaitable[bool]], 
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    if function is None or function is bool:
        async for arg in ensure_aiter(iterable, threaded=threaded):
            if not arg:
                yield arg
    else:
        fn = ensure_async(function, threaded=threaded)
        async for arg in ensure_aiter(iterable, threaded=threaded):
            if not (await fn(arg)):
                yield arg


@overload
async def async_reduce[T](
    function: Callable[[T, T], T] | Callable[[T, T], Awaitable[T]], 
    iterable: Iterable[T] | AsyncIterable[T], 
    initial: Undefined = undefined, 
    /, 
    threaded: bool = False, 
) -> T:
    ...
@overload
async def async_reduce[T, V](
    function: Callable[[V, T], V] | Callable[[V, T], Awaitable[V]], 
    iterable: Iterable[T] | AsyncIterable[T], 
    initial: V, 
    /, 
    threaded: bool = False, 
) -> V:
    ...
async def async_reduce[T, V](
    function: Callable[[T, T], T] | Callable[[T, T], Awaitable[T]] | Callable[[V, T], V] | Callable[[V, T], Awaitable[V]], 
    iterable: Iterable[T] | AsyncIterable[T], 
    initial: Undefined | V = undefined, 
    /, 
    threaded: bool = False, 
) -> T | V:
    iterator = ensure_aiter(iterable, threaded=threaded)
    if initial is undefined:
        try:
            prev: Any = await anext(iterator)
        except StopAsyncIteration:
            raise TypeError("reduce() of empty iterable with no initial value")
    else:
        prev = initial
    call = ensure_async(function, threaded=threaded)
    async for e in iterator:
        prev = await call(prev, e)
    return prev


async def async_zip(
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
    threaded: bool = False, 
) -> AsyncIterator[tuple]:
    if not iterables:
        async for e in ensure_aiter(iterable, threaded=threaded):
            yield e,
        return
    fs = [ensure_aiter(iterable, threaded=threaded).__anext__]
    fs.extend(ensure_aiter(it, threaded=threaded).__anext__ for it in iterables)
    try:
        while True:
            yield tuple([await f() for f in fs])
    except StopAsyncIteration:
        pass


async def async_chain(
    *iterables: Iterable | AsyncIterable, 
    threaded: bool = False, 
) -> AsyncIterator:
    for iterable in iterables:
        async for e in ensure_aiter(iterable, threaded=threaded):
            yield e


async def async_chain_from_iterable(
    iterable: Iterable[Iterable | AsyncIterable] | AsyncIterable[Iterable | AsyncIterable], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator:
    async for iterable in ensure_aiter(iterable, threaded=False):
        async for e in ensure_aiter(iterable, threaded=threaded):
            yield e

setattr(async_chain, "from_iterable", async_chain_from_iterable)


async def async_all(
    iterable: Iterable | AsyncIterable, 
    /, 
    threaded: bool = False, 
) -> bool:
    async for e in ensure_aiter(iterable, threaded=threaded):
        if not e:
            return False
    return True


async def async_any(
    iterable: Iterable | AsyncIterable, 
    /, 
    threaded: bool = False, 
) -> bool:
    async for e in ensure_aiter(iterable, threaded=threaded):
        if e:
            return True
    return False


def async_compress[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    selectors: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    return (e async for e, s in async_zip(iterable, selectors, threaded=threaded) if s)


async def async_cycle[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    seq: Sequence[T]
    if isinstance(iterable, Sequence):
        seq = iterable
        if isinstance(seq, MutableSequence):
            seq = tuple(seq)
    else:
        seq = []
        add = seq.append
        async for e in ensure_aiter(iterable, threaded=threaded):
            yield e
            add(e)
    while True:
        for e in seq:
            yield e


@overload
def async_accumulate[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    function: Callable[[T, T], T] | Callable[[T, T], Awaitable[T]], 
    /, 
    initial: Undefined = undefined, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    ...
@overload
def async_accumulate[T, V](
    iterable: Iterable[T] | AsyncIterable[T], 
    function: Callable[[V, T], V] | Callable[[V, T], Awaitable[V]], 
    /, 
    initial: V, 
    threaded: bool = False, 
) -> AsyncIterator[V]:
    ...
async def async_accumulate[T, V](
    iterable: Iterable[T] | AsyncIterable[T], 
    function: Callable[[T, T], T] | Callable[[T, T], Awaitable[T]] | Callable[[V, T], V] | Callable[[V, T], Awaitable[V]], 
    /, 
    initial: Undefined | V = undefined, 
    threaded: bool = False, 
) -> AsyncIterator[T] | AsyncIterator[V]:
    iterator = ensure_aiter(iterable, threaded=threaded)
    total: T | V
    if initial is undefined:
        try:
            total = await anext(iterator)
        except StopAsyncIteration:
            return
    else:
        total = cast(V, initial)
    yield total
    call = cast(Callable[[T | V, T], Awaitable[T | V]], ensure_async(function, threaded=threaded))
    async for e in iterator:
        total = await call(total, e)
        yield total


async def async_enumerate[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    start: int = 0, 
    threaded: bool = False, 
) -> AsyncIterator[tuple[int, T]]:
    i = start
    async for e in ensure_aiter(iterable, threaded=threaded):
        yield i, e
        i += 1


async def async_islice[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    start: int = 0, 
    stop: None | int = None, 
    step: int = 1, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    if start < 0:
        start = 0
    iterator = async_enumerate(iterable, threaded=threaded)
    if stop is None:
        async for i, e in iterator:
            if i < start:
                continue
            if step <= 1 or (i - start) % step:
                yield e
    elif start > stop:
        end = stop -1
        async for i, e in iterator:
            if i < start:
                continue
            if step <= 1 or (i - start) % step:
                yield e
            if i == end:
                break


async def async_takewhile[T](
    predicate: Callable[[T], Any], 
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    predicate = ensure_async(predicate, threaded=threaded)
    async for e in ensure_aiter(iterable, threaded=threaded):
        if await predicate(e):
            yield e
        break


async def async_dropwhile[T](
    predicate: Callable[[T], Any], 
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    predicate = ensure_async(predicate, threaded=threaded)
    iterator = ensure_aiter(iterable, threaded=threaded)
    async for e in iterator:
        if await predicate(e):
            continue
        yield e
        break
    else:
        return
    async for e in iterator:
        yield e


async def async_batched[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    n: int = 1, 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[tuple[T, ...]]:
    if n <= 0:
        n = 1
    if isinstance(iterable, Sequence):
        if n == 1:
            for e in iterable:
                yield e,
        else:
            for i, j in pairwise(range(0, len(iterable)+n, n)):
                yield tuple(iterable[i:j])
    elif n == 1:
        async for e in ensure_aiter(iterable, threaded=threaded):
            yield e,
    else:
        ls: list[T] = []
        put, clear = ls.append, ls.clear
        remains = n
        async for e in ensure_aiter(iterable, threaded=threaded):
            put(e)
            remains -= 1
            if not remains:
                yield tuple(ls)
                clear()
                remains = n
        if ls:
            yield tuple(ls)


@overload
def async_groupby[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    key: None = None, 
    threaded: bool = False, 
) -> AsyncIterator[tuple[T, AsyncIterator[T]]]:
    ...
@overload
def async_groupby[T, K](
    iterable: Iterable[T] | AsyncIterable[T], 
    key: Callable[[T], K], 
    threaded: bool = False, 
) -> AsyncIterator[tuple[K, AsyncIterator[T]]]:
    ...
async def async_groupby[T, K](
    iterable: Iterable[T] | AsyncIterable[T], 
    key: None | Callable[[T], K] = None, 
    threaded: bool = False, 
) -> AsyncIterator[tuple[T, AsyncIterator[T]]] | AsyncIterator[tuple[K, AsyncIterator[T]]]:
    iterator = ensure_aiter(iterable, threaded=threaded)
    exhausted = False
    cur_key: Any = undefined
    cur_value: Any = undefined
    async def grouper(target_key):
        nonlocal exhausted, cur_key, cur_value
        if cur_value is not undefined:
            yield cur_value
        async for cur_value in iterator:
            if key is None:
                cur_key = cur_value
            else:
                cur_key = key(cur_value)
            if cur_key != target_key:
                return
            yield cur_value
        exhausted = True
    async for _ in grouper(cur_key):
        pass
    while not exhausted:
        target_key = cur_key
        cur_group = grouper(cur_key)
        yield cur_key, cur_group
        if cur_key == target_key:
            async for _ in cur_group:
                pass


async def async_pairwise[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[tuple[T, T]]:
    iterator = ensure_aiter(iterable, threaded=threaded)
    try:
        a = await anext(iterator)
    except StopAsyncIteration:
        return
    async for b in iterator:
        yield a, b
        a = b


async def async_starmap[T](
    function: Callable[..., T] | Callable[..., Awaitable[T]], 
    iterable: Iterable | AsyncIterable, 
    /, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    fn = ensure_async(function, threaded=threaded)
    async for args in ensure_aiter(iterable, threaded=threaded):
        yield await fn(*args)


async def async_count(
    start: int = 0, 
    step: int = 1, 
) -> AsyncIterator[int]:
    n = start
    while True:
        yield n
        n += step


async def async_repeat[T](
    value: T, 
    /, 
    times: None | int = None, 
) -> AsyncIterator[T]:
    if times is None or times < 0:
        while True:
            yield value
    else:
        for _ in range(times):
            yield value


async def async_zip_longest(
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
    fillvalue=None, 
    threaded: bool = False, 
) -> AsyncIterator[tuple]:
    if not iterables:
        async for e in ensure_aiter(iterable, threaded=threaded):
            yield e,
        return
    fs = [ensure_aiter(iterable, threaded=threaded).__anext__]
    fs.extend(ensure_aiter(it, threaded=threaded).__anext__ for it in iterables)
    get_fillvalue = async_repeat(fillvalue).__anext__
    num_active = len(fs)
    while True:
        values: list = []
        add = values.append
        for i, get in enumerate(fs):
            try:
                add(await get())
            except StopAsyncIteration:
                num_active -= 1
                if not num_active:
                    return
                fs[i] = get_fillvalue
                add(fillvalue)
        yield tuple(values)


class _tee[T](AsyncIterator):

    def __init__(self, iterator: AsyncIterator[T], /):
        if isinstance(iterator, _tee):
            self.iterator: AsyncIterator[T] = iterator.iterator
            self.link: list = iterator.link
        else:
            self.iterator = iterator
            self.link = [None, None]

    def __aiter__(self, /) -> Self:
        return self

    async def __anext__(self, /) -> T:
        link = self.link
        if link[1] is None:
            link[0] = await anext(self.iterator)
            link[1] = [None, None]
        value, self.link = link
        return value


def async_tee[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    n: int = 2, 
    threaded: bool = False, 
) -> tuple[AsyncIterator[T], ...]:
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    if n == 0:
        return (ensure_aiter(()),)
    iterator = _tee(ensure_aiter(iterable, threaded=threaded))
    if n == 1:
        return iterator,
    iterators = [iterator]
    iterators.extend(_tee(iterator) for _ in range(n-1))
    return tuple(iterators)


async def call_as_aiter[T](
    function: Callable[[], T] | Callable[[], Awaitable[T]], 
    /, 
    sentinel = undefined, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    function = ensure_async(function, threaded=threaded)
    try:
        if sentinel is undefined:
            while True:
                yield await function()
        elif callable(sentinel):
            sentinel = ensure_async(sentinel)
            while not (await sentinel(r := await function())):
                yield r
        else:
            check = lambda r, /: r is not sentinel and r != sentinel
            while check(r := await function()):
                yield r
    except (StopIteration, StopAsyncIteration):
        pass


async def to_list[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    threaded: bool = False, 
) -> list[T]:
    if type(iterable) is list:
        return iterable # type: ignore
    return [e async for e in ensure_aiter(iterable, threaded=threaded)]


@overload
async def collect[K, V](
    iterable: Iterable[tuple[K, V]] | AsyncIterable[tuple[K, V]] | Mapping[K, V], 
    /, 
    rettype: Callable[[Iterable[tuple[K, V]]], MutableMapping[K, V]], 
    threaded: bool = False, 
) -> MutableMapping[K, V]:
    ...
@overload
async def collect[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    rettype: Callable[[Iterable[T]], Collection[T]] = list, 
    threaded: bool = False, 
) -> Collection[T]:
    ...
async def collect(
    iterable: Iterable | AsyncIterable, 
    /, 
    rettype: Callable[[Iterable], Collection] = list, 
    threaded: bool = False, 
) -> Collection:
    if isinstance(iterable, Iterable):
        if threaded and not isinstance(iterable, Collection):
            iterable = ensure_aiter(iterable, threaded=True)
        else:
            return rettype(iterable)
    if isinstance(rettype, type):
        if issubclass(rettype, MutableSequence):
            if rettype is list:
                return [e async for e in iterable]
            ls = rettype()
            append = ls.append
            async for e in iterable:
                append(e)
            return ls
        elif issubclass(rettype, MutableSet):
            if rettype is set:
                return {e async for e in iterable}
            st = rettype()
            add = st.add
            async for e in iterable:
                add(e)
            return st
        elif issubclass(rettype, MutableMapping):
            if rettype is dict:
                return {k: v async for k, v in iterable}
            dt = rettype()
            async for k, v in iterable:
                dt[k] = v
            return dt
    return rettype([e async for e in iterable])

