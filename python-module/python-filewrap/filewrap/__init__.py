#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 2, 8)
__all__ = [
    "SupportsRead", "SupportsReadinto", "SupportsWrite", "SupportsSeek", 
    "AsyncBufferedReader", "AsyncTextIOWrapper", "buffer_length", 
    "bio_chunk_iter", "bio_chunk_async_iter", "bio_skip_iter", "bio_skip_async_iter", 
    "bytes_iter", "bytes_async_iter", "bytes_iter_skip", "bytes_async_iter_skip", 
    "bytes_iter_to_reader", "bytes_iter_to_async_reader", "bytes_to_chunk_iter", 
    "bytes_to_chunk_async_iter", "bytes_ensure_part_iter", "bytes_ensure_part_async_iter", 
    "progress_bytes_iter", "progress_bytes_async_iter", "copyfileobj", "copyfileobj_async", 
    "bound_bytes_reader", "bound_async_bytes_reader", 
]

from asyncio import Lock as AsyncLock
from codecs import getdecoder, getencoder
from collections.abc import (
    Awaitable, AsyncIterable, AsyncIterator, Buffer, Callable, Iterable, Iterator, 
)
from functools import cached_property
from io import BufferedIOBase, BufferedReader, RawIOBase, TextIOWrapper
from inspect import isawaitable, isasyncgen, isgenerator
from itertools import chain
from re import compile as re_compile
from threading import Lock
from typing import cast, runtime_checkable, Any, BinaryIO, Final, Protocol, Self

from asynctools import async_chain, ensure_async, ensure_aiter, run_async
from property import funcproperty


READ_BUFSIZE = 1 << 16
CRE_NOT_UNIX_NEWLINES: Final = re_compile("\r\n|\r")


@BufferedIOBase.register
class VirtualBufferedReader:
    def __new__(cls, /, *a, **k):
        if cls is __class__: # type: ignore
            raise TypeError("not allowed to create instances")
        return super().__new__(cls, *a, **k)


@runtime_checkable
class SupportsRead[T](Protocol):
    def read(self, /, size: int) -> T: ...


@runtime_checkable
class SupportsReadinto[T](Protocol):
    def readinto(self, /, buf: T): ...


@runtime_checkable
class SupportsWrite[T](Protocol):
    def write(self, /, data: T): ...


@runtime_checkable
class SupportsSeek(Protocol):
    def seek(self, /, offset: int, whence: int): ...


class AsyncBufferedReader(BufferedReader):

    def __init__(
        self, 
        /, 
        raw: RawIOBase, 
        buffer_size: int = 0, 
    ):
        super().__init__(raw, 1)
        if buffer_size <= 0:
            buffer_size = READ_BUFSIZE
        self._buf = bytearray(buffer_size)
        self._buf_view = memoryview(self._buf)
        self._buf_pos = 0
        self._buf_stop = 0
        self._pos = raw.tell()

    def __del__(self, /):
        try:
            self.close()
        except:
            pass

    async def __aenter__(self, /) -> Self:
        return self

    async def __aexit__(self, /, *exc_info):
        await self.aclose()

    def __aiter__(self, /):
        return self

    async def __anext__(self, /):
        if line := await self.readline():
            return line
        else:
            raise StopAsyncIteration 

    def __getattr__(self, attr, /):
        return getattr(self.raw, attr)

    def __len__(self, /) -> int:
        return self.length

    @property
    def length(self, /) -> int:
        return getattr(self.raw, "length")

    @cached_property
    def _close(self, /):
        try:
            return getattr(self.raw, "aclose")
        except AttributeError:
            return getattr(self.raw, "close")

    @cached_property
    def _flush(self, /):
        return ensure_async(self.raw.flush, threaded=True)

    @cached_property
    def _read(self, /):
        return ensure_async(self.raw.read, threaded=True)

    @cached_property
    def _readinto(self, /):
        return ensure_async(self.raw.readinto, threaded=True)

    @cached_property
    def _readline(self, /):
        return ensure_async(self.raw.readline, threaded=True)

    @cached_property
    def _seek(self, /):
        return ensure_async(self.raw.seek, threaded=True)

    def calibrate(self, /, target: int = -1) -> bool:
        pos = self._pos
        if target < 0:
            target = self.raw.tell()
        if pos == target:
            return True
        buf_pos = self._buf_pos
        buf_stop = self._buf_stop
        self._pos = target
        move_left = pos - target
        reusable = 0 <= move_left <= buf_pos
        if reusable:
            width = buf_pos - move_left
            self._buf_view[:width] = self._buf_view[move_left:buf_pos]
            self._buf_pos = self._buf_stop = width
        else:
            self._buf_pos = self._buf_stop = 0
        return reusable

    async def aclose(self, /):
        ret = self.close()
        if isawaitable(ret):
            await ret

    def close(self, /):
        return run_async(self._close())

    async def flush(self, /):
        return await self._flush()

    def peek(self, size: int = 0, /) -> bytes:
        start, stop = self._buf_pos, self._buf_stop
        if size > 0:
            stop = min(start + size, stop)
        return self._buf_view[start:stop].tobytes()

    def review(self, size: int = 0, /) -> bytes:
        start, stop = 0, self._buf_pos
        if size > 0:
            start = max(0, stop - size)
        return self._buf_view[start:stop].tobytes()

    def context(self, /) -> tuple[bytes, int]:
        start, stop = self._buf_pos, self._buf_stop
        return self._buf_view[0:stop].tobytes(), start

    async def read(self, size: None | int = -1, /) -> bytes: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return b""
        if size is None:
            size = -1
        buf_view = self._buf_view
        buf_pos = self._buf_pos
        buf_stop = self._buf_stop
        buf_size = buf_stop - buf_pos
        if size > 0:
            if buf_size >= size:
                buf_pos_stop = self._buf_pos = buf_pos + size
                self._pos += size
                return buf_view[buf_pos:buf_pos_stop].tobytes()
            buffer_view = memoryview(bytearray(size))
            buffer_view[:buf_size] = buf_view[buf_pos:buf_stop]
            self._buf_pos = buf_stop
            self._pos += buf_size
            buf_size += await self.readinto(buffer_view[buf_size:])
            return buffer_view[:buf_size].tobytes()
        BUFSIZE = buffer_length(buf_view)
        read = self._read
        buffer = bytearray(buf_view[buf_pos:buf_stop])
        try:
            while data := await read(BUFSIZE):
                buffer += data
                length = buffer_length(data)
                self._pos += length
                if BUFSIZE == length:
                    buf_view[:] = data
                    if buf_pos != BUFSIZE:
                        buf_pos = self._buf_pos = self._buf_stop = BUFSIZE
                else:
                    buf_pos_stop = buf_stop + length
                    if buf_pos_stop <= BUFSIZE:
                        buf_view[buf_stop:buf_pos_stop] = data
                        self._buf_pos = self._buf_stop = buf_pos_stop
                    else:
                        index = BUFSIZE - length
                        buf_view[:index] = buf_view[-index:]
                        buf_view[-length:] = data
                        self._buf_pos = self._buf_stop = BUFSIZE
                    break
            return bytes(buffer)
        except:
            self.calibrate()
            raise

    async def read1(self, size: None | int = -1, /) -> bytes: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return b""
        if size is None:
            size = -1
        buf_view = self._buf_view
        buf_pos = self._buf_pos
        buf_stop = self._buf_stop
        buf_size = buf_stop - buf_pos
        if size > 0:
            if buf_size >= size:
                buf_pos_stop = self._buf_pos = buf_pos + size
                self._pos += size
                return buf_view[buf_pos:buf_pos_stop].tobytes()
            size -= buf_size
        try:
            data = await self._read(size)
        except:
            self.calibrate()
            raise
        prev_data = buf_view[buf_pos:buf_stop].tobytes()
        if data:
            BUFSIZE = buffer_length(buf_view)
            length = buffer_length(data)
            self._pos += buffer_length(prev_data) + length
            if BUFSIZE <= length:
                buf_view[:] = memoryview(data)[-BUFSIZE:]
                self._buf_pos = self._buf_stop = BUFSIZE
            else:
                buf_pos_stop = buf_stop + length
                if buf_pos_stop <= BUFSIZE:
                    buf_view[buf_stop:buf_pos_stop] = data
                    self._buf_pos = self._buf_stop = buf_pos_stop
                else:
                    index = BUFSIZE - length
                    buf_view[:index] = buf_view[-index:]
                    buf_view[-length:] = data
                    self._buf_pos = self._buf_stop = BUFSIZE
            return prev_data + data
        else:
            return prev_data

    async def readinto(self, buffer, /) -> int: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        size = buffer_length(buffer)
        if size == 0:
            return 0
        buf_view = self._buf_view
        buf_pos = self._buf_pos
        buf_stop = self._buf_stop
        buf_size = buf_stop - buf_pos
        if buf_size >= size:
            buf_pos_stop = buf_pos + size
            buffer[:] = buf_view[buf_pos:buf_pos_stop]
            self._buf_pos = buf_pos_stop
            self._pos += size
            return size
        try:
            readinto = self._readinto
        except AttributeError:
            read = self._read
            async def readinto(buffer, /) -> int:
                data = await read(buffer_length(buffer))
                if data:
                    size = buffer_length(data)
                    buffer[:size] = data
                    return size
                else:
                    return 0
        BUFSIZE = buffer_length(buf_view)
        buffer_view = memoryview(buffer)
        buffer_view[:buf_size] = buf_view[buf_pos:buf_stop]
        buf_pos = self._buf_pos = buf_stop
        self._pos += buf_size
        buffer_pos = buf_size
        size -= buf_size
        try:
            running = size > 0
            while running:
                if buf_stop < BUFSIZE:
                    length = await readinto(buf_view[buf_stop:])
                    if not length:
                        break
                    buf_stop = self._buf_stop = buf_stop + length
                    if buf_stop < BUFSIZE:
                        running = False
                else:
                    length = await readinto(buf_view)
                    if not length:
                        break
                    if length < BUFSIZE:
                        part1, part2 = buf_view[length:].tobytes(), buf_view[:length].tobytes()
                        index = buffer_length(part1)
                        buf_view[:index] = part1
                        buf_view[index:] = part2
                        running = False
                        buf_pos = self._buf_pos = BUFSIZE - length
                    else:
                        buf_pos = self._buf_pos = 0
                move = min(length, size)
                buffer_view[buffer_pos:buffer_pos+move] = buf_view[buf_pos:buf_pos+move]
                self._buf_pos += move
                self._pos += move
                buffer_pos += move
                if move == size:
                    running = False
                else:
                    size -= length
            return buffer_pos
        except:
            self.calibrate()
            raise

    async def readinto1(self, buffer, /) -> int: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        size = buffer_length(buffer)
        if size == 0:
            return 0
        buf_view = self._buf_view
        buf_pos = self._buf_pos
        buf_stop = self._buf_stop
        buf_size = buf_stop - buf_pos
        if buf_size >= size:
            buf_pos_stop = buf_pos + size
            buffer[:] = buf_view[buf_pos:buf_pos_stop]
            self._buf_pos = buf_pos_stop
            self._pos += size
            return size
        try:
            readinto = self._readinfo
        except AttributeError:
            read = self._read
            async def readinto(buffer, /) -> int:
                data = await read(buffer_length(buffer))
                if data:
                    size = buffer_length(data)
                    buffer[:size] = data
                    return size
                else:
                    return 0
        BUFSIZE = buffer_length(buf_view)
        buffer_view = memoryview(buffer)
        buffer_view[:buf_size] = buf_view[buf_pos:buf_stop]
        buf_pos = self._buf_pos = buf_stop
        self._pos += buf_size
        buffer_pos = buf_size
        size -= buf_size
        try:
            length = await readinto(buffer_view[buf_size:])
        except:
            self.calibrate()
            raise
        if length:
            BUFSIZE = buffer_length(buf_view)
            buffer_pos += length
            self._pos += length
            if BUFSIZE <= buffer_pos:
                buf_view[:] = buffer_view[-BUFSIZE:]
                self._buf_pos = self._buf_stop = BUFSIZE
            else:
                buf_pos_stop = buf_stop + length
                if buf_pos_stop <= BUFSIZE:
                    buf_view[buf_stop:buf_pos_stop] = buffer_view[-length:]
                    self._buf_pos = self._buf_stop = buf_pos_stop
                else:
                    index = BUFSIZE - length
                    buf_view[:index] = buf_view[-index:]
                    buf_view[-length:] = buffer_view[-length:]
                    self._buf_pos = self._buf_stop = BUFSIZE
        return buffer_pos

    async def readline(self, size: int | None = -1, /) -> bytes: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return b""
        if size is None:
            size = -1
        buf = self._buf
        buf_pos = self._buf_pos
        buf_stop = self._buf_stop
        buf_size = buf_stop - buf_pos
        if size > 0 and size <= buf_size:
            stop = buf_pos + size
            index = buf.find(b"\n", buf_pos, stop)
            if index > 0:
                buf_pos_stop = self._buf_pos = index + 1
                self._pos += buf_pos_stop - buf_pos
            else:
                buf_pos_stop = self._buf_pos = stop
                self._pos += size
            return self._buf_view[buf_pos:buf_pos_stop].tobytes()
        index = buf.find(b"\n", buf_pos, buf_stop)
        if index > 0:
            buf_pos_stop = self._buf_pos = index + 1
            self._pos += buf_pos_stop - buf_pos
            return self._buf_view[buf_pos:buf_pos_stop].tobytes()
        try:
            readline = self._readline
        except AttributeError:
            async def readline(size: None | int = -1, /) -> bytes:
                if size == 0:
                    return b""
                if size is None:
                    size = -1
                read = self._read
                cache = bytearray()
                if size > 0:
                    while size and (c := await read(1)):
                        cache += c
                        if c == b"\n":
                            break
                        size -= 1
                else:
                    while c := await read(1):
                        cache += c
                        if c == b"\n":
                            break
                return bytes(cache)
        if size > 0:
            size -= buf_size
        try:
            data = await readline(size)
        except:
            self.calibrate()
            raise
        buf_view = self._buf_view
        BUFSIZE = buffer_length(buf_view)
        length = buffer_length(data)
        prev_data = buf_view[buf_pos:buf_stop].tobytes()
        self._pos += buffer_length(prev_data) + length
        if BUFSIZE <= length:
            buf_view[:] = memoryview(data)[-BUFSIZE:]
            self._buf_pos = self._buf_stop = BUFSIZE
        else:
            buf_pos_stop = buf_stop + length
            if buf_pos_stop <= BUFSIZE:
                buf_view[buf_stop:buf_pos_stop] = data
                self._buf_pos = self._buf_stop = buf_pos_stop
            else:
                index = BUFSIZE - length
                buf_view[:index] = buf_view[-index:]
                buf_view[-length:] = data
                self._buf_pos = self._buf_stop = BUFSIZE
        return prev_data + data

    async def readlines(self, hint: int = -1, /) -> list[bytes]: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        readline = self.readline
        lines: list[bytes] = []
        append = lines.append
        if hint <= 0:
            while line := await readline():
                append(line)
        else:
            while hint > 0 and (line := await readline()):
                append(line)
                hint -= buffer_length(line)
        return lines

    async def seek(self, target: int, whence: int = 0, /) -> int: # type: ignore
        pos = self._pos
        if whence == 1:
            target += pos
        elif whence == 2:
            if target > 0:
                raise ValueError("target out of range: overflow")
            target = self._pos = await self._seek(target, 2)
            if target != pos:
                self.calibrate(target)
            return target
        if target < 0:
            raise ValueError("target out of range: underflow")
        if target != pos:
            buf_pos = target - pos + self._buf_pos
            if 0 <= buf_pos <= self._buf_stop:
                self._buf_pos = buf_pos
                pos = self._pos = target
            else:
                pos = self._pos = await self._seek(target, 0)
                self._buf_pos = self._buf_stop = 0
        return pos

    def tell(self, /) -> int:
        return self._pos


class AsyncTextIOWrapper(TextIOWrapper):

    def __init__(
        self, 
        /, 
        buffer: BinaryIO, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        line_buffering: bool = False, 
        write_through: bool = False, 
    ):
        super().__init__(
            buffer, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            line_buffering=line_buffering, 
            write_through=write_through, 
        )
        self.newline = newline
        self._text = ""

    def __del__(self, /):
        try:
            self.close()
        except:
            pass

    async def __aenter__(self, /) -> Self:
        return self

    async def __aexit__(self, /, *exc_info):
        await self.aclose()

    def __aiter__(self, /):
        return self

    async def __anext__(self, /):
        if line := await self.readline():
            return line
        else:
            raise StopAsyncIteration 

    def __getattr__(self, attr, /):
        return getattr(self.buffer, attr)

    @cached_property
    def _close(self, /):
        try:
            return getattr(self.buffer, "aclose")
        except AttributeError:
            return getattr(self.buffer, "close")

    @cached_property
    def _flush(self, /):
        return ensure_async(self.buffer.flush, threaded=True)

    @cached_property
    def _read(self, /):
        return ensure_async(self.buffer.read, threaded=True)

    @cached_property
    def _seek(self, /):
        return ensure_async(getattr(self.buffer, "seek"), threaded=True)

    @cached_property
    def _tell(self, /):
        return ensure_async(getattr(self.buffer, "tell"), threaded=True)

    @cached_property
    def _truncate(self, /):
        return ensure_async(self.buffer.truncate, threaded=True)

    @cached_property
    def _write(self, /):
        return ensure_async(self.buffer.write, threaded=True)

    async def aclose(self, /):
        ret = self.close()
        if isawaitable(ret):
            await ret

    def close(self, /):
        return run_async(self._close())

    async def flush(self, /):
        return await self._flush()

    async def read(self, size: None | int = -1, /) -> str: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return ""
        if size is None or size < 0:
            size = -1
        total = size
        if text := self._text:
            if 0 < size <= len(text):
                self._text = text[size:]
                return text[:size]
            if size > 0:
                size -= len(text)
        decode = getdecoder(self.encoding)
        read = self._read
        errors = self.errors or "strict"
        newline = self.newline
        data = await read(size)
        if size < 0 or buffer_length(data) < size:
            text_new, _ = decode(data, errors)
            if newline is None:
                text_new = CRE_NOT_UNIX_NEWLINES.sub("\n", text_new)
            self._text = ""
            return text + text_new

        ls_parts: list[str] = []
        add_part = ls_parts.append

        def process_part(data, errors="strict", /) -> int:
            nonlocal size
            text, n = decode(data, errors)
            add_part(text)
            if newline is None:
                if text != "\r":
                    newlines = CRE_NOT_UNIX_NEWLINES.findall(text)
                    size -= len(text) - (sum(map(len, newlines)) - len(newlines) + text.endswith("\r"))
            else:
                size -= len(text)
            return n

        cache: bytes | memoryview = memoryview(data)
        while size and buffer_length(data) == size:
            while cache:
                try:
                    cache = cache[process_part(cache):]
                    break
                except UnicodeDecodeError as e:
                    start, stop = e.start, e.end
                    if start:
                        process_part(cache[:start])
                    if e.reason in ("truncated data", "unexpected end of data"):
                        if stop == len(cache):
                            cache = cache[start:]
                            break
                    elif errors == "strict":
                        raise e
                    cache = cache[stop:]
            data = await read(size)
            cache = memoryview(bytes(cache) + data)
        if size and cache:
            process_part(cache, errors)
        text_new = "".join(ls_parts)
        if newline is None:
            text_new = CRE_NOT_UNIX_NEWLINES.sub("\n", text_new)
        text += text_new
        self._text = text[total:]
        return text[:total]

    async def readline(self, size=-1, /) -> str: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return ""
        if size is None:
            size = -1
        newline = self.newline
        if newline is None:
            newline = "\n"
        def find_stop(text: str, /) -> int:
            if newline:
                idx = text.find(newline)
                if idx > -1:
                    idx += len(newline)
                else:
                    idx = 0
            else:
                idx1 = text.find("\r")
                idx2 = text.find("\n")
                if idx1 > -1:
                    if idx2 == -1:
                        idx = idx1
                    elif idx2 - idx1 == 1:
                        idx = idx2
                    elif idx1 < idx2:
                        idx = idx1
                    else:
                        idx = idx2
                else:
                    idx = idx2
                idx += 1
            return idx
        if size > 0:
            if text := self._text:
                if stop := find_stop(text):
                    stop = min(stop, size)
                    self._text = text[stop:]
                    return text[:stop]
                elif size <= len(text):
                    self._text = text[size:]
                    return text[:size]
                self._text = ""
                size -= len(text)
            text_new = await self.read(size)
            stop = find_stop(text_new)
            if not stop or stop == len(text_new):
                return text + text_new
            self._text = text_new[stop:] + self._text
            return text + text_new[:stop]
        else:
            if text := self._text:
                if stop := find_stop(text):
                    self._text = text[stop:]
                    return text[:stop]
                self._text = ""
            ls_part: list[str] = [text]
            add_part = ls_part.append
            while text := await self.read(READ_BUFSIZE):
                if stop := find_stop(text):
                    if stop == len(text):
                        add_part(text)
                    else:
                        add_part(text[:stop])
                        self._text = text[stop:] + self._text
                    break
                else:
                    add_part(text)
            return "".join(ls_part)

    async def readlines(self, hint=-1, /) -> list[str]: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        readline = self.readline
        lines: list[str] = []
        append = lines.append
        if hint <= 0:
            while line := await readline():
                append(line)
        else:
            while hint > 0 and (line := await readline()):
                append(line)
                hint -= len(line)
        return lines

    def reconfigure(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        line_buffering: None | bool = None, 
        write_through: None | bool = None, 
    ):
        super().reconfigure(
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            line_buffering=line_buffering, 
            write_through=write_through, 
        )
        self.newline = newline

    async def seek(self, target: int, whence: int = 0, /) -> int: # type: ignore
        pos = self.tell()
        cur = await self._seek(target, whence)
        if cur != pos:
            self._text = ""
        return cur

    def tell(self, /) -> int:
        return self._tell()

    async def truncate(self, pos: None | int = None, /) -> int: # type: ignore
        return await self._truncate(pos)

    async def write(self, text: str, /) -> int: # type: ignore
        if newline := self.newline:
            text.replace("\n", newline)
        data = bytes(text, self.encoding, self.errors or "strict")
        if self.tell():
            if bom := get_bom(self.encoding):
                data.removeprefix(bom)
        await self._write(data)
        if self.write_through or self.line_buffering and ("\n" in text or "\r" in text):
            await self.flush()
        return len(text)

    async def writelines(self, lines: Iterable[str], /): # type: ignore
        write = self.write
        for line in lines:
            await write(line)


def get_bom(encoding: str, /) -> bytes:
    """get BOM (byte order mark) of the encoding
    """
    bom, _ = getencoder(encoding)("")
    return bom


def buffer_length(b: Buffer, /) -> int:
    try:
        return len(b) # type: ignore
    except:
        return len(memoryview(b))


def bio_chunk_iter(
    bio: SupportsRead[Buffer] | SupportsReadinto | Callable[[int], Buffer], 
    /, 
    size: int = -1, 
    chunksize: int = READ_BUFSIZE, 
    can_buffer: bool = False, 
    callback: None | Callable[[int], Any] = None, 
) -> Iterator[Buffer]:
    use_readinto = False
    if callable(bio):
        read = bio
    elif can_buffer and isinstance(bio, SupportsReadinto):
        readinto = bio.readinto
        use_readinto = True
    elif isinstance(bio, SupportsRead):
        read = bio.read
    else:
        readinto = bio.readinto
        def read(_):
            buf = bytearray(chunksize)
            length = readinto(buf)
            if length == chunksize:
                return buf
            return buf[:length]
    if not callable(callback):
        callback = None
    if use_readinto:
        buf = bytearray(chunksize)
        if size > 0:
            while size:
                if size < chunksize:
                    del buf[size:]
                length = readinto(buf)
                if callback:
                    callback(length)
                if length < buffer_length(buf):
                    del buf[length:]
                    yield buf
                    break
                yield buf
                size -= length
        else:
            while (length := readinto(buf)):
                if callback:
                    callback(length)
                if length < chunksize:
                    del buf[length:]
                    yield buf
                    break
                yield buf
    else:
        if size > 0:
            while size:
                readsize = min(chunksize, size)
                chunk = read(readsize)
                length = buffer_length(chunk)
                if callback:
                    callback(length)
                yield chunk
                if length < readsize:
                    break
                size -= length
        elif size < 0:
            while (chunk := read(chunksize)):
                if callback:
                    callback(buffer_length(chunk))
                yield chunk


async def bio_chunk_async_iter(
    bio: SupportsRead[Buffer] | SupportsRead[Awaitable[Buffer]] | SupportsReadinto | Callable[[int], Buffer] | Callable[[int], Awaitable[Buffer]], 
    /, 
    size: int = -1, 
    chunksize: int = READ_BUFSIZE, 
    can_buffer: bool = False, 
    callback: None | Callable[[int], Any] = None, 
) -> AsyncIterator[Buffer]:
    use_readinto = False
    if callable(bio):
        read: Callable[[int], Awaitable[Buffer]] = ensure_async(bio, threaded=True)
    elif can_buffer and isinstance(bio, SupportsReadinto):
        readinto = ensure_async(bio.readinto, threaded=True)
        use_readinto = True
    elif isinstance(bio, SupportsRead):
        read = ensure_async(bio.read, threaded=True)
    else:
        readinto = ensure_async(bio.readinto, threaded=True)
        async def read(_):
            buf = bytearray(chunksize)
            length = await readinto(buf)
            if length == chunksize:
                return buf
            return buf[:length]
    callback = ensure_async(callback) if callable(callback) else None
    if use_readinto:
        buf = bytearray(chunksize)
        if size > 0:
            while size:
                if size < chunksize:
                    del buf[size:]
                length = await readinto(buf)
                if callback:
                    await callback(length)
                if length < buffer_length(buf):
                    del buf[length:]
                    yield buf
                    break
                yield buf
                size -= length
        else:
            while (length := (await readinto(buf))):
                if callback:
                    await callback(length)
                if length < chunksize:
                    del buf[length:]
                    yield buf
                    break
                yield buf
    else:
        if size > 0:
            while size:
                readsize = min(chunksize, size)
                chunk = await read(readsize)
                length = buffer_length(chunk)
                if callback:
                    await callback(length)
                yield chunk
                if length < readsize:
                    break
                size -= readsize
        elif size < 0:
            while (chunk := (await read(chunksize))):
                if callback:
                    await callback(buffer_length(chunk))
                yield chunk


def bio_skip_iter(
    bio: SupportsRead[Buffer] | SupportsReadinto | Callable[[int], Buffer], 
    /, 
    size: int = -1, 
    chunksize: int = READ_BUFSIZE, 
    callback: None | Callable[[int], Any] = None, 
) -> Iterator[int]:
    if size == 0:
        return
    if not callable(callback):
        callback = None
    try:
        seek = getattr(bio, "seek")
        curpos = seek(0, 1)
        if size > 0:
            length = seek(size, 1) - curpos
        else:
            length = seek(0, 2) - curpos
    except Exception:
        if chunksize <= 0:
            chunksize = READ_BUFSIZE
        if callable(bio):
            read = bio
        elif hasattr(bio, "readinto"):
            readinto = bio.readinto
            buf = bytearray(chunksize)
            if size > 0:
                while size >= chunksize:
                    length = readinto(buf)
                    if callback:
                        callback(length)
                    yield length
                    if length < chunksize:
                        break
                    size -= chunksize
                else:
                    if size:
                        del buf[size:]
                        length = readinto(buf)
                        if callback:
                            callback(length)
                        yield length
            else:
                while (length := readinto(buf)):
                    if callback:
                        callback(length)
                    yield length
            return
        else:
            read = bio.read
        if size > 0:
            while size:
                readsize = min(chunksize, size)
                length = buffer_length(read(readsize))
                if callback:
                    callback(length)
                yield length
                if length < readsize:
                    break
                size -= readsize
        else:
            while (length := buffer_length(read(chunksize))):
                if callback:
                    callback(length)
                yield length
    else:
        if callback:
            callback(length)
        yield length


async def bio_skip_async_iter(
    bio: SupportsRead[Buffer] | SupportsRead[Awaitable[Buffer]] | SupportsReadinto | Callable[[int], Buffer] | Callable[[int], Awaitable[Buffer]], 
    /, 
    size: int = -1, 
    chunksize: int = READ_BUFSIZE, 
    callback: None | Callable[[int], Any] = None, 
) -> AsyncIterator[int]:
    if size == 0:
        return
    callback = ensure_async(callback) if callable(callback) else None
    length: int
    try:
        seek = ensure_async(getattr(bio, "seek"), threaded=True)
        curpos = await seek(0, 1)
        if size > 0:
            length = (await seek(size, 1)) - curpos
        else:
            length = (await seek(0, 2)) - curpos
    except Exception:
        if chunksize <= 0:
            chunksize = READ_BUFSIZE
        if callable(bio):
            read: Callable[[int], Awaitable[Buffer]] = ensure_async(bio, threaded=True)
        elif hasattr(bio, "readinto"):
            readinto = ensure_async(bio.readinto, threaded=True)
            buf = bytearray(chunksize)
            if size > 0:
                while size >= chunksize:
                    length = await readinto(buf)
                    if callback:
                        await callback(length)
                    yield length
                    if length < chunksize:
                        break
                    size -= chunksize
                else:
                    if size:
                        del buf[size:]
                        length = await readinto(buf)
                        if callback:
                            await callback(length)
                        yield length
            else:
                while (length := (await readinto(buf))):
                    if callback:
                        await callback(length)
                    yield length
        else:
            read = ensure_async(bio.read, threaded=True)
        if size > 0:
            while size:
                readsize = min(chunksize, size)
                length = buffer_length(await read(readsize))
                if callback:
                    await callback(length)
                yield length
                if length < readsize:
                    break
                size -= readsize
        else:
            while (length := buffer_length(await read(chunksize))):
                if callback:
                    await callback(length)
                yield length
    else:
        if callback:
            await callback(length)
        yield length


def bytes_iter(
    it: Iterable[Buffer], 
    /, 
    size: int = -1, 
    callback: None | Callable[[int], Any] = None, 
) -> Iterator[Buffer]:
    it = iter(it)
    if size < 0:
        yield from it
        return
    elif size == 0:
        return
    for b in it:
        l = buffer_length(b)
        if l <= size:
            yield b
            if callback is not None:
                callback(l)
            if l < size:
                size -= l
            else:
                break
        else:
            yield memoryview(b)[:size]
            if callback is not None:
                callback(size)
            break


async def bytes_async_iter(
    it: Iterable[Buffer] | AsyncIterable[Buffer], 
    /, 
    size: int = -1, 
    callback: None | Callable[[int], Any] = None, 
    threaded: bool = False, 
) -> AsyncIterator[Buffer]:
    it = aiter(ensure_aiter(it, threaded=threaded))
    if size < 0:
        async for chunk in it:
            yield chunk
        return
    elif size == 0:
        return
    callback = ensure_async(callback) if callable(callback) else None
    async for b in it:
        l = buffer_length(b)
        if l <= size:
            yield b
            if callback is not None:
                await callback(l)
            if l < size:
                size -= l
            else:
                break
        else:
            yield memoryview(b)[:size]
            if callback is not None:
                await callback(size)
            break


def bytes_iter_skip(
    it: Iterable[Buffer], 
    /, 
    size: int = -1, 
    callback: None | Callable[[int], Any] = None, 
) -> Iterator[Buffer]:
    it = iter(it)
    if size == 0:
        return it
    if not callable(callback):
        callback = None
    m: memoryview
    for m in map(memoryview, it): # type: ignore
        l = buffer_length(m)
        if callback:
            callback(min(l, size))
        if l == size:
            return it
        elif l > size:
            return chain((m[size:],), it)
        else:
            size -= l
    return iter(())


async def bytes_async_iter_skip(
    it: Iterable[Buffer] | AsyncIterable[Buffer], 
    /, 
    size: int = -1, 
    callback: None | Callable[[int], Any] = None, 
    threaded: bool = False, 
) -> AsyncIterator[Buffer]:
    it = aiter(ensure_aiter(it, threaded=threaded))
    if size == 0:
        return it
    callback = ensure_async(callback) if callable(callback) else None
    async for b in it:
        m = memoryview(b)
        l = buffer_length(m)
        if callback:
            await callback(min(l, size))
        if l == size:
            return it
        elif l > size:
            return async_chain((m[size:],), it)
        else:
            size -= l
    async def make_iter():
        if False:
            yield
    return make_iter()


def bytes_iter_to_reader(
    it: Iterable[Buffer], 
    /, 
) -> SupportsRead[bytearray]:
    getnext = iter(it).__next__
    pos = 0
    at_end = False
    unconsumed: bytearray = bytearray()
    lock = Lock()
    def __del__():
        try:
            close()
        except:
            pass
    def close():
        nonlocal at_end
        getattr(it, "close")()
        at_end = True
    def peek(n: int = 0, /) -> bytearray:
        if n <= 0:
            return unconsumed[:]
        return unconsumed[:n]
    def read(n: None | int = -1, /) -> bytearray:
        nonlocal pos, at_end, unconsumed
        if at_end or n == 0:
            return bytearray()
        if n is None:
            n = -1
        with lock:
            try:
                if n < 0:
                    while True:
                        unconsumed += getnext()
                else:
                    while n > buffer_length(unconsumed):
                        unconsumed += getnext()
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += buffer_length(b)
                    return b
            except StopIteration:
                at_end = True
                b = unconsumed[:]
                del unconsumed[:]
                pos += buffer_length(b)
                return b
    def readinto(buf, /) -> int:
        nonlocal pos, at_end, unconsumed
        if at_end or not (bufsize := buffer_length(buf)):
            return 0
        with lock:
            if n := buffer_length(unconsumed):
                if bufsize <= n:
                    buf[:], unconsumed = unconsumed[:bufsize], unconsumed[bufsize:]
                    pos += bufsize
                    return bufsize
                buf[:n] = unconsumed
                pos += n
                del unconsumed[:]
            try:
                while True:
                    if b := memoryview(getnext()):
                        m = n + len(b)
                        if m >= bufsize:
                            delta = bufsize - n
                            buf[n:] = b[:delta]
                            unconsumed += b[delta:]
                            pos += delta
                            return bufsize
                        else:
                            buf[n:m] = b
                            pos += len(b)
                            n = m
            except StopIteration:
                at_end = True
                return n
    def readline(n: None | int = -1, /) -> bytearray:
        nonlocal pos, unconsumed, at_end
        if at_end or n == 0:
            return bytearray()
        if n is None:
            n = -1
        with lock:
            if unconsumed:
                # search for b"\n"
                if (idx := unconsumed.find(49)) > -1:
                    idx += 1
                    if n < 0 or idx <= n:
                        b, unconsumed = unconsumed[:idx], unconsumed[idx:]
                        pos += idx
                        return b
                if n > 0 and buffer_length(unconsumed) >= n:
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += n
                    return b
            try:
                start = buffer_length(unconsumed)
                while True:
                    r = getnext()
                    if not r:
                        continue
                    unconsumed += r
                    if (idx := unconsumed.find(49, start)) > -1:
                        idx += 1
                        if n < 0 or idx <= n:
                            b, unconsumed = unconsumed[:idx], unconsumed[idx:]
                            pos += idx
                            return b
                    start = buffer_length(unconsumed)
                    if n > 0 and start >= n:
                        b, unconsumed = unconsumed[:n], unconsumed[n:]
                        pos += n
                        return b
            except StopIteration:
                at_end = True
                if unconsumed:
                    b = unconsumed[:]
                    del unconsumed[:]
                    pos += buffer_length(b)
                    return b
                raise
    def readlines(hint: int = -1, /) -> list[bytearray]:
        if at_end:
            return []
        lines: list[bytearray] = []
        append = lines.append
        if hint <= 0:
            while line := readline():
                append(line)
        else:
            while hint > 0 and (line := readline()):
                append(line)
                hint -= buffer_length(line)
        return lines
    def __next__() -> bytearray:
        if at_end or not (b := readline()):
            raise StopIteration
        return b
    reprs = f"<reader for {it!r}>"
    return type("reader", (VirtualBufferedReader,), {
        "__del__": staticmethod(__del__), 
        "__getattr__": staticmethod(lambda attr, /: getattr(it, attr)), 
        "__iter__": lambda self: self, 
        "__next__": staticmethod(__next__), 
        "__repr__": staticmethod(lambda: reprs), 
        "close": staticmethod(close), 
        "closed": funcproperty(staticmethod(lambda: at_end)), 
        "peek": staticmethod(peek), 
        "read": staticmethod(read), 
        "readinto": staticmethod(readinto), 
        "readline": staticmethod(readline), 
        "readlines": staticmethod(readlines), 
        "readable": staticmethod(lambda: True), 
        "seekable": staticmethod(lambda: False), 
        "tell": staticmethod(lambda: pos), 
    })()


def bytes_iter_to_async_reader(
    it: Iterable[Buffer] | AsyncIterable[Buffer], 
    /, 
    threaded: bool = True, 
) -> SupportsRead[Awaitable[bytearray]]:
    if isinstance(it, AsyncIterable):
        getnext = aiter(it).__anext__
    else:
        getnext = ensure_async(iter(it).__next__, threaded=threaded)
    pos = 0
    at_end = False
    unconsumed: bytearray = bytearray()
    lock = AsyncLock()
    def __del__():
        try:
            close()
        except:
            pass
    def close():
        run_async(aclose())
    async def aclose():
        nonlocal at_end
        try:
            method = getattr(it, "aclose")
        except AttributeError:
            method = getattr(it, "close")
        ret = method()
        if isawaitable(ret):
            await ret
        at_end = True
    def peek(n: int = 0, /) -> bytearray:
        if n <= 0:
            return unconsumed[:]
        return unconsumed[:n]
    async def read(n: None | int = -1, /) -> bytearray:
        nonlocal pos, at_end, unconsumed
        if at_end or n == 0:
            return bytearray()
        if n is None:
            n = -1
        async with lock:
            try:
                if n < 0:
                    while True:
                        unconsumed += await getnext()
                else:
                    while n > buffer_length(unconsumed):
                        unconsumed += await getnext()
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += buffer_length(b)
                    return b
            except (StopIteration, StopAsyncIteration):
                at_end = True
                b = unconsumed[:]
                del unconsumed[:]
                pos += buffer_length(b)
                return b
    async def readinto(buf, /) -> int:
        nonlocal pos, at_end, unconsumed
        if at_end or not (bufsize := buffer_length(buf)):
            return 0
        async with lock:
            if n := buffer_length(unconsumed):
                if bufsize <= n:
                    buf[:], unconsumed = unconsumed[:bufsize], unconsumed[bufsize:]
                    pos += bufsize
                    return bufsize
                buf[:n] = unconsumed
                pos += n
                del unconsumed[:]
            try:
                while True:
                    if b := memoryview(await getnext()):
                        m = n + len(b)
                        if m >= bufsize:
                            delta = bufsize - n
                            buf[n:] = b[:delta]
                            unconsumed += b[delta:]
                            pos += delta
                            return bufsize
                        else:
                            buf[n:m] = b
                            pos += len(b)
                            n = m
            except (StopIteration, StopAsyncIteration):
                at_end = True
                return n
    async def readline(n: None | int = -1, /) -> bytearray:
        nonlocal pos, unconsumed, at_end
        if at_end or n == 0:
            return bytearray()
        if n is None:
            n = -1
        async with lock:
            if unconsumed:
                # search for b"\n"
                if (idx := unconsumed.find(49)) > -1:
                    idx += 1
                    if n < 0 or idx <= n:
                        b, unconsumed = unconsumed[:idx], unconsumed[idx:]
                        pos += idx
                        return b
                if n > 0 and buffer_length(unconsumed) >= n:
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += n
                    return b
            try:
                start = buffer_length(unconsumed)
                while True:
                    r = await getnext()
                    if not r:
                        continue
                    unconsumed += r
                    if (idx := unconsumed.find(49, start)) > -1:
                        idx += 1
                        if n < 0 or idx <= n:
                            b, unconsumed = unconsumed[:idx], unconsumed[idx:]
                            pos += idx
                            return b
                    start = buffer_length(unconsumed)
                    if n > 0 and start >= n:
                        b, unconsumed = unconsumed[:n], unconsumed[n:]
                        pos += n
                        return b
            except (StopIteration, StopAsyncIteration):
                at_end = True
                if unconsumed:
                    b = unconsumed[:]
                    del unconsumed[:]
                    pos += buffer_length(b)
                    return b
                raise
    async def readlines(hint: int = -1, /) -> list[bytearray]:
        if at_end:
            return []
        if hint is None:
            hint = -1
        lines: list[bytearray] = []
        append = lines.append
        async with lock:
            if hint <= 0:
                while line := await readline():
                    append(line)
            else:
                while hint > 0 and (line := await readline()):
                    append(line)
                    hint -= buffer_length(line)
        return lines
    async def __anext__() -> bytearray:
        if at_end or not (b := await readline()):
            raise StopAsyncIteration
        return b
    reprs = f"<async_reader for {it!r}>"
    return type("async_reader", (VirtualBufferedReader,), {
        "__del__": staticmethod(__del__), 
        "__getattr__": staticmethod(lambda attr, /: getattr(it, attr)), 
        "__aiter__": lambda self: self, 
        "__anext__": staticmethod(__anext__), 
        "__repr__": staticmethod(lambda: reprs), 
        "close": staticmethod(close), 
        "aclose": staticmethod(aclose), 
        "closed": funcproperty(staticmethod(lambda: at_end)), 
        "peek": staticmethod(peek), 
        "read": staticmethod(read), 
        "readinto": staticmethod(readinto), 
        "readline": staticmethod(readline), 
        "readlines": staticmethod(readlines), 
        "readable": staticmethod(lambda: True), 
        "seekable": staticmethod(lambda: False), 
        "tell": staticmethod(lambda: pos), 
    })()


def bytes_to_chunk_iter(
    b: Buffer, 
    /, 
    chunksize: int = READ_BUFSIZE, 
) -> Iterator[memoryview]:
    m = memoryview(b)
    for i in range(0, buffer_length(m), chunksize):
        yield m[i:i+chunksize]


async def bytes_to_chunk_async_iter(
    b: Buffer, 
    /, 
    chunksize: int = READ_BUFSIZE, 
) -> AsyncIterator[memoryview]:
    m = memoryview(b)
    for i in range(0, buffer_length(m), chunksize):
        yield m[i:i+chunksize]


def bytes_ensure_part_iter(
    it: Iterable[Buffer], 
    /, 
    partsize: int = READ_BUFSIZE, 
) -> Iterator[Buffer]:
    n = partsize
    for b in it:
        m = memoryview(b)
        l = buffer_length(m)
        if l <= n:
            yield b
            if l == n:
                n = partsize
            else:
                n -= l
        else:
            yield m[:n]
            m = m[n:]
            while buffer_length(m) >= partsize:
                yield m[:partsize]
                m = m[partsize:]
            if m:
                yield m
                n = partsize - buffer_length(m)
            else:
                n = partsize


async def bytes_ensure_part_async_iter(
    it: Iterable[Buffer] | AsyncIterable[Buffer], 
    /, 
    partsize: int = READ_BUFSIZE, 
) -> AsyncIterator[Buffer]:
    n = partsize
    async for b in ensure_aiter(it):
        m = memoryview(b)
        l = buffer_length(m)
        if l <= n:
            yield b
            if l == n:
                n = partsize
            else:
                n -= l
        else:
            yield m[:n]
            m = m[n:]
            while buffer_length(m) >= partsize:
                yield m[:partsize]
                m = m[partsize:]
            if m:
                yield m
                n = partsize - buffer_length(m)
            else:
                n = partsize


def progress_bytes_iter[**Args](
    it: Iterable[Buffer] | Callable[[], Buffer], 
    make_progress: None | Callable[Args, Any] = None, 
    /, 
    *args: Args.args, 
    **kwds: Args.kwargs, 
) -> Iterator[Buffer]:
    update_progress: None | Callable = None
    close_progress: None | Callable = None
    if callable(it):
        it = iter(it, b"")
    if callable(make_progress):
        progress = make_progress(*args, **kwds)
        if isgenerator(progress):
            next(progress)
            update_progress = progress.send
            close_progress = progress.close
        else:
            update_progress = progress
            close_progress = getattr(progress, "close", None)
    try:
        if callable(update_progress):
            for chunk in it:
                yield chunk
                update_progress(buffer_length(chunk))
        else:
            for chunk in it:
                yield chunk
    finally:
        if callable(close_progress):
            close_progress()


async def progress_bytes_async_iter[**Args](
    it: Iterable[Buffer] | AsyncIterable[Buffer] | Callable[[], Buffer] | Callable[[], Awaitable[Buffer]], 
    make_progress: None | Callable[Args, Any] = None, 
    /, 
    *args: Args.args, 
    **kwds: Args.kwargs, 
) -> AsyncIterator[Buffer]:
    update_progress: None | Callable = None
    close_progress: None | Callable = None
    if callable(it):
        async def wrapiter(it) -> AsyncIterator[Buffer]:
            while True:
                chunk = it()
                if isawaitable(chunk):
                    chunk = await chunk
                if not chunk:
                    break
                yield chunk
        it = cast(AsyncIterable[Buffer], wrapiter(it))
    if callable(make_progress):
        progress = make_progress(*args, **kwds)
        if isgenerator(progress):
            await ensure_async(next)(progress)
            update_progress = progress.send
            close_progress = progress.close
        elif isasyncgen(progress):
            await anext(progress)
            update_progress = progress.asend
            close_progress = progress.aclose
        else:
            update_progress = progress
            close_progress = getattr(progress, "close", None)
    try:
        it = ensure_aiter(it)
        if callable(update_progress):
            update_progress = ensure_async(update_progress)
            async for chunk in it:
                yield chunk
                await update_progress(buffer_length(chunk))
        else:
            async for chunk in it:
                yield chunk
    finally:
        if callable(close_progress):
            await ensure_async(close_progress)()


def copyfileobj(
    fsrc, 
    fdst: SupportsWrite[Buffer], 
    /, 
    chunksize: int = READ_BUFSIZE, 
):
    if chunksize <= 0:
        chunksize = READ_BUFSIZE
    fdst_write = fdst.write
    fsrc_read = getattr(fsrc, "read", None)
    fsrc_readinto = getattr(fsrc, "readinto", None)
    if callable(fsrc_readinto):
        buf = bytearray(chunksize)
        view = memoryview(buf)
        while size := fsrc_readinto(buf):
            fdst_write(view[:size])
    elif callable(fsrc_read):
        while chunk := fsrc_read(chunksize):
            fdst_write(chunk)
    else:
        for chunk in fsrc:
            if chunk:
                fdst_write(chunk)


async def copyfileobj_async(
    fsrc, 
    fdst: SupportsWrite[Buffer], 
    /, 
    chunksize: int = READ_BUFSIZE, 
    threaded: bool = True, 
):
    if chunksize <= 0:
        chunksize = READ_BUFSIZE
    fdst_write = ensure_async(fdst.write, threaded=threaded)
    fsrc_read = getattr(fsrc, "read", None)
    fsrc_readinto = getattr(fsrc, "readinto", None)
    if callable(fsrc_readinto):
        fsrc_readinto = ensure_async(fsrc_readinto, threaded=threaded)
        buf = bytearray(chunksize)
        view = memoryview(buf)
        while size := await fsrc_readinto(buf):
            await fdst_write(view[:size])
    elif callable(fsrc_read):
        fsrc_read = ensure_async(fsrc_read, threaded=threaded)
        while chunk := await fsrc_read(chunksize):
            await fdst_write(chunk)
    else:
        chunkiter = ensure_aiter(fsrc, threaded=threaded)
        async for chunk in chunkiter:
            if chunk:
                await fdst_write(chunk)


def bound_bytes_reader(
    file: SupportsRead[Buffer], 
    size: int = -1, 
) -> SupportsRead[Buffer]:
    if size < 0:
        return file
    f_read = file.read
    f_readinto = getattr(file, "readinto", None)
    class Reader:
        @staticmethod
        def read(n: None | int = -1, /) -> Buffer:
            nonlocal size
            if n == 0 or size <= 0:
                return b""
            elif n is None or n < 0:
                data = f_read(size)
                size = 0
            else:
                data = f_read(min(size, n))
                size -= buffer_length(data)
            return data
        @staticmethod
        def readinto(buffer, /) -> int:
            nonlocal size
            if f_readinto is None:
                raise NotImplementedError("readinto")
            if size > 0:
                n = f_readinto(memoryview(buffer)[:size])
                size -= n
                return n
            return 0
    return Reader()


def bound_async_bytes_reader(
    file: SupportsRead[Buffer] | SupportsRead[Awaitable[Buffer]], 
    size: int = -1, 
) -> SupportsRead[Awaitable[Buffer]]:
    f_read: Callable[[int], Awaitable[Buffer]] = ensure_async(file.read, threaded=True)
    f_readinto = getattr(file, "readinto", None)
    if f_readinto is not None:
        f_readinto = ensure_async(f_readinto, threaded=True)
    at_end = False
    class Reader:
        @staticmethod
        async def read(n: None | int = -1, /) -> Buffer:
            nonlocal size
            if n == 0 or size <= 0:
                return b""
            elif n is None or n < 0:
                data = await f_read(size)
                size = 0
            else:
                data = await f_read(min(size, n))
                size -= buffer_length(data)
            return data
        @staticmethod
        async def readinto(buffer, /) -> int:
            nonlocal size
            if f_readinto is None:
                raise NotImplementedError("readinto")
            if size > 0:
                n = await f_readinto(memoryview(buffer)[:size])
                size -= n
                return n
            return 0
    return Reader()

