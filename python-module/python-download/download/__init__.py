#!/usr/bin/env python3
# encoding: utf

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = [
    "DownloadTaskStatus", "DownloadProgress", 
    "DownloadTask", "AsyncDownloadTask", 
    #"DownloadTaskManager", "AsyncDownloadTaskManager", 
    "download_iter", "download", "download_async_iter", "download_async", 
]

# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Ranges
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Range
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/206
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/ETag
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Range
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/If-Range
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding
# NOTE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Encoding

import errno

from asyncio import create_task
from asyncio.exceptions import CancelledError, InvalidStateError
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterator
from enum import IntEnum
from inspect import isawaitable
from os import fsdecode, fstat, makedirs, PathLike
from os.path import abspath, dirname, isdir, join as joinpath
from shutil import COPY_BUFSIZE # type: ignore
from threading import Event, Lock
from typing import cast, Any, NamedTuple, Self

from asynctools import ensure_aiter, ensure_async, as_thread
from concurrenttools import run_as_thread
from filewrap import bio_chunk_iter, bio_chunk_async_iter, bio_skip_iter, bio_skip_async_iter, SupportsWrite
from http_response import get_filename, get_length, is_chunked, is_range_request
from urlopen import urlopen


DEFAULT_ITER_BYTES = lambda resp: bio_chunk_iter(resp, chunksize=COPY_BUFSIZE)
DEFAULT_ASYNC_ITER_BYTES = lambda resp: bio_chunk_async_iter(resp, chunksize=COPY_BUFSIZE)

try:
    from aiofile import async_open, FileIOWrapperBase
    aiofile_installed = True
except ImportError:
    aiofile_installed = False
else:
    if "__getattr__" not in FileIOWrapperBase.__dict__:
        setattr(FileIOWrapperBase, "__getattr__", lambda self, attr, /: getattr(self.file, attr))


class DownloadTaskStatus(IntEnum):
    PENDING = 0
    RUNNING = 1
    PAUSED = 2
    FINISHED = 3
    CANCELED = 4
    FAILED = 5

    def __str__(self, /) -> str:
        return repr(self)

    @classmethod
    def of(cls, val, /) -> Self:
        if isinstance(val, cls):
            return val
        try:
            if isinstance(val, str):
                return cls[val]
        except KeyError:
            pass
        return cls(val)


class DownloadProgress(NamedTuple):
    total: int
    downloaded: int
    skipped: int
    last_increment: int = 0
    extra: Any = None

    @property
    def completed(self, /) -> int:
        return self.downloaded + self.skipped

    @property
    def remaining(self, /) -> int:
        return max(0, self.total - self.completed)

    @property
    def ratio(self, /) -> float:
        return self.completed / self.total

    @property
    def task_done(self, /) -> bool:
        return self.completed >= self.total


class BaseDownloadTask(ABC):
    state: DownloadTaskStatus = DownloadTaskStatus.PENDING
    progress: None | DownloadProgress = None
    _exception: None | BaseException

    def __init__(self, /):
        self.done_callbacks: list[Callable[[Self], Any]] = []

    def __del__(self, /):
        self.cancel()

    def __repr__(self, /) -> str:
        name = type(self).__qualname__
        state = self.state
        if state is DownloadTaskStatus.FAILED:
            return f"<{name} :: state={state!r} progress={self.progress!r} exception={self.exception()!r}>"
        return f"<{name} :: state={state!r} progress={self.progress!r}>"

    @property
    def pending(self, /) -> bool:
        return self.state is DownloadTaskStatus.PENDING

    @property
    def running(self, /) -> bool:
        return self.state is DownloadTaskStatus.RUNNING

    @property
    def paused(self, /) -> bool:
        return self.state is DownloadTaskStatus.PAUSED

    @property
    def finished(self, /) -> bool:
        return self.state is DownloadTaskStatus.FINISHED

    @property
    def canceled(self, /) -> bool:
        return self.state is DownloadTaskStatus.CANCELED

    @property
    def failed(self, /) -> bool:
        return self.state is DownloadTaskStatus.FAILED

    @property
    def processing(self, /) -> bool:
        return self.state in (DownloadTaskStatus.RUNNING, DownloadTaskStatus.PAUSED)

    @property
    def done(self, /) -> bool:
        return self.state in (DownloadTaskStatus.FINISHED, DownloadTaskStatus.CANCELED, DownloadTaskStatus.FAILED)

    def cancel(self, /):
        if not self.done:
            self.set_exception(CancelledError())
            self.state = DownloadTaskStatus.CANCELED

    def pause(self, /):
        if self.processing:
            self.state = DownloadTaskStatus.PAUSED
        else:
            raise InvalidStateError(f"can't pause when state={self.state!r}")

    def exception(self, /) -> None | BaseException:
        if self.done:
            return self._exception
        else:
            raise InvalidStateError(self.state)

    def set_exception(self, exception, /):
        self._exception = exception

    def result(self, /):
        if self.finished:
            return self._result
        elif not self.done:
            raise InvalidStateError(self.state)
        else:
            raise cast(BaseException, self._exception)

    def set_result(self, result, /):
        self._result = result

    def add_done_callback(self, /, callback: Callable[[Self], Any]):
        if self.done:
            callback(self)
        else:
            self.done_callbacks.append(callback)

    def remove_done_callback(self, /, callback: int | slice | Callable[[Self], Any] = -1):
        try:
            if callable(callback):
                self.done_callbacks.remove(callback)
            else:
                del self.done_callbacks[callback]
        except (IndexError, ValueError):
            pass

    @abstractmethod
    def run(self, /):
        match state := self.state:
            case DownloadTaskStatus.PENDING | DownloadTaskStatus.PAUSED:
                self.state = DownloadTaskStatus.RUNNING
            case DownloadTaskStatus.RUNNING:
                raise RuntimeError("already running")
            case _:
                raise RuntimeError(f"can't run when state={state!r}")


class DownloadTask(BaseDownloadTask):

    def __init__(
        self, 
        it: Iterator[DownloadProgress], 
        /, 
        submit=run_as_thread, 
    ):
        super().__init__()
        if not callable(submit):
            submit = submit.submit
        self.submit = submit
        self._it = it
        self._state_lock = Lock()
        self._done_event = Event()

    @classmethod
    def create_task(
        cls, 
        /, 
        *args, 
        submit=run_as_thread, 
        **kwargs, 
    ) -> Self:
        return cls(download_iter(*args, **kwargs), submit=submit)

    def add_done_callback(self, /, callback: Callable[[Self], Any]):
        with self._state_lock:
            if not self.done:
                self.done_callbacks.append(callback)
                return
        return callback(self)

    def cancel(self, /):
        with self._state_lock:
            super().cancel() 
        self._done_event.set()

    def pause(self, /):
        with self._state_lock:
            super().pause()

    def exception(self, /, timeout: None | float = None) -> None | BaseException:
        self._done_event.wait(timeout)
        return super().exception()

    def set_exception(self, exception, /):
        super().set_exception(exception)
        self._done_event.set()

    def result(self, /, timeout: None | float = None):
        self._done_event.wait(timeout)
        return super().result()

    def set_result(self, result, /):
        super().set_result(result)
        self._done_event.set()

    def run(self, /):
        super().run()
        state_lock = self._state_lock
        it = self._it
        step = it.__next__
        try:
            while self.running:
                self.progress = step()
        except KeyboardInterrupt:
            raise
        except StopIteration as exc:
            with state_lock:
                self.state = DownloadTaskStatus.FINISHED
                self.set_result(exc.value)
        except BaseException as exc:
            with state_lock:
                self.state = DownloadTaskStatus.FAILED
                self.set_exception(exc)
        else:
            if self.done:
                try:
                    getattr(it, "__del__")()
                except:
                    pass
                for callback in self.done_callbacks:
                    try:
                        callback(cast(Self, self))
                    except:
                        pass

    def start(self, /, wait: bool = True):
        with self._state_lock:
            if self.state in (DownloadTaskStatus.PENDING, DownloadTaskStatus.PAUSED):
                self.submit(self.run)
        if wait and not self.done:
            self._done_event.wait()


class AsyncDownloadTask(BaseDownloadTask):

    def __init__(
        self, 
        it: AsyncIterator[DownloadProgress], 
        /, 
        submit=create_task, 
    ):
        super().__init__()
        if not callable(submit):
            submit = submit.submit
        self.submit = submit
        self._it = it

    @classmethod
    def create_task(
        cls, 
        /, 
        *args, 
        submit=create_task, 
        **kwargs, 
    ) -> Self:
        return cls(download_async_iter(*args, **kwargs), submit=submit)

    async def run(self, /):
        super().run()
        it = self._it
        step = it.__anext__
        try:
            while self.running:
                self.progress = await step()
        except KeyboardInterrupt:
            raise
        except StopAsyncIteration as exc:
            self.state = DownloadTaskStatus.FINISHED
            self.set_result(None)
        except BaseException as exc:
            self.state = DownloadTaskStatus.FAILED
            self.set_exception(exc)
        else:
            if self.canceled:
                try:
                    if isinstance(it, AsyncGenerator):
                        await it.aclose()
                    else:
                        getattr(it, "__del__")()
                except:
                    pass
            elif self.done:
                for callback in self.done_callbacks:
                    try:
                        ret = callback(cast(Self, self))
                        if isawaitable(ret):
                            await ret
                    except:
                        pass

    def start(self, /):
        if self.state in (DownloadTaskStatus.PENDING, DownloadTaskStatus.PAUSED):
            return self.submit(self.run())


class DownloadTaskManager:
    ...


class AsyncDownloadTaskManager:
    ...


def download_iter(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] | Callable[[], dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
    iter_bytes: Callable = DEFAULT_ITER_BYTES, 
) -> Generator[DownloadProgress, None, None]:
    """
    """
    if callable(url):
        url = url()
    if callable(headers):
        headers = headers()
    elif headers:
        headers = dict(headers)
    else:
        headers = {}
    if type(url) is not str:
        extra_headers = getattr(url, "headers", None)
        if extra_headers:
            headers.update(extra_headers)
    headers["Accept-Encoding"] = "identity"

    if chunksize <= 0:
        chunksize = COPY_BUFSIZE

    resp = urlopen(url, headers=headers)
    try:
        length = get_length(resp)
        if length == 0 and is_chunked(resp):
            length = None

        fdst: SupportsWrite[bytes]
        if hasattr(file, "write"):
            file = fdst = cast(SupportsWrite[bytes], file)
        else:
            file = abspath(fsdecode(file))
            if isdir(file):
                file = joinpath(file, get_filename(resp, "download"))
            try:
                fdst = open(file, "ab" if resume else "wb")
            except FileNotFoundError:
                makedirs(dirname(file), exist_ok=True)
                fdst = open(file, "ab" if resume else "wb")

        extra = {"url": url, "file": file, "resume": resume}

        filesize = 0
        if resume:
            try:
                fileno = getattr(fdst, "fileno")()
                filesize = fstat(fileno).st_size
            except (AttributeError, OSError):
                pass
            else:
                if filesize == length:
                    yield DownloadProgress(length, 0, length, length, extra)
                    return
                elif length is not None and filesize > length:
                    raise OSError(errno.EIO, f"file {file!r} is larger than url {url!r}: {filesize} > {length} (in bytes)")
        elif length == 0:
            yield DownloadProgress(0, 0, 0, 0, extra)
            return

        if filesize and is_range_request(resp):
            resp.close()
            resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize})
            if not is_range_request(resp):
                raise OSError(errno.EIO, f"range request failed: {url!r}")

        yield DownloadProgress(length or 0, 0, 0, 0, extra)

        length_downloaded = 0
        length_skipped = 0

        fdst_write = fdst.write
        if filesize:
            if is_range_request(resp):
                length_skipped = filesize
                yield DownloadProgress(length or length_skipped, 0, length_skipped, length_skipped, extra)
            else:
                for skiplen in bio_skip_iter(resp, filesize):
                    length_skipped += skiplen
                    yield DownloadProgress(length or length_skipped, 0, length_skipped, skiplen, extra)

        for chunk in iter_bytes(resp):
            fdst_write(chunk)
            downlen = len(chunk)
            length_downloaded += downlen
            yield DownloadProgress(length or (length_skipped + length_downloaded), length_downloaded, length_skipped, downlen, extra)
    finally:
        resp.close()


def download(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] | Callable[[], dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
    iter_bytes: Callable = DEFAULT_ITER_BYTES, 
    make_reporthook: None | Callable[[None | int], Callable[[int], Any] | Generator[int, Any, Any]] = None, 
) -> DownloadProgress:
    """
    """
    update: None | Callable = None
    close: None | Callable = None
    download_gen = download_iter(
        url, 
        file, 
        resume=resume, 
        chunksize=chunksize, 
        headers=headers, 
        urlopen=urlopen, 
        iter_bytes=iter_bytes, 
    )
    try:
        if make_reporthook is not None:
            progress = next(download_gen)
            reporthook = make_reporthook(progress.total)
            if isinstance(reporthook, Generator):
                next(reporthook)
                update = reporthook.send
                close = reporthook.close
            else:
                update = reporthook
                close = getattr(reporthook, "close", None)
            update(progress.last_increment)
        if update is None:
            for progress in download_gen:
                pass
        else:
            for progress in download_gen:
                update(progress.last_increment)
        return progress
    finally:
        download_gen.close()
        if close is not None:
            close()


async def download_async_iter(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] | Callable[[], dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
    iter_bytes: Callable = DEFAULT_ASYNC_ITER_BYTES, 
) -> AsyncGenerator[DownloadProgress, None]:
    """
    """
    if callable(url):
        url = await ensure_async(url)()
    if callable(headers):
        headers = await ensure_async(headers)()
    elif headers:
        headers = dict(headers)
    else:
        headers = {}
    if type(url) is not str:
        extra_headers = getattr(url, "headers", None)
        if extra_headers:
            headers.update(extra_headers)
    headers["Accept-Encoding"] = "identity"

    if chunksize <= 0:
        chunksize = COPY_BUFSIZE

    urlopen = ensure_async(urlopen)

    resp = await urlopen(url, headers=headers)
    file_async_close: None | Callable = None
    try:
        length = get_length(resp)
        if length == 0 and is_chunked(resp):
            length = None

        fdst: SupportsWrite[bytes]
        if hasattr(file, "write"):
            file = fdst = cast(SupportsWrite[bytes], file)
        else:
            file = abspath(fsdecode(file))
            if isdir(file):
                file = joinpath(file, get_filename(resp, "download"))
            if aiofile_installed:
                try:
                    fdst = await async_open(file, "ab" if resume else "wb")
                except FileNotFoundError:
                    makedirs(dirname(file), exist_ok=True)
                    fdst = await async_open(file, "ab" if resume else "wb")
                file_async_close = fdst.close
            else:
                try:
                    fdst = open(file, "ab" if resume else "wb")
                except FileNotFoundError:
                    makedirs(dirname(file), exist_ok=True)
                    fdst = open(file, "ab" if resume else "wb")
                file_async_close = as_thread(fdst.close)

        extra = {"url": url, "file": file, "resume": resume}
        filesize = 0
        if resume:
            try:
                fileno = getattr(fdst, "fileno")()
                filesize = fstat(fileno).st_size
            except (AttributeError, OSError):
                pass
            else:
                if filesize == length:
                    yield DownloadProgress(length, 0, length, length, extra)
                    return
                elif length is not None and filesize > length:
                    raise OSError(errno.EIO, f"file {file!r} is larger than url {url!r}: {filesize} > {length} (in bytes)")
        elif length == 0:
            yield DownloadProgress(0, 0, 0, 0, extra)
            return

        if filesize and is_range_request(resp):
            if hasattr(resp, "aclose"):
                await resp.aclose()
            else:
                await ensure_async(resp.close)()
            resp = await urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize})
            if not is_range_request(resp):
                raise OSError(errno.EIO, f"range request failed: {url!r}")

        yield DownloadProgress(length or 0, 0, 0, 0, extra)

        length_downloaded = 0
        length_skipped = 0

        fdst_write = ensure_async(fdst.write)
        if filesize:
            if is_range_request(resp):
                length_skipped = filesize
                yield DownloadProgress(length or length_skipped, 0, length_skipped, length_skipped, extra)
            else:
                async for skiplen in bio_skip_async_iter(resp, filesize):
                    length_skipped += skiplen
                    yield DownloadProgress(length or length_skipped, 0, length_skipped, skiplen, extra)

        async for chunk in ensure_aiter(iter_bytes(resp)):
            await fdst_write(chunk)
            downlen = len(chunk)
            length_downloaded += downlen
            yield DownloadProgress(length or (length_skipped + length_downloaded), length_downloaded, length_skipped, downlen, extra)
    finally:
        if hasattr(resp, "aclose"):
            await resp.aclose()
        else:
            await ensure_async(resp.close)()
        if file_async_close:
            await file_async_close()


async def download_async(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] | Callable[[], dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
    iter_bytes: Callable = DEFAULT_ASYNC_ITER_BYTES, 
    make_reporthook: None | Callable[[None | int], Callable[[int], Any] | Generator[int, Any, Any] | AsyncGenerator[int, Any]] = None, 
) -> DownloadProgress:
    """
    """
    update: None | Callable = None
    close: None | Callable = None
    download_gen = download_async_iter(
        url, 
        file, 
        resume=resume, 
        chunksize=chunksize, 
        headers=headers, 
        urlopen=urlopen, 
        iter_bytes=iter_bytes, 
    )
    try:
        if make_reporthook is not None:
            progress = await anext(download_gen)
            reporthook = make_reporthook(progress.total)
            if isinstance(reporthook, AsyncGenerator):
                await anext(reporthook)
                update = reporthook.asend
                close = reporthook.aclose
            elif isinstance(reporthook, Generator):
                await as_thread(next)(reporthook)
                update = as_thread(reporthook.send)
                close = reporthook.close
            else:
                update = ensure_async(reporthook)
                close = getattr(reporthook, "close", None)
            await update(progress.last_increment)
        if update is None:
            async for progress in download_gen:
                pass
        else:
            async for progress in download_gen:
                await update(progress.last_increment)
        return progress
    finally:
        await download_gen.aclose()
        if close is not None:
            await ensure_async(close)()

