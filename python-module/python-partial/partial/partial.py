# /usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["partial", "ppartial", "currying"]

from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import cached_property, partial, update_wrapper
from inspect import _empty, signature, BoundArguments, Signature
from itertools import chain, repeat

from .placeholder import _


class ppartial(partial):

    def __new__(cls, func: Callable, /, *args, **kwds):
        if isinstance(func, partial):
            args = func.args + args
            kwds = {**func.keywords, **kwds}
            func = func.func
        return update_wrapper(super().__new__(cls, func, *args, **kwds), func)

    def __call__(self, /, *args, **kwargs):
        func, args0, kwargs0 = self.func, self.args, self.keywords

        if any(a == _ for a in args0):
            args_it = iter(args)
            pargs = (*(next(args_it, _) if v == _ else v for v in args0), *args_it)
        else:
            pargs = args0 + args
        kargs = {**kwargs0, **kwargs}

        if any(a == _ for a in chain(pargs, kargs.values())):
            return type(self)(func, *pargs, **kargs)
        return func(*pargs, **kargs)

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
    def skip(
        cls, 
        func: None | Callable = None, 
        /, 
        *, 
        skip: int = 0, 
        skip_keys=(), 
    ):
        if func is None:
            return partial(cls.skip, skip=skip, skip_keys=skip_keys)
        return cls(func, *repeat(_, skip), **dict(zip(skip_keys, repeat(_))))

    @classmethod
    def wrap(
        cls, 
        func: None | Callable = None, 
        /, 
        *, 
        prefer_keyword: bool = False, 
    ) -> Callable:
        if func is None:
            return partial(cls.wrap, prefer_keyword=prefer_keyword)
        def coalesce(value):
            return _ if value is _empty else value
        sig = signature(func)
        pargs = []
        kargs = {}
        for param in sig.parameters.values():
            match param.kind:
                case param.POSITIONAL_ONLY:
                    pargs.append(coalesce(param.default))
                case param.KEYWORD_ONLY:
                    kargs[param.name] = coalesce(param.default)
                case param.POSITIONAL_OR_KEYWORD:
                    if param.default is _empty:
                        if prefer_keyword:
                            kargs[param.name] = _
                        else:
                            pargs.append(_)
        return cls(func, *pargs, **kargs)


class currying(ppartial):

    def __call__(self, /, *args, **kwargs):
        func, args0, kwargs0 = self.func, self.args, self.keywords

        if any(a == _ for a in args0):
            args_it = iter(args)
            pargs = (*(next(args_it, _) if v == _ else v for v in args0), *args_it)
        else:
            pargs = args0 + args
        kargs = {**kwargs0, **kwargs}

        if any(a == _ for a in chain(pargs, kargs.values())):
            return type(self)(func, *pargs, **kargs)
        try:
            signature(func).bind(*pargs, **kargs)
        except TypeError as exc:
            if (exc.args 
                and isinstance(exc.args[0], str)
                and exc.args[0].startswith("missing a required")
            ):
                return type(self)(func, *pargs, **kargs)
            raise
        return func(*pargs, **kargs)

