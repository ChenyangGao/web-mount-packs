#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["argcount"]

from collections.abc import Callable
from inspect import getfullargspec


def argcount(func: Callable) -> int:
    try:
        return func.__code__.co_argcount
    except AttributeError:
        return len(getfullargspec(func).args)

