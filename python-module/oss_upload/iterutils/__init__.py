#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 1, 5)
__all__ = [
    "Return", "Yield", "YieldFrom", "iterable", "async_iterable", "foreach", "async_foreach", 
    "through", "async_through", "flatten", "async_flatten", "map", "filter", "reduce", "zip", 
    "chunked", "iter_unique", "async_iter_unique", "wrap_iter", "wrap_aiter", "acc_step", 
    "cut_iter", "run_gen_step", "run_gen_step_iter", "bfs_gen", "with_iter_next", "backgroud_loop", 
]

from abc import ABC, abstractmethod
from asyncio import create_task, sleep as async_sleep, to_thread
from builtins import map as _map, filter as _filter, zip as _zip
from collections import deque
from collections.abc import (
    AsyncIterable, AsyncIterator, Awaitable, Buffer, Callable, Coroutine, Generator, 
    Iterable, Iterator, MutableSet, Sequence, 
)
from contextlib import asynccontextmanager, contextmanager, ExitStack, AsyncExitStack
from dataclasses import dataclass
from itertools import batched, pairwise
from inspect import isawaitable, iscoroutinefunction
from _thread import start_new_thread
from time import sleep, time
from typing import overload, Any, AsyncContextManager, ContextManager, Literal

from asynctools import (
    async_filter, async_map, async_reduce, async_zip, async_batched, ensure_async, ensure_aiter, 
)
from texttools import format_time
from undefined import undefined, Undefined


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
        for v in _map(take_while, iterable):
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


def map(
    function: None | Callable, 
    iterable: Iterable | AsyncIterable, 
    /, 
    *iterables: Iterable | AsyncIterable, 
):      
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
    if iscoroutinefunction(function) or isinstance(iterable, AsyncIterable):
        return async_filter(function, iterable)
    return _filter(function, iterable)


def reduce(
    function: Callable, 
    iterable: Iterable | AsyncIterable, 
    initial = undefined, 
    /, 
):
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


@overload
def with_iter_next[T](
    iterable: Iterable[T], 
    /, 
    async_: Literal[False] = False, 
) -> ContextManager[Callable[[], T]]:
    ...
@overload
def with_iter_next[T](
    iterable: AsyncIterable[T], 
    /, 
    async_: Literal[False] = False, 
) -> ContextManager[Callable[[], Awaitable[T]]]:
    ...
@overload
def with_iter_next[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    async_: Literal[True], 
) -> ContextManager[Callable[[], Awaitable[T]]]:
    ...
@contextmanager
def with_iter_next[T](
    iterable: Iterable[T] | AsyncIterable[T], 
    /, 
    async_: Literal[False, True] = False, 
):
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
    async_: Literal[False] = False, 
) -> T:
    ...
@overload
def context[T](
    func: Callable[..., T] | Callable[..., Awaitable[T]], 
    *ctxs: ContextManager | AsyncContextManager, 
    async_: Literal[True], 
) -> Coroutine[Any, Any, T]:
    ...
def context[T](
    func: Callable[..., T] | Callable[..., Awaitable[T]], 
    *ctxs: ContextManager | AsyncContextManager, 
    async_: Literal[False, True] = False, 
) -> T | Coroutine[Any, Any, T]:
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
    async_: Literal[False] = False, 
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
def backgroud_loop(
    call: None | Callable = None, 
    /, 
    interval: int | float = 0.05, 
    *, 
    async_: Literal[False, True] = False, 
) -> ContextManager | AsyncContextManager:
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
        return asynccontextmanager(actx)()
    else:
        def ctx():
            nonlocal running
            try:
                yield start_new_thread(run, ())
            finally:
                running = False
                if use_default_call:
                    print("\r\x1b[K", end="")
        return contextmanager(ctx)()

