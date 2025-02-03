#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 7)
__all__ = [
    "thread_batch", "thread_pool_batch", "async_batch", 
    "threaded", "run_as_thread", "asynchronized", "run_as_async", 
    "threadpool_map", "taskgroup_map", 
]

from asyncio import (
    ensure_future, get_event_loop, BaseEventLoop, CancelledError, Future as AsyncFuture, 
    Queue as AsyncQueue, Semaphore as AsyncSemaphore, TaskGroup, 
)
from collections.abc import (
    AsyncIterable, AsyncIterator, Awaitable, Callable, Coroutine, Iterable, 
    Iterator, Mapping, 
)
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from functools import partial, update_wrapper
from inspect import isawaitable, iscoroutinefunction
from itertools import takewhile
from os import cpu_count
from queue import Queue, SimpleQueue, Empty
from _thread import start_new_thread
from threading import Event, Lock, Semaphore, Thread
from typing import cast, Any, ContextManager, Literal

from argtools import argcount
from asynctools import async_zip, ensure_coroutine, run_async
from decotools import optional


if "__del__" not in ThreadPoolExecutor.__dict__:
    setattr(ThreadPoolExecutor, "__del__", lambda self, /: self.shutdown(wait=False, cancel_futures=True))
if "__del__" not in TaskGroup.__dict__:
    setattr(TaskGroup, "__del__", lambda self, /: run_async(self.__aexit__(None, None, None)))


def thread_batch[T, V](
    work: Callable[[T], V] | Callable[[T, Callable], V], 
    tasks: Iterable[T], 
    callback: None | Callable[[V], Any] = None, 
    max_workers: None | int = None, 
):
    ac = argcount(work)
    if ac < 1:
        raise TypeError(f"{work!r} should accept a positional argument as task")
    with_submit = ac > 1
    if max_workers is None or max_workers <= 0:
        max_workers = min(32, (cpu_count() or 1) + 4)

    q: Queue[T | object] = Queue()
    get, put, task_done = q.get, q.put, q.task_done
    sentinal = object()
    lock = Lock()
    nthreads = 0
    running = True

    def worker():
        task: T | object
        while running:
            try:
                task = get(timeout=1)
            except Empty:
                continue
            if task is sentinal:
                put(sentinal)
                break
            task = cast(T, task)
            try:
                if with_submit:
                    r = cast(Callable[[T, Callable], V], work)(task, submit)
                else:
                    r = cast(Callable[[T], V], work)(task)
                if callback is not None:
                    callback(r)
            except BaseException:
                pass
            finally:
                task_done()

    def submit(task):
        nonlocal nthreads
        if nthreads < max_workers:
            with lock:
                if nthreads < max_workers:
                    start_new_thread(worker, ())
                    nthreads += 1
        put(task)

    for task in tasks:
        submit(task)
    try:
        q.join()
    finally:
        running = False
        q.queue.clear()
        put(sentinal)


def thread_pool_batch[T, V](
    work: Callable[[T], V] | Callable[[T, Callable], V], 
    tasks: Iterable[T], 
    callback: None | Callable[[V], Any] = None, 
    max_workers: None | int = None, 
):
    ac = argcount(work)
    if ac < 1:
        raise TypeError(f"{work!r} should take a positional argument as task")
    with_submit = ac > 1
    if max_workers is None or max_workers <= 0:
        max_workers = min(32, (cpu_count() or 1) + 4)

    ntasks = 0
    lock = Lock()
    done_evt = Event()

    def works(task):
        nonlocal ntasks
        try:
            if with_submit:
                r = cast(Callable[[T, Callable], V], work)(task, submit)
            else:
                r = cast(Callable[[T], V], work)(task)
            if callback is not None:
                callback(r)
        finally:
            with lock:
                ntasks -= 1
            if not ntasks:
                done_evt.set()

    def submit(task):
        nonlocal ntasks
        with lock:
           ntasks += 1
        return create_task(works, task)

    pool = ThreadPoolExecutor(max_workers)
    try:
        create_task = pool.submit
        for task in tasks:
            submit(task)
        if ntasks:
            done_evt.wait()
    finally:
        pool.shutdown(False, cancel_futures=True)


async def async_batch[T, V](
    work: Callable[[T], Coroutine[None, None, V]] | Callable[[T, Callable], Coroutine[None, None, V]], 
    tasks: Iterable[T] | AsyncIterable[T], 
    callback: None | Callable[[V], Any] = None, 
    max_workers: None | int | AsyncSemaphore = None, 
):
    if max_workers is None:
        max_workers = 32
    if isinstance(max_workers, int):
        if max_workers > 0:
            sema = AsyncSemaphore()
        else:
            sema = None
    else:
        sema = max_workers
    ac = argcount(work)
    if ac < 1:
        raise TypeError(f"{work!r} should accept a positional argument as task")
    with_submit = ac > 1
    async def works(task, sema=sema):
        if sema is not None:
            async with sema:
                return await works(task, None)
        try:
            if with_submit:
                r = await cast(Callable[[T, Callable], Coroutine[None, None, V]], work)(task, submit)
            else:
                r = await cast(Callable[[T], Coroutine[None, None, V]], work)(task)
            if callback is not None:
                t = callback(r)
                if isawaitable(t):
                    await t
        except KeyboardInterrupt:
            raise
        except BaseException as e:
            raise CancelledError from e
    async with TaskGroup() as tg:
        create_task = tg.create_task
        submit = lambda task, /: create_task(works(task))
        if isinstance(tasks, Iterable):
            for task in tasks:
                submit(task)
        else:
            async for task in tasks:
                submit(task)


@optional
def threaded[**Args, T](
    func: Callable[Args, T], 
    /, 
    lock: None | int | ContextManager = None, 
    **thread_init_kwds, 
) -> Callable[Args, Future[T]]:
    if isinstance(lock, int):
        lock = Semaphore(lock)
    def wrapper(*args: Args.args, **kwds: Args.kwargs) -> Future[T]:
        if lock is None:
            def asfuture():
                try: 
                    fu.set_result(func(*args, **kwds))
                except BaseException as e:
                    fu.set_exception(e)
        else:
            def asfuture():
                with lock:
                    try: 
                        fu.set_result(func(*args, **kwds))
                    except BaseException as e:
                        fu.set_exception(e)
        fu: Future[T] = Future()
        thread = fu.thread = Thread(target=asfuture, **thread_init_kwds) # type: ignore
        thread.start()
        return fu
    return update_wrapper(wrapper, func)


def run_as_thread[**Args, T](
    func: Callable[Args, T], 
    /, 
    *args: Args.args, 
    **kwargs: Args.kwargs, 
) -> Future[T]:
    return getattr(threaded, "__wrapped__")(func)(*args, **kwargs)


@optional
def asynchronized[**Args, T](
    func: Callable[Args, T], 
    /, 
    loop: None | BaseEventLoop = None, 
    executor: Literal[False, None] | Executor = None, 
) -> Callable[Args, AsyncFuture[T]]:
    def run_in_thread(loop, future, args, kwargs, /):
        try:
            loop.call_soon_threadsafe(future.set_result, func(*args, **kwargs))
        except BaseException as e:
            loop.call_soon_threadsafe(future.set_exception, e)
    def wrapper(*args: Args.args, **kwargs: Args.kwargs) -> AsyncFuture[T]:
        nonlocal loop
        if iscoroutinefunction(func):
            return ensure_future(func(*args, **kwargs), loop=loop)
        if loop is None:
            loop = cast(BaseEventLoop, get_event_loop())
        if executor is False:
            future = loop.create_future()
            start_new_thread(run_in_thread, (loop, future, args, kwargs))
            return future
        return loop.run_in_executor(executor, partial(func, *args, **kwargs))
    return wrapper


def run_as_async[**Args, T](
    func: Callable[Args, T], 
    /, 
    *args: Args.args, 
    **kwargs: Args.kwargs, 
) -> AsyncFuture[T]:
    return getattr(asynchronized, "__wrapped__")(func)(*args, **kwargs)


def threadpool_map[T](
    func: Callable[..., T], 
    it, 
    /, 
    *its, 
    max_workers: None | int = None, 
    kwargs: None | Mapping = None, 
) -> Iterator[T]:
    if kwargs is None:
        kwargs = {}
    if max_workers is None or max_workers <= 0:
        max_workers = min(32, (cpu_count() or 1) + 4)
    queue: SimpleQueue[None | Future] = SimpleQueue()
    get, put = queue.get, queue.put_nowait
    executor = ThreadPoolExecutor(max_workers=max_workers)
    submit = executor.submit
    running = True
    def make_tasks():
        try:
            for args in takewhile(lambda _: running, zip(it, *its)):
                try:
                    put(submit(func, *args, **kwargs))
                except RuntimeError:
                    break
        finally:
            put(None)
    try:
        start_new_thread(make_tasks, ())
        with executor:
            while fu := get():
                yield fu.result()
    finally:
        running = False
        executor.shutdown(wait=False, cancel_futures=True)


async def taskgroup_map[T](
    func: Callable[..., Awaitable[T]], 
    it, 
    /, 
    *its, 
    max_workers: None | int = None, 
    kwargs: None | Mapping = None, 
) -> AsyncIterator[T]:
    if max_workers is None or max_workers <= 0:
        max_workers = 32
    if kwargs is None:
        kwargs = {}
    sema = AsyncSemaphore(max_workers)
    queue: AsyncQueue[None | AsyncFuture] = AsyncQueue()
    get, put = queue.get, queue.put_nowait
    async def call(args):
        async with sema:
            return await func(*args, **kwargs)
    async def make_tasks():
        try:
            async for args in async_zip(it, *its):
                put(create_task(call(args)))
        finally:
            put(None)
    async with TaskGroup() as tg:
        create_task = tg.create_task
        create_task(make_tasks())
        while task := await get():
            yield await task

