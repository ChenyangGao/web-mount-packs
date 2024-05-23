#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["half_width", "full_width"]

from typing import Final


TRANSMAP_HALF2FULL: Final = {i: i + 65248 for i in range(33, 127)}
TRANSMAP_HALF2FULL[32] = 12288
TRANSMAP_FULL2HALF: Final = {v: k for k, v in TRANSMAP_HALF2FULL.items()}


def half_width(string: str, /) -> str:
    return string.translate(TRANSMAP_FULL2HALF)


def full_width(string: str, /) -> str:
    return string.translate(TRANSMAP_HALF2FULL)

