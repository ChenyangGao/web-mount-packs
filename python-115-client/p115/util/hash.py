#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["file_digest", "file_mdigest"]

from _hashlib import HASH # type: ignore
from hashlib import new as hash_new
from io import TextIOWrapper
from os import fstat
from typing import Callable, Optional

from .iter import acc_step


def file_digest(
    file, 
    digest: str | Callable[[], HASH] = "md5", 
    /, 
    start: int = 0, 
    stop: Optional[int] = None, 
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
    stop: Optional[int] = None, 
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
    total = 0
    if hasattr(file, "readinto"):
        readinto = file.readinto
        buf = bytearray(bufsize)
        view = memoryview(buf)
        if start > 0:
            try:
                file.seek(start)
            except OSError:
                buff = buf
                for *_, step in acc_step(start, bufsize):
                    if step < bufsize:
                        buff = bytearray(step)
                    if readinto(buff) < step:
                        return 0, digestobjs
        if stop is None:
            while (size := readinto(buf)):
                update(view[:size])
                total += size
        else:
            for total_before, total, step in acc_step(stop - start, bufsize):
                if step < bufsize:
                    buf = bytearray(step)
                    view = memoryview(buf)
                size = readinto(buf)
                if size < step:
                    update(view[:size])
                    total = total_before + size
                    break
                update(buf)
    elif hasattr(file, "read"):
        if isinstance(file, TextIOWrapper):
            file = file.buffer
        elif file.read(0) != b"":
            raise ValueError(f"{file!r} is not a file-like object in reading binary mode.")
        read = file.read
        if start > 0:
            try:
                file.seek(start)
            except OSError:
                for *_, step in acc_step(start, bufsize):
                    if len(read(step)) < step:
                        return 0, digestobjs
        if stop is None:
            while (data := read(bufsize)):
                update(data)
                total += len(data)
        else:
            for total_before, total, step in acc_step(stop - start, bufsize):
                data = read(step)
                update(data)
                size = len(data)
                if size < step:
                    total = total_before + size
                    break
    else:
        raise ValueError(f"{file!r} is not a file-like object in reading mode.")
    return total, digestobjs

