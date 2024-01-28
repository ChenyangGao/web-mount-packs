#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["SupportsWrite", "SupportsRead", "bio_skip_bytes"]

from collections.abc import Callable
from typing import Any, BinaryIO, Optional, Protocol, TypeVar


_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object: ...


class SupportsRead(Protocol[_T_co]):
    def read(self, __length: int = ...) -> _T_co: ...


BIOReader = TypeVar('BIOReader', BinaryIO, SupportsRead[bytes])


def bio_skip_bytes(
    bio: BIOReader, 
    skipsize: int, 
    chunksize: int = 1 << 16, 
    callback: Optional[Callable[[int], Any]] = None, 
) -> BIOReader:
    if skipsize <= 0:
        return bio
    if chunksize <= 0:
        chunksize = 1 << 16
    try:
        bio.seek(skipsize, 1) # type: ignore
        if callback:
            callback(skipsize)
    except:
        q, r = divmod(skipsize, chunksize)
        read = bio.read
        if q:
            if hasattr(bio, "readinto"):
                buf = bytearray(chunksize)
                readinto = bio.readinto
                for _ in range(q):
                    readinto(buf)
                    if callback:
                        callback(chunksize)
            else:
                for _ in range(q):
                    read(chunksize)
                    if callback:
                        callback(chunksize)
        if r:
            read(r)
            if callback:
                callback(r)
    return bio

