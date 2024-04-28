#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import functools


class PipeMeta(type):
    __ror__ = type.__call__


class PIPE(metaclass=PipeMeta):
    def __init__(self, val=None):
        self.val = val

    def __repr__(self):
        module = type(self).__module__
        if module == '__main__':
            return f'{type(self).__qualname__}({self.val!r})'
        return f'{module}.{type(self).__qualname__}({self.val!r})'

    def __invert__(self):
        return self.val

    def __or__(self, func):
        return func(self.val)

    def __ror__(self, other):
        self.val = other
        return self


class T_PIPE(PIPE):
    __gt__ = PIPE.__or__

    def __or__(self, func):
        self.val = func(self.val)
        return self


class N_PIPE(PIPE):

    @classmethod
    def __ror__(cls, other):
        return cls(other)


class NT_PIPE(N_PIPE, T_PIPE): pass


class PipeChain:
    def __init__(self, *functions):
        self.functions = functions

    @classmethod
    def from_iterable(cls, functions):
        self = cls.__new__(cls)
        self.functions = functions
        return self

    def __call__(self, x):
        return functools.reduce(self.pipe_call, self.functions, x)

    @staticmethod
    def pipe_call(a, b):
        return b(a)


class Args:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class Pipe:
    def __init__(self, func, f_chain=None):
        self.__func__ = func
        self.f_chain = [] if f_chain is None else f_chain
        functools.update_wrapper(self, func)

    def __repr__(self):
        module, name = type(self).__module__, type(self).__qualname__
        if module == '__main__':
            return f'<{name} object of {self.__name__} at {hex(id(self))}>'
        return f'<{module}.{name} object of {self.__name__} at {hex(id(self))}>'

    def __ror__(self, other):
        if type(other) is Args:
            r = self.__func__(*other.args, **other.kwargs)
        else:
            r = self.__func__(other)
        if not self.f_chain:
            return r
        reduce_call = PipeChain.from_iterable(self.f_chain)
        return reduce_call(r)

    def __call__(self, *args, **kwargs):
        return __class__(lambda x: self.__func__(x, *args, **kwargs))

    def __lshift__(self, other):
        if type(other) is Args:
            return self(*other.args, **other.kwargs)
        return self(other)

    __le__ = __lshift__

    def __add__(self, func):
        return type(self)(self.__func__, self.f_chain + [func,])

    def __and__(self, func):
        self.f_chain.append(func)
        return self

    def __invert__(self):
        return type(self)(self.__func__)

    def __neg__(self):
        return type(self)(self.__func__, self.f_chain[:-1])

    def __sub__(self, n:int):
        return type(self)(self.__func__, self.f_chain[:-n])


class LeftPipe:
    def __init__(self, func, args=None, kwargs=None, f_chain=None):
        self.__func__ = func
        self.f_chain = [] if f_chain is None else f_chain
        self.args, self.kwargs = args or (), kwargs or {}
        functools.update_wrapper(self, func)

    def __repr__(self):
        module, name = type(self).__module__, type(self).__qualname__
        if module == '__main__':
            return f'<{name} object of {self.__name__} at {hex(id(self))}>'
        return f'<{module}.{name} object of {self.__name__} at {hex(id(self))}>'

    def __call__(self, *args, **kwargs):
        r = self.__func__(*self.args, *args, **self.kwargs, **kwargs)
        if not self.f_chain:
            return r
        reduce_call = PipeChain.from_iterable(self.f_chain)
        return reduce_call(r)

    def __ror__(self, other):
        return self(other)

    def __mul__(self, args):
        return type(self)(self.__func__, self.args + args, self.kwargs)

    def __matmul__(self, arg):
        return self * (arg,)

    def __pow__(self, kwargs):
        return type(self)(self.__func__, self.args, {**self.kwargs, **kwargs})

    def __ipow__(self, kwargs):
        self.kwargs.update(kwargs)
        return self

    def __truediv__(self, func):
        return type(self)(func, self.args, self.kwargs)

    def __add__(self, func):
        return type(self)(self.__func__, self.args, self.kwargs, 
                          self.f_chain + [func,])

    def __and__(self, func):
        self.f_chain.append(func)
        return self

    def __lshift__(self, func):
        return type(self)(self(func))

    def __rshift__(self, func):
        return type(self)(func(self.__func__), self.args, self.kwargs)

    def passin(self, *args, **kwargs):
        args, kwargs = self.args + args, {**self.kwargs, **kwargs}
        return type(self)(self.__func__, args, kwargs)

    def partial(self, *args, **kwargs):
        func = functools.partial(self.__func__, *args, **kwargs)
        return type(self)(func, self.args, self.kwargs.copy())


class RightPipe(LeftPipe):
    def __call__(self, *args, **kwargs):
        r = self.__func__(*args, *self.args, **kwargs, **self.kwargs)
        reduce_call = PipeChain.from_iterable(self.f_chain)
        return reduce_call(r)

    def __mul__(self, args):
        return type(self)(self.__func__, args + self.args, self.kwargs)

    def __pow__(self, kwargs):
        return type(self)(self.__func__, self.args, {**kwargs, **self.kwargs})

    def __ipow__(self, kwargs):
        keys = kwargs.keys() - self.kwargs.keys()
        self.kwargs.update((k, kwargs[k]) for k in keys)
        return self

    def passin(self, *args, **kwargs):
        args, kwargs = args + self.args, {**kwargs, **self.kwargs}
        return type(self)(self.__func__, args, kwargs)

e = pipe = RightPipe(lambda x: x)


class Decorator:
    def __init__(self, func):
        self.__func__ = func
        functools.update_wrapper(self, func)

    def __repr__(self):
        return repr(self.__func__)

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            return self.__func__(func, *args, **kwargs)
        return functools.update_wrapper(wrapper, func)


class PipedDecorator(Decorator):
    Pipe = Pipe

    def __call__(self, func):
        return self.Pipe(super().__call__(func))

    __matmul__ = __rshift__ = __rlshift__ = __call__


class LeftPipedDecorator(PipedDecorator):
    Pipe = LeftPipe


class RightPipedDecorator(PipedDecorator):
    Pipe = RightPipe


@PipedDecorator
def piping(f, *args, **kwargs):
    return f(*args, **kwargs)


class Reducer:
    def __init__(self, func):
        self.__func__ = func

    def __repr__(self):
        module, qualname = type(self).__module__, type(self).__qualname__
        if module == '__main__':
            return f'{qualname}({self.__func__!r})'
        return f'{module}.{qualname}({self.__func__!r})'

    def __call__(self, *args, **kwargs):
        r = self.__func__(*args, **kwargs)
        return type(self)(r) if callable(r) else r

    def __rshift__(self, arg):
        if type(arg) is Args:
            return self(arg.args, arg.kwargs)
        return self(arg)

    __matmul__ = __rshift__

reducer = Reducer(lambda x: x)

