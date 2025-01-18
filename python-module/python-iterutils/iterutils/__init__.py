#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 9)
__all__ = [
    "iterable", "async_iterable", "foreach", "async_foreach", "through", "async_through", 
    "wrap_iter", "wrap_aiter", "acc_step", "cut_iter", "run_gen_step", "run_gen_step_iter", 
    "Return", "Yield", "YieldFrom", 
]

from abc import ABC, abstractmethod
from asyncio import to_thread
from collections.abc import (
    AsyncIterable, AsyncIterator, Callable, Generator, Iterable, Iterator, 
)
from dataclasses import dataclass
from inspect import isawaitable
from typing import overload, Any, Literal, TypeVar

from asynctools import async_map, async_zip, ensure_async, ensure_aiter


T = TypeVar("T")


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


def iterable(it, /) -> bool:
    try:
        return isinstance(iter(it), Iterable)
    except TypeError:
        return False


def async_iterable(it, /) -> bool:
    try:
        return isinstance(iter(it), AsyncIterable)
    except TypeError:
        return False


def foreach(value: Callable, iterable, /, *iterables):
    if iterables:
        for args in zip(iterable, *iterables):
            value(*args)
    else:
        for arg in iterable:
            value(arg)


async def async_foreach(value: Callable, iterable, /, *iterables, threaded: bool = True):
    value = ensure_async(value, threaded=threaded)
    if iterables:
        async for args in async_zip(iterable, *iterables, threaded=threaded):
            await value(*args)
    else:
        async for arg in ensure_aiter(iterable, threaded=threaded):
            await value(arg)


def through(it: Iterable, /, take_while: None | Callable = None):
    if take_while is None:
        for _ in it:
            pass
    else:
        for v in map(take_while, it):
            if not v:
                break


async def async_through(
    it: Iterable | AsyncIterable, 
    /, 
    take_while: None | Callable = None, 
    threaded: bool = True, 
):
    it = ensure_aiter(it, threaded=threaded)
    if take_while is None:
        async for _ in it:
            pass
    elif take_while is bool:
        async for v in it:
            if not v:
                break
    else:
        async for v in async_map(take_while, it):
            if not v:
                break


def wrap_iter(
    it: Iterable[T], 
    /, 
    callprev: None | Callable[[T], Any] = None, 
    callnext: None | Callable[[T], Any] = None, 
    callenter: None | Callable[[Iterable[T]], Any] = None, 
    callexit: None | Callable[[Iterable[T], None | BaseException], Any] = None, 
) -> Iterator[T]:
    if not callable(callprev):
        callprev = None
    if not callable(callnext):
        callnext = None
    try:
        if callable(callenter):
            callenter(it)
        for e in it:
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
            if not callexit(it, e):
                raise
        else:
            raise
    finally:
        if callable(callexit):
            callexit(it, None)


async def wrap_aiter(
    it: Iterable[T] | AsyncIterable[T], 
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
        async for e in ensure_aiter(it, threaded=threaded):
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
            if not await ensure_async(callexit, threaded=threaded)(it, e):
                raise
        else:
            raise
    finally:
        if callable(callexit):
            await ensure_async(callexit, threaded=threaded)(it, None)


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


def run_gen_step(
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
                it = await result
                try:
                    it = aiter(it)
                except TypeError:
                    for val in iter(it):
                        if isawaitable(val):
                            val = await val
                        yield val
                else:
                    async for val in it:
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

