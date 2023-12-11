#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["download", "requests_download"]

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

from concurrent.futures import ThreadPoolExecutor
from io import TextIOWrapper
from os import fsdecode, fstat, makedirs, PathLike
from os.path import isdir, join as joinpath
from shutil import COPY_BUFSIZE
from typing import cast, Any, BinaryIO, Callable, Mapping, NamedTuple, Optional

from requests import Response, Session

from .file import bio_skip_bytes, SupportsWrite
from .iter import cut_iter
from .response import get_filename, get_length, get_range, get_header, is_chunked, is_range_request
from .urlopen import urlopen


if not hasattr(Response, "__del__"):
    Response.__del__ = Response.close # type: ignore
if not hasattr(Session, "__del__"):
    Session.__del__  = Session.close # type: ignore


class DownloadResult(NamedTuple):
    file: str | BinaryIO | TextIOWrapper
    downloaded_size: int
    total_size: int


def download(
    url: str, 
    file: bytes | str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
    resume: bool = False, 
    chunksize = COPY_BUFSIZE, 
    headers: Optional[Mapping] = None, 
    make_reporthook: Optional[Callable[[Optional[int]], Callable[[int], Any]]] = None, 
    max_workers: int = 1, 
    urlopen: Callable = urlopen, 
    **request_kwargs, 
) -> DownloadResult:
    """
    """
    if headers:
        headers = {**headers, "Accept-Encoding": "identity"}
    else:
        headers = {"Accept-Encoding": "identity"}

    resp = None
    if isinstance(file, TextIOWrapper):
        fdst = file.buffer
    elif hasattr(file, "write"):
        fdst = file
    else:
        file = fsdecode(file)
        if not file or isdir(file):
            resp = urlopen(url, headers=headers, **request_kwargs)
            length = get_length(resp)
            file = joinpath(file, get_filename(resp, "download"))
        fdst = open(file, "ab" if resume else "wb")

    filesize = 0
    if resume:
        try:
            filesize = fstat(fdst.fileno()).st_size
        except (AttributeError, OSError):
            filesize = 0
        else:
            if resp is None:
                if filesize:
                    resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize}, **request_kwargs)
                    length = get_length(resp)
                    if is_range_request(resp):
                        length += filesize
                else:
                    resp = urlopen(url, headers=headers, **request_kwargs)
                    length = get_length(resp)
            if length is None or length == 0 and is_chunked(resp):
                pass
            elif filesize >= length:
                return DownloadResult(file, 0, length)

    if max_workers != 1:
        if resp is None:
            if filesize:
                resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize}, **request_kwargs)
                length = get_length(resp)
                if is_range_request(resp):
                    length += filesize
            else:
                resp = urlopen(url, headers=headers, **request_kwargs)
                length = get_length(resp)
        if length and length - filesize <= chunksize:
            max_workers = 1
        elif is_range_request(resp):
            resp.close()
        else:
            max_workers = 1

    downloaded_size = 0

    if max_workers != 1:
        if make_reporthook:
            reporthook = make_reporthook(length)
        else:
            reporthook = None

        def fetch_chunk(cut):
            start, stop = cut
            with urlopen(url, headers={**headers, "Range": "bytes=%d-%d" % (start, stop-1)}, **request_kwargs) as resp:
                return resp.read()

        with ThreadPoolExecutor(max_workers if max_workers > 0 else None) as executor:
            fdst_write = fdst.write
            if reporthook:
                reporthook(filesize)
            chunk_it = executor.map(fetch, cut_iter(filesize, length, chunksize))
            for chunk in chunk_it:
                downloaded_size += fdst_write(chunk)
                if reporthook:
                    reporthook(len(chunk))

        return DownloadResult(file, downloaded_size, length)

    if resp is None:
        if filesize:
            headers["Range"] = "bytes=%d-" % filesize
        else:
            headers["Accept-Encoding"] = "gzip"
        resp = urlopen(url, headers=headers, **request_kwargs)
        length = get_length(resp)
        if is_range_request(resp):
            length += filesize
    elif is_range_request(resp):
        rng = get_range(resp)
        if filesize and (not rng or rng[0] < filesize):
            resp.close()
            resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize}, **request_kwargs)

    if make_reporthook:
        reporthook = make_reporthook(length)
    else:
        reporthook = None

    with resp:
        fdst_write = fdst.write
        if is_range_request(resp):
            fsrc_read = resp.read
            if reporthook:
                reporthook(filesize)
            chunk_it = iter(lambda: fsrc_read(chunksize), b"")
        else:
            content_encoding = get_header("Content-Encoding") or ""
            if content_encoding in ("", "identity"):
                pass
            elif content_encoding in ("gzip", "deflate"):
                fsrc = __import__("gzip").open(fsrc)
            elif content_encoding == "bzip2":
                fsrc = __import__("bz2").open(fsrc)
            elif content_encoding == "application/x-xz":
                fsrc = __import__("lzma").open(fsrc)
            else:
                raise ValueError(f"unable to decode this Content-Encoding: {content_encoding!r}")
            fsrc_read = fsrc.read
            bio_skip_bytes(fsrc, filesize, callback=reporthook)
            chunk_it = iter(lambda: fsrc_read(chunksize), b"")

        for chunk in chunk_it:
            downloaded_size += fdst_write(chunk)
            if reporthook:
                reporthook(len(chunk))

    return DownloadResult(file, downloaded_size, filesize + downloaded_size)


def requests_download(
    url: str, 
    file: bytes | str | PathLike | SupportsWrite[bytes] | TextIOWrapper = "", 
    resume: bool = False, 
    chunksize = COPY_BUFSIZE, 
    headers: Optional[Mapping] = None, 
    make_reporthook: Optional[Callable[[Optional[int]], Callable[[int], Any]]] = None, 
    max_workers: int = 1, 
    urlopen: Callable = Session().get, 
    **request_kwargs, 
) -> DownloadResult:
    """
    """
    request_kwargs["stream"] = True

    if headers:
        headers = {**headers, "Accept-Encoding": "identity"}
    else:
        headers = {"Accept-Encoding": "identity"}

    resp = None
    if isinstance(file, TextIOWrapper):
        fdst = file.buffer
    elif hasattr(file, "write"):
        fdst = file
    else:
        file = fsdecode(file)
        if not file or isdir(file):
            resp = urlopen(url, headers=headers, **request_kwargs)
            resp.raise_for_status()
            length = get_length(resp)
            file = joinpath(file, get_filename(resp, "download"))
        fdst = open(file, "ab" if resume else "wb")

    filesize = 0
    if resume:
        try:
            filesize = fstat(fdst.fileno()).st_size
        except (AttributeError, OSError):
            filesize = 0
        else:
            if resp is None:
                if filesize:
                    resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize}, **request_kwargs)
                    resp.raise_for_status()
                    length = get_length(resp)
                    if is_range_request(resp):
                        length += filesize
                else:
                    resp = urlopen(url, headers=headers, **request_kwargs)
                    resp.raise_for_status()
                    length = get_length(resp)
            if length is None or length == 0 and is_chunked(resp):
                pass
            elif filesize >= length:
                return DownloadResult(file, 0, length)

    if max_workers != 1:
        if resp is None:
            if filesize:
                resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize}, **request_kwargs)
                resp.raise_for_status()
                length = get_length(resp)
                if is_range_request(resp):
                    length += filesize
            else:
                resp = urlopen(url, headers=headers, **request_kwargs)
                resp.raise_for_status()
                length = get_length(resp)
        if length and length - filesize <= chunksize:
            max_workers = 1
        elif is_range_request(resp):
            resp.close()
        else:
            max_workers = 1

    downloaded_size = 0

    if max_workers != 1:
        if make_reporthook:
            reporthook = make_reporthook(length)
        else:
            reporthook = None

        def fetch_chunk(cut):
            start, stop = cut
            with urlopen(url, headers={**headers, "Range": "bytes=%d-%d" % (start, stop-1)}, **request_kwargs) as resp:
                resp.raise_for_status()
                return resp.content

        with ThreadPoolExecutor(max_workers if max_workers > 0 else None) as executor:
            fdst_write = fdst.write
            if reporthook:
                reporthook(filesize)
            chunk_it = executor.map(fetch, cut_iter(filesize, length, chunksize))
            for chunk in chunk_it:
                downloaded_size += fdst_write(chunk)
                if reporthook:
                    reporthook(len(chunk))

        return DownloadResult(file, downloaded_size, length)

    if resp is None:
        if filesize:
            headers["Range"] = "bytes=%d-" % filesize
        else:
            headers["Accept-Encoding"] = "gzip"
        resp = urlopen(url, headers=headers, **request_kwargs)
        resp.raise_for_status()
        length = get_length(resp)
        if is_range_request(resp):
            length += filesize
    elif is_range_request(resp):
        rng = get_range(resp)
        if filesize and (not rng or rng[0] < filesize):
            resp.close()
            resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize}, **request_kwargs)
            resp.raise_for_status()

    if make_reporthook:
        reporthook = make_reporthook(length)
    else:
        reporthook = None

    with resp:
        fdst_write = fdst.write
        if is_range_request(resp):
            fsrc_read = resp.raw.read
            if reporthook:
                reporthook(filesize)
            chunk_it = iter(lambda: fsrc_read(chunksize), b"")
        else:
            def chunk_iter():
                remaining_bytes_to_skip = filesize
                for chunk in resp.iter_content(chunk_size=chunksize):
                    if remaining_bytes_to_skip:
                        chunk_size = len(chunk)
                        if remaining_bytes_to_skip >= chunk_size:
                            remaining_bytes_to_skip -= chunk_size
                            if reporthook:
                                reporthook(chunk_size)
                        else:
                            if reporthook:
                                reporthook(remaining_bytes_to_skip)
                            yield chunk[remaining_bytes_to_skip:]
                            remaining_bytes_to_skip = 0
                    else:
                        yield chunk
            chunk_it = chunk_iter()

        for chunk in chunk_it:
            downloaded_size += fdst_write(chunk)
            if reporthook:
                reporthook(len(chunk))

    return DownloadResult(file, downloaded_size, filesize + downloaded_size)

