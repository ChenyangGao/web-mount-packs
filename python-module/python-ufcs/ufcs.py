'''
This module implements UFCS for Python.

[Uniform Function Call Syntax (UFCS)](https://tour.dlang.org/tour/en/gems/uniform-function-call-syntax-ufcs)

UFCS is a key feature of D and enables code reusability and scalability through well-defined encapsulation.

UFCS allows any call to a free function fun(a) to be written as a member function call a.fun().

If a.fun() is seen by the compiler and the type doesn't have a member function called fun(), 
it tries to find a global function whose first parameter matches that of a.

This feature is especially useful when chaining complex function calls. Instead of writing
```
foo(bar(a))
```

It is possible to write
```
a.bar().foo()
```

--- doctest cases ---

>>> def map(iterable, fn):
...     return __builtins__.map(fn, iterable)
... 
>>> def filter(iterable, fn):
...     return __builtins__.filter(fn, iterable)
... 
>>> def reduce(iterable, fn):
...     return __import__('functools').reduce(fn, iterable)
... 
>>> iterable = range(100)
>>> (UFCSWrapper(iterable)
...     .map(lambda x: x + 1)
...     .filter(lambda x: x % 2)
...     .reduce(lambda x, y: x + y)
...     ._obj_
... ) == (
...     reduce(
...         filter(
...             map(
...                 iterable, lambda x: x + 1
...             )
...             , lambda x: x % 2
...         )
...         , lambda x, y: x + y
...     )
... )
True
>>> (UFCSAllWrapper(iterable)
...     .map(lambda x: x + 1)
...     .filter(lambda x: x % 2)
...     .reduce(lambda x, y: x + y)
...     ._obj_
... ) == (
...     reduce(
...         filter(
...             map(
...                 iterable, lambda x: x + 1
...             )
...             , lambda x: x % 2
...         )
...         , lambda x, y: x + y
...     )
... )
True

'''

from __future__ import annotations
from builtins import __dict__ as builtins_ # type: ignore
from collections import ChainMap
from functools import partial, update_wrapper
from sys import _getframe as getframe
from typing import Mapping, Optional


__all__ = ['UFCSWrapper', 'UFCSAllWrapper']


class UFCSWrapper:
    '''
    Uniform Function Call Syntax (UFCS) Wrapper for Python object

    [Uniform Function Call Syntax (UFCS)](https://tour.dlang.org/tour/en/gems/uniform-function-call-syntax-ufcs)

    :param globals: A global namespace for searching attribute, when the attribute does not exist on the object
    :return: A wrapper of a Python object that is able to use UFCS
    '''

    __slots__ = ['_obj_', '_globals_']

    def __init__(self, obj, globals: Optional[Mapping] = None):
        self._obj_ = obj
        if globals is not None:
            globals = ChainMap(globals, builtins_)
        self._globals_ = globals

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self._obj_!r})'

    def __getattr__(self, attr: str, _ahead: int = 1): # type: ignore
        obj = self._obj_
        try:
            f = getattr(obj, attr)
            if not callable(f):
                return f
        except AttributeError:
            globals_ = self._globals_
            if globals_ is None:
                globals_ = ChainMap(getframe(_ahead).f_globals, builtins_)
            try:
                fn = globals_[attr]
                if not callable(fn):
                    raise ValueError(f'{fn} is not a callable')
            except (KeyError, ValueError) as exc:
                raise AttributeError(attr) from exc
            else:
                if hasattr(fn, '__get__'):
                    f = fn.__get__(obj, type(obj))
                else:
                    f = update_wrapper(partial(fn, obj), fn)

        return update_wrapper(
            lambda *a, **k: type(self)(f(*a, **k)), f
        )


class UFCSAllWrapper(UFCSWrapper):

    def __getattr__(self, attr: str, _ahead: int = 2) -> UFCSAllWrapper:
        a = super().__getattr__(attr, _ahead)

        a2: UFCSAllWrapper = type(self)(a)
        if callable(a):
            update_wrapper(a2, a)
        return a2

    def __call__(self, *args, **kwargs):
        return self._obj_(*args, **kwargs)


if __name__ == '__main__':
    import doctest
    print(doctest.testmod())

