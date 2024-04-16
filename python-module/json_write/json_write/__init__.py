#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = [
    "json_log_gen_write", "json_log_write", "json_array_gen_write", "json_array_write", 
    "json_object_gen_write", "json_object_write", "json_groups_gen_write", "json_groups_write", 
    "json_gen_write", "json_write", "json_ensure_gen_write", "json_ensure_write", 
]

from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from functools import update_wrapper
from io import TextIOWrapper
from os import PathLike
from os.path import exists
from operator import itemgetter
from sys import stdout
from typing import Optional, Protocol, TypeAlias

dumps: Callable[..., bytes]
try:
    from orjson import dumps
except ImportError:
    odumps: Callable[..., str]
    try:
        from ujson import dumps as odumps
    except ImportError:
        from json import dumps as odumps
    dumps = lambda obj: bytes(odumps(obj, ensure_ascii=False), "utf-8")


PathType: TypeAlias = bytes | str | PathLike


class SupportsWriteBytes(Protocol):
    def write(self, s: bytes, /) -> object: ...


@contextmanager
def gen_as_ctx(gen: Generator, /):
    try:
        yield gen.send
    finally:
        gen.close()


def gen_startup(func, /):
    def wrapper(*args, **kwds):
        r = func(*args, **kwds)
        next(r)
        return r
    return update_wrapper(wrapper, func)


def foreach(fn, it, /, *its):
    if its:
        for args in zip(it, *its):
            fn(*args)
    else:
        for arg in it:
            fn(arg)


@gen_startup
def json_log_gen_write(
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    if isinstance(file, TextIOWrapper):
        file = file.buffer
    write = file.write
    while True:
        val = yield
        if value is not None:
            val = value(val)
        write(dumps(val))
        write(b"\n")


def json_log_write(
    it: Iterable, 
    /, 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    with gen_as_ctx(json_log_gen_write(value=value, file=file)) as write:
        foreach(write, it)


@gen_startup
def json_array_gen_write(
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    if isinstance(file, TextIOWrapper):
        file = file.buffer
    write = file.write
    write(b"[")
    try:
        not_first = False
        while True:
            val = yield
            if value is not None:
                val = value(val)
            if not_first:
                write(b","+dumps(val))
            else:
                write(dumps(val))
                not_first = True
    finally:
        write(b"]")


def json_array_write(
    it: Iterable, 
    /, 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    with gen_as_ctx(json_array_gen_write(value=value, file=file)) as write:
        foreach(write, it)


@gen_startup
def json_object_gen_write(
    key: Callable, 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    if isinstance(file, TextIOWrapper):
        file = file.buffer
    write = file.write
    write(b"{")
    try:
        not_first = False
        while True:
            val = yield
            if value is not None:
                val = value(val)
            if not_first:
                tpl = b",%s:%s"
            else:
                tpl = b"%s:%s"
                not_first = True
            write(tpl % (dumps(str(key(val))), dumps(val)))
    finally:
        write(b"}")


def json_object_write(
    it: Iterable, 
    /, 
    key: Optional[Callable] = None, 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    if key is None:
        if isinstance(it, Mapping):
            if hasattr(it, "items"):
                it = it.items()
            else:
                it = ((k, it[k]) for k in it)
        key = itemgetter(0)
        if value is None:
            value = itemgetter(1)
        else:
            value = lambda t, _val=value: _val(t[1])
    with gen_as_ctx(json_object_gen_write(key, value=value, file=file)) as write:
        foreach(write, it)


@gen_startup
def json_groups_gen_write(
    keys: Sequence[Callable], 
    *, 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    assert keys, "empty keys"
    if isinstance(file, TextIOWrapper):
        file = file.buffer
    write = file.write
    last_ks: tuple[bytes, ...] = ()
    write(b"{")
    try:
        while True:
            val = yield
            if value is not None:
                val = value(val)
            ks = tuple(dumps(str(key(val))) for key in keys)
            if last_ks:
                for i, (k0, k1) in enumerate(zip(last_ks, ks)):
                    if k0 != k1:
                        break
                ks2 = ks[i:-1]
                if ks2:
                    write(b"}" * len(ks2))
                write(b",")
            else:
                ks2 = ks[:-1]
            for k in ks2:
                write(b"%s:{" % k)
            write(b"%s:%s" % (ks[-1], dumps(val)))
            last_ks = ks
    finally:
        if last_ks:
            write(b"}" * len(keys))
        else:
            write(b"}")


def json_groups_write(
    it: Iterable, 
    /, 
    keys: Sequence[Callable], 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    with gen_as_ctx(json_groups_gen_write(keys, value=value, file=file)) as write:
        foreach(write, it)


def json_gen_write(
    keys: None | Callable | Sequence[Callable] = None, 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    if keys is None:
        return json_log_gen_write(value=value, file=file)
    elif callable(keys):
        return json_object_gen_write(keys, value=value, file=file)
    elif keys:
        if len(keys) == 1:
            return json_object_gen_write(keys[0], value=value, file=file)
        return json_groups_gen_write(keys, value=value, file=file)
    else:
        return json_array_gen_write(value=value, file=file)


def json_write(
    it: Iterable, 
    /, 
    keys: None | Callable | Sequence[Callable] = None, 
    value: Optional[Callable] = None, 
    file: SupportsWriteBytes | TextIOWrapper = stdout, 
):
    with gen_as_ctx(json_gen_write(keys=keys, value=value, file=file)) as write:
        foreach(write, it)


@gen_startup
def json_ensure_gen_write(
    path: PathType, 
    key: Optional[Callable] = None, 
    value: Optional[Callable] = None, 
    resume: bool = False, 
    bufsize: int = -1, 
):
    if bufsize <= 1:
        bufsize = -1
    if resume and exists(path):
        f = open(path, "r+b", buffering=bufsize)
    else:
        f = open(path, "wb", buffering=bufsize)
    seek = f.seek
    write = f.write
    not_first = seek(0, 2) >= 2
    if not not_first:
        seek(0)
    if key is None:
        while True:
            val = yield
            if value is not None:
                val = value(val)
            if not_first:
                seek(-1, 1)
                tpl = b",%s]"
            else:
                tpl = b"[%s]"
                not_first = True
            write(tpl % dumps(val))
    else:
        while True:
            val = yield
            if value is not None:
                val = value(val)
            if not_first:
                seek(-1, 1)
                tpl = b",%s:%s}"
            else:
                tpl = b"{%s:%s}"
                not_first = True
            write(tpl % (dumps(str(key(val))), dumps(val)))


def json_ensure_write(
    it: Iterable, 
    /, 
    path: PathType, 
    key: Optional[Callable] = None, 
    value: Optional[Callable] = None, 
    resume: bool = False, 
    bufsize: int = -1, 
):
    with gen_as_ctx(json_ensure_gen_write(
        it, 
        path, 
        key=key, 
        value=value, 
        resume=resume, 
        bufsize=bufsize, 
    )) as write:
        foreach(write, it)

