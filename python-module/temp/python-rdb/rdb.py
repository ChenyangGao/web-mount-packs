#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = ["is_connection", "ctx_con", "execute", "get_fields", "tuple_iter", "dict_iter", "dataclass_iter"]


from collections import namedtuple
from collections.abc import AsyncIterable, Iterable, AsyncIterator, Iterator 
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import overload

from argtools import Args


def is_connection(con, /) -> bool:
    """Determine whether the `con` is a database connection.
    See: https://peps.python.org/pep-0249/#connection-objects
    """
    return not isinstance(con, type) and all(
        callable(getattr(con, attr, None)) 
        for attr in ("close", "commit", "rollback", "cursor")
    )


# TODO add async version
@contextmanager
def ctx_con(
    con, 
    /, 
    cursor_args = None, 
    do_tsac: bool = False, 
    do_close: bool = False, 
):
    """
    """
    if not is_connection(con):
        if callable(con):
            con = con()
            do_close = True
        else:
            raise TypeError("cant't get database connection from `con`")
    try:
        if cursor_args is None:
            yield con
        else:
            cur = Args.call(con.cursor, cursor_args)
            try:
                yield cur
            finally:
                cur.close()
        if do_tsac:
            con.commit()
    except BaseException:
        if do_tsac:
            con.rollback()
        raise
    finally:
        if do_close:
            con.close()


def execute(
    con, 
    args_it, 
    /, 
    callback = None, 
    cursor_args = (), 
    do_tsac: bool = False, 
    do_close: bool = False, 
):
    """
    """
    do_callback = callable(callback)
    with ctx_con(
        con, 
        cursor_args = cursor_args, 
        do_tsac     = do_tsac, 
        do_close    = do_close, 
    ) as cur:
        execute = cur.execute
        for args in args_it:
            r = Args.call(execute, args)
            if do_callback:
                callback(r, cur)


def get_fields(cursor) -> None | tuple[str, ...]:
    if cursor.description is None:
        return
    return tuple(f[0] for f in cursor.description)


@overload
def tuple_iter(
    cursor: AsyncIterable, 
    fields: None | tuple[str, ...] = None, 
) -> AsyncIterator[tuple]: ...
@overload
def tuple_iter(
    cursor: Iterable, 
    fields: None | tuple[str, ...] = None, 
) -> Iterator[tuple]: ...
def tuple_iter(
    cursor, 
    fields: None | tuple[str, ...] = None, 
):
    if not fields:
        fields = get_fields(cursor)
    if not fields:
        raise RuntimeError("no field specified")
    cls = namedtuple("Record", fields)
    if hasattr(cursor.__aiter__):
        return (cls(*row) async for row in cursor)
    else:
        return (cls(*row) for row in cursor)


@overload
def dict_iter(
    cursor: AsyncIterable, 
    fields: None | tuple[str, ...] = None, 
) -> AsyncIterator[dict]: ...
@overload
def dict_iter(
    cursor: Iterable, 
    fields: None | tuple[str, ...] = None, 
) -> Iterator[dict]: ...
def dict_iter(
    cursor, 
    fields: None | tuple[str, ...] = None, 
):
    if not fields:
        fields = get_fields(cursor)
    if not fields:
        raise RuntimeError("no field specified")
    if hasattr(cursor.__aiter__):
        return (dict(zip(fields, row)) async for row in cursor)
    else:
        return (dict(zip(fields, row)) for row in cursor)


@overload
def dataclass_iter(
    cursor: AsyncIterable, 
    fields: None | tuple[str, ...] = None, 
) -> AsyncIterator: ...
@overload
def dataclass_iter(
    cursor: Iterable, 
    fields: None | tuple[str, ...] = None, 
) -> Iterator: ...
def dataclass_iter(
    cursor, 
    fields: None | tuple[str, ...] = None, 
):
    if not fields:
        fields = get_fields(cursor)
    if not fields:
        raise RuntimeError("no field specified")
    cls = dataclass(type("Record", (), {"__annotations__": {f: object for f in fields}}), unsafe_hash=True, slots=True)
    if hasattr(cursor.__aiter__):
        return (cls(*row) async for row in cursor)
    else:
        return (cls(*row) for row in cursor)

