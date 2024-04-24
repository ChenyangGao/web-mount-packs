#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["Flag", "Mask"]

from typing import cast, Never, Self 


class Flag:
    __slots__ = ("value",)
    value: bool

    def __init__(self, value: bool = False, /):
        super().__setattr__("value", value)

    def __bool__(self, /) -> bool:
        return self.value

    def __invert__(self, /) -> Self:
        return type(self)(not self.value)

    def __repr__(self, /) -> str:
        return f"{type(self).__qualname__}({self.value!r})"

    def __setattr__(self, key, val, /) -> Never:
        raise AttributeError("can't set attributes")

    def set(self, /) -> Self:
        super().__setattr__("value", True)
        return self

    def clear(self, /) -> Self:
        super().__setattr__("value", False)
        return self

    def reverse(self, /) -> Self:
        super().__setattr__("value", not self.value)
        return self


class Mask:
    __slots__ = ("value",)
    value: int

    def __init__(self, value: int = 0, /):
        super().__setattr__("value", value)

    def __abs__(self, /) -> Self:
        return type(self)(abs(self.value))

    def __bool__(self, /) -> bool:
        return bool(self.value)

    def __int__(self, /) -> int:
        return self.value

    def __invert__(self, /) -> Self:
        return type(self)(~self.value)

    def __neg__(self, /) -> Self:
        return type(self)(-self.value)

    def __pos__(self, /) -> Self:
        return type(self)(self.value)

    def __eq__(self, o, /) -> bool:
        if isinstance(o, int):
            val = o
        elif isinstance(o, type(self)):
            val = o.value
        else:
            return NotImplemented
        return self.value == val

    def __and__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        return cls(self.value & cast(int, o))

    __rand__ = __and__

    def __iand__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        super().__setattr__("value", self.value & cast(int, o))
        return self

    def __or__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        return cls(self.value | cast(int, o))

    __ror__ = __or__

    def __ior__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        super().__setattr__("value", self.value | cast(int, o))
        return self

    def __xor__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        return cls(self.value ^ cast(int, o))

    __rxor__ = __xor__

    def __ixor__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        super().__setattr__("value", self.value ^ cast(int, o))
        return self

    def __sub__(self, o: int | Self, /) -> Self:
        cls = type(self)
        if isinstance(o, cls):
            o = o.value
        # 🤔 l & ~r == (l | r) ^ r
        return cls(self.value & ~cast(int, o))

    def __isub__(self, o: int | Self, /) -> Self:
        if isinstance(o, type(self)):
            o = o.value
        super().__setattr__("value", self.value & ~cast(int, o))
        return self

    def __repr__(self, /) -> str:
        return f"{type(self).__qualname__}({bin(self.value)})"

    def __setattr__(self, key, val, /) -> Never:
        raise AttributeError("can't set attributes")

    join = __iand__
    set = __ior__
    clear = __isub__
    reverse = __ixor__

    def test(self, o: int | Self, /) -> bool:
        return bool(self & o)

    def set_bit(self, /, offset: int = 0) -> Self:
        return self.set(1 << offset)

    def clear_bit(self, /, offset: int = 0) -> Self:
        return self.clear(1 << offset)

    def reverse_bit(self, /, offset: int = 0) -> Self:
        return self.reverse(1 << offset)

    def test_bit(self, /, offset: int = 0) -> bool:
        return self.test(1 << offset)

    def reverse_cover(self, /, length=None) -> Self:
        if length is None:
            length = self.value.bit_length()
        return self.reverse((1 << length) - 1)

    def count_0(self, /) -> int:
        value = self.value
        return (-1 if value < 0 else 1) * (value.bit_length() - value.bit_count())

    def count_1(self, /) -> int:
        value = self.value
        return (-1 if value < 0 else 1) * value.bit_count()

