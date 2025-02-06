#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["check_response", "DuPanOSError"]

from collections.abc import Awaitable
from errno import EIO
from inspect import isawaitable


class DuPanOSError(OSError):
    ...


def check_response[T: (dict, Awaitable[dict])](resp: T, /) -> T:
    def check(resp: dict, /) -> dict:
        if resp["errno"]:
            raise DuPanOSError(EIO, resp)
        return resp
    if isawaitable(resp):
        async def call():
            return check(await resp)
        return call()
    return resp

