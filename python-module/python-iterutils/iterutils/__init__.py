#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 2, 2)
__all__ = [
    "Return", "Yield", "YieldFrom", "iterable", "async_iterable", 
    "foreach", "async_foreach", "through", "async_through", "flatten", 
    "async_flatten", "collect", "async_collect", "group_collect", 
    "async_group_collect", "map", "filter", "reduce", "zip", "chunked", 
    "iter_unique", "async_iter_unique", "wrap_iter", "wrap_aiter", 
    "acc_step", "cut_iter", "iter_gen_step", "iter_gen_step_async", 
    "run_gen_step", "run_gen_step_sync_iter", "run_gen_step_async_iter", 
    "run_gen_step_iter", "as_gen_step", "bfs_gen", "with_iter_next", 
    "backgroud_loop", 
]

from abc import ABC, abstractmethod
from asyncio import create_task, sleep as async_sleep, to_thread
from builtins import map as _map, filter as _filter, zip as _zip
from collections import defaultdict, deque
from collections.abc import (
    AsyncIterable, AsyncIterator, Awaitable, Buffer, Callable, 
    Collection, Container, Coroutine, Generator, Iterable, Iterator, 
    Mapping, MutableMapping, MutableSet, MutableSequence, Sequence, 
    ValuesView, 
)
from contextlib import (
    asynccontextmanager, contextmanager, ExitStack, AsyncExitStack, 
)
from copy import copy
from dataclasses import dataclass
from itertools import batched, pairwise
from inspect import isawaitable, iscoroutinefunction
from sys import _getframe
from _thread import start_new_thread
from time import sleep, time
from types import FrameType
from typing import (
    cast, overload, Any, AsyncContextManager, ContextManager, Literal, 
    Protocol, 
)

from asynctools import (
    async_filter, async_map, async_reduce, async_zip, async_batched, 
    ensure_async, ensure_aiter, collect as async_collect, 
)
from decotools import optional
from texttools import format_time
from undefined import undefined


class SupportsBool(Protocol):
    """
    """
    def __bool__(self, /) -> bool: ...


class Reraised(BaseException):
    """
    """
    def __init__(self, exc: BaseException, /):
        if isinstance(exc, Reraised):
            exc = exc.exception
        self.exception: BaseException = exc


@dataclass(slots=True, frozen=True, unsafe_hash=True)
class YieldBase(ABC):
    """
    """
    value: Any
    may_await: None | bool | Literal[1] = False
    may_call: None | bool | Literal[1] = None

    @property
    @abstractmethod
    def yield_type(self, /) -> int:
        ...


class Return(YieldBase):
    """
    """
    __slots__ = ()
    yield_type = 0


class Yield(YieldBase):
    """
    """
    __slots__ = ()
    yield_type = 1


class YieldFrom(YieldBase):
    """
    """
    __slots__ = ()
    yield_type = 2


def iterable(iterable, /) -> bool:
    """
    """
    try:
        return isinstance(iter(iterable), Iterable)
    except TypeError:
        return False


def async_iterable(iterable, /) -> bool:
    """
    """
    try:
        return isinstance(iter(iterable), AsyncIterable)
    except TypeError:
        return False


def foreach(
    value: Callable, 
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
):
    """
    """
    if not (isinstance(iterable, Iterable) and all(isinstance(it, Iterable) for it in iterables)):
        return async_foreach(value, iterable, *iterables)
    if iterables:
        for args in _zip(iterable, *iterables):
            value(*args)
    else:
        for arg in iterable:
            value(arg)


async def async_foreach(
    value: Callable, 
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
    threaded: bool = False, 
):
    """
    """
    value = ensure_async(value, threaded=threaded)
    if iterables:
        async for args in async_zip(iterable, *iterables, threaded=threaded):
            await value(*args)
    else:
        async for arg in ensure_aiter(iterable, threaded=threaded):
            await value(arg)


def through(
    iterable: Iterable | AsyncIterable, 
    /, 
    take_while: None | Callable = None, 
):
    """
    """
    if not isinstance(iterable, Iterable):
        return async_through(iterable, take_while)
    if take_while is None:
        for _ in iterable:
            pass
    else:
        for v in _map(take_while, iterable):
            if not v:
                break


async def async_through(
    iterable: Iterable | AsyncIterable, 
    /, 
    take_while: None | Callable = None, 
    threaded: bool = False, 
):
    """
    """
    iterable = ensure_aiter(iterable, threaded=threaded)
    if take_while is None:
        async for _ in iterable:
            pass
    elif take_while is bool:
        async for v in iterable:
            if not v:
                break
    else:
        async for v in async_map(take_while, iterable):
            if not v:
                break


@overload
def flatten(
    iterable: Iterable, 
    /, 
    exclude_types: type | tuple[type, ...] = (Buffer, str), 
) -> Iterator:
    ...
@overload
def flatten(
    iterable: AsyncIterable, 
    /, 
    exclude_types: type | tuple[type, ...] = (Buffer, str), 
) -> AsyncIterator:
    ...
def flatten(
    iterable: Iterable | AsyncIterable, 
    /, 
    exclude_types: type | tuple[type, ...] = (Buffer, str), 
) -> Iterator | AsyncIterator:
    """
    """
    if not isinstance(iterable, Iterable):
        return async_flatten(iterable, exclude_types)
    def gen(iterable):
        for e in iterable:
            if isinstance(e, (Iterable, AsyncIterable)) and not isinstance(e, exclude_types):
                yield from gen(e)
            else:
                yield e
    return gen(iterable)


async def async_flatten(
    iterable: Iterable | AsyncIterable, 
    /, 
    exclude_types: type | tuple[type, ...] = (Buffer, str), 
    threaded: bool = False, 
) -> AsyncIterator:
    """
    """
    async for e in ensure_aiter(iterable, threaded=threaded):
        if isinstance(e, (Iterable, AsyncIterable)) and not isinstance(e, exclude_types):
            async for e in async_flatten(e, exclude_types, threaded=threaded):
                yield e
        else:
            yield e


@overload
def collect[K, V](
    iterable: Iterable[tuple[K, V]] | Mapping[K, V], 
    /, 
    rettype: Callable[[Iterable[tuple[K, V]]], MutableMapping[K, V]], 
) -> MutableMapping[K, V]:
    ...
@overload
def collect[T](
    iterable: Iterable[T], 
    /, 
    rettype: Callable[[Iterable[T]], Collection[T]] = list, 
) -> Collection[T]:
    ...
@overload
def collect[K, V](
    iterable: AsyncIterable[tuple[K, V]], 
    /, 
    rettype: Callable[[Iterable[tuple[K, V]]], MutableMapping[K, V]], 
) -> Coroutine[Any, Any, MutableMapping[K, V]]:
    ...
@overload
def collect[T](
    iterable: AsyncIterable[T], 
    /, 
    rettype: Callable[[Iterable[T]], Collection[T]] = list, 
) -> Coroutine[Any, Any, Collection[T]]:
    ...
def collect(
    iterable: Iterable | AsyncIterable | Mapping, 
    /, 
    rettype: Callable[[Iterable], Collection] = list, 
) -> Collection | Coroutine[Any, Any, Collection]:
    """
    """
    if not isinstance(iterable, Iterable):
        return async_collect(iterable, rettype)
    return rettype(iterable)


@overload
def group_collect[K, V, C: Container](
    iterable: Iterable[tuple[K, V]], 
    mapping: None = None, 
    factory: None | C | Callable[[], C] = None, 
) -> dict[K, C]:
    ...
@overload
def group_collect[K, V, C: Container, M: MutableMapping](
    iterable: Iterable[tuple[K, V]], 
    mapping: M, 
    factory: None | C | Callable[[], C] = None, 
) -> M:
    ...
@overload
def group_collect[K, V, C: Container](
    iterable: AsyncIterable[tuple[K, V]], 
    mapping: None = None, 
    factory: None | C | Callable[[], C] = None, 
) -> Coroutine[Any, Any, dict[K, C]]:
    ...
@overload
def group_collect[K, V, C: Container, M: MutableMapping](
    iterable: AsyncIterable[tuple[K, V]], 
    mapping: M, 
    factory: None | C | Callable[[], C] = None, 
) -> Coroutine[Any, Any, M]:
    ...
def group_collect[K, V, C: Container, M: MutableMapping](
    iterable: Iterable[tuple[K, V]] | AsyncIterable[tuple[K, V]], 
    mapping: None | M = None, 
    factory: None | C | Callable[[], C] = None, 
) -> dict[K, C] | M | Coroutine[Any, Any, dict[K, C]] | Coroutine[Any, Any, M]:
    """
    """
    if not isinstance(iterable, Iterable):
        return async_group_collect(iterable, mapping, factory)
    if factory is None:
        if isinstance(mapping, defaultdict):
            factory = mapping.default_factory
        elif mapping:
            factory = type(next(iter(ValuesView(mapping))))
        else:
            factory = cast(type[C], list)
    elif callable(factory):
        pass
    elif isinstance(factory, Container):
        factory = cast(Callable[[], C], lambda _obj=factory: copy(_obj))
    else:
        raise ValueError("can't determine factory")
    factory = cast(Callable[[], C], factory)
    if isinstance(factory, type):
        factory_type = factory
    else:
        factory_type = type(factory())
    if issubclass(factory_type, MutableSequence):
        add = getattr(factory_type, "append")
    else:
        add = getattr(factory_type, "add")
    if mapping is None:
        mapping = cast(M, {})
    for k, v in iterable:
        try:
            c = mapping[k]
        except LookupError:
            c = mapping[k] = factory()
        add(c, v)
    return mapping


@overload
async def async_group_collect[K, V, C: Container](
    iterable: Iterable[tuple[K, V]] | AsyncIterable[tuple[K, V]], 
    mapping: None = None, 
    factory: None | C | Callable[[], C] = None, 
    threaded: bool = False, 
) -> dict[K, C]:
    ...
@overload
async def async_group_collect[K, V, C: Container, M: MutableMapping](
    iterable: Iterable[tuple[K, V]] | AsyncIterable[tuple[K, V]], 
    mapping: M, 
    factory: None | C | Callable[[], C] = None, 
    threaded: bool = False, 
) -> M:
    ...
async def async_group_collect[K, V, C: Container, M: MutableMapping](
    iterable: Iterable[tuple[K, V]] | AsyncIterable[tuple[K, V]], 
    mapping: None | M = None, 
    factory: None | C | Callable[[], C] = None, 
    threaded: bool = False, 
) -> dict[K, C] | M:
    """
    """
    iterable = ensure_aiter(iterable, threaded=threaded)
    if factory is None:
        if isinstance(mapping, defaultdict):
            factory = mapping.default_factory
        elif mapping:
            factory = type(next(iter(ValuesView(mapping))))
        else:
            factory = cast(type[C], list)
    elif callable(factory):
        pass
    elif isinstance(factory, Container):
        factory = cast(Callable[[], C], lambda _obj=factory: copy(_obj))
    else:
        raise ValueError("can't determine factory")
    factory = cast(Callable[[], C], factory)
    if isinstance(factory, type):
        factory_type = factory
    else:
        factory_type = type(factory())
    if issubclass(factory_type, MutableSequence):
        add = getattr(factory_type, "append")
    else:
        add = getattr(factory_type, "add")
    if mapping is None:
        mapping = cast(M, {})
    async for k, v in iterable:
        try:
            c = mapping[k]
        except LookupError:
            c = mapping[k] = factory()
        add(c, v)
    return mapping


def map(
    function: None | Callable, 
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
):
    """
    """
    if (
        iscoroutinefunction(function) or 
        isinstance(iterable, AsyncIterable) or 
        any(isinstance(i, AsyncIterable) for i in iterables)
    ):
        if function is None:
            if iterables:
                return async_zip(iterable, *iterables)
            else:
                return iterable
        return async_map(function, iterable, *iterables)
    if function is None:
        if iterables:
            return _zip(iterable, *iterables)
        else:
            return iterable
    return _map(function, iterable, *iterables)


def filter(
    function: None | Callable, 
    iterable: Iterable | AsyncIterable, 
    /, 
):
    """
    """
    if iscoroutinefunction(function) or isinstance(iterable, AsyncIterable):
        return async_filter(function, iterable)
    return _filter(function, iterable)


def reduce(
    function: Callable, 
    iterable: Iterable | AsyncIterable, 
    initial: Any = undefined, 
    /, 
):
    """
    """
    if iscoroutinefunction(function) or isinstance(iterable, AsyncIterable):
        return async_reduce(function, iterable, initial)
    from functools import reduce
    if initial is undefined:
        return reduce(function, iterable)
    return reduce(function, iterable, initial)


def zip(
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
):
    """
    """
    if isinstance(iterable, AsyncIterable) or any(isinstance(i, AsyncIterable) for i in iterables):
        return async_zip(iterable, *iterables)
    return _zip(iterable, *iterables)


@overload
def chunked[T](
    iterable: Iterable[T], 
    n: int = 1, 
    /, 
) -> Iterator[Sequence[T]]:
    ...
@overload
def chunked[T](
    iterable: AsyncIterable[T], 
    n: int = 1, 
    /, 
) -> AsyncIterator[Sequence[T]]:
    ...
def chunked[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    n: int = 1, 
    /, 
) -> Iterator[Sequence[T]] | AsyncIterator[Sequence[T]]:
    """
    """
    if n < 0:
        n = 1
    if isinstance(iterable, Sequence):
        if n == 1:
            return ((e,) for e in iterable)
        return (iterable[i:j] for i, j in pairwise(range(0, len(iterable)+n, n)))
    elif isinstance(iterable, Iterable):
        return batched(iterable, n)
    else:
        return async_batched(iterable, n)


@overload
def iter_unique[T](
    iterable: Iterable[T], 
    /, 
    seen: None | MutableSet = None, 
) -> Iterator[T]:
    ...
@overload
def iter_unique[T](
    iterable: AsyncIterable[T], 
    /, 
    seen: None | MutableSet = None, 
) -> AsyncIterator[T]:
    ...
def iter_unique[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    seen: None | MutableSet = None, 
) -> Iterator[T] | AsyncIterator[T]:
    """
    """
    if not isinstance(iterable, Iterable):
        return async_iter_unique(iterable, seen)
    if seen is None:
        seen = set()
    def gen(iterable):
        add = seen.add
        for e in iterable:
            if e not in seen:
                yield e
                add(e)
    return gen(iterable)


async def async_iter_unique[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    seen: None | MutableSet = None, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    """
    """
    if seen is None:
        seen = set()
    add = seen.add
    async for e in ensure_aiter(iterable, threaded=threaded):
        if e not in seen:
            yield e
            add(e)


@overload
def wrap_iter[T](
    iterable: Iterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
) -> Iterator[T]:
    ...
@overload
def wrap_iter[T](
    iterable: AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
) -> AsyncIterator[T]:
    ...
def wrap_iter[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
) -> Iterator[T] | AsyncIterator[T]:
    """
    """
    if not isinstance(iterable, Iterable):
        return wrap_aiter(
            iterable, 
            callprev=callprev, 
            callnext=callnext, 
        )
    if not callable(callprev):
        callprev = None
    if not callable(callnext):
        callnext = None
    def gen():
        for e in iterable:
            callprev and callprev(e)
            yield e
            callnext and callnext(e)
    return gen()


async def wrap_aiter[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
    threaded: bool = False, 
) -> AsyncIterator[T]:
    """
    """
    callprev = ensure_async(callprev, threaded=threaded) if callable(callprev) else None
    callnext = ensure_async(callnext, threaded=threaded) if callable(callnext) else None
    async for e in ensure_aiter(iterable, threaded=threaded):
        callprev and await callprev(e)
        yield e
        callnext and await callnext(e)


def acc_step(
    start: int, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int, int]]:
    """
    """
    if stop is None:
        start, stop = 0, start
    for i in range(start + step, stop, step):
        yield start, (start := i), step
    if start != stop:
        yield start, stop, stop - start


def cut_iter(
    start: int, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int]]:
    """
    """
    if stop is None:
        start, stop = 0, start
    for start in range(start + step, stop, step):
        yield start, step
    if start != stop:
        yield stop, stop - start


def _get_async(back: int = 2) -> bool:
    f: None | FrameType
    f = _getframe(back)
    f_globals = f.f_globals
    f_locals  = f.f_locals
    if f_locals is f_globals:
        return f_locals.get("async_") or False
    while f_locals is not None and f_locals is not f_globals:
        if "async_" in f_locals:
            return f_locals["async_"] or False
        f = f.f_back
        if f is None:
            break
        f_locals = f.f_locals
    return False


@overload
def call_as_async[**Args, T: Coroutine](
    func: Callable[Args, T], /, 
    may_await: bool | Literal[1] = False, 
    threaded: bool = False, 
) -> Callable[Args, T]:
    ...
@overload
def call_as_async[**Args, T](
    func: Callable[Args, T], /, 
    may_await: bool | Literal[1] = False, 
    threaded: bool = False, 
) -> Callable[Args, Coroutine[Any, Any, T]]:
    ...
def call_as_async[**Args, T](
    func: Callable[Args, T], 
    /, 
    may_await: bool | Literal[1] = False, 
    threaded: bool = False, 
) -> Callable[Args, T] | Callable[Args, Coroutine[Any, Any, T]]:
    """
    """
    if iscoroutinefunction(func):
        return func
    def wraps(*args, **kwds):
        try:
            return func(*args, **kwds)
        except (StopIteration, StopAsyncIteration) as e:
            raise Reraised(e) from e
    async def wrapper(*args, **kwds):
        if threaded:
            value = await to_thread(wraps, *args, **kwds)
        else:
            value = wraps(*args, **kwds)
        if may_await is 1 or may_await and isawaitable(value):
            value = await value
        return value
    return wrapper


def iter_gen_step(
    gen_step: Generator | Callable[[], Generator], 
    may_call: bool | Literal[1] = True, 
):
    """
    """
    if callable(gen_step):
        gen_step = gen_step()
    send  = gen_step.send
    throw = gen_step.throw
    close = gen_step.close
    value: Any = None
    try:
        while True:
            if isinstance(value, YieldBase):
                raise StopIteration(value)
            try:
                if may_call is 1 or may_call and callable(value):
                    value = value()
            except BaseException as e:
                value = throw(e)
            else:
                value = send(value)
            yield value
    except StopIteration as e:
        value = e.value
        if isinstance(value, YieldBase):
            maybe_callable = value.may_call
            if maybe_callable is not None:
                may_call = maybe_callable
            value = value.value
        if may_call is 1 or may_call and callable(value):
            try:
                value = value()
            except BaseException as e:
                try:
                    value = throw(e)
                except BaseException as e:
                    raise Reraised(e) from e
        yield value
    finally:
        close()


async def iter_gen_step_async(
    gen_step: Generator | Callable[[], Generator], 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
):
    """
    """
    if callable(gen_step):
        gen_step = gen_step()
    send: Callable  = call_as_async(gen_step.send, threaded=threaded)
    throw: Callable = call_as_async(gen_step.throw, threaded=threaded)
    close: Callable = call_as_async(gen_step.close, threaded=threaded)
    value: Any = None
    try:
        while True:
            if isinstance(value, YieldBase):
                raise StopIteration(value)
            try:
                if may_call is 1 or may_call and callable(value):
                    value = await call_as_async(
                        value, may_await=may_await, threaded=threaded)()
                elif may_await is 1 or may_await and isawaitable(value):
                    value = await value
            except BaseException as e:
                if isinstance(e, Reraised):
                    e = e.exception
                value = await throw(e)
            else:
                value = await send(value)
            yield value
    except BaseException as e:
        if isinstance(e, Reraised):
            e = e.exception
        if isinstance(e, StopIteration):
            value = e.value
            if isinstance(value, YieldBase):
                maybe_awaitable = value.may_await
                if maybe_awaitable is not None:
                    may_await = maybe_awaitable
                maybe_callable  = value.may_call
                if maybe_callable is not None:
                    may_call = maybe_callable
                value = value.value
            try:
                if may_call is 1 or may_call and callable(value):
                    value = await call_as_async(
                        value, may_await=may_await, threaded=threaded)()
                elif may_await is 1 or may_await and isawaitable(value):
                    value = await value
            except BaseException as e:
                try:
                    value = await throw(e)
                except BaseException as e:
                    raise Reraised(e) from e
            yield value
        else:
            raise
    finally:
        await close()


def run_gen_step(
    gen_step: Generator | Callable[[], Generator], 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
    running_flag: None | SupportsBool | Callable[[], SupportsBool] | Callable[[], Awaitable[SupportsBool]] = None, 
    *, 
    async_: None | bool = None, 
):
    """
    """
    if async_ is None:
        async_ = _get_async()
    if async_:
        async def process():
            gen = iter_gen_step_async(
                gen_step, 
                may_await=may_await, 
                may_call=may_call, 
                threaded=threaded, 
            )
            try:
                if running_flag is None:
                    async for value in gen:
                        pass
                elif callable(running_flag):
                    pred = call_as_async(running_flag, threaded=threaded)
                    if not await pred():
                        raise RuntimeError("stop before starting", gen) from StopIteration()
                    async for value in gen:
                        if not await pred():
                            raise RuntimeError("stop midway", gen) from StopIteration(value)
                else:
                    if not running_flag:
                        raise RuntimeError("stop before starting", gen) from StopIteration()
                    async for value in gen:
                        if not running_flag:
                            raise RuntimeError("stop midway", gen) from StopIteration(value)
                return value
            except Reraised as e:
                raise e.exception
            except KeyboardInterrupt as e:
                e.args = gen,
                e.add_note(f"stop iterating gen_step: {gen!r}")
                raise
        return process()
    else:
        gen = iter_gen_step(gen_step, may_call=may_call)
        try:
            if running_flag is None:
                for value in gen:
                    pass
            else:
                if not callable(running_flag):
                    running_flag = running_flag.__bool__
                if not running_flag():
                    raise RuntimeError("stop before starting", gen) from StopIteration()
                for value in gen:
                    if not running_flag():
                        raise RuntimeError("stop midway", gen) from StopIteration(value)
            return value
        except Reraised as e:
            raise e.exception
        except KeyboardInterrupt as e:
            e.args = gen,
            e.add_note(f"stop iterating gen_step: {gen!r}")
            raise


def run_gen_step_sync_iter(
    gen_step: Generator | Callable[[], Generator], 
    may_call: bool | Literal[1] = True, 
) -> Iterator:
    """
    """
    if callable(gen_step):
        gen_step = gen_step()
    send:  Callable = gen_step.send
    throw: Callable = gen_step.throw
    close: Callable = gen_step.close
    def extract(value, may_call=may_call, /):
        yield_type = -1
        if isinstance(value, YieldBase):
            yield_type = value.yield_type
            maybe_callable = value.may_call
            if maybe_callable is not None:
                may_call = maybe_callable
            value      = value.value
        if may_call is 1 or may_call and callable(value):
            value = value()
        return yield_type, value
    try:
        value = send(None)
        while True:
            try:
                yield_type, value = extract(value)
                match yield_type:
                    case 0:
                        return value
                    case 1:
                        yield value
                    case 2:
                        yield from value
            except BaseException as e:
                value = throw(e)
            else:
                value = send(value)
    except StopIteration as e:
        try:
            yield_type, value = extract(e.value)
            match yield_type:
                case 1:
                    yield value
                case 2:
                    yield from value
                case _:
                    return value
        except BaseException as e:
            throw(e)
    finally:
        close()


async def run_gen_step_async_iter(
    gen_step: Generator | Callable[[], Generator], 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
) -> AsyncIterator:
    """
    """
    if callable(gen_step):
        gen_step = gen_step()
    send:  Callable = call_as_async(gen_step.send, threaded=threaded)
    throw: Callable = call_as_async(gen_step.throw, threaded=threaded)
    close: Callable = call_as_async(gen_step.close, threaded=threaded)
    async def extract(value, may_await=may_await, may_call=may_call, /):
        yield_type = -1
        if isinstance(value, YieldBase):
            yield_type = value.yield_type
            maybe_awaitable = value.may_await
            if maybe_awaitable is not None:
                may_await = maybe_awaitable
            maybe_callable = value.may_call
            if maybe_callable is not None:
                may_call = maybe_callable
            value = value.value
        if may_call is 1 or may_call and callable(value):
            value = await call_as_async(
                value, may_await=may_await, threaded=threaded)()
        elif may_await is 1 or may_await and isawaitable(value):
            value = await value
        return yield_type, value
    try:
        value = await send(None)
        while True:
            try:
                yield_type, value = await extract(value)
                match yield_type:
                    case 0:
                        return
                    case 1:
                        yield value
                    case 2:
                        async for val in ensure_aiter(value, threaded=threaded):
                            yield val
            except BaseException as e:
                if isinstance(e, Reraised):
                    e = e.exception
                value = await throw(e)
            else:
                value = await send(value)
    except BaseException as e:
        if isinstance(e, Reraised):
            e = e.exception
        if isinstance(e, StopIteration):
            try:
                yield_type, value = await extract(e.value)
                match yield_type:
                    case 1:
                        yield value
                    case 2:
                        async for val in ensure_aiter(value, threaded=threaded):
                            yield val
            except BaseException as e:
                if isinstance(e, Reraised):
                    e = e.exception
                await throw(e)
        else:
            raise
    finally:
        await close()


@overload
def run_gen_step_iter(
    gen_step: Generator | Callable[[], Generator], 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
    *, 
    async_: None = None, 
) -> Iterator | AsyncIterator:
    ...
@overload
def run_gen_step_iter(
    gen_step: Generator | Callable[[], Generator], 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
    *, 
    async_: Literal[False], 
) -> Iterator:
    ...
@overload
def run_gen_step_iter(
    gen_step: Generator | Callable[[], Generator], 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
    *, 
    async_: Literal[True], 
) -> AsyncIterator:
    ...
def run_gen_step_iter(
    gen_step: Generator | Callable[[], Generator], 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
    *, 
    async_: None | bool = None, 
) -> Iterator | AsyncIterator:
    """
    """
    if async_ is None:
        async_ = _get_async()
    if async_:
        return run_gen_step_async_iter(
            gen_step, 
            may_await=may_await, 
            may_call=may_call, 
            threaded=threaded, 
        )
    else:
        return run_gen_step_sync_iter(gen_step, may_call=may_call)


@optional
def as_gen_step(
    func: Callable, 
    /, 
    iter: bool = False, 
    may_await: bool | Literal[1] = True, 
    may_call: bool | Literal[1] = True, 
    threaded: bool = False, 
    running_flag: None | SupportsBool | Callable[[], SupportsBool] | Callable[[], Awaitable[SupportsBool]] = None, 
    *, 
    async_: None | bool = None, 
) -> Callable:
    """装饰器，构建一个 gen_step 函数
    """
    if async_ is None:
        async_ = _get_async()
    def wrapper(*args, **kwds):
        if iter:
            return run_gen_step_iter(
                func(*args, **kwds), 
                may_await=may_await, 
                may_call=may_call, 
                threaded=threaded, 
                async_=async_, # type: ignore
            )
        else:
            return run_gen_step(
                func(*args, **kwds), 
                may_await=may_await, 
                may_call=may_call, 
                threaded=threaded, 
                running_flag=running_flag, 
                async_=async_, 
            )
    return wrapper


@overload
def bfs_gen[T](
    initial: T, 
    /, 
    unpack_iterator: Literal[False] = False, 
) -> Generator[T, T | None, None]:
    ...
@overload
def bfs_gen[T](
    initial: T | Iterator[T], 
    /, 
    unpack_iterator: Literal[True], 
) -> Generator[T, T | None, None]:
    ...
def bfs_gen[T](
    initial: T | Iterator[T], 
    /, 
    unpack_iterator: bool = False, 
) -> Generator[T, T | None, None]:
    """辅助函数，返回生成器，用来简化广度优先遍历
    """
    dq: deque[T] = deque()
    push, pushmany, pop = dq.append, dq.extend, dq.popleft
    if isinstance(initial, Iterator) and unpack_iterator:
        pushmany(initial)
    else:
        push(initial) # type: ignore
    while dq:
        args: None | T = yield (val := pop())
        if unpack_iterator:
            while args is not None:
                if isinstance(args, Iterator):
                    pushmany(args)
                else:
                    push(args)
                args = yield val
        else:
            while args is not None:
                push(args)
                args = yield val


@overload
def with_iter_next[T](
    iterable: Iterable[T], 
    /, 
    async_: Literal[False], 
) -> ContextManager[Callable[[], T]]:
    ...
@overload
def with_iter_next[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    async_: Literal[True], 
) -> ContextManager[Callable[[], Awaitable[T]]]:
    ...
@overload
def with_iter_next[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    async_: None = None, 
) -> ContextManager[Callable[[], T]] | ContextManager[Callable[[], Awaitable[T]]]:
    ...
@contextmanager
def with_iter_next[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    async_: None | Literal[False, True] = None, 
):
    """
    """
    if async_ is None:
        if not isinstance(iterable, Iterable):
            async_ = True
        else:
            async_ = _get_async()
    if async_:
        get_next: Callable[[], T] | Callable[[], Awaitable[T]] = ensure_aiter(iterable).__anext__
    elif isinstance(iterable, Iterable):
        get_next = iter(iterable).__next__
    else:
        get_next = aiter(iterable).__anext__
        async_ = True
    if async_:
        try:
            yield get_next
        except StopAsyncIteration:
            pass
    else:
        try:
            yield get_next
        except StopIteration:
            pass


@overload
def context[T](
    func: Callable[..., T], 
    *ctxs: ContextManager, 
    async_: Literal[False], 
) -> T:
    ...
@overload
def context[T](
    func: Callable[..., T] | Callable[..., Awaitable[T]], 
    *ctxs: ContextManager | AsyncContextManager, 
    async_: Literal[True], 
) -> Coroutine[Any, Any, T]:
    ...
@overload
def context[T](
    func: Callable[..., T] | Callable[..., Awaitable[T]], 
    *ctxs: ContextManager | AsyncContextManager, 
    async_: None = None, 
) -> T | Coroutine[Any, Any, T]:
    ...
def context[T](
    func: Callable[..., T] | Callable[..., Awaitable[T]], 
    *ctxs: ContextManager | AsyncContextManager, 
    async_: None | Literal[False, True] = None, 
) -> T | Coroutine[Any, Any, T]:
    """
    """
    if async_ is None:
        if iscoroutinefunction(func):
            async_ = True
        else:
            async_ = _get_async()
    if async_:
        async def call():
            args: list = []
            add_arg = args.append
            with ExitStack() as stack:
                async with AsyncExitStack() as async_stack:
                    enter = stack.enter_context
                    async_enter = async_stack.enter_async_context
                    for ctx in ctxs:
                        if isinstance(ctx, AsyncContextManager):
                            add_arg(await async_enter(ctx))
                        else:
                            add_arg(enter(ctx))
                    ret = func(*args)
                    if isawaitable(ret):
                        ret = await ret
                    return ret
        return call()
    else:
        with ExitStack() as stack:
            return func(*map(stack.enter_context, ctxs)) # type: ignore


@overload
def backgroud_loop(
    call: None | Callable = None, 
    /, 
    interval: int | float = 0.05, 
    *, 
    async_: Literal[False], 
) -> ContextManager:
    ...
@overload
def backgroud_loop(
    call: None | Callable = None, 
    /, 
    interval: int | float = 0.05, 
    *, 
    async_: Literal[True], 
) -> AsyncContextManager:
    ...
@overload
def backgroud_loop(
    call: None | Callable = None, 
    /, 
    interval: int | float = 0.05, 
    *, 
    async_: None = None, 
) -> ContextManager | AsyncContextManager:
    ...
def backgroud_loop(
    call: None | Callable = None, 
    /, 
    interval: int | float = 0.05, 
    *, 
    async_: None | Literal[False, True] = None, 
) -> ContextManager | AsyncContextManager:
    """
    """
    if async_ is None:
        if iscoroutinefunction(call):
            async_ = True
        else:
            async_ = _get_async()
    use_default_call = not callable(call)
    if use_default_call:
        start = time()
        def call():
            print(f"\r\x1b[K{format_time(time() - start)}", end="")
    def run():
        while running:
            try:
                yield call
            except Exception:
                pass
            if interval > 0:
                if async_:
                    yield async_sleep(interval)
                else:
                    sleep(interval)
    running = True
    if async_:
        @asynccontextmanager
        async def actx():
            nonlocal running
            try:
                task = create_task(run())
                yield task
            finally:
                running = False
                task.cancel()
                if use_default_call:
                    print("\r\x1b[K", end="")
        return actx()
    else:
        @contextmanager
        def ctx():
            nonlocal running
            try:
                yield start_new_thread(run, ())
            finally:
                running = False
                if use_default_call:
                    print("\r\x1b[K", end="")
        return ctx()

