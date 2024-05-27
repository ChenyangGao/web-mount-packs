#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

from argparse import ArgumentParser, RawTextHelpFormatter

from . import startfile, __version__

def main():
    parser = ArgumentParser(
        description="Start file(s) with its/their associated application.", 
        formatter_class=RawTextHelpFormatter, 
    )
    parser.add_argument("paths", metavar="path", nargs="*", help="path to file or directory")
    parser.add_argument("-v", "--version", action="store_true", help="print the current version")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    paths = args.paths
    if not paths:
        parser.parse_args(["-h"])

    for path in paths:
        startfile(path)

if __name__ == "__main__":
    main()
