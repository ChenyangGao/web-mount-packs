#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "python url downloader"

from argparse import ArgumentParser, RawTextHelpFormatter
from collections import deque
from collections.abc import Callable
from functools import partial
from os import makedirs
from shutil import COPY_BUFSIZE # type: ignore
from time import perf_counter

def parse_args():
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument("urls", metavar="url", nargs="*", help="URL(s) to be downloaded, if omitted, read from stdin (one URL per line)")
    parser.add_argument("-d", "--savedir", default="", help="path to the downloaded file")
    parser.add_argument("-r", "--resume", action="store_true", help="skip downloaded data")
    parser.add_argument("-hs", "--headers", help="dictionary of HTTP Headers to send with")
    parser.add_argument("-ur", "--use-request", choices=("urlopen", "requests", "urllib3", "httpx"), default="urlopen", help="choose a request method")
    parser.add_argument("-v", "--version", action="store_true", help="print the current version")
    args = parser.parse_args()
    if args.version:
        from download import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args


def headers_str_to_dict(headers: str, /) -> dict[str, str]:
    return dict(
        header.split(": ", 1) 
        for header in headers.strip("\n").split("\n")
    )


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


def main():
    args = parse_args()

    from download import download

    urlopen: Callable
    from download import DEFAULT_ITER_BYTES as iter_bytes
    match args.use_request:
        case "urlopen":
            from urlopen import urlopen
        case "requests":
            try:
                from requests import Session
                from requests_request import request # type: ignore
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "requests_request"], check=True)
                from requests import Session
                from requests_request import request # type: ignore
            urlopen = partial(request, session=Session())
            iter_bytes = lambda resp: resp.iter_content(COPY_BUFSIZE)
        case "urllib3":
            try:
                from urllib3_request import request as urlopen
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "urllib3_request"], check=True)
                from urllib3_request import request as urlopen
        case "httpx":
            try:
                from httpx import Client
                from httpx_request import request # type: ignore
            except ImportError:
                from sys import executable
                from subprocess import run
                run([executable, "-m", "pip", "install", "-U", "httpx_request"], check=True)
                from httpx import Client
                from httpx_request import request # type: ignore
            urlopen = partial(request, session=Client())
            iter_bytes = lambda resp: resp.iter_bytes(COPY_BUFSIZE)

    if args.urls:
        urls = args.urls
    else:
        from sys import stdin
        urls = (l.removesuffix("\n") for l in stdin)

    savedir = args.savedir
    if savedir:
        makedirs(savedir, exist_ok=True)

    try:
        headers = args.headers
        if headers is not None:
            headers = headers_str_to_dict(headers)
        for url in urls:
            if not url:
                continue
            try:
                file = download(
                    url, 
                    file=savedir, 
                    resume=args.resume, 
                    make_reporthook=progress, 
                    headers=headers, 
                    urlopen=urlopen, 
                    iter_bytes=iter_bytes, 
                )
                print(f"\r\x1b[K\x1b[1;32mDOWNLOADED\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n |_ ⏬ \x1b[4;34m{file!r}\x1b[0m")
            except Exception as e:
                print(f"\r\x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n  |_ 🙅 \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
    except (EOFError, KeyboardInterrupt):
        pass
    except BrokenPipeError:
        from sys import stderr
        stderr.close()


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

