#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["HTTPFileReader", "AsyncHTTPFileReader"]

import errno

from collections.abc import Callable, Iterator, Mapping
from functools import cached_property, partial
from http.client import HTTPResponse
from io import (
    BufferedReader, RawIOBase, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE, 
)
from os import fstat, stat, PathLike
from shutil import COPY_BUFSIZE # type: ignore
from typing import Any, BinaryIO, IO, Optional, Protocol, Self, TypeVar
from types import MappingProxyType
from warnings import warn

from http_response import get_filename, get_length, get_range, get_total_length, is_chunked, is_range_request
from property import funcproperty
from urlopen import urlopen


def get_filesize(file, /, dont_read: bool = True) -> int:
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
        headers: Optional[Mapping] = None, 
        start: int = 0, 
        # NOTE: If the offset of the forward seek is not higher than this value, 
        #       it will be directly read and discarded, default to 1 MB
        seek_threshold: int = 1 << 20, 
        urlopen: Callable[..., HTTPResponse] = urlopen, 
    ):
        if headers:
            headers = {**headers, "Accept-Encoding": "identity"}
        else:
            headers = {"Accept-Encoding": "identity"}
        if start > 0:
            headers["Range"] = f"bytes={start}-"
        elif start < 0:
            headers["Range"] = f"bytes={start}"
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

    def __iter__(self, /):
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
        return f"{name}({self.url!r}, urlopen={self.urlopen!r}, headers={self.headers!r})"

    def __setattr__(self, attr, val, /):
        raise TypeError("can't set attribute")

    def _add_start(self, delta: int, /):
        self.__dict__["start"] += delta

    def close(self, /):
        if not self.closed:
            self.response.close()
            self.__dict__["closed"] = True

    @funcproperty
    def closed(self, /):
        return self.__dict__["closed"]

    @funcproperty
    def file(self, /) -> BinaryIO:
        return self.response

    def fileno(self, /) -> int:
        return self.file.fileno()

    def flush(self, /):
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
        if self.file.closed:
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
        if self.file.closed:
            self.reconnect()
        size = self.file.readinto(buffer)
        if size:
            self._add_start(size)
        return size

    def readline(self, size: Optional[int] = -1, /) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0 or not self.chunked and self.tell() >= self.length:
            return b""
        if self.file.closed:
            self.reconnect()
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
        if self.file.closed:
            self.reconnect()
        ls = self.file.readlines(hint)
        if ls:
            self._add_start(sum(map(len, ls)))
        return ls

    def reconnect(self, /, start: Optional[int] = None) -> int:
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
            headers={**self.headers, "Range": f"bytes={start}-"}
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
        return self.start

    def truncate(self, size: Optional[int] = None, /):
        raise UnsupportedOperation(errno.ENOTSUP, "truncate")

    def writable(self, /) -> bool:
        return False

    def write(self, b, /) -> int:
        raise UnsupportedOperation(errno.ENOTSUP, "write")

    def writelines(self, lines, /):
        raise UnsupportedOperation(errno.ENOTSUP, "writelines")

    def wrap(
        self, 
        /, 
        text_mode: bool = False, 
        buffering: Optional[int] = None, 
        encoding: Optional[str] = None, 
        errors: Optional[str] = None, 
        newline: Optional[str] = None, 
    ) -> Self | IO:
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


try:
    from requests import Session

    class RequestsFileReader(HTTPFileReader):

        def __init__(
            self, 
            /, 
            url: str | Callable[[], str], 
            headers: Optional[Mapping] = None, 
            start: int = 0, 
            seek_threshold: int = 1 << 20, 
            urlopen: Callable = Session().get, 
        ):
            def urlopen_wrapper(url: str, headers: Optional[Mapping] = headers):
                resp = urlopen(url, headers=headers, stream=True)
                resp.raise_for_status()
                return resp
            super().__init__(
                url, 
                headers=headers, 
                start=start, 
                seek_threshold=seek_threshold, 
                urlopen=urlopen_wrapper, 
            )

        def _add_start(self, delta: int, /):
            pass

        @funcproperty
        def file(self, /) -> BinaryIO:
            return self.response.raw

        def tell(self, /) -> int:
            start = self.start
            if start >= self.length:
                return start
            return start + self.file.tell()

    __all__.append("RequestsFileReader")
except ImportError:
    pass


try:
    from aiohttp import ClientSession

    ...
except ImportError:
    pass


try:
    from httpx import Client, AsyncClient

    ...
except ImportError:
    pass


# TODO: 实现 AsyncHTTPFileReader
# TODO: 支持异步文件，使用 aiohttp，参考 aiofiles 的接口实现
# TODO: 设计实现一个 HTTPFileWriter，用于实现上传，关闭后视为上传完成

