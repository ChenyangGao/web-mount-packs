#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "calculate file hashes"

from argparse import ArgumentParser, RawTextHelpFormatter
from hashlib import algorithms_available
from os.path import isfile

from iterdir import iterdir


def parse_args(argv=None):
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument("paths", metavar="path", nargs="*", help="file path(s) to be downloaded, if omitted, read from stdin (one path per line)")
    parser.add_argument("-hs", "--hashs", metavar="hash", nargs="*", default=["md5"], choices=algorithms_available, help="hash algorithms, default to 'md5'")
    parser.add_argument("-s", "--start", default=0, type=int, help="start from file offset, default to 0 (start of file)")
    parser.add_argument("-t", "--stop", type=int, help="stop until file offset, default to None (end of file)")
    parser.add_argument("-v", "--version", action="store_true", help="print the current version")
    args = parser.parse_args(argv)
    if args.version:
        from hashtools import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args

 
def main(argv=None):
    from hashtools import file_mdigest 

    args = parse_args(argv)

    if args.paths:
        paths = args.paths
    else:
        from sys import stdin
        paths = (l.removesuffix("\n") for l in stdin)

    hashalgs = args.hashs
    start = args.start
    stop = args.stop
    try:
        for path in paths:
            if not path:
                continue
            for file in iterdir(path, min_depth=0, max_depth=-1, predicate=lambda p: isfile(p)):
                size, hashes = file_mdigest(open(file, "rb"), *hashalgs, start=start, stop=stop)
                print({"path": file, "size": size, **{alg: h.hexdigest() for alg, h in zip(hashalgs, hashes)}})
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

