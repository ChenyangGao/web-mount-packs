#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__all__ = ["urlopen", "download"]

import errno

from collections.abc import Callable, Generator, Mapping, Sequence
from copy import copy
from http.client import HTTPResponse
from http.cookiejar import CookieJar
from inspect import isgenerator
from json import dumps
from os import fsdecode, fstat, makedirs, PathLike
from os.path import abspath, dirname, isdir, join as joinpath
from shutil import COPY_BUFSIZE # type: ignore
from ssl import SSLContext, _create_unverified_context
from typing import cast, Any
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, HTTPSHandler, OpenerDirector, Request

from filewrap import bio_skip_iter, SupportsRead, SupportsWrite
from http_response import get_filename, get_length, is_chunked, is_range_request


if "__del__" not in HTTPResponse.__dict__:
    setattr(HTTPResponse, "__del__", HTTPResponse.close)


def urlopen(
    url: str | Request, 
    method: str = "GET", 
    params: None | str | Mapping | Sequence[tuple[Any, Any]] = None, 
    data: None | bytes | str | Mapping | Sequence[tuple[Any, Any]] = None, 
    json: Any = None, 
    headers: None | dict[str, str] = {"User-agent": ""}, 
    timeout: None | int | float = None, 
    cookies: None | CookieJar = None, 
    proxy: None | tuple[str, str] = None, 
    opener: OpenerDirector = build_opener(HTTPSHandler(context=_create_unverified_context())), 
    context: None | SSLContext = None, 
    origin: None | str = None, 
) -> HTTPResponse:
    if isinstance(url, str) and not urlsplit(url).scheme:
        if origin:
            if not url.startswith("/"):
                url = "/" + url
            url = origin + url
    if params:
        if not isinstance(params, str):
            params = urlencode(params)
    params = cast(None | str, params)
    if json is not None:
        if isinstance(json, bytes):
            data = json
        else:
            data = dumps(json).encode("utf-8")
        if headers:
            headers = {**headers, "Content-type": "application/json"}
        else:
            headers = {"Content-type": "application/json"}
    elif data is not None:
        if isinstance(data, bytes):
            pass
        elif isinstance(data, str):
            data = data.encode("utf-8")
        else:
            data = urlencode(data).encode("latin-1")
    data = cast(None | bytes, data)
    if isinstance(url, Request):
        req = url
        if params:
            req.full_url += "?&"["?" in req.full_url] + params
        if headers:
            for key, val in headers.items():
                req.add_header(key, val)
        if data is not None:
            req.data = data
        req.method = method.upper()
    else:
        if params:
            url += "?&"["?" in url] + params
        req = Request(url, data=data, headers=headers or {}, method=method.upper())
    if proxy:
        req.set_proxy(*proxy)
    if opener is None:
        opener = build_opener()
    if context is not None:
        opener.add_handler(HTTPSHandler(context=context))
    if cookies is not None:
        opener.add_handler(HTTPCookieProcessor(cookies))
    if timeout is None:
        return opener.open(req)
    else:
        return opener.open(req, timeout=timeout)


def download(
    url: str, 
    file: bytes | str | PathLike | SupportsWrite[bytes] = "", 
    resume: bool = False, 
    chunksize: int = COPY_BUFSIZE, 
    headers: None | dict[str, str] = None, 
    make_reporthook: None | Callable[[None | int], Callable[[int], Any] | Generator[int, Any, Any]] = None, 
    **urlopen_kwargs, 
) -> str | SupportsWrite[bytes]:
    """Download a URL into a file.

    Example::

        1. use `make_reporthook` to show progress:

            You can use the following function to show progress for the download task

            .. code: python

                from time import perf_counter

                def progress(total=None):
                    read_num = 0
                    start_t = perf_counter()
                    while True:
                        read_num += yield
                        speed = read_num / 1024 / 1024 / (perf_counter() - start_t)
                        print(f"\r\x1b[K{read_num} / {total} | {speed:.2f} MB/s", end="", flush=True)

            Or use the following function for more real-time speed

            .. code: python

                from collections import deque
                from time import perf_counter
    
                def progress(total=None):
                    dq = deque(maxlen=64)
                    read_num = 0
                    dq.append((read_num, perf_counter()))
                    while True:
                        read_num += yield
                        cur_t = perf_counter()
                        speed = (read_num - dq[0][0]) / 1024 / 1024 / (cur_t - dq[0][1])
                        print(f"\r\x1b[K{read_num} / {total} | {speed:.2f} MB/s", end="", flush=True)
                        dq.append((read_num, cur_t))
    """
    if headers:
        headers = {**headers, "Accept-encoding": "identity"}
    else:
        headers = {"Accept-encoding": "identity"}

    if chunksize <= 0:
        chunksize = COPY_BUFSIZE

    resp: HTTPResponse = urlopen(url, headers=headers, **urlopen_kwargs)
    content_length = get_length(resp)
    if content_length == 0 and is_chunked(resp):
        content_length = None

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
            fileno = getattr(fdst, "fileno")()
            filesize = fstat(fileno).st_size
        except (AttributeError, OSError):
            pass
        else:
            if filesize == content_length:
                return file
            if filesize and is_range_request(resp):
                if filesize == content_length:
                    return file
            elif content_length is not None and filesize > content_length:
                raise OSError(
                    errno.EIO, 
                    f"file {file!r} is larger than url {url!r}: {filesize} > {content_length} (in bytes)", 
                )

    reporthook_close: None | Callable = None
    if callable(make_reporthook):
        reporthook = make_reporthook(content_length)
        if isgenerator(reporthook):
            reporthook_close = reporthook.close
            next(reporthook)
            reporthook = reporthook.send
        else:
            reporthook_close = getattr(reporthook, "close", None)
        reporthook = cast(Callable[[int], Any], reporthook)
    else:
        reporthook = None

    try:
        if filesize:
            if is_range_request(resp):
                resp.close()
                resp = urlopen(url, headers={**headers, "Range": "bytes=%d-" % filesize}, **urlopen_kwargs)
                if not is_range_request(resp):
                    raise OSError(errno.EIO, f"range request failed: {url!r}")
                if reporthook is not None:
                    reporthook(filesize)
            elif resume:
                for _ in bio_skip_iter(resp, filesize, callback=reporthook):
                    pass

        fsrc_read = resp.read 
        fdst_write = fdst.write
        while (chunk := fsrc_read(chunksize)):
            fdst_write(chunk)
            if reporthook is not None:
                reporthook(len(chunk))
    finally:
        resp.close()
        if callable(reporthook_close):
            reporthook_close()

    return file

