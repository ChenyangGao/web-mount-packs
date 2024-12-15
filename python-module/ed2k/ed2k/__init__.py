#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["Ed2kHash", "ed2k_hash", "ed2k_hash_async"]
__version__ = (0, 0, 2)

from collections.abc import AsyncIterator, Awaitable, Iterator, Sized
from typing import Final

from filewrap import (
    Buffer, SupportsRead, 
    bio_chunk_iter, bio_chunk_async_iter, 
    bytes_to_chunk_iter, bytes_to_chunk_async_iter, 
)
from Crypto.Hash.MD4 import MD4Hash


MD4_BLOCK_SIZE: Final = 1024 * 9500
MD4_EMPTY_HASH: Final = b"1\xd6\xcf\xe0\xd1j\xe91\xb7<Y\xd7\xe0\xc0\x89\xc0"


def buffer_length(b: Buffer, /) -> int:
    if isinstance(b, Sized):
        return len(b)
    else:
        return len(memoryview(b))


def ensure_bytes(b: Buffer, /) -> bytes | bytearray | memoryview:
    if isinstance(b, (bytes, bytearray, memoryview)):
        return b
    return memoryview(b)


class Ed2kHash:

    def __init__(self, b: Buffer = b"", /):
        self.block_hashes = bytearray()
        self._last_hashobj = MD4Hash()
        self._remainder = 0
        self.update(b)

    def update(self, b: Buffer, /):
        size = buffer_length(b)
        if not size:
            return
        block_hashes = self.block_hashes
        remainder = self._remainder
        last_hashobj = self._last_hashobj
        m = memoryview(b)
        start = 0
        if remainder:
            start = MD4_BLOCK_SIZE - remainder
            last_hashobj.update(m[:start])
            block_hashes[-16:] = last_hashobj.digest()
        if start < size: 
            for start in range(start, size, MD4_BLOCK_SIZE):
                last_hashobj = MD4Hash(m[start:start+MD4_BLOCK_SIZE])
                block_hashes += last_hashobj.digest()
        self._remainder = (size - start) % MD4_BLOCK_SIZE
        self._last_hashobj = last_hashobj

    def digest(self, /) -> bytes:
        block_hashes = self.block_hashes
        if not self._remainder:
            block_hashes = block_hashes + MD4_EMPTY_HASH
        return MD4Hash(block_hashes).digest()

    def hexdigest(self, /) -> str:
        return self.digest().hex()


def ed2k_hash(file: Buffer | SupportsRead[Buffer]) -> tuple[int, str]:
    if hasattr(file, "getbuffer"):
        file = file.getbuffer()
    if isinstance(file, Buffer):
        chunk_iter: Iterator[Buffer] = bytes_to_chunk_iter(file, chunksize=MD4_BLOCK_SIZE)
    else:
        chunk_iter = bio_chunk_iter(file, chunksize=MD4_BLOCK_SIZE, can_buffer=True)
    block_hashes = bytearray()
    filesize = 0
    for chunk in map(ensure_bytes, chunk_iter):
        block_hashes += MD4Hash(chunk).digest()
        filesize += len(chunk)
    if not filesize % MD4_BLOCK_SIZE:
        block_hashes += MD4_EMPTY_HASH
    return filesize, MD4Hash(block_hashes).hexdigest()


async def ed2k_hash_async(file: Buffer | SupportsRead[Buffer] | SupportsRead[Awaitable[Buffer]]) -> tuple[int, str]:
    if hasattr(file, "getbuffer"):
        file = file.getbuffer()
    if isinstance(file, Buffer):
        chunk_iter: AsyncIterator[Buffer] = bytes_to_chunk_async_iter(file, chunksize=MD4_BLOCK_SIZE)
    else:
        chunk_iter = bio_chunk_async_iter(file, chunksize=MD4_BLOCK_SIZE, can_buffer=True)
    block_hashes = bytearray()
    filesize = 0
    async for chunk in chunk_iter:
        chunk = ensure_bytes(chunk)
        block_hashes += MD4Hash(chunk).digest()
        filesize += len(chunk)
    if not filesize % MD4_BLOCK_SIZE:
        block_hashes += MD4_EMPTY_HASH
    return filesize, MD4Hash(block_hashes).hexdigest()

