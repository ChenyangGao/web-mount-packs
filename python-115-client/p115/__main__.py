#!/usr/bin/env python3
# encoding: utf-8

from os.path import dirname
from sys import path

path.insert(0, dirname(__file__))

from cmd import parser # type: ignore

args = parser.parse_args()
args.func(args)

