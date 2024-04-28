#!/usr/bin/env python3
# encoding: utf-8

from alist.cmd import parser

args = parser.parse_args()
if args.func:
    args.func(args)
else:
    parser.parse_args(["-h"])

