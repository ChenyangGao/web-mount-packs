#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["DownloadTask", "download_iter", "download", "requests_download"]

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="python url downloader")
    parser.add_argument("url", nargs="?", help="URL(s) to be downloaded (one URL per line), if omitted, read from stdin")
    parser.add_argument("-d", "--savedir", default="", help="path to the downloaded file")
    parser.add_argument("-r", "--resume", action="store_true", help="skip downloaded data")
    parser.add_argument("-hs", "--headers", help="dictionary of HTTP Headers to send with")
    parser.add_argument("-rq", "--use-requests", action="store_true", help="use `requests` module")
    args = parser.parse_args()

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

from collections.abc import Callable, Generator, Iterator
from inspect import isgenerator
from os import fsdecode, fstat, makedirs, PathLike
from os.path import abspath, dirname, isdir, join as joinpath
from shutil import COPY_BUFSIZE # type: ignore
from threading import Event
from typing import cast, Any, NamedTuple, Never, Optional, Self

from requests import Response, Session

if __name__ == "__main__":
    from sys import path
    path.insert(0, dirname(dirname(__file__)))
    from util.concurrent import run_as_thread # type: ignore
    from util.file import bio_skip_iter, SupportsRead, SupportsWrite # type: ignore
    from util.iter import cut_iter # type: ignore
    from util.response import get_filename, get_length, is_chunked, is_range_request # type: ignore
    from util.text import headers_str_to_dict # type: ignore
    from util.urlopen import urlopen # type: ignore
    del path[0]
else:
    from .concurrent import run_as_thread
    from .file import bio_skip_iter, SupportsRead, SupportsWrite
    from .iter import cut_iter
    from .response import get_filename, get_length, is_chunked, is_range_request
    from .text import headers_str_to_dict
    from .urlopen import urlopen


if "__del__" not in Response.__dict__:
    setattr(Response, "__del__", Response.close)
if "__del__" not in Session.__dict__:
    setattr(Session, "__del__", Session.close)


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


class DownloadTask:

    def __init__(self, /, gen, submit=run_as_thread):
        if not callable(submit):
            submit = submit.submit
        self._submit = submit
        self._state = "PENDING"
        self._gen = gen
        self._done_event = Event()

    def __repr__(self, /) -> str:
        return f"<{type(self).__qualname__} :: state={self.state!r} progress={self.progress!r}>"

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
    def progress(self, /) -> Optional[DownloadProgress]:
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
    headers: Optional[dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
) -> Iterator[DownloadProgress]:
    """
    """
    if not isinstance(url, str):
        url = url()

    if headers:
        headers = {**headers, "Accept-Encoding": "identity"}
    else:
        headers = {"Accept-Encoding": "identity"}

    if chunksize <= 0:
        chunksize = COPY_BUFSIZE

    resp = urlopen(url, headers=headers)
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

    yield DownloadProgress(length, 0, 0, 0, extra)

    length_downloaded = 0
    length_skipped = 0
    with resp:
        fsrc_read = resp.read
        fdst_write = fdst.write
        if filesize:
            if is_range_request(resp):
                length_skipped = filesize
                yield DownloadProgress(length, 0, length_skipped, length_skipped, extra)
            else:
                for skiplen in bio_skip_iter(resp, filesize):
                    length_skipped += skiplen
                    yield DownloadProgress(length, 0, length_skipped, skiplen, extra)

        while (chunk := fsrc_read(chunksize)):
            downlen = fdst_write(chunk)
            length_downloaded += downlen
            yield DownloadProgress(length, length_downloaded, length_skipped, downlen, extra)


def download(
    url: str | Callable[[], str], 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: Optional[dict[str, str]] = None, 
    urlopen: Callable = urlopen, 
    make_reporthook: Optional[Callable[[Optional[int]], Callable[[int], Any] | Generator[int, Any, Any]]] = None, 
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
    urlopen: Callable = Session().get, 
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


if __name__ == "__main__":
    from collections import deque
    from time import perf_counter

    def progress(total=None):
        dq: deque[tuple[int, float]] = deque(maxlen=64)
        read_num = 0
        dq.append((read_num, perf_counter()))
        while True:
            read_num += yield
            cur_t = perf_counter()
            speed = (read_num - dq[0][0]) / 1024 / 1024 / (cur_t - dq[0][1])
            if total:
                percentage = read_num / total * 100
                print(f"\r\x1b[K{read_num} / {total} | {speed:.2f} MB/s | {percentage:.2f} %", end="", flush=True)
            else:
                print(f"\r\x1b[K{read_num} | {speed:.2f} MB/s", end="", flush=True)
            dq.append((read_num, cur_t))

    url = args.url
    if url:
        urls = url.splitlines()
    else:
        from sys import stdin
        urls = (l.removesuffix("\n") for l in stdin)
    savedir = args.savedir
    if savedir:
        makedirs(savedir, exist_ok=True)

    if args.use_requests:
        downloader: Callable = requests_download
    else:
        downloader = download

    try:
        headers = args.headers
        if headers is not None:
            headers = headers_str_to_dict(headers)
        for url in urls:
            if not url:
                continue
            try:
                file = downloader(
                    url, 
                    file=savedir, 
                    resume=args.resume, 
                    make_reporthook=progress, 
                    headers=headers, 
                )
                print(f"\r\x1b[K\x1b[1;32mDOWNLOADED\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n |_ ⏬ \x1b[4;34m{file!r}\x1b[0m")
            except BaseException as e:
                print(f"\r\x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n  |_ 🙅 \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
    except BrokenPipeError:
        from sys import stderr
        stderr.close()

