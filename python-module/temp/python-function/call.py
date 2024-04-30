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

