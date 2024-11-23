#!/usr/bin/env python3
# encoding: utf-8

def main():
    from p115servedb.init import parser

    args = parser.parse_args()
    if args.version:
        from p115servedb import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    if args.func:
        args.func(args)
    else:
        parser.parse_args(["-h"])

if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

