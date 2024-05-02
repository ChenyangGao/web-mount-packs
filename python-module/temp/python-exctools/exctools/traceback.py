#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["get_traceback_exceptipn", "get_traceback_string"]

from sys import exc_info
from traceback import TracebackException


def get_traceback_exceptipn(exc=None):
    if exc is None:
        return TracebackException(*exc_info())
    return TracebackException(type(exc), exc, exc.__traceback__)


def get_traceback_string(exc=None):
    tb_exc = get_traceback_exceptipn(exc)
    return "".join(tb_exc.format())

