#!/usr/bin/env python3
# coding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = ["_", "Holder", "HolderF"]

from io import BytesIO
from tokenize import tokenize, NAME
from typing import cast, Callable, Final, Mapping


BASETYPES: Final[tuple[type, ...]] = (bool, int, float, complex, bytes, str)
_ = type("HolderP", (), {"__repr__": staticmethod(lambda: "_")})()


class Holder:

    def __init__(
        self, 
        expr: str, 
        namespace: None | Mapping = None, 
        basetypes: tuple[type, ...] = BASETYPES, 
    ):
        self._expr = expr
        self._namespace = namespace
        self._basetypes = basetypes
        partitions = self._partitions = self._partition(expr)
        argcount = self._argcount = len(partitions) // 2
        func_str: str
        if argcount == 0:
            func_str = "lambda : " + expr
        else:
            func_str = "".join((
                "lambda ", 
                "__0", 
                *(", __%d" % i for i in range(1, argcount)), 
                ": ", 
                *("%s__%d" % (partitions[i*2], i) 
                              for i in range(0, argcount)), 
                partitions[-1]
            ))
        self._func_str = func_str
        self._func = eval(func_str, None, namespace)

    @property
    def func(self) -> Callable:
        return self._func

    @property
    def func_str(self) -> str:
        return self._func_str

    @staticmethod
    def _partition(
        expr: str, 
        _finditer=__import__("re").compile("\n").finditer, 
    ) -> list[str]:
        nl_idxs = (0, 0, *(m.end() for m in _finditer(expr)))
        start = 0
        ls = []
        for tk in tokenize(BytesIO(expr.encode("utf-8")).readline):
            if tk.type == NAME and tk.string == "_":
                idx = nl_idxs[tk.start[0]] + tk.start[1]
                ls.append(expr[start:idx])
                ls.append("_")
                start = idx + 1
        else:
            ls.append(expr[start:])
        return ls

    def __len__(self) -> int:
        return self._argcount

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self._expr!r})"

    def __str__(self) -> str:
        return self._expr

    def __call__(self, *args):
        argcount = len(self)
        argcount_pass = len(args)
        if argcount_pass > argcount:
            raise TypeError(f"At most {argcount} arguments, got {argcount_pass}")
        elif argcount == 0:
            return self._func()
        elif argcount_pass < argcount:
            return self.bind(*args)
        for arg in args:
            if arg is _ or type(arg) in (Holder, HolderF) and len(arg):
                return self.bind(*args)
        return self._func(*args)

    def __getitem__(self, args) -> Holder | HolderF:
        if type(args) is tuple:
            return self.bind(*args)
        elif type(args) is dict and args and all(type(k) is int for k in args):
            args_ = [_] * min((max(args) + 1, len(self)))
            for k, v in args.items():
                try:
                    args_[k] = v
                except IndexError:
                    pass
            return self.bind(*args)
        else:
            return self.bind(args)

    def bind(self, *args) -> Holder | HolderF:
        argcount = len(self)
        argcount_pass = len(args)
        if argcount_pass > argcount:
            raise TypeError(f"At most {argcount} arguments, got {argcount_pass}")
        if all(a is _ for a in args):
            return self

        F_HOLDERP  = 1 << 0
        F_HOLDER   = 1 << 1
        F_HOLDERF  = 1 << 2
        F_BASETYPE = 1 << 3
        F_OTERTYPE = 1 << 4
        flag = int(len(args) < len(self))
        basetypes = self._basetypes
        for arg in args:
            if arg is _:
                flag |= F_HOLDERP
            else:
                arg_t = type(arg)
                if arg_t is Holder:
                    flag |= F_HOLDER
                elif arg_t is HolderF:
                    flag |= F_HOLDERF
                elif arg_t in basetypes:
                    flag |= F_BASETYPE
                else:
                    flag |= F_OTERTYPE

        if flag & F_HOLDERF or flag & F_OTERTYPE:
            return HolderF(self, *args)
        else:
            partitions = list(self._partitions)
            for arg, idx in zip(args, range(1, len(partitions), 2)):
                if arg is _:
                    continue
                elif isinstance(arg, Holder):
                    partitions[idx] = "(%s)" % arg
                else:
                    partitions[idx] = repr(arg)
            return Holder("".join(partitions), self._namespace)


class HolderF:

    def __init__(self, f: Callable, *args):
        self._func: Callable | Holder
        f_t = type(f)
        if f_t is Holder:
            f = cast(Holder, f)
            the_types = (Holder, *f._basetypes)
            if all(a is _ or type(a) in the_types for a in args):
                f = f.bind(*args)
                self._func = f
                self._args = (_,) * len(f)
                self._argcount = len(f)
                self._holders = [(i, None, 1) for i in range(len(f))]
            else:
                self._func = f
                argcount = len(f)
                argcount_pass = len(args)
                diff = argcount - argcount_pass
                if diff < 0:
                    raise TypeError(f"At most {argcount} arguments, got {argcount_pass}")
                elif diff > 0:
                    args += (_,) * diff
                self._args = args
                ls = self._holders = []
                for i, a in enumerate(args):
                    if a is _:
                        ls.append((i, None, 1))
                    elif type(a) in (Holder, HolderF):
                        ls.append((i, a, len(a)))
                self._argcount = sum(t[2] for t in ls)
        elif f_t is HolderF:
            f = cast(HolderF, f)
            if args:
                f = f.bind(*args)
            self._func = f._func
            self._args = f._args
            self._argcount = f._argcount
            self._holders = f._holders
        else:
            self._func = f
            self._args = args
            ls = self._holders = []
            for i, a in enumerate(args):
                if a is _:
                    ls.append((i, None, 1))
                elif type(a) in (Holder, HolderF):
                    ls.append((i, a, len(a)))
            self._argcount = sum(t[2] for t in ls)

    @property
    def func(self) -> Callable:
        return self._func

    @property
    def args(self) -> tuple:
        return self._args

    def __len__(self) -> int:
        return self._argcount

    def __repr__(self) -> str:
        if type(self._func) is Holder:
            sup = max((i for i, a in enumerate(self._args) if a is not _), default=-1) + 1
            return "%s(%s)" % (
                type(self).__qualname__, 
                ', '.join(map(repr, (self._func, *self._args[:sup]))), 
            )
        else:
            return "%s(%s)" % (
                type(self).__qualname__, 
                ', '.join(map(repr, (self._func, *self._args))), 
            )

    def __call__(self, *args):
        f = self.bind(*args)
        if len(f):
            return f
        fn = f._func
        if type(fn) is Holder:
            fn = fn._func
        return fn(*(a() if type(a) in (Holder, HolderF) else a for a in f._args))

    def __getitem__(self, args) -> HolderF:
        if type(args) is tuple:
            return self.bind(*args)
        elif type(args) is dict and args and all(type(k) is int for k in args):
            args_ = [_] * min((max(args) + 1, len(self)))
            for k, v in args.items():
                try:
                    args_[k] = v
                except IndexError:
                    pass
            return self.bind(*args_)
        else:
            return self.bind(args)

    def bind(self, *args) -> HolderF:
        argcount = len(self)
        argcount_pass = len(args)
        if argcount_pass > argcount:
            raise TypeError(f"At most {argcount} arguments, got {argcount_pass}")
        if all(a is _ for a in args):
            return self
        args_ = list(self._args)
        start = 0
        for idx, f, c in self._holders:
            if start >= argcount_pass:
                break
            stop = start + c
            if f is None:
                args_[idx] = args[start]
            else:
                args_[idx] = f.bind(*args[start:stop])
            start = stop
        return type(self)(self._func, *args_)

