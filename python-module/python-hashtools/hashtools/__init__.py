#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["file_digest", "file_mdigest", "file_digest_async", "file_mdigest_async"]

from _hashlib import HASH # type: ignore
from collections.abc import Callable
from hashlib import new as hash_new
from io import TextIOWrapper
from os import fstat

from filewrap import bio_skip_iter, bio_skip_async_iter, bio_chunk_iter, bio_chunk_async_iter


def file_digest(
    file, 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
) -> tuple[int, HASH]:
    total, (digestobj,) = file_mdigest(file, digest, start=start, stop=stop, bufsize=bufsize)
    return total, digestobj


def file_mdigest(
    file, 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    *digests: str | Callable[[], HASH], 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
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
        buffer = file.getbuffer()[start:stop]
        update(buffer)
        return len(buffer), digestobjs
    try:
        length = fstat(file.fileno()).st_size
    except (AttributeError, OSError):
        try:
            length = len(file)
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
    if start > 0:
        try:
            file.seek(start)
        except OSError:
            for _ in bio_skip_iter(file, start):
                pass
    total = 0
    if stop is None:
        size = -1
    else:
        size = stop - start
    for chunk in bio_chunk_iter(file, size, can_buffer=True):
        update(chunk)
        total += len(chunk)
    return total, digestobjs


async def file_digest_async(
    file, 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
) -> tuple[int, HASH]:
    total, (digestobj,) = await file_mdigest_async(file, digest, start=start, stop=stop, bufsize=bufsize)
    return total, digestobj


async def file_mdigest_async(
    file, 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    *digests: str | Callable[[], HASH], 
    start: int = 0, 
    stop: None | int = None, 
    bufsize: int = 1 << 16, 
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
        buffer = file.getbuffer()[start:stop]
        update(buffer)
        return len(buffer), digestobjs
    try:
        length = fstat(file.fileno()).st_size
    except (AttributeError, OSError):
        try:
            length = len(file)
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
    if start > 0:
        try:
            file.seek(start)
        except OSError:
            for _ in bio_skip_iter(file, start):
                pass
    total = 0
    if stop is None:
        size = -1
    else:
        size = stop - start
    async for chunk in bio_chunk_async_iter(file, size, can_buffer=True):
        update(chunk)
        total += len(chunk)
    return total, digestobjs

