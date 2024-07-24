#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["file_digest", "file_mdigest", "file_digest_async", "file_mdigest_async"]

from _hashlib import HASH # type: ignore
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable, Iterator
from hashlib import new as hash_new
from inspect import isawaitable
from io import TextIOWrapper
from os import fstat
from typing import Any

from asynctools import ensure_async, ensure_aiter
from filewrap import (
    Buffer, SupportsRead, SupportsReadinto, 
    bio_skip_iter, bio_skip_async_iter, 
    bio_chunk_iter, bio_chunk_async_iter, 
    bytes_iter, bytes_async_iter, 
    bytes_iter_skip, bytes_async_iter_skip, 
    bytes_to_chunk_iter, bytes_to_chunk_async_iter, 
)


def file_digest(
    file: Buffer | SupportsRead[Buffer] | SupportsReadinto | Iterable[Buffer], 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
    callback: None | Callable[[int], Any] = None, 
) -> tuple[int, HASH]:
    total, (digestobj,) = file_mdigest(
        file, 
        digest, 
        start=start, 
        stop=stop, 
        bufsize=bufsize, 
        callback=callback, 
    )
    return total, digestobj


def file_mdigest(
    file: Buffer | SupportsRead[Buffer] | SupportsReadinto | Iterable[Buffer], 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    *digests: str | Callable[[], HASH], 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
    callback: None | Callable[[int], Any] = None, 
) -> tuple[int, tuple[HASH, ...]]:
    if digests:
        digestobjs = tuple(hash_new(d) if isinstance(d, str) else d() for d in (digest, *digests))
        def update(b, t=tuple(d.update for d in digestobjs), /):
            for update in t:
                update(b)
    else:
        digestobj = hash_new(digest) if isinstance(digest, str) else digest()
        digestobjs = digestobj,
        update = digestobj.update
    if hasattr(file, "getbuffer"):
        file = file.getbuffer()
    b_it: Iterator[Buffer]
    if isinstance(file, Buffer):
        file = memoryview(file)[start:stop]
        if not file:
            return 0, digestobjs
        if callback is not None:
            callback(start)
        b_it = bytes_to_chunk_iter(file)
    elif isinstance(file, (SupportsRead, SupportsReadinto)):
        try:
            fileno = getattr(file, "fileno")()
            length = fstat(fileno).st_size
        except (AttributeError, OSError):
            try:
                length = len(file) # type: ignore
            except TypeError:
                length = -1
        if length == 0:
            return 0, digestobjs
        elif length > 0:
            if start < 0:
                start += length
            if start < 0:
                start = 0
            elif start >= length:
                return 0, digestobjs
            if stop is not None:
                if stop < 0:
                    stop += length
                if stop <= 0 or start >= stop:
                    return 0, digestobjs
                elif stop >= length:
                    stop = None
        elif start < 0:
            raise ValueError("can't use negative start index on a file with unknown length")
        elif stop is not None:
            if stop < 0:
                raise ValueError("can't use negative stop index on a file with unknown length")
            if stop <= 0 or start >= stop:
                return 0, digestobjs
        if start:
            for _ in bio_skip_iter(file, start, callback=callback):
                pass
        if stop:
            b_it = bio_chunk_iter(file, stop - start, can_buffer=True)
        else:
            b_it = bio_chunk_iter(file, can_buffer=True)
    else:
        if start < 0 or stop and stop < 0:
            raise ValueError("negative indices should not be used when using `Iterable[Buffer]`")
        elif stop and start >= stop:
            return 0, digestobjs
        b_it = file
        if start:
            b_it = bytes_iter_skip(b_it, start, callback=callback)
        if stop:
            b_it = bytes_iter(b_it, stop - start)
    length = 0
    for chunk in b_it:
        update(chunk)
        length += (chunksize := len(chunk))
        if callback is not None:
            callback(chunksize)
    return length, digestobjs


async def file_digest_async(
    file: Buffer | SupportsRead[Buffer] | SupportsReadinto | Iterable[Buffer] | AsyncIterable[Buffer], 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
    callback: None | Callable[[int], Any] = None, 
) -> tuple[int, HASH]:
    total, (digestobj,) = await file_mdigest_async(
        file, 
        digest, 
        start=start, 
        stop=stop, 
        bufsize=bufsize, 
        callback=callback, 
    )
    return total, digestobj


async def file_mdigest_async(
    file: Buffer | SupportsRead[Buffer] | SupportsReadinto | Iterable[Buffer] | AsyncIterable[Buffer], 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    *digests: str | Callable[[], HASH], 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
    callback: None | Callable[[int], Any] = None, 
    threaded: bool = False, 
) -> tuple[int, tuple[HASH, ...]]:
    if digests:
        digestobjs = tuple(hash_new(d) if isinstance(d, str) else d() for d in (digest, *digests))
        def update(b, t=tuple(d.update for d in digestobjs), /):
            for update in t:
                update(b)
    else:
        digestobj = hash_new(digest) if isinstance(digest, str) else digest()
        digestobjs = digestobj,
        update = digestobj.update
    if callback is not None:
        callback = ensure_async(callback, threaded=threaded)
    if hasattr(file, "getbuffer"):
        file = file.getbuffer()
    b_it: AsyncIterator[Buffer]
    if isinstance(file, Buffer):
        file = memoryview(file)[start:stop]
        if not file:
            return 0, digestobjs
        if callback is not None:
            await callback(start)
        b_it = bytes_to_chunk_async_iter(file)
    elif isinstance(file, (SupportsRead, SupportsReadinto)):
        try:
            fileno = getattr(file, "fileno")()
            length = fstat(fileno).st_size
        except (AttributeError, OSError):
            try:
                length = len(file) # type: ignore
            except TypeError:
                length = -1
        if length == 0:
            return 0, digestobjs
        elif length > 0:
            if start < 0:
                start += length
            if start < 0:
                start = 0
            elif start >= length:
                return 0, digestobjs
            if stop is not None:
                if stop < 0:
                    stop += length
                if stop <= 0 or start >= stop:
                    return 0, digestobjs
                elif stop >= length:
                    stop = None
        elif start < 0:
            raise ValueError("can't use negative start index on a file with unknown length")
        elif stop is not None:
            if stop < 0:
                raise ValueError("can't use negative stop index on a file with unknown length")
            if stop <= 0 or start >= stop:
                return 0, digestobjs
        if start:
            async for _ in bio_skip_async_iter(file, start, callback=callback):
                pass
        if stop:
            b_it = bio_chunk_async_iter(file, stop - start, can_buffer=True)
        else:
            b_it = bio_chunk_async_iter(file, can_buffer=True)
    else:
        if start < 0 or stop and stop < 0:
            raise ValueError("negative indices should not be used when using `Iterable[Buffer]`")
        elif stop and start >= stop:
            return 0, digestobjs
        b_it = ensure_aiter(file, threaded=threaded)
        if start:
            b_it = await bytes_async_iter_skip(b_it, start, callback=callback, threaded=threaded)
        if stop:
            b_it = bytes_async_iter(b_it, stop - start, threaded=threaded)
    length = 0
    async for chunk in b_it:
        update(chunk)
        length += (chunksize := len(chunk))
        if callback is not None:
            await callback(chunksize)
    return length, digestobjs

