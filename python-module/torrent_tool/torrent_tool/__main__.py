#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "torrent to magnet"

from argparse import ArgumentParser

parser = ArgumentParser(description=__doc__)
parser.add_argument("files", nargs="*", help="paths to torrent files")
parser.add_argument("-f", "--full", action="store_true", help="append more detailed queries")
parser.add_argument("-v", "--version", action="store_true", help="print the current version")
args = parser.parse_args()
if args.version:
    from torrent_tool import __version__
    print(".".join(map(str, __version__)))
    raise SystemExit(0)
if not args.files:
    parser.parse_args(["-h"])

from os import scandir
from os.path import isdir
from sys import stdout

from torrent_tool import torrent_to_magnet

write = stdout.buffer.raw.write # type: ignore
files = args.files
full = args.full
try:
    for file in files:
        if isdir(file):
            files.extend(scandir(file))
        else:
            try:
                data = open(file, "rb").read()
                write(torrent_to_magnet(data, full=full).encode("utf-8"))
                write(b"\n")
            except (ValueError, LookupError):
                pass
except BrokenPipeError:
    from sys import stderr
    stderr.close()
except KeyboardInterrupt:
    pass

