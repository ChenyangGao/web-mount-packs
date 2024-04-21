#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["Flag", "Mask"]

from typing import Generic, Never, Self, TypeVar 


class Flag:
    __slots__ = ("value",)
    value: bool

    def __init__(self, initial_value: bool = False, /):
        self.__dict__["value"] = bool(initial_value)

    def __bool__(self, /) -> bool:
        return self.value

    def __invert__(self, /) -> Self:
        return type(self)(not self.value)

    def __repr__(self, /) -> str:
        return f"{type(self).__qualname__}({self.value!r})"

    def __setattr__(self, key, val, /) -> Never:
        raise AttributeError("can't set attributes")

    def set(self, /):
        self.__dict__["value"] = True

    def clear(self, /):
        self.__dict__["value"] = False

    def reverse(self, /):
        self.__dict__["value"] = not self.value


class Mask:
    __slots__ = ("value",)
    value: int

    def __init__(self, value: int = 0, /):
        self.__dict__["value"] = value

    def __eq__(self, o: int | Self, /) -> bool:
        if isinstance(o, type(self)):
            o = o.value
        return self.value == o

    def __invert__(self, /) -> Self:
        return type(self)(~self.value)

    def __and__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        return cls(self.value & o)

    __rand__ = __and__

    def __iand__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        self.__dict__["value"] = self.value & o
        return self

    def __or__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        return cls(self.value | o)

    __ror__ = __or__

    def __ior__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        self.__dict__["value"] = self.value | o
        return self

    def __xor__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        return cls(self.value ^ o)

    __rxor__ = __xor__

    def __ixor__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        self.__dict__["value"] = self.value ^ o
        return self

    def __sub__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        # 🤔 l & ~r == (l | r) ^ r
        return cls(self.value & ~o)

    def __isub__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        self.__dict__["value"] = self.value & ~o
        return self

    def __repr__(self, /) -> str:
        return f"{type(self).__qualname__}({bin(self.value)})"

    def __setattr__(self, key, val, /) -> Never:
        raise AttributeError("can't set attributes")

    def count_0(self, /) -> int:
        return self.value.bit_length() - self.value.bit_count()

    def count_1(self, /) -> int:
        return self.value.bit_count()

    join = __iand__
    set = __ior__
    clear = __isub__
    reverse = __ixor__

    def test(self, o: int | Self, /) -> bool:
        return bool(self & o)

    def set_bit(self, /, offset: int = 0) -> Self:
        return self |= 1 << offset

    def clear_bit(self, /, offset: int = 0) -> Self:
        return self &= ~(1 << offset)

    def reverse_bit(self, /, offset: int = 0) -> Self:
        return self ^= 1 << offset

    def test_bit(self, /, offset: int = 0) -> bool:
        return bool(self & (1 << offset))

    def reverse_cover(self, /) -> Self:
        return self.reverse((1 << self.value.bit_length()) - 1)


class IntMask(int):
    ...

