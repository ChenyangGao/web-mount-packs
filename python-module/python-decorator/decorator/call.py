__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 3)
__all__ = ['call_before', 'call_after', 'call_error', 'call_finally', 
           'dispatch_by_args', 'expand_by_args']

from inspect import isawaitable, iscoroutinefunction
from typing import cast, Callable, Optional, Union, Tuple, Type

from .decorator import optional_decorate


@optional_decorate
def call_before(
    f: Optional[Callable] = None, 
    /, 
    call: Callable = lambda *args: None, 
    async_: Optional[bool] = None, 
) -> Callable:
    f = cast(Callable, f)
    if async_ or (async_ is None and iscoroutinefunction(f)):
        async def wrapper(*args, **kwds):
            _ = call(f, args, kwds)
            if isawaitable(_):
                await _
            return await f(*args, **kwds)
    else:
        def wrapper(*args, **kwds):
            call(f, args, kwds)
            return f(*args, **kwds)
    return wrapper


@optional_decorate
def call_after(
    f: Optional[Callable] = None, 
    /, 
    call: Callable = lambda *args: None, 
    async_: Optional[bool] = None, 
) -> Callable:
    f = cast(Callable, f)
    if async_ or (async_ is None and iscoroutinefunction(f)):
        async def wrapper(*args, **kwds):
            r = await f(*args, **kwds)
            _ = call(f, args, kwds, r)
            if isawaitable(_):
                await _
            return r
    else:
        def wrapper(*args, **kwds):
            r = f(*args, **kwds)
            call(f, args, kwds, r)
            return r
    return wrapper


@optional_decorate
def call_error(
    f: Optional[Callable] = None, 
    /, 
    call: Callable = lambda *args: None, 
    exceptions: Union[
        Type[BaseException], 
        Tuple[Type[BaseException], ...]
    ] = BaseException, 
    async_: Optional[bool] = None, 
    suppress: bool = False, 
) -> Callable:
    f = cast(Callable, f)
    if async_ or (async_ is None and iscoroutinefunction(f)):
        async def wrapper(*args, **kwds):
            try:
                return await f(*args, **kwds)
            except exceptions as exc:
                _ = call(f, args, kwds, exc)
                if isawaitable(_):
                    await _
                if not suppress:
                    raise
    else:
        def wrapper(*args, **kwds):
            try:
                return f(*args, **kwds)
            except exceptions as exc:
                call(f, args, kwds, exc)
                if not suppress:
                    raise
    return wrapper


@optional_decorate
def call_finally(
    f: Optional[Callable] = None, 
    /, 
    call: Callable = lambda *args: None, 
    async_: Optional[bool] = None, 
) -> Callable:
    f = cast(Callable, f)
    if async_ or (async_ is None and iscoroutinefunction(f)):
        async def wrapper(*args, **kwds):
            try:
                r = await f(*args, **kwds)
                return r
            except BaseException as exc:
                r = exc
                raise
            finally:
                _ = call(f, args, kwds, r)
                if isawaitable(_):
                    await _
    else:
        def wrapper(*args, **kwds):
            try:
                r = f(*args, **kwds)
                return r
            except BaseException as exc:
                r = exc
                raise
            finally:
                call(f, args, kwds, r)
    return wrapper


def _tuple_prefix(self, other):
    if len(self) < len(other):
        return False
    for a1, a2 in zip(self, other):
        if not (a1 is a2 or a1 == a2):
            return False
    return True


def _dict_include(self, other):
    other_keys = set(other)
    if other_keys != other_keys & self.keys():
        return False
    for k in other_keys:
        a1, a2 = self[k], other[k]
        if not (a1 is a2 or a1 == a2):
            return False
    return True


class dispatch_by_args:

    def __init__(self, func=None, /):
        if func is not None:
            self.default = func
        self.alternates = []

    @staticmethod
    def default(*args, **kwds):
        raise NotImplementedError

    def register(self, fn=None, /, *args, **kwds):
        if fn is None:
            return lambda func, /: self.register(func, *args, **kwds)
        elif not callable(fn):
            return lambda func, /: self.register(func, fn, *args, **kwds)
        self.alternates.append(
            ((args, tuple(kwds.items())), fn))
        return fn

    def __call__(self, *args, **kwds):
        for (pargs, pkwds), fn in self.alternates:
            if _tuple_prefix(args, pargs) and _dict_include(kwds, pkwds):
                return fn(*args, **kwds)
        return self.default(*args, **kwds)


class expand_by_args(dispatch_by_args):

    def __call__(self, *args, **kwds):
        for (pargs, pkwds), fn in self.alternates:
            if _tuple_prefix(args, pargs) and _dict_include(kwds, pkwds):
                return fn(
                    *args[len(pargs):],
                    **{k: v for k, v in kwds.items() if k not in pkwds},
                )
        return self.default(*args, **kwds)

