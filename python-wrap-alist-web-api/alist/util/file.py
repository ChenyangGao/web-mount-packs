#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "SupportsWrite", "SupportsRead", 
    "bio_skip_bytes", "get_filesize", "HTTPFileReader", "RequestsFileReader"
]

import errno

from functools import cached_property, partial
from http.client import HTTPResponse
from io import (
    BufferedReader, RawIOBase, TextIOWrapper, UnsupportedOperation, DEFAULT_BUFFER_SIZE, 
)
from os import fstat, stat, PathLike
from typing import Any, BinaryIO, Callable, Mapping, Optional, Protocol, TypeVar
from types import MappingProxyType
from warnings import warn

from requests import Session

from .property import funcproperty
from .response import get_filename, get_length, is_chunked, is_range_request
from .urlopen import urlopen


_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object: ...


class SupportsRead(Protocol[_T_co]):
    def read(self, __length: int = ...) -> _T_co: ...


def bio_skip_bytes(
    bio: BinaryIO, 
    skipsize: int, 
    chunksize: int = 1 << 16, 
    callback: Optional[Callable[[int], Any]] = None, 
) -> BinaryIO:
    if skipsize <= 0:
        return bio
    if chunksize <= 0:
        chunksize = 1 << 16
    try:
        bio.seek(skipsize, 1)
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


def get_filesize(file, /) -> int:
    if isinstance(file, (bytes, str, PathLike)):
        return stat(file).st_size
    if hasattr(file, "fileno"):
        try:
            return fstat(file.fileno()).st_size
        except Exception:
            pass
    try:
        return len(file)
    except TypeError:
        pass
    bufsize = 1 << 16
    total = 0
    if hasattr(file, "readinto"):
        readinto = file.readinto
        buf = bytearray(bufsize)
        while (size := readinto(buf)):
            total += size
    elif hasattr(file, "read"):
        if isinstance(file, TextIOWrapper):
            file = file.buffer
        else:
            if file.read(0) != b"":
                raise ValueError(f"{file!r} is not a file-like object in reading binary mode.")
        read = file.read
        while (data := read(bufsize)):
            total += len(data)
    else:
        raise ValueError(f"{file!r} is not a file-like object in reading mode.")
    return total


class HTTPFileReader(RawIOBase):
    url: str
    response: Any
    length: int
    chunked: bool
    start: int
    closed: bool
    urlopen: Callable
    headers: Mapping
    _seekable: bool

    def __init__(
        self, 
        url: str, 
        /, 
        headers: Mapping = {}, 
        urlopen: Callable[..., HTTPResponse] = urlopen, 
    ):
        headers = {**headers, "Accept-Encoding": "identity"}
        response = urlopen(url, headers=headers)
        self.__dict__.update(
            url = url, 
            response = response, 
            length = get_length(response) or 0, 
            chunked = is_chunked(response), 
            start = 0, 
            closed = False, 
            urlopen = urlopen, 
            headers = MappingProxyType(headers), 
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
        self.response.close()
        self.__dict__["closed"] = True

    @funcproperty
    def file(self, /):
        return self.response

    @funcproperty
    def fileno(self, /):
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
        data = self.file.read(size)
        if data:
            self._add_start(len(data))
        return data

    def readable(self, /) -> bool:
        return True

    def readinto(self, buffer, /) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
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
        elif size is None:
            size = -1
        if self.file.closed:
            self.reconnect()
        data = self.file.readline(size)
        if data:
            self._add_start(len(data))
        return data

    def readlines(self, hint: int = -1, /) -> list[bytes]:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
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
        self.response.close()
        self.__dict__.update(
            response=self.urlopen(self.url, headers={**self.headers, "Range": f"bytes={start}-"}), 
            start=start, 
        )
        return start

    def seek(self, pos: int, whence: int = 0, /) -> int:
        if not self._seekable:
            raise OSError(errno.EINVAL, "not a seekable stream")
        if whence == 0:
            if pos < 0:
                raise OSError(errno.EINVAL, f"negative seek start: {pos!r}")
            old_pos = self.tell()
            if old_pos == pos:
                return pos
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
    ):
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


class RequestsFileReader(HTTPFileReader):

    def __init__(
        self, 
        url: str, 
        /, 
        headers: Mapping = {}, 
        urlopen: Callable = Session().get, 
    ):
        headers = {**headers, "Accept-Encoding": "identity"}
        response = urlopen(url, headers=headers, stream=True)
        self.__dict__.update(
            url = url, 
            response = response, 
            length = get_length(response) or 0, 
            chunked = is_chunked(response), 
            start = 0, 
            closed = False, 
            urlopen = partial(urlopen, stream=True), 
            headers = MappingProxyType(headers), 
            _seekable = is_range_request(response), 
        )

    def _add_start(self, delta: int, /):
        pass

    @funcproperty
    def file(self, /):
        return self.response.raw

    def tell(self, /) -> int:
        return self.start + self.file.tell()

