#!/usr/bin/env python3
# encoding: utf-8

__all__ = ["parser", "subparsers"]

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(
    description="clouddrive 命令行工具集", 
    formatter_class=RawTextHelpFormatter, 
)
parser.set_defaults(sub="")
subparsers = parser.add_subparsers(required=True)

