#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["SupportsGeturl", "encode_multipart_data", "encode_multipart_data_async"]

from itertools import chain
from collections.abc import AsyncIterable, AsyncIterator, ItemsView, Iterable, Iterator, Mapping
from typing import Any, Protocol, TypeVar
from urllib.parse import quote
from uuid import uuid4

from asynctools import ensure_aiter, async_chain
from filewrap import bio_chunk_iter, bio_chunk_async_iter, SupportsRead
from integer_tool import int_to_bytes


AnyStr = TypeVar("AnyStr", bytes, str, covariant=True)


class SupportsGeturl(Protocol[AnyStr]):
    def geturl(self) -> AnyStr: ...


def ensure_bytes(s, /) -> bytes | bytearray | memoryview:
    if isinstance(s, (bytes, bytearray, memoryview)):
        return s
    if isinstance(s, int):
        return int_to_bytes(s)
    elif isinstance(s, str):
        return bytes(s, "utf-8")
    try:
        return bytes(s)
    except TypeError:
        return bytes(str(s), "utf-8")


def encode_multipart_data(
    data: Mapping[str, Any], 
    files: Mapping[str, bytes | bytearray | memoryview | 
                        SupportsRead[bytes] | SupportsRead[bytearray] | SupportsRead[memoryview] | 
                        Iterable[bytes] | Iterable[bytearray] | Iterable[memoryview]], 
    boundary: None | str = None, 
) -> tuple[dict, Iterator[bytes | bytearray | memoryview]]:
    if not boundary:
        boundary = uuid4().bytes.hex()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    def encode_data(data) -> Iterator[bytes | bytearray | memoryview]:
        if isinstance(data, Mapping):
            data = ItemsView(data)
        for name, value in data:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\n\r\n' % bytes(quote(name), "ascii")
            yield ensure_bytes(value)
            yield b"\r\n"

    def encode_files(files) -> Iterator[bytes | bytearray | memoryview]:
        if isinstance(files, Mapping):
            files = ItemsView(files)
        for name, file in files:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\nContent-Type: application/octet-stream\r\n\r\n' % bytes(quote(name), "ascii")
            if isinstance(file, (bytes, bytearray, memoryview)):
                yield file
            elif hasattr(file, "read"):
                yield from bio_chunk_iter(file)
            else:
                yield from file
            yield b"\r\n"

    boundary_line = b"--%s\r\n" % boundary.encode("utf-8")
    return headers, chain(encode_data(data), encode_files(files), (b'--%s--\r\n' % boundary.encode("ascii"),))


def encode_multipart_data_async(
    data: Mapping[str, Any], 
    files: Mapping[str, bytes | bytearray | memoryview | 
                        SupportsRead[bytes] | SupportsRead[bytearray] | SupportsRead[memoryview] | 
                        Iterable[bytes] | Iterable[bytearray] | Iterable[memoryview] | 
                        AsyncIterable[bytes] | AsyncIterable[bytearray] | AsyncIterable[memoryview]], 
    boundary: None | str = None, 
) -> tuple[dict, AsyncIterator[bytes | bytearray | memoryview]]:
    if not boundary:
        boundary = uuid4().bytes.hex()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    async def encode_data(data) -> AsyncIterator[bytes | bytearray | memoryview]:
        if isinstance(data, Mapping):
            data = ItemsView(data)
        for name, value in data:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\n\r\n' % bytes(quote(name), "ascii")
            yield ensure_bytes(value)
            yield b"\r\n"

    async def encode_files(files) -> AsyncIterator[bytes | bytearray | memoryview]:
        if isinstance(files, Mapping):
            files = ItemsView(files)
        for name, file in files:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\nContent-Type: application/octet-stream\r\n\r\n' % bytes(quote(name), "ascii")
            if isinstance(file, (bytes, bytearray, memoryview)):
                yield file
            elif hasattr(file, "read"):
                async for b in bio_chunk_async_iter(file):
                    yield b
            else:
                async for b in ensure_aiter(file):
                    yield b
            yield b"\r\n"

    boundary_line = b"--%s\r\n" % boundary.encode("utf-8")
    return headers, async_chain(encode_data(data), encode_files(files), (b'--%s--\r\n' % boundary.encode("ascii"),))

