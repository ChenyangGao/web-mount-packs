#!/usr/bin/env python3
# coding: utf-8

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 0)
__all__ = []


from function import reduce


def call_each(x, /, *fs):
    return (f(x) for f in fs)


def f_inverse(f, /):
    return lambda *args, **kwds: f(*revered(args), **kwds)


def _kwds_merge(kwds1, kwds2):
    if not kwds1:
        return kwds2
    elif not kwds2:
        return kwds1
    else:
        kwds1.update(kwds2)
        return kwds1


def f_partial(f, /, *args0, **kwds0):
    return lambda *args, **kwds: f(*args0, *args, **_kwds_merge(kwds0, kwds))


def f_partial_back(f, /, *args0, **kwds0):
    return lambda *args, **kwds: f(*args, *args0, **_kwds_merge(kwds0, kwds))


def f_hold_place(f, indexs, /, *args0, out_of_index_range="raise"):
    len_args0 = len(args0)
    raise_out_range = out_of_index_range == "raise"
    take_out_range = out_of_index_range == "take"
    def abs_index(idx):
        if idx >= 0:
            if raise_out_range and idx >= len_args0:
                raise IndexError
            return idx
        idx += len_args0
        if raise_out_range and idx < 0:
            raise IndexError
        return idx
    def merge_args(args):
        it = iter(args)
        ps = sorted(zip(map(abs_index, indexs), it), key=lambda t: t[0])
        last_idx = 0
        for idx, a in ps:
            if idx < 0:
                if take_out_range:
                    yield a
                continue
            if last_idx < idx and last_idx < len_args0:
                yield from args0[last_idx:idx]
                last_idx = idx
            if last_idx >= len_args0:
                if not take_out_range:
                    break
            yield a
        else:
            yield from args0[last_idx:]
        if take_out_range:
            yield from it
    return lambda *args, **kwds: f(*merge_args(args), **kwds0)


def f_insert_place(f, *index_arg_pairs, out_of_index_range="raise"):
    raise_out_range = out_of_index_range == "raise"
    take_out_range = out_of_index_range == "take"
    def abs_index(idx, length):
        if idx >= 0:
            if idx >= length and raise_out_range:
                raise IndexError
            return idx
        idx += length
        if idx < 0 and raise_out_range:
            raise IndexError
        return idx
    def merge_args(args):
        len_args = len(args)
        ps = sorted(((abs_index(i, len_args), a) for i, a in index_arg_pairs), key=lambda t: t[0])
        last_idx = 0
        for idx, a in ps:
            if idx < 0:
                if take_out_range:
                    yield a
                continue
            if idx < last_idx and last_idx < len_args:
                yield from args[last_idx:idx]
                last_idx = idx
            if last_idx >= len_args:
                if not take_out_range:
                    break
            yield a
        else:
            yield from args[last_idx:]
    return lambda *args, **kwds: f(*merge_args(args), **kwds)


