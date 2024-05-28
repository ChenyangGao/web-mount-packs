#!/usr/bin/env python3
# encoding: utf-8

def main():
    from clouddrive.cmd import parser

    args = parser.parse_args()
    if args.func:
        args.func(args)
    else:
        parser.parse_args(["-h"])

if __name__ == "__main__":
    main()
