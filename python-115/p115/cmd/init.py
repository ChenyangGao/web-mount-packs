#!/usr/bin/env python3
# encoding: utf-8

__all__ = ["parser", "subparsers"]

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    description="python-115 命令行工具集", 
    formatter_class=RawTextHelpFormatter, 
)
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.set_defaults(func=None)
subparsers = parser.add_subparsers()

