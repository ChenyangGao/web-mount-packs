#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["file_reviter"]


from collections.abc import Generator, Iterator
from io import TextIOWrapper
from typing import overload, BinaryIO


def _reviter(b: bytes, /) -> Generator[bytes, None, bytes]:
    stop = len(b)
    if b[-1] == 10: # \n
        stop -= 1
    try:
        rindex = b.rindex
        while True:
            start = rindex(10, 0, stop)
            yield b[start+1:stop+1]
            stop = start
    except ValueError:
        return b[:stop+1]


@overload
def file_reviter(
    file: BinaryIO, 
    chunksize: int = 1 << 16, 
) -> Iterator[bytes]: ...
@overload
def file_reviter(
    file: TextIOWrapper, 
    chunksize: int = 1 << 16, 
) -> Iterator[str]: ...
def file_reviter(
    file, 
    chunksize: int = 1 << 16, 
) -> Iterator:
    if isinstance(file, TextIOWrapper):
        encoding = file.encoding
        for line in file_reviter(file.buffer, chunksize):
            yield str(line, encoding)
        return
    read = file.read
    seek = file.seek
    size = seek(0, 2)
    if not size:
        return
    rest = b""
    while size > chunksize:
        size -= chunksize
        seek(size)
        rest = yield from _reviter(read(chunksize) + rest)
    if size:
        seek(0)
        yield (yield from _reviter(read(size) + rest))

