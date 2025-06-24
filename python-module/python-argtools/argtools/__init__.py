#!/usr/bin/env python3
# coding: utf-8

"""This module provides several classes, which are used to collect 
some arguments at one time and then use them repeatedly later.
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["argcount", "Args", "UpdativeArgs", "Call"]

from collections.abc import Callable
from copy import copy
from functools import partial, update_wrapper
from inspect import getfullargspec
from typing import cast, Any


def argcount(func: Callable, /) -> int:
    if isinstance(func, partial):
        return max(0, argcount(func.func) - len(func.args))
    try:
        return func.__code__.co_argcount
    except AttributeError:
        return len(getfullargspec(func).args)


class Args:
    """Takes some positional arguments and keyword arguments, 
    and put them into an instance, which can be used repeatedly 
    every next time.

    Fields::
        self.args: the collected positional arguments
        self.kwargs: the collected keyword arguments
    """
    __slots__ = ("args", "kwargs")

    def __init__(self, /, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__[T](self, /, func: Callable[..., T]) -> T:
        """Pass in the collected positional arguments and keyword 
        arguments when calling the callable `func`."""
        return func(*self.args, **self.kwargs)

    def __copy__(self, /):
        return type(self)(*self.args, **self.kwargs)

    def __eq__(self, other):
        if isinstance(other, Args):
            return self.args == other.args and self.kwargs == other.kwargs
        return False

    def __iter__(self, /):
        return iter((self.args, self.kwargs))

    def __repr__(self):
        return "%s(%s)" % (
            type(self).__qualname__,
            ", ".join((
                *map(repr, self.args),
                *("%s=%r" % e for e in self.kwargs.items()),
            )),
        )

    @classmethod
    def call[T](cls, /, func: Callable[..., T], args: Any = ()) -> T:
        """Call the callable `func` and pass in the arguments `args`.

        The actual behavior as below:
            if isinstance(args, Args):
                return args(func)
            elif type(args) is tuple:
                return func(*args)
            elif type(args) is dict:
                return func(**args)
            return func(args)
        """
        if isinstance(args, Args):
            return args(func)
        args_type = type(args)
        if args_type == tuple:
            return func(*args)
        elif args_type == dict:
            return func(**args)
        else:
            return func(args)


class UpdativeArgs(Args):
    """Takes some positional arguments and keyword arguments, 
    and put them into an instance, which can be used repeatedly 
    every next time.
    This derived class provides some methods to update the
    collected arguments.

    Fields::
        self.args: the collected positional arguments
        self.kwargs: the collected keyword arguments
    """
    __slots__ = ("args", "kwargs")

    def extend(self, /, *args, **kwargs):
        """Extend the collected arguments.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.extend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(1, 2, 3, 7, 8, x=4, y=5, z=6, r=0)
        >>> args is args2
        True
        """
        if args:
            self.args += args
        if kwargs:
            kwargs0 = self.kwargs
            kwargs0.update(
                (k, kwargs[k])
                for k in kwargs.keys() - kwargs0.keys()
            )
        return self

    def copy_extend(self, /, *args, **kwargs):
        """Extend the collected arguments in a copied instance.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_extend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(1, 2, 3, 7, 8, x=4, y=5, z=6, r=0)
        >>> args is args2
        False
        """
        return copy(self).extend(*args, **kwargs)

    def prepend(self, /, *args, **kwargs):
        """Prepend the collected arguments.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.prepend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(7, 8, 1, 2, 3, x=9, y=5, z=6, r=0)
        >>> args is args2
        True
        """
        if args:
            self.args = args + self.args
        if kwargs:
            self.kwargs.update(kwargs)
        return self

    def copy_prepend(self, /, *args, **kwargs):
        """Prepend the collected arguments in a copied instance.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_prepend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(7, 8, 1, 2, 3, x=9, y=5, z=6, r=0)
        >>> args is args2
        False
        """
        return copy(self).prepend(*args, **kwargs)

    def update(self, /, *args, **kwargs):
        """Update the collected arguments.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.update(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(7, 8, 3, x=9, y=5, z=6, r=0)
        >>> args is args2
        True
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args.update(7, 8, 10, 11, x=9, r=0)
        UpdativeArgs(7, 8, 10, 11, x=9, y=5, z=6, r=0)
        """
        if args:
            n = len(args) - len(self.args)
            if n >= 0:
                self.args = args
            else:
                self.args = args + self.args[n:]
        if kwargs:
            self.kwargs.update(kwargs)
        return self

    def copy_update(self, /, *args, **kwargs):
        """Update the collected arguments in a copied instance.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_update(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(7, 8, 3, x=9, y=5, z=6, r=0)
        >>> args is args2
        False

        Idempotence
        >>> args3 = args2.copy_update(7, 8, x=9, r=0)
        >>> args2 == args3
        True

        Idempotence
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_update(7, 8, 10, 11, x=9, r=0)
        >>> args3 = args2.copy_update(7, 8, 10, 11, x=9, r=0)
        >>> args2 == args3
        True
        """
        return copy(self).update(*args, **kwargs)

    def update_extend(self, /, *args, **kwargs):
        """Update and entend the collected arguments.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.update_extend(7, 8, 10, 11, x=9, r=0)
        >>> args2
        UpdativeArgs(1, 2, 3, 11, x=4, y=5, z=6, r=0)
        >>> args is args2
        True
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args.update_extend(7, 8, x=9, r=0)
        UpdativeArgs(1, 2, 3, x=4, y=5, z=6, r=0)
        """
        if args:
            n = len(self.args) - len(args)
            if n < 0:
                self.args += args[n:]
        if kwargs:
            kwargs0 = self.kwargs
            kwargs0.update(
                (k, kwargs[k])
                for k in kwargs.keys() - kwargs0.keys()
            )
        return self

    def copy_update_extend(self, /, *args, **kwargs):
        """Update and extend the collected arguments in
        a copied instance.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_update_extend(7, 8, 10, 11, x=9, r=0)
        >>> args2
        UpdativeArgs(1, 2, 3, 11, x=4, y=5, z=6, r=0)
        >>> args is args2
        False

        Idempotence
        >>> args3 = args2.copy_update_extend(7, 8, 10, 11, x=9, r=0)
        >>> args2 == args3
        True

        Idempotence
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_update_extend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(1, 2, 3, x=4, y=5, z=6, r=0)
        >>> args3 = args2.copy_update_extend(7, 8, x=9, r=0)
        >>> args2 == args3
        True
        """
        return copy(self).update_extend(*args, **kwargs)


class Call[**Params, R](partial):
    """
    """
    def __new__(
        cls, 
        func: Callable[Params, R], 
        /, 
        *args: Params.args, 
        **kwds: Params.kwargs, 
    ):
        if hasattr(func, "func"):
            args = cast(Params.args, getattr(func, "args", ()) + args)
            kwargs: None | dict = None
            try:
                kwargs = getattr(func, "kwargs")
            except AttributeError:
                kwargs = getattr(func, "keywords", None)
            if kwargs:
                kwds = cast(Params.kwargs, {**kwargs, **kwds})
            func = func.func
        return update_wrapper(super().__new__(cls, func, *args, **kwds), func)

    @property
    def kwargs(self, /) -> Params.kwargs:
        return self.keywords

    def __call__(self, /) -> R:
        return self.func(*self.args, **self.kwargs)


if __name__ == "__main__":
    import doctest
    doctest.testmod()

