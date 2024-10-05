#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "calculate file ed2k hash"

from argparse import ArgumentParser, RawTextHelpFormatter
from json import dumps
from os.path import basename, isfile

from iterdir import iterdir

parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
parser.add_argument("paths", metavar="path", nargs="*", help="file path(s) to be downloaded, if omitted, read from stdin (one path per line)")
parser.add_argument("-v", "--version", action="store_true", help="print the current version")

NAME_TRANSTAB = dict(zip(b"/|", ("%2F", "%7C")))


def parse_args(argv=None):
    args = parser.parse_args(argv)
    if args.version:
        from ed2k import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args

 
def main(argv=None):
    from ed2k import ed2k_hash 

    args = parse_args(argv)

    if args.paths:
        paths = args.paths
    else:
        from sys import stdin
        paths = (l.removesuffix("\n") for l in stdin)

    try:
        for path in paths:
            if not path:
                continue
            for file in iterdir(path, min_depth=0, max_depth=-1, predicate=lambda p: isfile(p)):
                size, ed2k = ed2k_hash(open(file, "rb"))
                print(dumps({
                    "path": file, 
                    "size": size, 
                    "ed2k": ed2k, 
                    "url": f"ed2k://|file|{basename(file).translate(NAME_TRANSTAB)}|{size}|{ed2k}|/", 
                }, ensure_ascii=False))
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

