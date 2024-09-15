#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "Connection", "FieldDescription", 
    "cm_connection", "cm_async_connection", 
    "cm_cursor", "cm_async_cursor", 
    "execute", "async_execute", 
    "cursor_description", "cursor_fields", 
    "cursor_tuple_iter", "cursor_dict_iter", "cursor_dataclass_iter", 
]

from collections import namedtuple
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable, Iterator, Mapping
from contextlib import aclosing, asynccontextmanager, closing, contextmanager
from dataclasses import dataclass, Field
from itertools import chain, repeat
from typing import overload, runtime_checkable, NamedTuple, Protocol

from argtools import Args


@runtime_checkable
class Connection(Protocol):
    """See: https://peps.python.org/pep-0249/#connection-objects"""
    def close(self, /):
        pass

    def cursor(self, /):
        pass

    def commit(self, /):
        pass

    def rollback(self, /):
        pass


@runtime_checkable
class DataclassType(Protocol):

    @classmethod
    def __dataclass_fields__(cls, /) -> dict[str, Field]:
        pass


class FieldDescription(NamedTuple):
    name: str
    type_code: None | int
    display_size: None | int
    internal_size: None | int
    precision: None | int
    scale: None | int
    null_ok: None | int

    TYPE_MAP = {
        0: type(None), 
        1: int, 
        2: float, 
        3: str, 
        4: bytes, 
    }

    @property
    def type(self, /):
        return type(self).TYPE_MAP.get(self.type_code)


@contextmanager
def cm_connection(
    connect: Connection | Callable[..., Connection], 
    /, 
    args: None | tuple | dict | Args = None, 
    do_tsac: bool = False, 
) -> Connection:
    if isinstance(connect, Connection):
        con = connect
        if do_tsac:
            autocommit = getattr(con, "autocommit", None)
            can_set_autocommit = autocommit != 0 and autocommit is not None
            if can_set_autocommit:
                con.autocommit = False
            try:
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise
            finally:
                if can_set_autocommit:
                    con.autocommit = autocommit
        else:
            yield con
    else:
        if args is None:
            con = connect()
        elif isinstance(args, tuple):
            con = connect(*args)
        elif isinstance(args, dict):
            con = connect(**args)
        else:
            con = args(connect)
        with closing(con):
            if do_tsac:
                try:
                    yield con
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
            else:
                yield con


@asynccontextmanager
async def cm_async_connection(
    connect: Connection | Callable[..., Connection], 
    /, 
    args: None | tuple | dict | Args = None, 
    do_tsac: bool = False, 
) -> Connection:
    if isinstance(connect, Connection):
        con = connect
        if do_tsac:
            autocommit = getattr(con, "autocommit", None)
            can_set_autocommit = autocommit != 0 and autocommit is not None
            if can_set_autocommit:
                con.autocommit = False
            try:
                yield con
                await con.commit()
            except BaseException:
                await con.rollback()
                raise
            finally:
                if can_set_autocommit:
                    con.autocommit = autocommit
        else:
            yield con
    else:
        if args is None:
            con = connect()
        elif isinstance(args, tuple):
            con = connect(*args)
        elif isinstance(args, dict):
            con = connect(**args)
        else:
            con = args(connect)
        async with aclosing(con):
            if do_tsac:
                try:
                    yield con
                    await con.commit()
                except BaseException:
                    await con.rollback()
                    raise
            else:
                yield con


@contextmanager
def cm_cursor(
    connect: Connection | Callable[..., Connection], 
    /, 
    connect_args: None | tuple | dict | Args = None, 
    cursor_args: None | tuple | dict | Args = None, 
    do_tsac: bool = False, 
):
    with cm_connection(connect, connect_args, do_tsac=do_tsac) as con:
        if args is None:
            cursor = con.cursor()
        elif isinstance(args, tuple):
            cursor = con.cursor(*args)
        elif isinstance(args, dict):
            cursor = con.cursor(**args)
        else:
            cursor = args(con.cursor)
        with closing(cursor):
            yield cursor


@asynccontextmanager
async def cm_async_cursor(
    connect: Connection | Callable[..., Connection], 
    /, 
    connect_args: None | tuple | dict | Args = None, 
    cursor_args: None | tuple | dict | Args = None, 
    do_tsac: bool = False, 
):
    async with cm_async_connection(connect, connect_args, do_tsac=do_tsac) as con:
        if args is None:
            cursor = con.cursor()
        elif isinstance(args, tuple):
            cursor = con.cursor(*args)
        elif isinstance(args, dict):
            cursor = con.cursor(**args)
        else:
            cursor = args(con.cursor)
        async with aclosing(cursor):
            yield cursor


def execute(
    con, 
    /, 
    sql: str, 
    params = None, 
    cursor_args: None | tuple | dict | Args = None, 
):
    if isinstance(con, Connection):
        if args is None:
            cursor = con.cursor()
        elif isinstance(args, tuple):
            cursor = con.cursor(*args)
        elif isinstance(args, dict):
            cursor = con.cursor(**args)
        else:
            cursor = args(con.cursor)
    else:
        cursor = con
    if params is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, params)
    return cursor


async def async_execute(
    con: Connection, 
    /, 
    sql: str, 
    params = None, 
    cursor_args: None | tuple | dict | Args = None, 
):
    if isinstance(con, Connection):
        if args is None:
            cursor = con.cursor()
        elif isinstance(args, tuple):
            cursor = con.cursor(*args)
        elif isinstance(args, dict):
            cursor = con.cursor(**args)
        else:
            cursor = args(con.cursor)
    else:
        cursor = con
    if params is None:
        await cursor.execute(sql)
    else:
        await cursor.execute(sql, params)
    return cursor


def cursor_description(cursor, /) -> tuple[FieldDescription, ...]:
    if cursor.description is None:
        return ()
    return tuple(map(FieldDescription._make, cursor.description))


def cursor_fields(cursor, /) -> tuple[str, ...]:
    if cursor.description is None:
        return ()
    return tuple(fdesc[0] for fdesc in cursor.description)


def map_parse(
    parse: None | Callable | Mapping[int | str, Callable], 
    record: tuple, 
    fields: tuple[str, ...] = (), 
) -> Iterator:
    if parse is None:
        return record 
    elif isinstance(parse, Mapping):
        def parse_one(one, /):
            i, (f, v) = one
            try:
                return parse[i](v)
            except KeyError:
                pass
            if f:
                try:
                    return parse[f](v)
                except KeyError:
                    pass
            return v
        return map(parse_one, enumerate(zip(chain(fields, repeat(""), record))))
    else:
        return map(parse, record)


@overload
def cursor_tuple_iter(
    cursor: AsyncIterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterator[tuple]:
    ...
@overload
def cursor_tuple_iter(
    cursor: Iterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> Iterator[tuple]:
    ...
def cursor_tuple_iter(
    cursor: Iterable[tuple] | AsyncIterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterator[tuple] | Iterator[tuple]:
    if not fields:
        fields = cursor_fields(cursor)
    if fields:
        call = namedtuple("Record", fields)._make
    elif not parse:
        return cursor
    else:
        call = tuple
    if isinstance(cursor, AsyncIterable):
        return (call(*map_parse(parse, row, fields)) async for row in cursor)
    else:
        return (call(*map_parse(parse, row, fields)) for row in cursor)


@overload
def cursor_dict_iter(
    cursor: AsyncIterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterator[dict]:
    ...
@overload
def cursor_dict_iter(
    cursor: Iterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> Iterator[dict]:
    ...
def cursor_dict_iter(
    cursor: Iterable[tuple] | AsyncIterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> Iterator[dict] | AsyncIterator[dict]:
    if not fields:
        fields = cursor_fields(cursor)
    if not fields:
        raise RuntimeError("no field specified")
    if isinstance(cursor, AsyncIterable):
        return (dict(zip(fields, map_parse(parse, row, fields))) async for row in cursor)
    else:
        return (dict(zip(fields, map_parse(parse, row, fields))) for row in cursor)


@overload
def cursor_dataclass_iter(
    cursor: AsyncIterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterator[DataclassType]:
    ...
@overload
def cursor_dataclass_iter(
    cursor: Iterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> Iterator[DataclassType]:
    ...
def cursor_dataclass_iter(
    cursor: Iterable[tuple] | AsyncIterable[tuple], 
    /, 
    fields: tuple[str, ...] = (), 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterator[DataclassType] | Iterator[DataclassType]:
    if not fields:
        fields = cursor_fields(cursor)
    if not fields:
        raise RuntimeError("no field specified")
    Record = dataclass(
        type("Record", (), {"__annotations__": {f: object for f in fields}}), 
        unsafe_hash=True, 
        slots=True, 
    )
    if isinstance(cursor, AsyncIterable):
        return (Record(*map_parse(parse, row, fields)) async for row in cursor)
    else:
        return (Record(*map_parse(parse, row, fields)) for row in cursor)

