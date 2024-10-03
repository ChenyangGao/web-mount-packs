#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "python urlopen"

from argparse import ArgumentParser, RawTextHelpFormatter
from collections import deque
from time import perf_counter


parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
parser.add_argument("url", nargs="?", help="URL to be downloaded")
parser.add_argument("-o", "--output-file", help="file path to be downloaded, if omitted, print into stdout")
parser.add_argument("-r", "--resume", action="store_true", help="skip downloaded data")
parser.add_argument("-hs", "--headers", help="dictionary of HTTP Headers to send with")
parser.add_argument("-v", "--version", action="store_true", help="print the current version")


def parse_args(argv=None):
    args = parser.parse_args(argv)
    if args.version:
        from urlopen import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    if not args.url:
        parser.parse_args(["-h"])
    return args


def headers_str_to_dict(headers: str, /) -> dict[str, str]:
    return dict(
        header.split(": ", 1) 
        for header in headers.strip("\n").split("\n")
    )


def progress(total: None | int = None):
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


def main(argv=None):
    args = parse_args(argv)

    from urlopen import download

    url = args.url

    headers = args.headers
    if headers is not None:
        headers = headers_str_to_dict(headers)

    output_file = args.output_file
    if output_file:
        from os.path import dirname
        dir_ = dirname(output_file)
        if dir_:
            from os import makedirs
            makedirs(dir_, exist_ok=True)

        download(
            url, 
            output_file, 
            resume=args.resume, 
            make_reporthook=progress, 
            headers=headers, 
        )
    else: 
        from sys import stdout

        download(
            url, 
            stdout.buffer, 
            headers=headers, 
        )


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

