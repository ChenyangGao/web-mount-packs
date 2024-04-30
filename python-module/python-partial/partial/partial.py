# /usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["partial", "ppartial", "skippartial"]

from collections.abc import Callable, Iterable, Sequence
from functools import cached_property, partial, update_wrapper
from inspect import signature, BoundArguments, Signature
from itertools import chain

from undefined import undefined
from .placeholder import _


def _exist_placeholder(args: Iterable) -> bool:
    return any(a is _ or a is undefined for a in args)


class ppartial(partial):

    def __new__(cls, func: Callable, /, *args, **kwargs):
        if isinstance(func, partial):
            args = func.args + args
            kwargs = {**func.keywords, **kwargs}
            func = func.func
        return update_wrapper(super().__new__(cls, func, *args, **kwargs), func)

    def __call__(self, /, *args, **kwargs):
        args_, kwargs_ = self.args, self.keywords

        if _exist_placeholder(args_):
            args_it = iter(args)
            pargs = (*(next(args_it, _) if v is _ or v is undefined else v for v in args_), *args_it)
        else:
            pargs = args_ + args
        kargs = {**kwargs_, **kwargs}

        if _exist_placeholder(pargs) or _exist_placeholder(kargs.values()):
            return type(self)(self.func, *pargs, **kargs)
        return self.func(*pargs, **kargs)

    @cached_property
    def __signature__(self, /) -> Signature:
        bound_args = self.bound_args
        arguments = bound_args.arguments
        def param_new(param):
            if param.kind is param.VAR_POSITIONAL or param.kind is param.VAR_KEYWORD:
                return param
            elif param.name in arguments:
                return param.replace(default=arguments[param.name])
            else:
                return param.replace(default=_)
        return Signature(map(param_new, bound_args.signature.parameters.values())) # type: ignore

    @cached_property
    def bound_args(self, /) -> BoundArguments:
        bound_args = signature(self.func).bind_partial(*self.args, **self.keywords)
        bound_args.apply_defaults()
        return bound_args

    @classmethod
    def wrap(cls, func: Callable, /) -> Callable:
        def wrapper(*args, **kwargs):
            if _exist_placeholder(args) or _exist_placeholder(kwargs.values()):
                return cls(func, *args, **kwargs)
            return func(*args, **kwargs)
        return update_wrapper(wrapper, func)


class skippartial(partial):
    skip: int | Sequence[int]

    def __new__(
        cls, 
        skip: int | Iterable[int], 
        func: Callable, 
        /, 
        *args, 
        **kwargs, 
    ):
        if isinstance(func, partial):
            if isinstance(func, skippartial):
                if isinstance(func, cls):
                    old_skip = func.skip
                    if isinstance(old_skip, int):
                        old_skip = range(old_skip)
                    if isinstance(skip, int):
                        skip = range(skip)
                    skip = chain(old_skip, skip)
            args = func.args + args
            kwargs = {**func.keywords, **kwargs}
            func = func.func

        self = super().__new__(cls, func, *args, **kwargs)

        if isinstance(skip, int):
            if skip < 0:
                raise ValueError(f"bad skip {skip!r}: cannot be negative")
            self.skip = skip
        else:
            if isinstance(skip, range):
                if skip.step < 0:
                    skip = skip[::-1]
            else:
                skip = sorted(set(skip))
            if not skip:
                self.skip = 0
            elif skip[0] < 0:
                raise ValueError(f"bad skip {skip!r}: negative numbers are not allowed")
            else:
                self.skip = skip

        return self

    def __call__(self, /, *args, **kwargs):
        skip = self.skip
        if skip == 0:
            return self.func(
                *self.args, *args, 
                **{**self.keywords, **kwargs}
            )
        elif isinstance(skip, int):
            lack = skip - len(args)
            if lack > 0:
                raise TypeError("Cannot fully fill the skipped positions, "
                                "lacks %s positional arguments" % lack)
            return self.func(
                *args[:skip], *self.args, *args[skip:], 
                **{**self.keywords, **kwargs}
            )
        else:
            lack = skip[-1] - len(args) - len(self.args) + 1
            if lack > 0:
                raise TypeError("Cannot fully fill the skipped positions, "
                                "lacks %s positional arguments" % lack)
            args_ = self.args
            args_it = iter(args)
            args_l: list = []
            lp = -1
            for i, (p, a) in enumerate(zip(skip, args_it)):
                if p - lp > 1:
                    if lp < 0:
                        args_l.extend(args_[0:p])
                    else:
                        args_l.extend(args_[lp:p-i])
                args_l.append(a)
                lp = p - i
            args_l.extend(args_[lp:])
            args_l.extend(args_it)
            return self.func(
                *args_l, **{**self.keywords, **kwargs})

    def __repr__(self, /):
        args = ", ".join(chain(
            (str(self.skip), repr(self.func)), 
            map(repr, self.args), 
            ("%s=%r" % item for item in self.keywords.items())
        ))
        return f"{type(self).__qualname__}({args})"

