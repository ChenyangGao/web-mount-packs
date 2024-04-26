#!/usr/bin/env python3
# encoding: utf-8

from p115.cmd import parser

args = parser.parse_args()
args.func(args)

