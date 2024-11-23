#!/usr/bin/env python3
# encoding: utf-8

# TODO: 实现一种 memoryview，可以作为环形缓冲区使用
# TODO: 使用 codecs.iterdecode 来避免解码过程中的一些重复操作
# TODO: AsyncTextIOWrapper 的 read 和 readline 算法效率不高，因为会反复创建二进制对象，如果可以复用一段或者几段(内存块组)内存，则可以大大增加效率，还可以引入环形缓冲区（使用长度限定的 bytearray，之后所有操作在 memoryview 上进行，根据当前的可用区块开返回 memoryview），以减少内存分配的开销
# TODO: AsyncTextIOWrapper.readline 有大量的字符串拼接操作，效率极低，需用 str.joins 方法优化

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 2, 5)
__all__ = [
    "Buffer", "SupportsRead", "SupportsReadinto", "SupportsWrite", "SupportsSeek", 
    "AsyncBufferedReader", "AsyncTextIOWrapper", 
    "bio_chunk_iter", "bio_chunk_async_iter", 
    "bio_skip_iter", "bio_skip_async_iter", 
    "bytes_iter", "bytes_async_iter", 
    "bytes_iter_skip", "bytes_async_iter_skip", 
    "bytes_iter_to_reader", "bytes_iter_to_async_reader", 
    "bytes_to_chunk_iter", "bytes_to_chunk_async_iter", 
    "bytes_ensure_part_iter", "bytes_ensure_part_async_iter", 
    "progress_bytes_iter", "progress_bytes_async_iter", 
    "copyfileobj", "copyfileobj_async", 
]

from asyncio import to_thread, Lock as AsyncLock
from collections.abc import Awaitable, AsyncIterable, AsyncIterator, Callable, Iterable, Iterator, Sized
from functools import update_wrapper
from io import BufferedIOBase, BufferedReader, BytesIO, RawIOBase, TextIOWrapper
from inspect import isawaitable, iscoroutinefunction, isasyncgen, isgenerator
from itertools import chain
from os import linesep
from re import compile as re_compile
from shutil import COPY_BUFSIZE # type: ignore
from threading import Lock
from typing import cast, runtime_checkable, Any, BinaryIO, ParamSpec, Protocol, Self, TypeVar

try:
    from collections.abc import Buffer # type: ignore
except ImportError:
    from _ctypes import _SimpleCData
    from array import array

    @runtime_checkable
    class Buffer(Protocol): # type: ignore
        def __buffer__(self, flags: int, /) -> memoryview:
            pass

    Buffer.register(bytes)
    Buffer.register(bytearray)
    Buffer.register(memoryview)
    Buffer.register(_SimpleCData)
    Buffer.register(array)

from asynctools import async_chain, ensure_async, ensure_aiter, run_async
from property import funcproperty


Args = ParamSpec("Args")
_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)

@BufferedIOBase.register
class VirtualBufferedReader:
    def __new__(cls, /, *a, **k):
        if cls is __class__: # type: ignore
            raise TypeError("not allowed to create instances")
        return super().__new__(cls, *a, **k)

CRE_NOT_UNIX_NEWLINES_sub = re_compile("\r\n|\r").sub


@runtime_checkable
class SupportsRead(Protocol[_T_co]):
    def read(self, /, __length: int = ...) -> _T_co: ...


@runtime_checkable
class SupportsReadinto(Protocol):
    def readinto(self, /, buf: Buffer = ...) -> int: ...


@runtime_checkable
class SupportsWrite(Protocol[_T_contra]):
    def write(self, /, __s: _T_contra) -> object: ...


@runtime_checkable
class SupportsSeek(Protocol):
    def seek(self, /, __offset: int, __whence: int = 0) -> int: ...


# TODO: 一些特定编码的 bom 用字典写死，编码名可以规范化，用 codecs.lookup(encoding).name
def get_bom(encoding: str) -> bytes:
    code = memoryview(bytes("a", encoding))
    if len(code) == 1:
        return b""
    for i in range(1, len(code)):
        try:
            str(code[:i], encoding)
            return code[:i].tobytes()
        except UnicodeDecodeError:
            pass
    raise UnicodeError


class AsyncBufferedReader(BufferedReader):

    def __init__(
        self, 
        /, 
        raw: RawIOBase, 
        buffer_size: int = 8192, 
    ):
        super().__init__(raw, min(buffer_size, 1))
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
        raw = self.raw
        try:
            ret = getattr(raw, "aclose")()
        except (AttributeError, TypeError):
            ret = getattr(raw, "close")()
        if isawaitable(ret):
            await ret

    def close(self, /):
        raw = self.raw
        try:
            ret = getattr(raw, "aclose")()
        except (AttributeError, TypeError):
            ret = getattr(raw, "close")()
        if isawaitable(ret):
            run_async(ret)

    async def flush(self, /):
        return await ensure_async(self.raw.flush, threaded=True)()

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
        BUFSIZE = len(buf_view)
        read = ensure_async(self.raw.read, threaded=True)
        buffer = bytearray(buf_view[buf_pos:buf_stop])
        try:
            while data := await read(BUFSIZE):
                buffer += data
                length = len(data)
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
            data = await ensure_async(self.raw.read, threaded=True)(size)
        except:
            self.calibrate()
            raise
        prev_data = buf_view[buf_pos:buf_stop].tobytes()
        if data:
            BUFSIZE = len(buf_view)
            length = len(data)
            self._pos += len(prev_data) + length
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
        size = len(buffer)
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
            readinto = ensure_async(self.raw.readinto, threaded=True)
        except AttributeError:
            read = ensure_async(self.raw.read, threaded=True)
            async def readinto(buffer, /) -> int:
                data = await read(len(buffer))
                if data:
                    size = len(data)
                    buffer[:size] = data
                    return size
                else:
                    return 0
        BUFSIZE = len(buf_view)
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
                        index = len(part1)
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
        size = len(buffer)
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
            readinto = ensure_async(self.raw.readinto, threaded=True)
        except AttributeError:
            read = ensure_async(self.raw.read, threaded=True)
            async def readinto(buffer, /) -> int:
                data = await read(len(buffer))
                if data:
                    size = len(data)
                    buffer[:size] = data
                    return size
                else:
                    return 0
        BUFSIZE = len(buf_view)
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
            BUFSIZE = len(buf_view)
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
            readline = ensure_async(self.raw.readline, threaded=True)
        except AttributeError:
            async def readline(size: None | int = -1, /) -> bytes:
                if size == 0:
                    return b""
                if size is None:
                    size = -1
                read = ensure_async(self.raw.read, threaded=True)
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
        BUFSIZE = len(buf_view)
        length = len(data)
        prev_data = buf_view[buf_pos:buf_stop].tobytes()
        self._pos += len(prev_data) + length
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
                hint -= len(line)
        return lines

    async def seek(self, target: int, whence: int = 0, /) -> int: # type: ignore
        pos = self._pos
        if whence == 1:
            target += pos
        elif whence == 2:
            if target > 0:
                raise ValueError("target out of range: overflow")
            target = self._pos = await ensure_async(self.raw.seek, threaded=True)(target, 2)
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
                pos = self._pos = await ensure_async(self.raw.seek, threaded=True)(target, 0)
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
        self._bom = get_bom(self.encoding)

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

    async def aclose(self, /):
        buffer = self.buffer
        try:
            ret = getattr(buffer, "aclose")()
        except (AttributeError, TypeError):
            ret = getattr(buffer, "close")()
        if isawaitable(ret):
            await ret

    def close(self, /):
        buffer = self.buffer
        try:
            ret = getattr(buffer, "aclose")()
        except (AttributeError, TypeError):
            ret = getattr(buffer, "close")()
        if isawaitable(ret):
            run_async(ret)

    async def flush(self, /):
        return await ensure_async(self.buffer.flush, threaded=True)()

    async def read(self, size: None | int = -1, /) -> str: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return ""
        if size is None:
            size = -1
        read = ensure_async(self.buffer.read, threaded=True)
        encoding = self.encoding
        errors = self.errors or "strict"
        newline = self.newline
        if size < 0:
            data = await read(-1)
        else:
            data = await read(size)
        if not isinstance(data, Sized):
            data = memoryview(data)
        if size < 0 or len(cast(Sized, data)) < size:
            text = str(data, encoding, errors)
            if newline is None:
                text = CRE_NOT_UNIX_NEWLINES_sub("\n", text)
            return text

        def process_part(data, errors="strict", /) -> int:
            text = str(data, encoding, errors)
            if newline is None:
                text = CRE_NOT_UNIX_NEWLINES_sub("\n", text)
            add_part(text)
            return len(text)

        ls_parts: list[str] = []
        add_part = ls_parts.append
        if not isinstance(data, Sized):
            data = memoryview(data)
        cache = bytes(data)
        while size and len(cast(Sized, data)) == size:
            while cache:
                try:
                    size -= process_part(cache)
                    cache = b""
                except UnicodeDecodeError as e:
                    start, stop = e.start, e.end
                    if start:
                        size -= process_part(cache[:start])
                    if e.reason == "truncated data":
                        if stop == len(cache):
                            cache = cache[start:]
                            break
                        else:
                            while stop < len(cache):
                                stop += 1
                                try:
                                    size -= process_part(cache[start:stop])
                                    cache = cache[stop:]
                                    break_this_loop = True
                                    break
                                except UnicodeDecodeError as exc:
                                    e = exc
                                    if e.reason != "truncated data":
                                        break
                                    if stop == len(cache):
                                        cache = cache[start:]
                                        break_this_loop = True
                                        break
                            if break_this_loop:
                                break
                    elif e.reason == "unexpected end of data" and stop == len(cache):
                        cache = cache[start:]
                        break
                    if errors == "strict":
                        raise e
                    size -= process_part(cache[start:stop], errors)
                    cache = cache[stop:]
            data = await read(size)
            if not isinstance(data, Sized):
                data = memoryview(data)
            cache += data
        if cache:
            process_part(cache, errors)
        return "".join(ls_parts)

    async def readline(self, size=-1, /) -> str: # type: ignore
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return ""
        if size is None:
            size = -1
        read = ensure_async(self.buffer.read, threaded=True)
        seek = self.seek
        encoding = self.encoding
        errors = self.errors or "strict"
        newline = self.newline
        peek = getattr(self.buffer, "peek", None)
        if not callable(peek):
            peek = None
        if newline:
            sepb = bytes(newline, encoding)
            if bom := self._bom:
                sepb = sepb.removeprefix(bom)
        else:
            crb = bytes("\r", encoding)
            lfb = bytes("\n", encoding)
            if bom := self._bom:
                crb = crb.removeprefix(bom)
                lfb = lfb.removeprefix(bom)
            lfb_len = len(lfb)
        buf = bytearray()
        text = ""
        reach_end = False
        if size < 0:
            while True:
                if peek is None:
                    while c := await read(1):
                        buf += c
                        if newline:
                            if buf.endswith(sepb):
                                break
                        elif buf.endswith(lfb):
                            break
                        elif buf.endswith(crb):
                            peek_maybe_lfb = await read(lfb_len)
                            if not isinstance(peek_maybe_lfb, Sized):
                                peek_maybe_lfb = memoryview(peek_maybe_lfb)
                            if peek_maybe_lfb == lfb:
                                buf += lfb
                            elif peek_maybe_lfb:
                                # TODO: 这是一个提前量，未必需要立即往回 seek，因为转换为 str 后可能尾部不是 \r（因为可以和前面的符号结合），所以这个可能可以被复用，如果需要优化，可以在程序结束时的 finally 部分最终执行 seek（可能最终字符被消耗所以不需要 seek）
                                o = len(cast(Sized, peek_maybe_lfb))
                                await seek(-o, 1)
                                if o < lfb_len:
                                    reach_end = True
                            break
                    else:
                        reach_end = True
                else:
                    while True:
                        buf_stop = len(buf)
                        peek_b = peek()
                        if peek_b:
                            buf += peek_b
                        if newline:
                            if (idx := buf.find(sepb)) > -1:
                                idx += len(sepb)
                                await read(idx - buf_stop)
                                del buf[idx:]
                                break
                        elif (idx := buf.find(lfb)) > -1:
                            idx += len(lfb)
                            await read(idx - buf_stop)
                            del buf[idx:]
                            break
                        elif (idx := buf.find(crb)) > -1:
                            idx += len(crb)
                            await read(idx - buf_stop)
                            if buf.startswith(lfb, idx):
                                await read(lfb_len)
                                del buf[idx+lfb_len:]
                            else:
                                del buf[idx:]
                            break
                        if peek_b:
                            await read(len(peek_b))
                        c = await read(1)
                        if not c:
                            reach_end = True
                            break
                        buf += c
                while buf:
                    try:
                        text += str(buf, encoding)
                        buf.clear()
                    except UnicodeDecodeError as e:
                        start, stop = e.start, e.end
                        if start:
                            text += str(buf[:start], encoding)
                        if e.reason == "truncated data":
                            if stop == len(buf):
                                buf = buf[start:]
                                break
                            else:
                                while stop < len(buf):
                                    stop += 1
                                    try:
                                        text += str(buf[start:stop], encoding)
                                        buf = buf[stop:]
                                        break_this_loop = True
                                        break
                                    except UnicodeDecodeError as exc:
                                        e = exc
                                        if e.reason != "truncated data":
                                            break
                                        if stop == len(buf):
                                            buf = buf[start:]
                                            break_this_loop = True
                                            break
                                if break_this_loop:
                                    break
                        if e.reason == "unexpected end of data" and stop == len(buf):
                            buf = buf[start:]
                            break
                        if errors == "strict":
                            raise
                        text += str(buf[start:stop], encoding, errors)
                        buf = buf[stop:]
                else:
                    if newline:
                        if text.endswith(newline):
                            return text[:-len(newline)] + "\n"
                    elif newline is None:
                        if text.endswith("\r\n"):
                            return text[:-2] + "\n"
                        elif text.endswith("\r"):
                            return text[:-1] + "\n"
                        elif text.endswith("\n"):
                            return text
                    elif text.endswith(("\r\n", "\r", "\n")):
                        return text
                    if reach_end:
                        return text
        else:
            while True:
                rem = size - len(text)
                if peek is None:
                    while rem and (c := await read(1)):
                        buf += c
                        rem -= 1
                        if newline:
                            if buf.endswith(sepb):
                                break
                        elif buf.endswith(lfb):
                            break
                        elif buf.endswith(crb):
                            peek_maybe_lfb = await read(lfb_len)
                            if not isinstance(peek_maybe_lfb, Sized):
                                peek_maybe_lfb = memoryview(peek_maybe_lfb)
                            if peek_maybe_lfb == lfb:
                                buf += lfb
                            elif peek_maybe_lfb:
                                o = len(cast(Sized, peek_maybe_lfb))
                                await seek(-o, 1)
                                if o < lfb_len:
                                    reach_end = True
                            break
                    else:
                        reach_end = True
                else:
                    while rem:
                        buf_stop = len(buf)
                        peek_b = peek()
                        if peek_b:
                            if len(peek_b) >= rem:
                                buf += peek_b[:rem]
                                rem = 0
                            else:
                                buf += peek_b
                                rem -= len(peek_b)
                        if newline:
                            if (idx := buf.find(sepb)) > -1:
                                idx += 1
                                await read(idx - buf_stop)
                                del buf[idx:]
                                break
                        elif (idx := buf.find(lfb)) > -1:
                            idx += 1
                            await read(idx - buf_stop)
                            del buf[idx:]
                            break
                        elif (idx := buf.find(crb)) > -1:
                            idx += 1
                            await read(idx - buf_stop)
                            if buf.startswith(lfb, idx):
                                await read(lfb_len)
                                del buf[idx+lfb_len:]
                            else:
                                del buf[idx:]
                            break
                        if rem:
                            c = await read(1)
                            if not c:
                                reach_end = True
                                break
                            rem -= 1
                            buf += c
                while buf:
                    try:
                        text += str(buf, encoding)
                        buf.clear()
                    except UnicodeDecodeError as e:
                        start, stop = e.start, e.end
                        if start:
                            text += str(buf[:start], encoding)
                        if e.reason in ("unexpected end of data", "truncated data") and stop == len(buf):
                            buf = buf[start:]
                            break
                        if errors == "strict":
                            raise
                        text += str(buf[start:stop], encoding, errors)
                        buf = buf[stop:]
                else:
                    if newline:
                        if text.endswith(newline):
                            return text[:-len(newline)] + "\n"
                    elif newline is None:
                        if text.endswith("\r\n"):
                            return text[:-2] + "\n"
                        elif text.endswith("\r"):
                            return text[:-1] + "\n"
                        elif text.endswith("\n"):
                            return text
                    elif text.endswith(("\r\n", "\r", "\n")):
                        return text
                    if reach_end or len(text) == size:
                        return text

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
        return await ensure_async(getattr(self.buffer, "seek"), threaded=True)(target, whence)

    def tell(self, /) -> int:
        return getattr(self.buffer, "tell")()

    async def truncate(self, pos: None | int = None, /) -> int: # type: ignore
        return await ensure_async(getattr(self.buffer, "truncate"), threaded=True)(pos)

    async def write(self, text: str, /) -> int: # type: ignore
        match self.newline:
            case "" | "\n":
                pass
            case None:
                if linesep != "\n":
                    text = text.replace("\n", linesep)
            case _:
                text = text.replace("\n", linesep)
        data = bytes(text, self.encoding, self.errors or "strict")
        await ensure_async(self.buffer.write, threaded=True)(data)
        if self.write_through or self.line_buffering and ("\n" in text or "\r" in text):
            await self.flush()
        return len(text)

    async def writelines(self, lines: Iterable[str], /): # type: ignore
        write = self.write
        for line in lines:
            await write(line)


def bio_chunk_iter(
    bio: SupportsRead[Buffer] | SupportsReadinto | Callable[[int], Buffer], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
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
                if length < len(buf):
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
                length = len(chunk)
                if callback:
                    callback(length)
                yield chunk
                if length < readsize:
                    break
                size -= length
        elif size < 0:
            while (chunk := read(chunksize)):
                if callback:
                    callback(len(chunk))
                yield chunk


async def bio_chunk_async_iter(
    bio: SupportsRead[Buffer] | SupportsReadinto | Callable[[int], Buffer | Awaitable[Buffer]], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
    can_buffer: bool = False, 
    callback: None | Callable[[int], Any] = None, 
) -> AsyncIterator[Buffer]:
    use_readinto = False
    if callable(bio):
        read = ensure_async(bio, threaded=True)
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
                if length < len(buf):
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
                length = len(chunk)
                if callback:
                    await callback(length)
                yield chunk
                if length < readsize:
                    break
                size -= readsize
        elif size < 0:
            while (chunk := (await read(chunksize))):
                if callback:
                    await callback(len(chunk))
                yield chunk


def bio_skip_iter(
    bio: SupportsRead[Buffer] | SupportsReadinto | Callable[[int], Buffer], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
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
            chunksize = COPY_BUFSIZE
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
                length = len(read(readsize))
                if callback:
                    callback(length)
                yield length
                if length < readsize:
                    break
                size -= readsize
        else:
            while (length := len(read(chunksize))):
                if callback:
                    callback(length)
                yield length
    else:
        if callback:
            callback(length)
        yield length


async def bio_skip_async_iter(
    bio: SupportsRead[Buffer] | SupportsReadinto | Callable[[int], Buffer | Awaitable[Buffer]], 
    /, 
    size: int = -1, 
    chunksize: int = COPY_BUFSIZE, 
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
            chunksize = COPY_BUFSIZE
        if callable(bio):
            read = ensure_async(bio, threaded=True)
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
                length = len(await read(readsize))
                if callback:
                    await callback(length)
                yield length
                if length < readsize:
                    break
                size -= readsize
        else:
            while (length := len(await read(chunksize))):
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
        l = len(b)
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
        l = len(b)
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
        l = len(m)
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
        l = len(m)
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
                    while n > len(unconsumed):
                        unconsumed += getnext()
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += len(b)
                    return b
            except StopIteration:
                at_end = True
                b = unconsumed[:]
                del unconsumed[:]
                pos += len(b)
                return b
    def readinto(buf, /) -> int:
        nonlocal pos, at_end, unconsumed
        if at_end or not (bufsize := len(buf)):
            return 0
        with lock:
            n = len(unconsumed)
            if bufsize <= n:
                buf[:], unconsumed = unconsumed[:bufsize], unconsumed[bufsize:]
                pos += bufsize
                return bufsize
            buf[:n] = unconsumed
            del unconsumed[:]
            try:
                while True:
                    b = getnext()
                    if not b:
                        continue
                    m = n + len(b)
                    if m >= bufsize:
                        buf[n:] = b[:bufsize-n]
                        unconsumed += b[bufsize-n:]
                        pos += bufsize
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
                if n > 0 and len(unconsumed) >= n:
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += n
                    return b
            try:
                start = len(unconsumed)
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
                    start = len(unconsumed)
                    if n > 0 and start >= n:
                        b, unconsumed = unconsumed[:n], unconsumed[n:]
                        pos += n
                        return b
            except StopIteration:
                at_end = True
                if unconsumed:
                    b = unconsumed[:]
                    del unconsumed[:]
                    pos += len(b)
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
                hint -= len(line)
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
) -> SupportsRead[bytearray]:
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
        nonlocal at_end
        try:
            method = getattr(it, "aclose")
        except AttributeError:
            method = getattr(it, "close")
        ret = method()
        if isawaitable(ret):
            run_async(ret)
        at_end = True
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
                    while n > len(unconsumed):
                        unconsumed += await getnext()
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += len(b)
                    return b
            except (StopIteration, StopAsyncIteration):
                at_end = True
                b = unconsumed[:]
                del unconsumed[:]
                pos += len(b)
                return b
    async def readinto(buf, /) -> int:
        nonlocal pos, at_end, unconsumed
        if at_end or not (bufsize := len(buf)):
            return 0
        async with lock:
            n = len(unconsumed)
            if bufsize <= n:
                buf[:], unconsumed = unconsumed[:bufsize], unconsumed[bufsize:]
                pos += bufsize
                return bufsize
            buf[:n] = unconsumed
            del unconsumed[:]
            try:
                while True:
                    b = await getnext()
                    if not b:
                        continue
                    m = n + len(b)
                    if m >= bufsize:
                        buf[n:] = b[:bufsize-n]
                        unconsumed += b[bufsize-n:]
                        pos += bufsize
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
                if n > 0 and len(unconsumed) >= n:
                    b, unconsumed = unconsumed[:n], unconsumed[n:]
                    pos += n
                    return b
            try:
                start = len(unconsumed)
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
                    start = len(unconsumed)
                    if n > 0 and start >= n:
                        b, unconsumed = unconsumed[:n], unconsumed[n:]
                        pos += n
                        return b
            except (StopIteration, StopAsyncIteration):
                at_end = True
                if unconsumed:
                    b = unconsumed[:]
                    del unconsumed[:]
                    pos += len(b)
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
                    hint -= len(line)
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
    chunksize: int = COPY_BUFSIZE, 
) -> Iterator[memoryview]:
    m = memoryview(b)
    for i in range(0, len(m), chunksize):
        yield m[i:i+chunksize]


async def bytes_to_chunk_async_iter(
    b: Buffer, 
    /, 
    chunksize: int = COPY_BUFSIZE, 
) -> AsyncIterator[memoryview]:
    m = memoryview(b)
    for i in range(0, len(m), chunksize):
        yield m[i:i+chunksize]


def bytes_ensure_part_iter(
    it: Iterable[Buffer], 
    /, 
    partsize: int = COPY_BUFSIZE, 
) -> Iterator[Buffer]:
    n = partsize
    for b in it:
        m = memoryview(b)
        l = len(m)
        if l <= n:
            yield b
            if l == n:
                n = partsize
            else:
                n -= l
        else:
            yield m[:n]
            m = m[n:]
            while len(m) >= partsize:
                yield m[:partsize]
                m = m[partsize:]
            if m:
                yield m
                n = partsize - len(m)
            else:
                n = partsize


async def bytes_ensure_part_async_iter(
    it: Iterable[Buffer] | AsyncIterable[Buffer], 
    /, 
    partsize: int = COPY_BUFSIZE, 
) -> AsyncIterator[Buffer]:
    n = partsize
    async for b in ensure_aiter(it):
        m = memoryview(b)
        l = len(m)
        if l <= n:
            yield b
            if l == n:
                n = partsize
            else:
                n -= l
        else:
            yield m[:n]
            m = m[n:]
            while len(m) >= partsize:
                yield m[:partsize]
                m = m[partsize:]
            if m:
                yield m
                n = partsize - len(m)
            else:
                n = partsize


def progress_bytes_iter(
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
                update_progress(len(chunk))
        else:
            for chunk in it:
                yield chunk
    finally:
        if callable(close_progress):
            close_progress()


async def progress_bytes_async_iter(
    it: Iterable[Buffer] | AsyncIterable[Buffer] | Callable[[], Buffer] | Callable[[], Awaitable[Buffer]], 
    make_progress: None | Callable[Args, Any] = None, 
    /, 
    *args: Args.args, 
    **kwds: Args.kwargs, 
) -> AsyncIterator[Buffer]:
    update_progress: None | Callable = None
    close_progress: None | Callable = None
    if callable(it):
        async def wrapiter(it) -> Buffer:
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
                await update_progress(len(chunk))
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
    chunksize: int = COPY_BUFSIZE, 
):
    if chunksize <= 0:
        chunksize = COPY_BUFSIZE
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
    chunksize: int = COPY_BUFSIZE, 
    threaded: bool = True, 
):
    if chunksize <= 0:
        chunksize = COPY_BUFSIZE
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

