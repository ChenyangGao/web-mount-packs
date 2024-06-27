#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 6)
__all__ = [
    "SupportsGeturl", "url_origin", "complete_url", "cookies_str_to_dict", "headers_str_to_dict", 
    "encode_multipart_data", "encode_multipart_data_async", 
]

from collections.abc import AsyncIterable, AsyncIterator, ItemsView, Iterable, Iterator, Mapping
from itertools import chain
from mimetypes import guess_type
from os import fsdecode
from os.path import basename
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
    data: None | Mapping[str, Any] = None, 
    files: None | Mapping[str, Buffer | SupportsRead[Buffer] | Iterable[Buffer]] = None, 
    boundary: None | str = None, 
) -> tuple[dict, Iterator[Buffer]]:
    if not boundary:
        boundary = uuid4().hex
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    def encode_data(data) -> Iterator[Buffer]:
        if not data:
            return
        if isinstance(data, Mapping):
            data = ItemsView(data)
        for name, value in data:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\n\r\n' % bytes(quote(name), "ascii")
            yield ensure_bytes(value)
            yield b"\r\n"

    def encode_files(files) -> Iterator[Buffer]:
        if not files:
            return
        if isinstance(files, Mapping):
            files = ItemsView(files)
        for name, file in files:
            headers: dict[bytes, bytes] = {b"Content-Disposition": b'form-data; name="%s"' % quote(name).encode("ascii")}
            filename: bytes | str = ""
            if isinstance(file, (list, tuple)):
                match file:
                    case [file]:
                        pass
                    case [file_name, file]:
                        pass
                    case [file_name, file, file_type]:
                        if file_type:
                            headers[b"Content-Type"] = ensure_bytes(file_type)
                    case [file_name, file, file_type, file_headers, *rest]:
                        if isinstance(file_headers, Mapping):
                            file_headers = ItemsView(file_headers)
                        for k, v in file_headers:
                            headers[ensure_bytes(k).title()] = ensure_bytes(v)
                        if file_type:
                            headers[b"Content-Type"] = ensure_bytes(file_type)
            if isinstance(file, Buffer):
                pass
            elif isinstance(file, str):
                file = file.encode("utf-8")
            elif hasattr(file, "read"):
                file = bio_chunk_iter(file)
                if not filename:
                    path = getattr(file, name, None)
                    if path:
                        filename = basename(path)
                        if b"Content-Type" not in headers:
                            headers[b"Content-Type"] = ensure_bytes(guess_type(fsdecode(filename))[0] or b"application/octet-stream")
            if filename:
                headers[b"Content-Disposition"] += b'; filename="%s"' % quote(filename).encode("ascii")
            else:
                headers[b"Content-Disposition"] += b'; filename="%032x"' % uuid4().int
            yield boundary_line
            for entry in headers.items():
                yield b"%s: %s\r\n" % entry
            yield b"\r\n"
            if isinstance(file, Buffer):
                yield file
            else:
                yield from file
            yield b"\r\n"

    boundary_line = b"--%s\r\n" % boundary.encode("utf-8")
    return headers, chain(encode_data(data), encode_files(files), (b'--%s--\r\n' % boundary.encode("ascii"),))


def encode_multipart_data_async(
    data: None | Mapping[str, Any] = None, 
    files: None | Mapping[str, Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer]] = None, 
    boundary: None | str = None, 
) -> tuple[dict, AsyncIterator[Buffer]]:
    if not boundary:
        boundary = uuid4().hex
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    async def encode_data(data) -> AsyncIterator[Buffer]:
        if not data:
            return
        if isinstance(data, Mapping):
            data = ItemsView(data)
        for name, value in data:
            yield boundary_line
            yield b'Content-Disposition: form-data; name="%s"\r\n\r\n' % bytes(quote(name), "ascii")
            yield ensure_bytes(value)
            yield b"\r\n"

    async def encode_files(files) -> AsyncIterator[Buffer]:
        if not files:
            return
        if isinstance(files, Mapping):
            files = ItemsView(files)
        for name, file in files:
            headers: dict[bytes, bytes] = {b"Content-Disposition": b'form-data; name="%s"' % quote(name).encode("ascii")}
            filename: bytes | str = ""
            if isinstance(file, (list, tuple)):
                match file:
                    case [file]:
                        pass
                    case [file_name, file]:
                        pass
                    case [file_name, file, file_type]:
                        if file_type:
                            headers[b"Content-Type"] = ensure_bytes(file_type)
                    case [file_name, file, file_type, file_headers, *rest]:
                        if isinstance(file_headers, Mapping):
                            file_headers = ItemsView(file_headers)
                        for k, v in file_headers:
                            headers[ensure_bytes(k).title()] = ensure_bytes(v)
                        if file_type:
                            headers[b"Content-Type"] = ensure_bytes(file_type)
            if isinstance(file, Buffer):
                pass
            elif isinstance(file, str):
                file = file.encode("utf-8")
            elif hasattr(file, "read"):
                file = bio_chunk_async_iter(file)
                if not filename:
                    path = getattr(file, name, None)
                    if path:
                        filename = basename(path)
                        if b"Content-Type" not in headers:
                            headers[b"Content-Type"] = ensure_bytes(guess_type(fsdecode(filename))[0] or b"application/octet-stream")
            else:
                file = ensure_aiter(file)
            if filename:
                headers[b"Content-Disposition"] += b'; filename="%s"' % quote(filename).encode("ascii")
            else:
                headers[b"Content-Disposition"] += b'; filename="%032x"' % uuid4().int
            yield boundary_line
            for entry in headers.items():
                yield b"%s: %s\r\n" % entry
            yield b"\r\n"
            if isinstance(file, Buffer):
                yield file
            else:
                async for chunk in file:
                    yield chunk
            yield b"\r\n"

    boundary_line = b"--%s\r\n" % boundary.encode("utf-8")
    return headers, async_chain(encode_data(data), encode_files(files), (b'--%s--\r\n' % boundary.encode("ascii"),))

