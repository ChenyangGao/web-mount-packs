__all__ = ['_', 'PLACE_HOLDER', 'PlaceHold']


_ = PLACE_HOLDER = type('PLACE_HOLDER', (), {'__repr__': lambda self: '_'})()


class PlaceHold:

    __slots__ = ('fn', 'args')

    def __init__(self, fn, args=()):
        self.fn = fn
        self.args = tuple(args)

    def __call__(self, *args):
        iargs = iter(args)
        fn, args = self.fn, self.args
        args = [next(iargs, a) if a is PLACE_HOLDER else a 
                for a in args]
        args.extend(iargs)
        if any(map(lambda x: x is PLACE_HOLDER, args)):
            return type(self)(fn, args)
        else:
            return fn(*args)

    def __repr__(self):
        fn = self.fn
        fn_name = getattr(fn, '__qualname__', getattr(fn, '__name__', repr(fn)))
        return f"{fn_name}{self.args}"

