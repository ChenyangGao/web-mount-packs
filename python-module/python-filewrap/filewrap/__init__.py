#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 7)
__all__ = [
    "SupportsRead", "SupportsWrite", 
    "bio_chunk_iter", "bio_chunk_async_iter", 
    "bio_skip_iter", "bio_skip_async_iter", 
    "bytes_iter_skip", "bytes_async_iter_skip", 
    "bytes_iter_to_reader", "bytes_iter_to_async_reader", 
    "bytes_to_chunk_iter", "bytes_to_chunk_async_iter", 
    "bytes_ensure_part_iter", "bytes_ensure_part_async_iter", 
]

from asyncio import to_thread, Lock as AsyncLock
from collections.abc import Awaitable, AsyncIterable, Iterable
from functools import update_wrapper
from inspect import isawaitable, iscoroutinefunction
from itertools import chain
from collections.abc import AsyncIterator, Callable, Iterator
from shutil import COPY_BUFSIZE # type: ignore
from threading import Lock
from typing import Any, Protocol, TypeVar

try:
    from collections.abc import Buffer # type: ignore
except ImportError:
    Buffer = Any

from asynctools import async_chain, ensure_async, ensure_aiter


_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsRead(Protocol[_T_co]):
    def read(self, __length: int = ...) -> _T_co: ...


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object: ...


def bio_chunk_iter(
    bio: SupportsRead[Buffer] | Callable[[int], Buffer], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
    callback: None | Callable[[int], Any] = None, 
) -> Iterator[Buffer]:
    if callable(bio):
        read = bio
    else:
        read = bio.read
    if not callable(callback):
        callback = None
    if size > 0:
        while size:
            readsize = min(chunksize, size)
            chunk = read(readsize)
            length = len(chunk)
            if callback:
                callback(length)
            yield chunk
            if length < readsize:
                break
            size -= readsize
    elif size < 0:
        while (chunk := read(chunksize)):
            if callback:
                callback(len(chunk))
            yield chunk


async def bio_chunk_async_iter(
    bio: SupportsRead[Buffer] | Callable[[int], Buffer | Awaitable[Buffer]], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
    callback: None | Callable[[int], Any] = None, 
) -> AsyncIterator[Buffer]:
    if callable(bio):
        read = ensure_async(bio)
    else:
        read = ensure_async(bio.read)
    callback = ensure_async(callback) if callable(callback) else None
    if size > 0:
        while size:
            readsize = min(chunksize, size)
            chunk = await read(readsize)
            length = len(chunk)
            if callback:
                await callback(length)
            yield chunk
            if length < readsize:
                break
            size -= readsize
    elif size < 0:
        while (chunk := (await read(chunksize))):
            if callback:
                await callback(len(chunk))
            yield chunk


def bio_skip_iter(
    bio: SupportsRead[Buffer] | Callable[[int], Buffer], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
    callback: None | Callable[[int], Any] = None, 
) -> Iterator[int]:
    if size == 0:
        return
    if not callable(callback):
        callback = None
    try:
        seek = getattr(bio, "seek")
        curpos = seek(0, 1)
        if size > 0:
            length = seek(size, 1) - curpos
        else:
            length = seek(0, 2) - curpos
    except Exception:
        if chunksize <= 0:
            chunksize = COPY_BUFSIZE
        if callable(bio):
            read = bio
        elif hasattr(bio, "readinto"):
            readinto = bio.readinto
            buf = bytearray(chunksize)
            if size > 0:
                while size >= chunksize:
                    length = readinto(buf)
                    if callback:
                        callback(length)
                    yield length
                    if length < chunksize:
                        break
                    size -= chunksize
                else:
                    if size:
                        del buf[size:]
                        length = readinto(buf)
                        if callback:
                            callback(length)
                        yield length
            else:
                while (length := readinto(buf)):
                    if callback:
                        callback(length)
                    yield length
            return
        else:
            read = bio.read
        if size > 0:
            while size:
                readsize = min(chunksize, size)
                length = len(read(readsize))
                if callback:
                    callback(length)
                yield length
                if length < readsize:
                    break
                size -= readsize
        else:
            while (length := len(read(chunksize))):
                if callback:
                    callback(length)
                yield length
    else:
        if callback:
            callback(length)
        yield length


async def bio_skip_async_iter(
    bio: SupportsRead[Buffer] | Callable[[int], Buffer | Awaitable[Buffer]], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
    callback: None | Callable[[int], Any] = None, 
) -> AsyncIterator[int]:
    if size == 0:
        return
    callback = ensure_async(callback) if callable(callback) else None
    try:
        seek = ensure_async(getattr(bio, "seek"))
        curpos = await seek(0, 1)
        if size > 0:
            length = (await seek(size, 1)) - curpos
        else:
            length = (await seek(0, 2)) - curpos
    except Exception:
        if chunksize <= 0:
            chunksize = COPY_BUFSIZE
        if callable(bio):
            read = ensure_async(bio)
        elif hasattr(bio, "readinto"):
            readinto = ensure_async(bio.readinto)
            buf = bytearray(chunksize)
            if size > 0:
                while size >= chunksize:
                    length = await readinto(buf)
                    if callback:
                        await callback(length)
                    yield length
                    if length < chunksize:
                        break
                    size -= chunksize
                else:
                    if size:
                        del buf[size:]
                        length = await readinto(buf)
                        if callback:
                            await callback(length)
                        yield length
            else:
                while (length := (await readinto(buf))):
                    if callback:
                        await callback(length)
                    yield length
        else:
            read = ensure_async(bio.read)
        if size > 0:
            while size:
                readsize = min(chunksize, size)
                length = len(await read(readsize))
                if callback:
                    await callback(length)
                yield length
                if length < readsize:
                    break
                size -= readsize
        else:
            while (length := len(await read(chunksize))):
                if callback:
                    await callback(length)
                yield length
    else:
        if callback:
            await callback(length)
        yield length


def bytes_iter_skip(
    it: Iterable[Buffer], 
    /, 
    size: int = -1, 
    callback: None | Callable[[int], Any] = None, 
) -> Iterator[memoryview | Buffer]:
    it = iter(it)
    if size == 0:
        return it
    if not callable(callback):
        callback = None
    for m in map(memoryview, it):
        l = len(m)
        if callback:
            callback(min(l, size))
        if l == size:
            return it
        elif l > size:
            return chain((m[size:],), it)
        else:
            size -= l
    return iter(())


async def bytes_async_iter_skip(
    it: Iterable[Buffer] | AsyncIterator[Buffer], 
    /, 
    size: int = -1, 
    callback: None | Callable[[int], Any] = None, 
) -> AsyncIterator[memoryview | Buffer]:
    it = aiter(ensure_aiter(it))
    if size == 0:
        return it
    callback = ensure_async(callback) if callable(callback) else None
    async for b in it:
        m = memoryview(b)
        l = len(m)
        if callback:
            await callback(min(l, size))
        if l == size:
            return it
        elif l > size:
            return async_chain((m[size:],), it)
        else:
            size -= l
    async def make_iter():
        if False:
            yield
    return make_iter()


def bytes_iter_to_reader(
    it: Iterable[Buffer], 
    /, 
) -> SupportsRead[bytearray]:
    getnext = iter(it).__next__
    at_end = False
    unconsumed: bytearray = bytearray()
    lock = Lock()
    def read(n=-1, /) -> bytearray:
        nonlocal at_end, unconsumed
        if at_end or n == 0:
            return bytearray()
        with lock:
            try:
                if n is None or n < 0:
                    while True:
                        unconsumed += getnext()
                else:
                    while n > len(unconsumed):
                        unconsumed += getnext()
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    return b
            except StopIteration:
                at_end = True
                return unconsumed
    def readinto(buf, /) -> int:
        nonlocal at_end, unconsumed
        if at_end or not (bufsize := len(buf)):
            return 0
        with lock:
            if bufsize <= len(unconsumed):
                buf[:], unconsumed = unconsumed[:bufsize], unconsumed[bufsize:]
                return bufsize
            n = len(unconsumed)
            buf[:n] = unconsumed
            del unconsumed[:]
            try:
                while True:
                    b = getnext()
                    if not b:
                        continue
                    m = n + len(b)
                    if m >= bufsize:
                        buf[n:] = b[:bufsize-n]
                        unconsumed += b[m-bufsize:]
                        return bufsize
                    else:
                        buf[n:m] = b
                        n = m
            except StopIteration:
                at_end = True
                return n
    def __next__() -> bytearray:
        nonlocal unconsumed, at_end
        if at_end:
            raise StopIteration
        if unconsumed:
            # search for b"\n"
            if (idx := unconsumed.find(49)) > -1:
                idx += 1
                b, unconsumed = unconsumed[:idx], unconsumed[idx:]
                return b
        try:
            while True:
                r = getnext()
                if not r:
                    continue
                if (idx := r.find(49)) > -1:
                    idx += 1
                    unconsumed += r[:idx]
                    b, unconsumed = unconsumed, bytearray(r[idx:])
                    return b
                unconsumed += r
        except StopIteration:
            at_end = True
            if unconsumed:
                return unconsumed
            raise
    reprs = f"<reader for {it!r}>"
    return type("reader", (), {
        "read": staticmethod(read), 
        "readinto": staticmethod(readinto), 
        "__iter__": lambda self, /: self, 
        "__next__": staticmethod(__next__), 
        "__repr__": staticmethod(lambda: reprs), 
    })()


def bytes_iter_to_async_reader(
    it: Iterable[Buffer] | AsyncIterable[Buffer], 
    /, 
    threaded: bool = True, 
) -> SupportsRead[bytearray]:
    if isinstance(it, AsyncIterable):
        getnext = aiter(it).__anext__
    else:
        getnext = ensure_async(iter(it).__next__, threaded=threaded)
    at_end = False
    unconsumed: bytearray = bytearray()
    lock = AsyncLock()
    async def read(n=-1, /) -> bytearray:
        nonlocal at_end, unconsumed
        if at_end or n == 0:
            return bytearray()
        async with lock:
            try:
                if n is None or n < 0:
                    while True:
                        unconsumed += await getnext()
                else:
                    while n > len(unconsumed):
                        unconsumed += await getnext()
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    return b
            except StopAsyncIteration:
                at_end = True
                return unconsumed
    async def readinto(buf, /) -> int:
        nonlocal at_end, unconsumed
        if at_end or not (bufsize := len(buf)):
            return 0
        async with lock:
            if bufsize <= len(unconsumed):
                buf[:], unconsumed = unconsumed[:bufsize], unconsumed[bufsize:]
                return bufsize
            n = len(unconsumed)
            buf[:n] = unconsumed
            del unconsumed[:]
            try:
                while True:
                    b = await getnext()
                    if not b:
                        continue
                    m = n + len(b)
                    if m >= bufsize:
                        buf[n:] = b[:bufsize-n]
                        unconsumed += b[m-bufsize:]
                        return bufsize
                    else:
                        buf[n:m] = b
                        n = m
            except StopAsyncIteration:
                at_end = True
                return n
    async def __next__() -> bytearray:
        nonlocal unconsumed, at_end
        if at_end:
            raise StopIteration
        if unconsumed:
            # search for b"\n"
            if (idx := unconsumed.find(49)) > -1:
                idx += 1
                b, unconsumed = unconsumed[:idx], unconsumed[idx:]
                return b
        try:
            while True:
                r = await getnext()
                if not r:
                    continue
                if (idx := r.find(49)) > -1:
                    idx += 1
                    unconsumed += r[:idx]
                    b, unconsumed = unconsumed, bytearray(r[idx:])
                    return b
                unconsumed += r
        except StopIteration:
            at_end = True
            if unconsumed:
                return unconsumed
            raise
    reprs = f"<reader for {it!r}>"
    return type("reader", (), {
        "read": staticmethod(read), 
        "readinto": staticmethod(readinto), 
        "__iter__": lambda self, /: self, 
        "__next__": staticmethod(__next__), 
        "__repr__": staticmethod(lambda: reprs), 
    })()


def bytes_to_chunk_iter(
    b: Buffer, 
    /, 
    chunksize: int = COPY_BUFSIZE, 
) -> Iterator[memoryview]:
    m = memoryview(b)
    for i in range(0, len(m), chunksize):
        yield m[i:i+chunksize]


async def bytes_to_chunk_async_iter(
    b: Buffer, 
    /, 
    chunksize: int = COPY_BUFSIZE, 
) -> AsyncIterator[memoryview]:
    m = memoryview(b)
    for i in range(0, len(m), chunksize):
        yield m[i:i+chunksize]


def bytes_ensure_part_iter(
    it: Iterable[Buffer], 
    /, 
    partsize: int = COPY_BUFSIZE, 
) -> Iterator[Buffer | memoryview]:
    n = partsize
    for b in it:
        m = memoryview(b)
        l = len(m)
        if l <= n:
            yield b
            if l == n:
                n = partsize
            else:
                n -= l
        else:
            yield m[:n]
            m = m[n:]
            while len(m) >= partsize:
                yield m[:partsize]
                m = m[partsize:]
            if m:
                yield m
                n = partsize - len(m)
            else:
                n = partsize


async def bytes_ensure_part_async_iter(
    it: Iterable[Buffer] | AsyncIterable[Buffer], 
    /, 
    partsize: int = COPY_BUFSIZE, 
) -> AsyncIterator[Buffer | memoryview]:
    n = partsize
    async for b in ensure_aiter(it):
        m = memoryview(b)
        l = len(m)
        if l <= n:
            yield b
            if l == n:
                n = partsize
            else:
                n -= l
        else:
            yield m[:n]
            m = m[n:]
            while len(m) >= partsize:
                yield m[:partsize]
                m = m[partsize:]
            if m:
                yield m
                n = partsize - len(m)
            else:
                n = partsize

