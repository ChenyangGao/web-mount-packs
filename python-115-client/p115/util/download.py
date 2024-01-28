#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["download", "requests_download"]

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

from collections.abc import Callable, Generator
from inspect import isgenerator
from os import fsdecode, fstat, makedirs, PathLike
from os.path import abspath, dirname, isdir, join as joinpath
from shutil import COPY_BUFSIZE # type: ignore
from typing import cast, Any, Optional

from requests import Response, Session

if __name__ == "__main__":
    from sys import path
    path.insert(0, dirname(dirname(__file__)))
    from util.file import bio_skip_bytes, SupportsRead, SupportsWrite # type: ignore
    from util.iter import cut_iter # type: ignore
    from util.response import get_filename, get_length, is_chunked, is_range_request # type: ignore
    from util.text import headers_str_to_dict # type: ignore
    from util.urlopen import urlopen # type: ignore
    del path[0]
else:
    from .file import bio_skip_bytes, SupportsRead, SupportsWrite
    from .iter import cut_iter
    from .response import get_filename, get_length, is_chunked, is_range_request
    from .text import headers_str_to_dict
    from .urlopen import urlopen


if "__del__" not in Response.__dict__:
    setattr(Response, "__del__", Response.close)
if "__del__" not in Session.__dict__:
    setattr(Session, "__del__", Session.close)


def download(
    url: str, 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: Optional[dict[str, str]] = None, 
    make_reporthook: Optional[Callable[[Optional[int]], Callable[[int], Any] | Generator[int, Any, Any]]] = None, 
    urlopen: Callable = urlopen, 
) -> str | SupportsWrite[bytes]:
    """
    """
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

    filesize = 0
    if resume:
        try:
            filesize = fstat(fdst.fileno()).st_size # type: ignore
        except (AttributeError, OSError):
            pass
        else:
            if filesize == length:
                return file
            elif length is not None and filesize > length:
                raise OSError(errno.EIO, f"file {file!r} is larger than url {url!r}: {filesize} > {length} (in bytes)")
    elif length == 0:
        return file

    if make_reporthook:
        reporthook = make_reporthook(length)
        if isgenerator(reporthook):
            next(reporthook)
            reporthook = reporthook.send
        reporthook = cast(Callable[[int], Any], reporthook)
    else:
        reporthook = None

    if filesize and is_range_request(resp):
        resp.close()
        resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize})
        if not is_range_request(resp):
            raise OSError(errno.EIO, f"range request failed: {url!r}")

    with resp:
        fsrc_read = resp.read
        fdst_write = fdst.write
        if filesize:
            if is_range_request(resp):
                if reporthook:
                    reporthook(filesize)
            else:
                bio_skip_bytes(resp, filesize, callback=reporthook)

        while (chunk := fsrc_read(chunksize)):
            fdst_write(chunk)
            if reporthook:
                reporthook(len(chunk))

    return file


def requests_download(
    url: str, 
    urlopen: Callable = Session().get, 
    **kwargs, 
) -> str | SupportsWrite[bytes]:
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

