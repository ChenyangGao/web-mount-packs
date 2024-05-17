#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = [
    "set", "clear", "reverse", "test", "set_bit", "clear_bit", "reverse_bit", "test_bit", 
    "reverse_cover", "count_0", "count_1", "int_to_bytes", "int_from_bytes", "is_pow2", 
    "sup_pow2", "inf_pow2", "ceildiv", 
]

from sys import byteorder
from typing import Literal


def set(n: int, /, val: int) -> int:
    return n | val


def clear(n: int, /, val: int) -> int:
    return n & ~val


def reverse(n: int, /, val: int) -> int:
    return n ^ val


def test(n: int, /, val: int) -> int:
    return bool(n & val)


def set_bit(n: int, /, offset: int = 0) -> int:
    return n | (1 << offset)


def clear_bit(n: int, /, offset: int = 0) -> int:
    return n & ~(1 << offset)


def reverse_bit(n: int, /, offset: int = 0) -> int:
    return n ^ (1 << offset)


def test_bit(n: int, /, offset: int = 0) -> int:
    return bool(n & (1 << offset))


def reverse_cover(
    n: int, 
    /, 
    length: None | int = None, 
) -> int:
    if length is None:
        length = n.bit_length()
    return n ^ ((1 << length) - 1)


def count_0(n: int, /) -> int:
    return (-1 if n < 0 else 1) * (n.bit_length() - n.bit_count())


def count_1(n: int, /) -> int:
    return (-1 if n < 0 else 1) * n.bit_count()


def int_to_bytes(
    n: int, 
    /, 
    byteorder: Literal["little", "big"] = byteorder, 
    signed: bool = True, 
) -> bytes:
    return int.to_bytes(
        n, 
        length=(n.bit_length() + 0b111) >> 3, 
        byteorder=byteorder, 
        signed=signed
    )


def int_from_bytes(
    b: bytes | bytearray | memoryview, 
    /, 
    byteorder: Literal["little", "big"] = byteorder, 
    signed: bool = True, 
) -> int:
    return int.from_bytes(b, byteorder=byteorder, signed=signed)


def is_pow2(n: int, /) -> bool:
    return n > 0 and n & (n - 1) == 0


def sup_pow2(n: int, /) -> int:
    if n <= 0:
        return 1
    elif n & (n - 1) == 0:
        return n
    else:
        return 1 << n.bit_length()


def inf_pow2(n: int, /) -> int:
    if n <= 0:
        return 0
    else:
        return 1 << (n.bit_length() - 1)


def ceildiv(x: int, y: int, /) -> int:
    return -int(-x // y)

