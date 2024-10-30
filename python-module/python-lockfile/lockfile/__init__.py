#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["LockFailed", "lockfile", "lockfile_async"]

from asyncio import sleep as asleep
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from os import fsdecode, remove, PathLike
from time import perf_counter, sleep
from typing import Any

from aiofile import async_open


class LockFailed(OSError):
    pass


@contextmanager
def lockfile(
    filepath: bytes | str | PathLike = "lockfile", 
    timeout: float | int = 0, 
    check_interval: float | int = 0, 
):
    if timeout <= 0:
        try:
            open(filepath, "xb", buffering=0).close()
        except OSError as exc:
            raise LockFailed("lockfile creation failed") from exc
    else:
        stop_t = timeout + perf_counter()
        while perf_counter() < stop_t:
            try:
                open(filepath, "xb", buffering=0).close()
                break
            except OSError:
                if check_interval > 0:
                    sleep(check_interval)
        else:
            raise LockFailed("lockfile creation failed")
    try:
        yield
    finally:
        try:
            remove(filepath)
        except OSError:
            pass


@asynccontextmanager
async def lockfile_async(
    filepath: bytes | str | PathLike = "lockfile", 
    timeout: float | int = 0, 
    check_interval: float | int = 0, 
):
    filepath = fsdecode(filepath)
    if timeout <= 0:
        try:
            async with async_open(filepath, "xb"):
                pass
        except OSError as exc:
            raise LockFailed("lockfile creation failed") from exc
    else:
        stop_t = timeout + perf_counter()
        while perf_counter() < stop_t:
            try:
                async with async_open(filepath, "xb"):
                    pass
                break
            except OSError:
                await asleep(check_interval if check_interval > 0 else 0)
        else:
            raise LockFailed("lockfile creation failed")
    try:
        yield
    finally:
        try:
            remove(filepath)
        except OSError:
            pass

# TODO: 增加几种加锁的机制，Windows 下使用命名管道，linux 下使用 fcntl.flock

