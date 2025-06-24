#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = [
    "set", "clear", "reverse", "test", "set_bit", "clear_bit", "reverse_bit", "test_bit", 
    "reverse_cover", "bit_length", "count_1", "count_0", "int_to_bytes", "int_from_bytes", 
    "is_pow2", "sup_pow2", "inf_pow2", "floordiv", "ceildiv", 
]

from typing import Literal


_to_bytes = int.to_bytes
_from_bytes = int.from_bytes


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
        length = bit_length(n)
    return n ^ ((1 << length) - 1)


bit_length = int.bit_length
count_1 = int.bit_count


def count_0(n: int, /) -> int:
    return bit_length(n) - count_1(n)


def int_to_bytes(
    n: int, 
    /, 
    byteorder: Literal["little", "big"] = "big", 
    signed: bool = False, 
) -> bytes:
    return _to_bytes(
        n, 
        length=(bit_length(n) + 0b111) >> 3, 
        byteorder=byteorder, 
        signed=signed
    )


def int_from_bytes(
    b: bytes | bytearray | memoryview, 
    /, 
    byteorder: Literal["little", "big"] = "big", 
    signed: bool = False, 
) -> int:
    return _from_bytes(b, byteorder=byteorder, signed=signed)


def is_pow2(n: int, /) -> bool:
    "是否 2 的自然数次幂"
    return n > 0 and n & (n - 1) == 0


def sup_pow2(n: int, /) -> int:
    "不大于 x 的最大的 2 的自然数次幂"
    if n < 1:
        raise ValueError(f"{n!r} < 1")
    return 1 << bit_length(n - 1)


def inf_pow2(n: int, /) -> int:
    "不小于 x 的最小的 2 的自然数次幂"
    if n <= 1:
        return 1
    return 1 << (bit_length(n) - 1)


def floordiv(x: int, y: int, /) -> int:
    "向下整除的除法"
    return x // y


def ceildiv(x: int, y: int, /) -> int:
    "向上整除的除法"
    return -(-x // y)

