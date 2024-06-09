#!/usr/bin/env python3
# encoding: utf

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = [
    "DownloadTask", "download_iter", "download", "requests_download", 
    "download_async_iter", "async_download", 
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

from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterator
from inspect import isasyncgen, isgenerator
from os import fsdecode, fstat, makedirs, PathLike
from os.path import abspath, dirname, isdir, join as joinpath
from shutil import COPY_BUFSIZE # type: ignore
from threading import Event
from typing import cast, Any, NamedTuple, Self

from aiohttp_client_request import request as aiohttp_request
from asynctools import ensure_async, as_thread
from concurrenttools import run_as_thread
from filewrap import bio_skip_iter, bio_skip_async_iter, SupportsRead, SupportsWrite
from http_request import headers_str_to_dict
from http_response import get_filename, get_length, is_chunked, is_range_request
from iterutils import cut_iter
from requests_request import request as requests_request
from urlopen import urlopen

try:
    from aiofile import async_open, FileIOWrapperBase
    aiofile_installed = True
except ImportError:
    aiofile_installed = False
else:
    if "__getattr__" not in FileIOWrapperBase.__dict__:
        setattr(FileIOWrapperBase, "__getattr__", lambda self, attr, /: getattr(self.file, attr))


class DownloadProgress(NamedTuple):
    total: int
    downloaded: int
    skipped: int
    last_incr: int = 0
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


# TODO 设计一个 AsyncDownloadTask
class DownloadTask:

    def __init__(self, /, gen, submit=run_as_thread):
        if not callable(submit):
            submit = submit.submit
        self._submit = submit
        self._state = "PENDING"
        self._gen = gen
        self._done_event = Event()

    def __repr__(self, /) -> str:
        match state := self.state:
            case "FINISHED":
                return f"<{type(self).__qualname__} :: state={state!r} result={self.result} progress={self.progress!r}>"
            case "FAILED":
                return f"<{type(self).__qualname__} :: state={state!r} reason={self.result} progress={self.progress!r}>"
        return f"<{type(self).__qualname__} :: state={state!r} progress={self.progress!r}>"

    @classmethod
    def create_task(
        cls, 
        /, 
        *args, 
        submit=run_as_thread, 
        **kwargs, 
    ) -> Self:
        return cls(download_iter(*args, **kwargs), submit=submit)

    @property
    def closed(self, /) -> bool:
        return self._state in ("CANCELED", "FAILED", "FINISHED")

    @property
    def progress(self, /) -> None | DownloadProgress:
        return self.__dict__.get("_progress")

    @property
    def result(self, /):
        self._done_event.wait()
        return self._result

    @result.setter
    def result(self, val, /):
        self._result = val
        self._done_event.set()

    @property
    def state(self, /) -> str:
        return self._state

    def close(self, /):
        if self._state in ("CANCELED", "FAILED", "FINISHED"):
            pass
        else:
            state = self._state
            self._state = "CANCELED"
            if state != "RUNNING":
                self.run()

    def pause(self, /):
        if self._state in ("PAUSED", "RUNNING"):
            self._state = "PAUSED"
        else:
            raise RuntimeError(f"can't pause when state={self._state!r}")

    def _run(self, /):
        if self._state in ("PENDING", "PAUSED"):
            self._state = "RUNNING"
        else:
            raise RuntimeError(f"can't run when state={self._state!r}")
        gen = self._gen
        try:
            while self._state == "RUNNING":
                self._progress = next(gen)
        except KeyboardInterrupt:
            raise
        except StopIteration as exc:
            self._state = "FINISHED"
            self.result = exc.value
        except BaseException as exc:
            self._state = "FAILED"
            self.result = exc
        else:
            if self._state == "CANCELED":
                try:
                    gen.close()
                finally:
                    self.result = None

    def run(self, /):
        return self._submit(self._run)

    def run_wait(self, /):
        if not self._done_event.is_set():
            if self._state == "RUNNING":
                self._done_event.wait()
            else:
                self._run()


def download_iter(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] | Callable[[], dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
) -> Generator[DownloadProgress, None, None]:
    """
    """
    if not isinstance(url, str):
        url = url()

    if callable(headers):
        headers = headers()
    if headers:
        headers = {**headers, "Accept-Encoding": "identity"}
    else:
        headers = {"Accept-Encoding": "identity"}

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
                filesize = fstat(fdst.fileno()).st_size # type: ignore
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

        fsrc_read = resp.read
        fdst_write = fdst.write
        if filesize:
            if is_range_request(resp):
                length_skipped = filesize
                yield DownloadProgress(length or length_skipped, 0, length_skipped, length_skipped, extra)
            else:
                for skiplen in bio_skip_iter(resp, filesize):
                    length_skipped += skiplen
                    yield DownloadProgress(length or length_skipped, 0, length_skipped, skiplen, extra)

        while (chunk := fsrc_read(chunksize)):
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
    make_reporthook: None | Callable[[None | int], Callable[[int], Any] | Generator[int, Any, Any]] = None, 
):
    """
    """
    gen = download_iter(url, file, resume=resume, chunksize=chunksize, headers=headers, urlopen=urlopen)
    if make_reporthook:
        progress = next(gen)
        reporthook = make_reporthook(progress.total)
        if isgenerator(reporthook):
            next(reporthook)
            reporthook = reporthook.send
        reporthook = cast(Callable[[int], Any], reporthook)
        reporthook(progress.last_incr)
    else:
        reporthook = None

    for progress in gen:
        reporthook and reporthook(progress.last_incr)


def requests_download(
    url: str | Callable[[], str], 
    urlopen: Callable = requests_request, 
    **kwargs, 
):
    """
    """
    def urlopen_wrapper(url, headers):
        resp = urlopen(url, headers=headers, stream=True)
        resp.raise_for_status()
        resp.read = resp.raw.read
        return resp
    return download(url, urlopen=urlopen_wrapper, **kwargs)


async def download_async_iter(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] | Callable[[], dict[str, str]] = None, 
    urlopen: Callable = aiohttp_request, 
) -> AsyncGenerator[DownloadProgress, None]:
    """
    """
    if not isinstance(url, str):
        url = await ensure_async(url)()

    if callable(headers):
        headers = await ensure_async(headers)()
    if headers:
        headers = {**headers, "Accept-Encoding": "identity"}
    else:
        headers = {"Accept-Encoding": "identity"}

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
                filesize = fstat(fdst.fileno()).st_size # type: ignore
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
            await ensure_async(resp.close)()
            resp = await urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize})
            if not is_range_request(resp):
                raise OSError(errno.EIO, f"range request failed: {url!r}")

        yield DownloadProgress(length or 0, 0, 0, 0, extra)

        length_downloaded = 0
        length_skipped = 0

        fsrc_read = ensure_async(resp.read)
        fdst_write = ensure_async(fdst.write)
        if filesize:
            if is_range_request(resp):
                length_skipped = filesize
                yield DownloadProgress(length or length_skipped, 0, length_skipped, length_skipped, extra)
            else:
                async for skiplen in bio_skip_async_iter(resp, filesize):
                    length_skipped += skiplen
                    yield DownloadProgress(length or length_skipped, 0, length_skipped, skiplen, extra)

        while (chunk := (await fsrc_read(chunksize))):
            await fdst_write(chunk)
            downlen = len(chunk)
            length_downloaded += downlen
            yield DownloadProgress(length or (length_skipped + length_downloaded), length_downloaded, length_skipped, downlen, extra)
    finally:
        await ensure_async(resp.close)()
        if file_async_close:
            await file_async_close()


async def async_download(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] | Callable[[], dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
    make_reporthook: None | Callable[[None | int], Callable[[int], Any] | Generator[int, Any, Any] | AsyncGenerator[int, Any]] = None, 
):
    """
    """
    gen = download_async_iter(url, file, resume=resume, chunksize=chunksize, headers=headers, urlopen=urlopen)
    reporthook_close: None | Callable = None
    if make_reporthook:
        progress = await anext(gen)
        reporthook = make_reporthook(progress.total)
        if isasyncgen(reporthook):
            await anext(reporthook)
            reporthook_close = reporthook.aclose
            reporthook = reporthook.asend
        elif isgenerator(reporthook):
            await as_thread(next)(reporthook)
            reporthook_close = as_thread(reporthook.close)
            reporthook = as_thread(reporthook.send)
        else:
            reporthook = ensure_async(cast(Callable, reporthook))
        await reporthook(progress.last_incr)
    else:
        reporthook = None

    try:
        async for progress in gen:
            reporthook and await reporthook(progress.last_incr)
    finally:
        await gen.aclose()
        if reporthook_close:
            await reporthook_close()

