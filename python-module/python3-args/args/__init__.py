#!/usr/bin/env python3
# coding: utf-8

"""This module provides several classes, which are used to collect 
some arguments at one time and then use them repeatedly later.
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["argcount", "Args", "UpdativeArgs"]

from collections.abc import Callable
from copy import copy
from inspect import getfullargspec
from typing import Any, Callable, Generic, ParamSpec, TypeVar


T = TypeVar("T")
P = ParamSpec("P")


def argcount(func: Callable) -> int:
    try:
        return func.__code__.co_argcount
    except AttributeError:
        return len(getfullargspec(func).args)


class Args(Generic[T, P]):
    """Takes some positional arguments and keyword arguments, 
    and put them into an instance, which can be used repeatedly 
    every next time.

    Fields::
        self.pargs: the collected positional arguments
        self.kargs: the collected keyword arguments
    """
    __slots__ = ("pargs", "kargs")

    def __init__(self, /, *pargs, **kargs):
        self.pargs: P.args = pargs
        self.kargs: P.kwargs = kargs

    def __call__(self, /, func: Callable[..., T]) -> T:
        """Pass in the collected positional arguments and keyword 
        arguments when calling the callable `func`."""
        return func(*self.pargs, **self.kargs)

    def __copy__(self, /):
        return type(self)(*self.pargs, **self.kargs)

    def __eq__(self, other):
        if isinstance(other, Args):
            return self.pargs == other.pargs and self.kargs == other.kargs
        return False

    def __iter__(self, /):
        return iter((self.pargs, self.kargs))

    def __repr__(self):
        return "%s(%s)" % (
            type(self).__qualname__,
            ", ".join((
                *map(repr, self.pargs),
                *("%s=%r" % e for e in self.kargs.items()),
            )),
        )

    @classmethod
    def call(cls, /, func: Callable[..., T], args: Any = ()) -> T:
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
        type_ = type(args)
        if type_ is tuple:
            return func(*args)
        elif type_ is dict:
            return func(**args)
        return func(args)


class UpdativeArgs(Args):
    """Takes some positional arguments and keyword arguments, 
    and put them into an instance, which can be used repeatedly 
    every next time.
    This derived class provides some methods to update the
    collected arguments.

    Fields::
        self.pargs: the collected positional arguments
        self.kargs: the collected keyword arguments
    """
    __slots__ = ("pargs", "kargs")

    def extend(self, /, *pargs, **kargs):
        """Extend the collected arguments.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.extend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(1, 2, 3, 7, 8, x=4, y=5, z=6, r=0)
        >>> args is args2
        True
        """
        if pargs:
            self.pargs += pargs
        if kargs:
            kargs0 = self.kargs
            kargs0.update(
                (k, kargs[k])
                for k in kargs.keys() - kargs0.keys()
            )
        return self

    def copy_extend(self, /, *pargs, **kargs):
        """Extend the collected arguments in a copied instance.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_extend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(1, 2, 3, 7, 8, x=4, y=5, z=6, r=0)
        >>> args is args2
        False
        """
        return copy(self).extend(*pargs, **kargs)

    def prepend(self, /, *pargs, **kargs):
        """Prepend the collected arguments.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.prepend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(7, 8, 1, 2, 3, x=9, y=5, z=6, r=0)
        >>> args is args2
        True
        """
        if pargs:
            self.pargs = pargs + self.pargs
        if kargs:
            self.kargs.update(kargs)
        return self

    def copy_prepend(self, /, *pargs, **kargs):
        """Prepend the collected arguments in a copied instance.

        Examples::
        >>> args = UpdativeArgs(1, 2, 3, x=4, y=5, z=6)
        >>> args2 = args.copy_prepend(7, 8, x=9, r=0)
        >>> args2
        UpdativeArgs(7, 8, 1, 2, 3, x=9, y=5, z=6, r=0)
        >>> args is args2
        False
        """
        return copy(self).prepend(*pargs, **kargs)

    def update(self, /, *pargs, **kargs):
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
        if pargs:
            n = len(pargs) - len(self.pargs)
            if n >= 0:
                self.pargs = pargs
            else:
                self.pargs = pargs + self.pargs[n:]
        if kargs:
            self.kargs.update(kargs)
        return self

    def copy_update(self, /, *pargs, **kargs):
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
        return copy(self).update(*pargs, **kargs)

    def update_extend(self, /, *pargs, **kargs):
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
        if pargs:
            n = len(self.pargs) - len(pargs)
            if n < 0:
                self.pargs += pargs[n:]
        if kargs:
            kargs0 = self.kargs
            kargs0.update(
                (k, kargs[k])
                for k in kargs.keys() - kargs0.keys()
            )
        return self

    def copy_update_extend(self, /, *pargs, **kargs):
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
        return copy(self).update_extend(*pargs, **kargs)


if __name__ == "__main__":
    import doctest
    doctest.testmod()

