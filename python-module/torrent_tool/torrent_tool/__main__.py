#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "(torrent) file to (magnet) link"

from argparse import ArgumentParser, RawTextHelpFormatter
from collections import deque
from os import scandir
from os.path import isdir
from sys import stdout


def parse_args(argv=None):
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument("paths", nargs="*", metavar="path", help="paths to torrent files, use stdin as default")
    parser.add_argument("-i", "--ignore-suffix", action="store_true", help="regardless of the suffix (extension), otherwise only files with the .torrent suffix will be processed")
    parser.add_argument("-f", "--full", action="store_true", help="more detailed query string")
    parser.add_argument("-v", "--version", action="store_true", help="print the current version")
    args = parser.parse_args(argv)
    if args.version:
        from torrent_tool import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args


def main(argv=None):
    from torrent_tool import torrent_to_magnet

    args = parse_args(argv)
    full = args.full
    ignore_suffix = args.ignore_suffix

    paths: deque[str]
    if args.paths:
        paths = deque(args.paths)
    else:
        from sys import stdin
        paths = deque(line.removesuffix("\n") for line in stdin)

    get = paths.popleft
    write = stdout.buffer.raw.write # type: ignore

    try:
        while paths:
            path = get()
            try:
                if isdir(path):
                    paths.extend(p.path for p in scandir(path))
                elif ignore_suffix or path.endswith(".torrent"):
                    try:
                        data = open(path, "rb").read()
                        write(torrent_to_magnet(data, full=full).encode("utf-8"))
                        write(b"\n")
                    except (ValueError, LookupError):
                        pass
            except OSError:
                pass
    except BrokenPipeError:
        from sys import stderr
        stderr.close()
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

