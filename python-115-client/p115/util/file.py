#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["get_filesize", "HTTPFileReader", "RequestsFileReader"]

import errno

from functools import partial
from http.client import HTTPResponse
from io import RawIOBase, TextIOWrapper, UnsupportedOperation
from os import fstat, stat, PathLike
from typing import Any, Callable, Mapping, Optional
from types import MappingProxyType

from requests import Session

from .urlopen import urlopen


def get_filesize(file, /) -> int:
    if isinstance(file, (bytes, str, PathLike)):
        return stat(file).st_size
    if hasattr(file, "fileno"):
        try:
            return fstat(file.fileno()).st_size
        except Exception:
            pass
    bufsize = 1 << 16
    total = 0
    if hasattr(file, "readinto"):
        readinto = fileobj.readinto
        buf = bytearray(bufsize)
        while (size := readinto(buf)):
            total += size
    elif hasattr(fileobj, "read"):
        if isinstance(fileobj, TextIOWrapper):
            fileobj = fileobj.buffer
        else:
            if fileobj.read(0) != b"":
                raise ValueError(f"{fileobj!r} is not a file-like object in reading binary mode.")
        read = fileobj.read
        while (data := read(bufsize)):
            total += len(data)
    else:
        raise ValueError(f"{fileobj!r} is not a file-like object in reading mode.")
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
        headers = {**headers, "Accept-Encoding": "identity", "Range": "bytes=0-"}
        response = urlopen(url, headers=headers)
        resp_headers = {k.lower(): v for k, v in response.headers.items()}
        self.__dict__.update(
            url = url, 
            response = response, 
            length = response.length or 0, 
            chunked = resp_headers.get("transfer-encoding") == "chunked", 
            start = 0, 
            closed = False, 
            urlopen = urlopen, 
            headers = MappingProxyType(headers), 
            _seekable = resp_headers.get("accept-ranges") == "bytes", 
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

    @property
    def file(self, /):
        return self.response

    @property
    def fileno(self, /) -> int:
        return self.file.fileno()

    def flush(self, /):
        return self.file.flush()

    def isatty(self, /) -> bool:
        return False

    @property
    def mode(self, /) -> str:
        return "rb"

    @property
    def name(self, /) -> str:
        return self.url

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

    def reconnect(self, /, start: Optional[int] = None):
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

    def seekable(self, /):
        return self._seekable

    def tell(self, /) -> int:
        return self.start

    def truncate(self, size: Optional[int] = None, /):
        raise UnsupportedOperation(errno.ENOTSUP, "truncate")

    def writable(self, /):
        return False

    def write(self, b, /) -> int:
        raise UnsupportedOperation(errno.ENOTSUP, "write")

    def writelines(self, lines, /):
        raise UnsupportedOperation(errno.ENOTSUP, "writelines")


class RequestsFileReader(HTTPFileReader):

    def __init__(
        self, 
        url: str, 
        /, 
        headers: Mapping = {}, 
        urlopen: Callable = Session().get, 
    ):
        headers = {**headers, "Accept-Encoding": "identity", "Range": "bytes=0-"}
        response = urlopen(url, headers=headers, stream=True)
        self.__dict__.update(
            url = url, 
            response = response, 
            length = int(response.headers.get("Content-Length", 0)), 
            chunked = response.headers.get("Transfer-Encoding") == "chunked", 
            start = 0, 
            closed = False, 
            urlopen = partial(urlopen, stream=True), 
            headers = MappingProxyType(headers), 
            _seekable = response.headers.get("Accept-Ranges") == "bytes", 
        )

    def _add_start(self, delta: int, /):
        pass

    @property
    def file(self, /):
        return self.response.raw

    def tell(self, /) -> int:
        return self.start + self.file.tell()

