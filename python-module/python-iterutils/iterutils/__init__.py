#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 1, 2)
__all__ = [
    "Return", "Yield", "YieldFrom", "iterable", "async_iterable", "foreach", "async_foreach", 
    "through", "async_through", "flatten", "async_flatten", "iter_unique", "async_iter_unique", 
    "chunked", "wrap_iter", "wrap_aiter", "acc_step", "cut_iter", "run_gen_step", 
    "run_gen_step_iter", "bfs_gen", 
]


from abc import ABC, abstractmethod
from asyncio import to_thread
from collections import deque
from collections.abc import (
    AsyncIterable, AsyncIterator, Buffer, Callable, Generator, 
    Iterable, Iterator, MutableSet, Sequence, 
)
from dataclasses import dataclass
from itertools import batched, pairwise
from inspect import isawaitable
from typing import overload, Any, Literal

from asynctools import async_map, async_zip, async_batched, ensure_async, ensure_aiter


@dataclass(slots=True, frozen=True)
class YieldBase(ABC):
    value: Any
    identity: bool = False
    try_call_me: bool = True

    @property
    @abstractmethod
    def yield_type(self, /) -> int:
        ...


class Return(YieldBase):
    yield_type = 0


class Yield(YieldBase):
    yield_type = 1


class YieldFrom(YieldBase):
    yield_type = 2


def iterable(iterable, /) -> bool:
    try:
        return isinstance(iter(iterable), Iterable)
    except TypeError:
        return False


def async_iterable(iterable, /) -> bool:
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
    if not (isinstance(iterable, Iterable) and all(isinstance(it, Iterable) for it in iterables)):
        return async_foreach(value, iterable, *iterables)
    if iterables:
        for args in zip(iterable, *iterables):
            value(*args)
    else:
        for arg in iterable:
            value(arg)


async def async_foreach(
    value: Callable, 
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
    threaded: bool = True, 
):
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
    if not isinstance(iterable, Iterable):
        return async_through(iterable, take_while)
    if take_while is None:
        for _ in iterable:
            pass
    else:
        for v in map(take_while, iterable):
            if not v:
                break


async def async_through(
    iterable: Iterable | AsyncIterable, 
    /, 
    take_while: None | Callable = None, 
    threaded: bool = True, 
):
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
) -> Iterable:
    ...
@overload
def flatten(
    iterable: AsyncIterable, 
    /, 
    exclude_types: type | tuple[type, ...] = (Buffer, str), 
) -> AsyncIterable:
    ...
def flatten(
    iterable: Iterable | AsyncIterable, 
    /, 
    exclude_types: type | tuple[type, ...] = (Buffer, str), 
) -> Iterable | AsyncIterable:
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
    threaded: bool = True, 
) -> AsyncIterator:
    async for e in ensure_aiter(iterable, threaded=threaded):
        if isinstance(e, (Iterable, AsyncIterable)) and not isinstance(e, exclude_types):
            async for e in async_flatten(e, exclude_types, threaded=threaded):
                yield e
        else:
            yield e


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
    if seen is None:
        seen = set()
    add = seen.add
    async for e in ensure_aiter(iterable, threaded=threaded):
        if e not in seen:
            yield e
            add(e)


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
def wrap_iter[T](
    iterable: Iterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
    callenter: None | Callable[[Iterable[T]], Any] = None, 
    callexit: None | Callable[[Iterable[T], None | BaseException], Any] = None, 
) -> Iterator[T]:
    ...
@overload
def wrap_iter[T](
    iterable: AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
    callenter: None | Callable[[Iterable[T] | AsyncIterable[T]], Any] = None, 
    callexit: None | Callable[[Iterable[T] | AsyncIterable[T], None | BaseException], Any] = None, 
) -> AsyncIterator[T]:
    ...
def wrap_iter[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
    callenter: None | Callable[[Iterable[T]], Any] | Callable[[Iterable[T] | AsyncIterable[T]], Any] = None, 
    callexit: ( None | Callable[[Iterable[T], None | BaseException], Any] | 
                Callable[[Iterable[T] | AsyncIterable[T], None | BaseException], Any] ) = None, 
) -> Iterator[T] | AsyncIterator[T]:
    if not isinstance(iterable, Iterable):
        return wrap_aiter(
            iterable, 
            callprev=callprev, 
            callnext=callnext, 
            callenter=callenter, # type: ignore
            callexit=callexit, # type: ignore
        )
    if not callable(callprev):
        callprev = None
    if not callable(callnext):
        callnext = None
    def gen():
        try:
            if callable(callenter):
                callenter(iterable)
            for e in iterable:
                if callprev:
                    try:
                        callprev(e)
                    except (StopIteration, GeneratorExit):
                        break
                yield e
                if callnext:
                    try:
                        callnext(e)
                    except (StopIteration, GeneratorExit):
                        break
        except BaseException as e:
            if callable(callexit):
                if not callexit(iterable, e):
                    raise
            else:
                raise
        finally:
            if callable(callexit):
                callexit(iterable, None)
    return gen()


async def wrap_aiter[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
    callenter: None | Callable[[Iterable[T] | AsyncIterable[T]], Any] = None, 
    callexit: None | Callable[[Iterable[T] | AsyncIterable[T], None | BaseException], Any] = None, 
    threaded: bool = True, 
) -> AsyncIterator[T]:
    callprev = ensure_async(callprev, threaded=threaded) if callable(callprev) else None
    callnext = ensure_async(callnext, threaded=threaded) if callable(callnext) else None
    try:
        async for e in ensure_aiter(iterable, threaded=threaded):
            if callprev:
                try:
                    await callprev(e)
                except (StopAsyncIteration, GeneratorExit):
                    break
            yield e
            if callnext:
                try:
                    await callnext(e)
                except (StopAsyncIteration, GeneratorExit):
                    break
    except BaseException as e:
        if callable(callexit):
            if not await ensure_async(callexit, threaded=threaded)(iterable, e):
                raise
        else:
            raise
    finally:
        if callable(callexit):
            await ensure_async(callexit, threaded=threaded)(iterable, None)


def acc_step(
    start: int, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int, int]]:
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
    if stop is None:
        start, stop = 0, start
    for start in range(start + step, stop, step):
        yield start, step
    if start != stop:
        yield stop, stop - start


def run_gen_step[T](
    gen_step: Generator[Any, Any, T] | Callable[[], Generator[Any, Any, T]], 
    *, 
    async_: bool = False, 
    threaded: bool = False, 
    as_iter: bool = False, 
) -> T:
    if callable(gen_step):
        gen = gen_step()
        close = gen.close
    else:
        gen = gen_step
        close = None
    send = gen.send
    throw = gen.throw
    if async_:
        async def process():
            try:
                if threaded:
                    value = await to_thread(send, None)
                else:
                    value = send(None)
                while True:
                    if isinstance(value, YieldBase):
                        raise StopIteration(value)
                    try:
                        if callable(value):
                            value = value()
                        if isawaitable(value):
                            value = await value
                    except BaseException as e:
                        if threaded:
                            value = await to_thread(throw, e)
                        else:
                            value = throw(e)
                    else:
                        if threaded:
                            value = await to_thread(send, value)
                        else:
                            value = send(value)
            except StopIteration as e:
                value = e.value
                identity = False
                try_call_me = True
                if isinstance(value, YieldBase):
                    identity = value.identity
                    try_call_me = value.try_call_me
                    value = value.value
                if callable(value) and try_call_me:
                    value = value()
                if not identity and isawaitable(value):
                    value = await value
                return value
            finally:
                if close is not None:
                    if threaded:
                        await to_thread(close)
                    else:
                        close()
        result = process()
        if as_iter:
            async def wrap(result):
                iterable = await result
                try:
                    iterable = aiter(iterable)
                except TypeError:
                    for val in iter(iterable):
                        if isawaitable(val):
                            val = await val
                        yield val
                else:
                    async for val in iterable:
                        yield val
            result = wrap(result)
        return result
    else:
        try:
            value = send(None)
            while True:
                if isinstance(value, YieldBase):
                    raise StopIteration(value)
                try:
                    if callable(value):
                        value = value()
                except BaseException as e:
                    value = throw(e)
                else:
                    value = send(value)
        except StopIteration as e:
            value = e.value
            try_call_me = True
            if isinstance(value, YieldBase):
                try_call_me = value.try_call_me
                value = value.value
            if callable(value) and try_call_me:
                value = value()
            if as_iter:
                value = iter(value)
            return value
        finally:
            if close is not None:
                close()


@overload
def run_gen_step_iter(
    gen_step: Generator | Callable[[], Generator], 
    threaded: bool = False, 
    *, 
    async_: Literal[False] = False, 
) -> Iterator:
    ...
@overload
def run_gen_step_iter(
    gen_step: Generator | Callable[[], Generator], 
    threaded: bool = False, 
    *, 
    async_: Literal[True], 
) -> AsyncIterator:
    ...
def run_gen_step_iter(
    gen_step: Generator | Callable[[], Generator], 
    threaded: bool = False, 
    *, 
    async_: bool = False, 
) -> Iterator | AsyncIterator:
    if callable(gen_step):
        gen = gen_step()
        close = gen.close
    else:
        gen = gen_step
        close = None
    send = gen.send
    throw = gen.throw
    if async_:
        async def process():
            async def extract(value):
                identity = False
                try_call_me = True
                yield_type = -1
                if isinstance(value, YieldBase):
                    identity = value.identity
                    try_call_me = value.try_call_me
                    yield_type = value.yield_type
                    value = value.value
                if try_call_me and callable(value):
                    value = value()
                if not identity and isawaitable(value):
                    value = await value
                return yield_type, value
            try:
                if threaded:
                    value = await to_thread(send, None)
                else:
                    value = send(None)
                while True:
                    try:
                        yield_type, value = await extract(value)
                        match yield_type:
                            case 1:
                                yield value
                            case 2:
                                async for val in ensure_aiter(value, threaded=threaded):
                                    yield val
                    except BaseException as e:
                        if threaded:
                            value = await to_thread(throw, e)
                        else:
                            value = throw(e)
                    else:
                        if threaded:
                            value = await to_thread(send, value)
                        else:
                            value = send(value)
            except StopIteration as e:
                yield_type, value = await extract(e.value)
                match yield_type:
                    case 1:
                        yield value
                    case 2:
                        async for val in ensure_aiter(value, threaded=threaded):
                            yield val
            finally:
                if close is not None:
                    if threaded:
                        await to_thread(close)
                    else:
                        close()
    else:
        def process():
            def extract(value, /):
                try_call_me = True
                yield_type = -1
                if isinstance(value, YieldBase):
                    try_call_me = value.try_call_me
                    yield_type  = value.yield_type
                    value       = value.value
                if try_call_me and callable(value):
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
                yield_type, value = extract(e.value)
                match yield_type:
                    case 1:
                        yield value
                    case 2:
                        yield from value
                    case _:
                        return value
            finally:
                if close is not None:
                    close()
    return process()


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

