#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["thread_batch", "thread_pool_batch", "async_batch", "threaded", "run_as_thread"]

from asyncio import CancelledError, Semaphore as AsyncSemaphore, TaskGroup
from collections.abc import Callable, Coroutine, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial, update_wrapper
from inspect import isawaitable
from queue import Queue
from threading import Event, Lock, Semaphore, Thread
from typing import cast, Any, ContextManager, Optional, ParamSpec, TypeVar

from argtools import argcount
from decotools import optional


Args = ParamSpec("Args")
T = TypeVar("T")
V = TypeVar("V")


def thread_batch(
    work: Callable[[T], V] | Callable[[T, Callable], V], 
    tasks: Iterable[T], 
    callback: Optional[Callable[[V], Any]] = None, 
    workers: int = 1, 
):
    ac = argcount(work)
    if ac < 1:
        raise TypeError(f"{work!r} should accept a positional argument as task")
    with_submit = ac > 1
    if workers <= 0:
        workers = 1
    sentinal = object()
    q: Queue[T | object] = Queue()
    get, put, task_done = q.get, q.put, q.task_done
    def worker():
        task: T | object
        while (task := get()) is not sentinal:
            task = cast(T, task)
            try:
                if with_submit:
                    r = cast(Callable[[T, Callable], V], work)(task, put)
                else:
                    r = cast(Callable[[T], V], work)(task)
                if callback is not None:
                    callback(r)
            except BaseException:
                pass
            task_done()
        put(sentinal)
    for task in tasks:
        put(task)
    for _ in range(workers):
        Thread(target=worker).start()
    try:
        q.join()
    finally:
        q.queue.clear()
        put(sentinal)


def thread_pool_batch(
    work: Callable[[T], V] | Callable[[T, Callable], V], 
    tasks: Iterable[T], 
    callback: Optional[Callable[[V], Any]] = None, 
    max_workers: Optional[int] = None, 
):
    ac = argcount(work)
    if ac < 1:
        raise TypeError(f"{work!r} should take a positional argument as task")
    with_submit = ac > 1
    n = 0
    lock = Lock()
    done_evt = Event()
    def works(task):
        nonlocal n
        try:
            if with_submit:
                r = cast(Callable[[T, Callable], V], work)(task, submit)
            else:
                r = cast(Callable[[T], V], work)(task)
            if callback is not None:
                callback(r)
        finally:
            with lock:
                n -= 1
            if not n:
                done_evt.set()
    def submit(task):
        nonlocal n
        with lock:
           n += 1
        return create_task(works, task)
    pool = ThreadPoolExecutor(max_workers)
    try:
        create_task = pool.submit
        for task in tasks:
            submit(task)
        done_evt.wait()
    finally:
        pool.shutdown(False, cancel_futures=True)


async def async_batch(
    work: Callable[[T], Coroutine[None, None, V]] | Callable[[T, Callable], Coroutine[None, None, V]], 
    tasks: Iterable[T], 
    callback: Optional[Callable[[V], Any]] = None, 
    sema: Optional[AsyncSemaphore] = None, 
):
    ac = argcount(work)
    if ac < 1:
        raise TypeError(f"{work!r} should accept a positional argument as task")
    with_submit = ac > 1
    async def works(task):
        try:
            if sema is None:
                if with_submit:
                    r = await cast(Callable[[T, Callable], Coroutine[None, None, V]], work)(task, submit)
                else:
                    r = await cast(Callable[[T], Coroutine[None, None, V]], work)(task)
            else:
                async with sema:
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
    def submit(task):
        return create_task(works(task))
    async with TaskGroup() as tg:
        create_task = tg.create_task
        for task in tasks:
            submit(task)


@optional
def threaded(
    func: Callable[Args, Any], 
    /, 
    lock: None | int | ContextManager = None, 
    **thread_init_kwds, 
) -> Callable[Args, Future]:
    if isinstance(lock, int):
        lock = Semaphore(lock)
    def wrapper(*args, **kwds) -> Future[V]:
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
        fu: Future[V] = Future()
        thread = fu.thread = Thread(target=asfuture, **thread_init_kwds) # type: ignore
        thread.start()
        return fu
    return update_wrapper(wrapper, func)


def run_as_thread(
    func: Callable, 
    /, 
    *args, 
    **kwargs, 
) -> Future:
    return threaded(func)(*args, **kwargs)

