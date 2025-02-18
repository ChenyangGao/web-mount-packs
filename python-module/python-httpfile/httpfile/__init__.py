#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 5)
__all__ = ["HTTPFileReader", "AsyncHTTPFileReader"]

import errno

from collections.abc import Awaitable, Callable, Mapping
from functools import cached_property, partial
from importlib.util import find_spec
from inspect import isawaitable
from io import (
    BufferedReader, RawIOBase, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE, 
)
from os import fstat, stat, PathLike
from shutil import COPY_BUFSIZE # type: ignore
from sys import exc_info
from typing import cast, overload, Any, BinaryIO, Literal, Self
from types import MappingProxyType
from warnings import warn

from asynctools import ensure_async, run_async
from filewrap import AsyncBufferedReader, AsyncTextIOWrapper
from http_response import get_filename, get_length, get_range, get_total_length, is_chunked, is_range_request
from property import funcproperty
from urlopen import urlopen


def get_filesize(
    file, 
    /, 
    dont_read: bool = True, 
) -> int:
    if isinstance(file, (bytes, str, PathLike)):
        return stat(file).st_size
    curpos = 0
    try:
        curpos = file.seek(0, 1)
        seekable = True
    except Exception:
        seekable = False
    if not seekable:
        try:
            curpos = file.tell()
        except Exception:
            pass
    try:
        return len(file) - curpos
    except TypeError:
        pass
    if hasattr(file, "fileno"):
        try:
            return fstat(file.fileno()).st_size - curpos
        except Exception:
            pass
    if hasattr(file, "headers"):
        l = get_length(file)
        if l is not None:
            return l - curpos
    if seekable:
        try:
            return file.seek(0, 2) - curpos
        finally:
            file.seek(curpos)
    if dont_read:
        return -1
    total = 0
    if hasattr(file, "readinto"):
        readinto = file.readinto
        buf = bytearray(COPY_BUFSIZE)
        while (size := readinto(buf)):
            total += size
    elif hasattr(file, "read"):
        read = file.read
        while (chunk := read(COPY_BUFSIZE)):
            total += len(chunk)
    else:
        return -1
    return total


class HTTPFileReader(RawIOBase, BinaryIO):
    url: str | Callable[[], str]
    response: Any
    length: int
    chunked: bool
    start: int
    urlopen: Callable
    headers: Mapping
    seek_threshold: int
    _seekable: bool

    def __init__(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        start: int = 0, 
        # NOTE: If the offset of the forward seek is not higher than this value, 
        #       it will be directly read and discarded, default to 1 MB
        seek_threshold: int = 1 << 20, 
        urlopen = urlopen, 
    ):
        if headers:
            headers = {**headers, "accept-encoding": "identity"}
        else:
            headers = {"accept-encoding": "identity"}
        if start > 0:
            headers["range"] = f"bytes={start}-"
        elif start < 0:
            headers["range"] = f"bytes={start}"
        if urlopen is None:
            urlopen = globals()["urlopen"]
        if callable(url):
            geturl = url
            def url():
                url = geturl()
                headers_extra = getattr(url, "headers")
                if headers_extra:
                    headers.update(headers_extra)
                return url
        elif hasattr(url, "headers"):
            headers_extra = getattr(url, "headers")
            if headers_extra:
                headers.update(headers_extra)
        response = urlopen(url() if callable(url) else url, headers=headers)
        if start:
            rng = get_range(response)
            if not rng:
                raise OSError(errno.ESPIPE, "non-seekable")
            start = rng[0]
        self.__dict__.update(
            url = url, 
            response = response, 
            length = get_total_length(response) or 0, 
            chunked = is_chunked(response), 
            start = start, 
            closed = False, 
            urlopen = urlopen, 
            headers = MappingProxyType(headers), 
            seek_threshold = max(seek_threshold, 0), 
            _seekable = is_range_request(response), 
        )

    def __del__(self, /):
        try:
            self.close()
        except:
            pass

    def __enter__(self, /):
        return self

    def __exit__(self, /, *exc_info):
        self.close()

    def __iter__(self, /) -> Self:
        return self

    def __len__(self, /) -> int:
        return self.length

    def __next__(self, /) -> bytes:
        line = self.readline()
        if line:
            return line
        else:
            raise StopIteration

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(url={self.url!r}, headers={self.headers!r}, start={self.tell()}, seek_threshold={self.seek_threshold}, urlopen={self.urlopen!r})"

    def __setattr__(self, attr, val, /):
        raise TypeError("can't set attribute")

    def _add_start(self, delta: int, /):
        if not self.file_can_tell:
            self.__dict__["start"] += delta

    @cached_property
    def file_can_tell(self, /) -> bool:
        try:
            self.file.tell()
            return True
        except (AttributeError, TypeError, OSError):
            return False

    @funcproperty
    def file_closed(self, /) -> bool:
        return self.file.closed

    @property
    def closed(self, /) -> bool:
        return self.__dict__["closed"]

    def close(self, /):
        if not self.closed:
            self.response.close()
            self.__dict__["closed"] = True

    @funcproperty
    def file(self, /) -> BinaryIO:
        return self.response

    def fileno(self, /) -> int:
        return self.file.fileno()

    def flush(self, /):
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return self.file.flush()

    def isatty(self, /) -> bool:
        return False

    @cached_property
    def mode(self, /) -> str:
        return "rb"

    @cached_property
    def name(self, /) -> str:
        return get_filename(self.response)

    def read(self, size: int = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0 or not self.chunked and self.tell() >= self.length:
            return b""
        if self.file_closed:
            self.reconnect()
        if size is None or size < 0:
            data = self.file.read()
        else:
            data = self.file.read(size)
        if data:
            self._add_start(len(data))
        return data

    def readable(self, /) -> bool:
        return True

    def readinto(self, buffer, /) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if not buffer or not self.chunked and self.tell() >= self.length:
            return 0
        if self.file_closed:
            self.reconnect()
        try:
            readinto = self.file.readinto
        except AttributeError:
            read = self.file.read
            def readinto(buffer, /):
                data = read(len(buffer))
                size = len(data)
                buffer[:size] = data
                return data
        size = readinto(buffer)
        if size:
            self._add_start(size)
        return size

    def readline(self, size: None | int = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0 or not self.chunked and self.tell() >= self.length:
            return b""
        if self.file_closed:
            self.reconnect()
        # TODO: if no readline method, give a default impl
        if size is None or size < 0:
            data = self.file.readline()
        else:
            data = self.file.readline(size)
        if data:
            self._add_start(len(data))
        return data

    def readlines(self, hint: int = -1, /) -> list[bytes]:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if not self.chunked and self.tell() >= self.length:
            return []
        if self.file_closed:
            self.reconnect()
        # TODO: if no readlines method, give a default impl
        ls = self.file.readlines(hint)
        if ls:
            self._add_start(sum(map(len, ls)))
        return ls

    def reconnect(self, /, start: None | int = None) -> int:
        if not self._seekable:
            if start is None and self.tell() or start:
                raise OSError(errno.EOPNOTSUPP, "Unsupport for reconnection of non-seekable streams.")
            start = 0
        if start is None:
            start = self.tell()
        elif start < 0:
            start = self.length + start
            if start < 0:
                start = 0
        if start >= self.length:
            self.__dict__.update(start=start)
            return start
        self.response.close()
        url = self.url
        response = self.urlopen(
            url() if callable(url) else url, 
            headers={**self.headers, "range": f"bytes={start}-"}
        )
        length_new = get_total_length(response)
        if self.length != length_new:
            raise OSError(errno.EIO, f"file size changed: {self.length} -> {length_new}")
        self.__dict__.update(
            response=response, 
            start=start, 
            closed=False, 
        )
        return start

    def seek(self, pos: int, whence: int = 0, /) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if not self._seekable:
            raise OSError(errno.EINVAL, "not a seekable stream")
        if whence == 0:
            if pos < 0:
                raise OSError(errno.EINVAL, f"negative seek start: {pos!r}")
            old_pos = self.tell()
            if old_pos == pos:
                return pos
            if pos > old_pos and (size := pos - old_pos) <= self.seek_threshold:
                if size <= COPY_BUFSIZE:
                    self.read(size)
                else:
                    buf = bytearray(COPY_BUFSIZE)
                    readinto = self.readinto
                    while size > COPY_BUFSIZE:
                        readinto(buf)
                        size -= COPY_BUFSIZE
                    self.read(size)
            else:
                self.reconnect(pos)
            return pos
        elif whence == 1:
            if pos == 0:
                return self.tell()
            return self.seek(self.tell() + pos)
        elif whence == 2:
            return self.seek(self.length + pos)
        else:
            raise OSError(errno.EINVAL, f"whence value unsupported: {whence!r}")

    def seekable(self, /) -> bool:
        return self._seekable

    def tell(self, /) -> int:
        if self.file_can_tell:
            start = self.start
            if start >= self.length:
                return start
            return start + self.file.tell()
        else:
            return self.start

    def truncate(self, size: None | int = None, /):
        raise UnsupportedOperation(errno.ENOTSUP, "truncate")

    def writable(self, /) -> bool:
        return False

    def write(self, b, /) -> int:
        raise UnsupportedOperation(errno.ENOTSUP, "write")

    def writelines(self, lines, /):
        raise UnsupportedOperation(errno.ENOTSUP, "writelines")

    @overload
    @classmethod
    def open(
        cls, 
        /, 
        url: str | Callable[[], str], 
        mode: Literal["br", "rb"], 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ) -> Self | BufferedReader:
        ...
    @overload
    @classmethod
    def open(
        cls, 
        /, 
        url: str | Callable[[], str], 
        mode: Literal["r", "rt", "tr"] = "r", 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ) -> TextIOWrapper:
        ...
    @classmethod
    def open(
        cls, 
        /, 
        url: str | Callable[[], str], 
        mode: Literal["r", "rt", "tr", "br", "rb"] = "r", 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ) -> Self | BufferedReader | TextIOWrapper:
        file = cls(
            url=url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
            urlopen=urlopen, 
        )
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        return file.wrap(
            text_mode="b" not in mode, # type: ignore
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    @overload
    def wrap(
        self, 
        /, 
        text_mode: Literal[False] = False, 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> Self | BufferedReader:
        ...
    @overload
    def wrap(
        self, 
        /, 
        text_mode: Literal[True], 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> TextIOWrapper:
        ...
    def wrap(
        self, 
        /, 
        text_mode: Literal[False, True] = False, 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> Self | BufferedReader | TextIOWrapper:
        if buffering is None:
            if text_mode:
                buffering = DEFAULT_BUFFER_SIZE
            else:
                buffering = 0
        if buffering == 0:
            if text_mode:
                raise OSError(errno.EINVAL, "can't have unbuffered text I/O")
            return self
        line_buffering = False
        buffer_size: int
        if buffering < 0:
            buffer_size = DEFAULT_BUFFER_SIZE
        elif buffering == 1:
            if not text_mode:
                warn("line buffering (buffering=1) isn't supported in binary mode, "
                     "the default buffer size will be used", RuntimeWarning)
            buffer_size = DEFAULT_BUFFER_SIZE
            line_buffering = True
        else:
            buffer_size = buffering
        raw = self
        buffer = BufferedReader(raw, buffer_size)
        if text_mode:
            return TextIOWrapper(
                buffer, 
                encoding=encoding, 
                errors=errors, 
                newline=newline, 
                line_buffering=line_buffering, 
            )
        else:
            return buffer


class AsyncHTTPFileReader(HTTPFileReader):
    url: str | Callable[[], Awaitable[str]] # type: ignore

    def __init__(
        self, 
        /, 
        url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ):
        self.__dict__.update(closed=False, start=0, _seekable=True)
        self.__dict__["_initing"] = run_async(self.__ainit__(
            url=url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
            urlopen=urlopen, 
        ))

    async def __aenter__(self, /) -> Self:
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        return self

    async def __aexit__(self, /, *exc_info):
        await self.aclose()

    def __aiter__(self, /) -> Self:
        return self

    async def __anext__(self, /) -> bytes:
        if line := await self.readline():
            return line
        else:
            raise StopAsyncIteration

    async def __ainit__(
        self, 
        /, 
        url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ):
        if headers:
            headers = {**headers, "accept-encoding": "identity"}
        else:
            headers = {"accept-encoding": "identity"}
        if start > 0:
            headers["range"] = f"bytes={start}-"
        elif start < 0:
            headers["range"] = f"bytes={start}"
        if urlopen is None:
            urlopen = globals()["urlopen"]
        if callable(url):
            geturl = url
            async def url() -> str:
                url = geturl()
                if isawaitable(url):
                    url = await url
                headers_extra = getattr(url, "headers")
                if headers_extra:
                    headers.update(headers_extra)
                return cast(str, url)
        elif hasattr(url, "headers"):
            headers_extra = getattr(url, "headers")
            if headers_extra:
                headers.update(headers_extra)
        urlopen = ensure_async(urlopen, threaded=True)
        response = await urlopen((await url()) if callable(url) else url, headers=headers)
        if start:
            rng = get_range(response)
            if not rng:
                raise OSError(errno.ESPIPE, "non-seekable")
            start = rng[0]
        self.__dict__.update(
            url = url, 
            response = response, 
            length = get_total_length(response) or 0, 
            chunked = is_chunked(response), 
            start = start, 
            urlopen = urlopen, 
            headers = MappingProxyType(headers), 
            seek_threshold = max(seek_threshold, 0), 
            _seekable = is_range_request(response), 
        )
        self.__dict__.pop("_initing", None)

    async def aclose(self, /):
        if not self.closed:
            self.__dict__["closed"] = True
            await self.close_response()

    def close(self, /):
        if not self.closed:
            self.__dict__["closed"] = True
            try:
                ret = self.response.aclose()
            except (AttributeError, TypeError):
                try:
                    ret = self.response.close()
                except (AttributeError, TypeError):
                    return
            if isawaitable(ret):
                run_async(ret)

    async def close_response(self, /):
        try:
            ret = self.response.aclose()
        except (AttributeError, TypeError):
            try:
                ret = self.response.close()
            except (AttributeError, TypeError):
                return
        if isawaitable(ret):
            await ret

    async def flush(self, /):
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        return await ensure_async(self.file.flush, threaded=True)()

    async def read(self, size: int = -1, /) -> bytes: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        if size == 0 or not self.chunked and self.tell() >= self.length:
            return b""
        if self.file_closed:
            await self.reconnect()
        read = ensure_async(self.file.read, threaded=True)
        if size is None or size < 0:
            data = await read(-1)
        else:
            data = await read(size)
        if data:
            self._add_start(len(data))
        return data

    async def readinto(self, buffer, /) -> int: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        if not buffer or not self.chunked and self.tell() >= self.length:
            return 0
        if self.file_closed:
            await self.reconnect()
        try:
            readinto = ensure_async(self.file.readinto, threaded=True)
        except AttributeError:
            read = ensure_async(self.file.read, threaded=True)
            async def readinto(buffer, /):
                data = await read(len(buffer))
                size = len(data)
                buffer[:size] = data
                return size
        size = await readinto(buffer)
        if size:
            self._add_start(size)
        return size

    async def readline(self, size: None | int = -1, /) -> bytes: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        if size == 0 or not self.chunked and self.tell() >= self.length:
            return b""
        if self.file_closed:
            await self.reconnect()
        # TODO: if no readline method, give a default impl
        if size is None or size < 0:
            data = await ensure_async(self.file.readline, threaded=True)()
        else:
            data = await ensure_async(self.file.readline, threaded=True)(size)
        if data:
            self._add_start(len(data))
        return data

    async def readlines(self, hint: int = -1, /) -> list[bytes]: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        if not self.chunked and self.tell() >= self.length:
            return []
        if self.file_closed:
            await self.reconnect()
        # TODO: if no readlines method, give a default impl
        ls = await ensure_async(self.file.readlines, threaded=True)(hint)
        if ls:
            self._add_start(sum(map(len, ls)))
        return ls

    async def reconnect(self, /, start: None | int = None) -> int: # type: ignore
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        if not self._seekable:
            if start is None and self.tell() or start:
                raise OSError(errno.EOPNOTSUPP, "Unsupport for reconnection of non-seekable streams.")
            start = 0
        if start is None:
            start = self.tell()
        elif start < 0:
            start = self.length + start
            if start < 0:
                start = 0
        if start >= self.length:
            self.__dict__.update(start=start)
            return start
        await self.close_response()
        url = self.url
        response = await self.urlopen(
            (await url()) if callable(url) else url, 
            headers={**self.headers, "range": f"bytes={start}-"}
        )
        length_new = get_total_length(response)
        if self.length != length_new:
            raise OSError(errno.EIO, f"file size changed: {self.length} -> {length_new}")
        self.__dict__.update(
            response=response, 
            start=start, 
            closed=False, 
        )
        return start

    async def seek(self, pos: int, whence: int = 0, /) -> int: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if _initing := self.__dict__.get("_initing"):
            await _initing
            self.__dict__.pop("_initing", None)
        if not self._seekable:
            raise OSError(errno.EINVAL, "not a seekable stream")
        if whence == 0:
            if pos < 0:
                raise OSError(errno.EINVAL, f"negative seek start: {pos!r}")
            old_pos = self.tell()
            if old_pos == pos:
                return pos
            if pos > old_pos and (size := pos - old_pos) <= self.seek_threshold:
                if size <= COPY_BUFSIZE:
                    await self.read(size)
                else:
                    buf = bytearray(COPY_BUFSIZE)
                    readinto = self.readinto
                    while size > COPY_BUFSIZE:
                        await readinto(buf)
                        size -= COPY_BUFSIZE
                    await self.read(size)
            else:
                await self.reconnect(pos)
            return pos
        elif whence == 1:
            if pos == 0:
                return self.tell()
            return await self.seek(self.tell() + pos)
        elif whence == 2:
            return await self.seek(self.length + pos)
        else:
            raise OSError(errno.EINVAL, f"whence value unsupported: {whence!r}")

    @classmethod
    async def new(
        cls, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ) -> Self: # type: ignore
        self = cls.__new__(cls)
        await self.__ainit__(
            url=url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
            urlopen=urlopen, 
        )
        return self

    @overload # type: ignore
    @classmethod
    async def open(
        cls, 
        /, 
        url: str | Callable[[], str], 
        mode: Literal["br", "rb"], 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ) -> Self | AsyncBufferedReader:
        ...
    @overload
    @classmethod
    async def open(
        cls, 
        /, 
        url: str | Callable[[], str], 
        mode: Literal["r", "rt", "tr"] = "r", 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ) -> AsyncTextIOWrapper:
        ...
    @classmethod
    async def open(
        cls, 
        /, 
        url: str | Callable[[], str], 
        mode: Literal["r", "rt", "tr", "br", "rb"] = "r", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        headers: None | Mapping = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        urlopen = None, 
    ) -> Self | AsyncBufferedReader | AsyncTextIOWrapper:
        file = await cls.new(
            url=url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
            urlopen=urlopen, 
        )
        if mode not in ("r", "rt", "tr", "rb", "br"):
            raise OSError(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        return file.wrap(
            text_mode="b" not in mode, # type: ignore
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    @overload
    def wrap(
        self, 
        /, 
        text_mode: Literal[False] = False, 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> Self | AsyncBufferedReader:
        ...
    @overload
    def wrap(
        self, 
        /, 
        text_mode: Literal[True], 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> AsyncTextIOWrapper:
        ...
    def wrap(
        self, 
        /, 
        text_mode: bool = False, 
        *, 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
    ) -> Self | AsyncBufferedReader | AsyncTextIOWrapper:
        if buffering is None:
            if text_mode:
                buffering = DEFAULT_BUFFER_SIZE
            else:
                buffering = 0
        if buffering == 0:
            if text_mode:
                raise OSError(errno.EINVAL, "can't have unbuffered text I/O")
            return self
        line_buffering = False
        buffer_size: int
        if buffering < 0:
            buffer_size = DEFAULT_BUFFER_SIZE
        elif buffering == 1:
            if not text_mode:
                warn("line buffering (buffering=1) isn't supported in binary mode, "
                     "the default buffer size will be used", RuntimeWarning)
            buffer_size = DEFAULT_BUFFER_SIZE
            line_buffering = True
        else:
            buffer_size = buffering
        raw = self
        buffer = AsyncBufferedReader(raw, buffer_size)
        if text_mode:
            return AsyncTextIOWrapper(
                buffer, 
                encoding=encoding, 
                errors=errors, 
                newline=newline, 
                line_buffering=line_buffering, 
            )
        else:
            return buffer


if find_spec("urllib3"):
    from urllib.error import HTTPError

    _urllib3_urlopen = None

    class Urllib3FileReader(HTTPFileReader):

        def __init__(
            self, 
            /, 
            url: str | Callable[[], str], 
            headers: None | Mapping = None, 
            start: int = 0, 
            seek_threshold: int = 1 << 20, 
            urlopen = None, 
        ):
            global _urllib3_urlopen
            from urllib3 import request
            from urllib3.poolmanager import PoolManager

            if isinstance(urlopen, PoolManager):
                urlopen = partial(urlopen.request, "GET", preload_content=False)
            elif urlopen is None:
                if _urllib3_urlopen is None:
                    urlopen = _urllib3_urlopen = partial(cast(Callable, request), "GET", preload_content=False)
                else:
                    urlopen = _urllib3_urlopen
            else:
                urlopen = partial(urlopen, preload_content=False)

            def urlopen_wrapper(url: str, headers: None | Mapping = headers):
                resp = urlopen(url, headers=headers)
                if resp.status >= 400:
                    raise HTTPError(resp.url, resp.status, resp.reason, resp.headers, resp)
                return resp

            super().__init__(
                url, 
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
                urlopen=urlopen_wrapper, 
            )

    __all__.append("Urllib3FileReader")


if find_spec("requests"):
    _requests_urlopen = None

    class RequestsFileReader(HTTPFileReader):

        def __init__(
            self, 
            /, 
            url: str | Callable[[], str], 
            headers: None | Mapping = None, 
            start: int = 0, 
            seek_threshold: int = 1 << 20, 
            urlopen = None, 
        ):
            global _requests_urlopen
            from requests import request, Session
            if isinstance(urlopen, Session):
                urlopen = partial(urlopen.request, "GET", stream=True)
            elif urlopen is None:
                if _requests_urlopen is None:
                    if "__del__" not in Session.__dict__:
                        setattr(Session, "__del__", lambda self, /: self.close())
                    urlopen = _requests_urlopen = partial(request, "GET", stream=True)
                else:
                    urlopen = _requests_urlopen
            else:
                urlopen = partial(urlopen, stream=True)
            def urlopen_wrapper(url: str, headers: None | Mapping = headers):
                resp = urlopen(url, headers=headers)
                resp.raise_for_status()
                return resp
            super().__init__(
                url, 
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
                urlopen=urlopen_wrapper, 
            )

        @funcproperty
        def file(self, /) -> BinaryIO:
            return self.response.raw

    __all__.append("RequestsFileReader")


if find_spec("aiohttp"):
    from types import MethodType

    _aiohttp_urlopen = None

    class AiohttpFileReader(AsyncHTTPFileReader):

        async def __ainit__(
            self, 
            /, 
            url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
            headers: None | Mapping = None, 
            start: int = 0, 
            seek_threshold: int = 1 << 20, 
            urlopen = None, 
        ):
            global _aiohttp_urlopen
            from aiohttp import request, ClientSession

            if isinstance(urlopen, ClientSession):
                urlopen = urlopen.get
            elif urlopen is None:
                if _aiohttp_urlopen is None:
                    urlopen = _aiohttp_urlopen = partial(request, "GET")
                else:
                    urlopen = _aiohttp_urlopen
            async def urlopen_wrapper(url: str, headers: None | Mapping = headers):
                ctx = urlopen(url, headers=headers)
                resp = await ctx.__aenter__()
                resp.aclose = lambda: ctx.__aexit__(None, None, None)
                resp.raise_for_status()
                return resp
            await super().__ainit__(
                url=url, 
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
                urlopen=urlopen_wrapper, 
            )

        @funcproperty
        def file(self, /) -> BinaryIO:
            return self.response.content

        @funcproperty
        def file_closed(self, /) -> bool:
            return self.response.closed

    __all__.append("AiohttpFileReader")


if find_spec("httpx"):
    from filewrap import bytes_iter_to_reader, bytes_iter_to_async_reader

    def httpx_request(
        url, 
        method: str = "GET", 
        auth = None, 
        follow_redirects: bool = True, 
        stream: bool = True, 
        session = None, 
        **request_kwargs, 
    ):
        if session is None:
            from httpx import Client
            if "__del__" not in Client.__dict__:
                setattr(Client, "__del__", lambda self: self.close())
            session = Client()
        resp = session.send(
            request=session.build_request(
                method=method, 
                url=url, 
                **request_kwargs, 
            ), 
            auth=auth, 
            follow_redirects=follow_redirects, 
            stream=stream, 
        )
        setattr(resp, "session", session)
        return resp

    async def httpx_request_async(
        url, 
        method: str = "GET", 
        auth = None, 
        follow_redirects: bool = True, 
        stream: bool = True, 
        session = None, 
        **request_kwargs, 
    ):
        if session is None:
            from httpx import AsyncClient
            if "__del__" not in AsyncClient.__dict__:
                setattr(AsyncClient, "__del__", lambda self: run_async(self.aclose()))
            session = AsyncClient()
        resp = await session.send(
            request=session.build_request(
                method=method, 
                url=url, 
                **request_kwargs, 
            ), 
            auth=auth, 
            follow_redirects=follow_redirects, 
            stream=stream, 
        )
        setattr(resp, "session", session)
        return resp

    class HttpxFileReader(HTTPFileReader):

        def __init__(
            self, 
            /, 
            url: str | Callable[[], str], 
            headers: None | Mapping = None, 
            start: int = 0, 
            seek_threshold: int = 1 << 20, 
            urlopen = None, 
        ):
            from httpx import Client

            if urlopen is None or isinstance(urlopen, Client):
                urlopen = partial(httpx_request, session=urlopen)

            def urlopen_wrapper(url: str, headers: None | Mapping = headers):
                resp = urlopen(url, headers=headers)
                resp.raise_for_status()
                file = bytes_iter_to_reader(resp.iter_raw())
                self.__dict__["file"] = file
                return resp

            super().__init__(
                url, 
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
                urlopen=urlopen_wrapper, 
            )

        @funcproperty
        def file_closed(self, /) -> bool:
            return self.response.is_closed

    class AsyncHttpxFileReader(AsyncHTTPFileReader):

        async def __ainit__(
            self, 
            /, 
            url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
            headers: None | Mapping = None, 
            start: int = 0, 
            seek_threshold: int = 1 << 20, 
            urlopen = None, 
        ):
            from httpx import AsyncClient

            if urlopen is None or isinstance(urlopen, AsyncClient):
                urlopen = partial(httpx_request_async, session=urlopen)

            async def urlopen_wrapper(url: str, headers: None | Mapping = headers):
                resp = await urlopen(url, headers=headers)
                resp.raise_for_status()
                file = bytes_iter_to_async_reader(resp.aiter_raw())
                self.__dict__["file"] = file
                return resp

            await super().__ainit__(
                url=url, 
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
                urlopen=urlopen_wrapper, 
            )

        @funcproperty
        def file_closed(self, /) -> bool:
            return self.response.is_closed

    __all__.append("HttpxFileReader")
    __all__.append("AsyncHttpxFileReader")

# TODO: 增加 blacksheep 的 HTTPFileReader
# TODO: 设计实现一个 HTTPFileWriter，用于实现上传，关闭后视为上传完成
# TODO: httpx 重新实现 stream 和 async_stream 方法，确保不需要用上下文管理器，如此才能真的简化
