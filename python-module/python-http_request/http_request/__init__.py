#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 5)
__all__ = [
    "SupportsGeturl", "url_origin", "complete_url", "cookies_str_to_dict", "headers_str_to_dict", 
    "encode_multipart_data", "encode_multipart_data_async", 
]

from itertools import chain
from collections.abc import AsyncIterable, AsyncIterator, ItemsView, Iterable, Iterator, Mapping
from re import compile as re_compile, Pattern
from typing import runtime_checkable, Any, Final, Protocol, TypeVar
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

from asynctools import ensure_aiter, async_chain
from filewrap import bio_chunk_iter, bio_chunk_async_iter, Buffer, SupportsRead
from integer_tool import int_to_bytes
from texttools import text_to_dict


AnyStr = TypeVar("AnyStr", bytes, str, covariant=True)

CRE_URL_SCHEME: Final = re_compile(r"^(?i:[a-z][a-z0-9.+-]*)://")


@runtime_checkable
class SupportsGeturl(Protocol[AnyStr]):
    def geturl(self) -> AnyStr: ...


def url_origin(url: str, /) -> str:
    if url.startswith("://"):
        url = "http" + url
    elif CRE_URL_SCHEME.match(url) is None:
        url = "http://" + url
    urlp = urlsplit(url)
    scheme, netloc = urlp.scheme, urlp.netloc
    if not netloc:
        netloc = "localhost"
    return f"{scheme}://{netloc}"


def complete_url(url: str, /) -> str:
    if url.startswith("://"):
        url = "http" + url
    elif CRE_URL_SCHEME.match(url) is None:
        url = "http://" + url
    urlp = urlsplit(url)
    repl = {"query": "", "fragment": ""}
    if not urlp.netloc:
        repl["path"] = "localhost"
    return urlunsplit(urlp._replace(**repl)).rstrip("/")


def cookies_str_to_dict(
    cookies: str, 
    /, 
    kv_sep: str | Pattern[str] = re_compile(r"\s*=\s*"), 
    entry_sep: str | Pattern[str] = re_compile(r"\s*;\s*"), 
) -> dict[str, str]:
    return text_to_dict(cookies.strip(), kv_sep, entry_sep)


def headers_str_to_dict(
    headers: str, 
    /, 
    kv_sep: str | Pattern[str] = re_compile(r":\s+"), 
    entry_sep: str | Pattern[str] = re_compile("\n+"), 
) -> dict[str, str]:
    return text_to_dict(headers.strip(), kv_sep, entry_sep)


def ensure_bytes(s, /) -> Buffer:
    if isinstance(s, Buffer):
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
    files: Mapping[str, Buffer | SupportsRead[Buffer] | Iterable[Buffer]], 
    boundary: None | str = None, 
) -> tuple[dict, Iterator[Buffer]]:
    if not boundary:
        boundary = uuid4().bytes.hex()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    def encode_data(data) -> Iterator[Buffer]:
        if isinstance(data, Mapping):
            data = ItemsView(data)
        for name, value in data:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\n\r\n' % bytes(quote(name), "ascii")
            yield ensure_bytes(value)
            yield b"\r\n"

    def encode_files(files) -> Iterator[Buffer]:
        if isinstance(files, Mapping):
            files = ItemsView(files)
        for name, file in files:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\nContent-Type: application/octet-stream\r\n\r\n' % bytes(quote(name), "ascii")
            if isinstance(file, Buffer):
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
    files: Mapping[str, Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer]], 
    boundary: None | str = None, 
) -> tuple[dict, AsyncIterator[Buffer]]:
    if not boundary:
        boundary = uuid4().bytes.hex()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    async def encode_data(data) -> AsyncIterator[Buffer]:
        if isinstance(data, Mapping):
            data = ItemsView(data)
        for name, value in data:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\n\r\n' % bytes(quote(name), "ascii")
            yield ensure_bytes(value)
            yield b"\r\n"

    async def encode_files(files) -> AsyncIterator[Buffer]:
        if isinstance(files, Mapping):
            files = ItemsView(files)
        for name, file in files:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\nContent-Type: application/octet-stream\r\n\r\n' % bytes(quote(name), "ascii")
            if isinstance(file, Buffer):
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

