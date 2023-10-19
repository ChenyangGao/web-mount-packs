#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"


import sys


if sys.version_info < (3, 10):
    msg = f"""\
Python version at least 3.10, got
    * executable: {sys.executable!r}
    * version: {sys.version}
    * version_info: {sys.version_info!r}
"""
    raise RuntimeError(msg)


if __name__ == "__main__":
    from cli import run

    run()

