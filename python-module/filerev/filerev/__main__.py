#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "Reverse output each line of a file"

from argparse import ArgumentParser

parser = ArgumentParser(description=__doc__)
parser.add_argument("path", nargs="?", help="path to a file")
parser.add_argument("-v", "--version", action="store_true", help="print the current version")
args = parser.parse_args()
if args.version:
    from filerev import __version__
    print(".".join(map(str, __version__)))
    raise SystemExit(0)

from sys import stdout

write = stdout.buffer.raw.write # type: ignore
try:
    if args.path:
        from filerev import file_reviter

        lines = file_reviter(open(args.path, "rb"))
    else:
        from sys import stdin

        lines = reversed(stdin.buffer.readlines())
    for line in lines:
        if not line.endswith(b"\n"):
            line += b"\n"
        write(line)
except BrokenPipeError:
    from sys import stderr
    stderr.close()
except KeyboardInterrupt:
    pass

