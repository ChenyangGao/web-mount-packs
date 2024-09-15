#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "Connection", "FieldDescription", 
    "cm_connection", "cm_async_connection", "cm_cursor", "cm_async_cursor", 
    "execute", "async_execute", "cursor_description", "cursor_fields", 
    "cursor_iter", "cursor_tuple_iter", "cursor_dict_iter", "cursor_dataclass_iter", 
]

from collections.abc import AsyncIterable, AsyncIterable, Callable, Iterable, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, Field
from inspect import isawaitable
from itertools import chain, repeat
from keyword import iskeyword
from operator import itemgetter
from typing import overload, runtime_checkable, Any, NamedTuple, Protocol, TypeVar

from argtools import Args
from dictattr import AttrDict


T = TypeVar("T")
R = TypeVar("R")


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


def identity_row(fields: tuple[str, ...], val: T, /) -> T:
    return val


async def do_aclose(obj, /):
    if hasattr(obj, "aclose"):
        await obj.aclose()
    elif hasattr(obj, "close"):
        ret = obj.close()
        if isawaitable(ret):
            await ret


@contextmanager
def cm_connection(
    connect: Connection | Callable[..., Connection], 
    /, 
    connect_args: tuple | dict | Args = (), 
) -> Connection:
    is_manual_con = not isinstance(connect, Connection)
    con = Args.call(connect, connect_args) if is_manual_con else connect
    not_autocommit = not getattr(con, "autocommit", False)
    try:
        yield con
        if not not_autocommit:
            con.commit()
    except BaseException:
        if not not_autocommit:
            con.rollback()
        raise
    finally:
        if is_manual_con:
            con.close()


@asynccontextmanager
async def cm_async_connection(
    connect: Connection | Callable[..., Connection], 
    /, 
    connect_args: tuple | dict | Args = (), 
) -> Connection:
    is_manual_con = not isinstance(connect, Connection)
    con = Args.call(connect, connect_args) if is_manual_con else connect
    not_autocommit = not getattr(con, "autocommit", False)
    try:
        yield con
        if not not_autocommit:
            await con.commit()
    except BaseException:
        if not not_autocommit:
            await con.rollback()
        raise
    finally:
        if is_manual_con:
            await do_aclose(con)


@contextmanager
def cm_cursor(
    connect: Connection | Callable[..., Connection], 
    /, 
    connect_args: tuple | dict | Args = (), 
    cursor_args: tuple | dict | Args = (), 
):
    with cm_connection(connect, connect_args) as con:
        cursor = Args.call(con.cursor, cursor_args)
        try:
            yield cursor
        finally:
            cursor.close()


@asynccontextmanager
async def cm_async_cursor(
    connect: Connection | Callable[..., Connection], 
    /, 
    connect_args: tuple | dict | Args = (), 
    cursor_args: tuple | dict | Args = (), 
):
    async with cm_async_connection(connect, connect_args) as con:
        cursor = Args.call(con.cursor, cursor_args)
        try:
            yield cursor
        finally:
            await do_aclose(cursor)


def execute(
    con, 
    /, 
    sql: str, 
    params = None, 
    cursor_args: tuple | dict | Args = (), 
):
    if isinstance(con, Connection):
        cursor = Args.call(con.cursor, cursor_args)
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
    cursor_args: tuple | dict | Args = (), 
):
    if isinstance(con, Connection):
        cursor = Args.call(con.cursor, cursor_args)
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
) -> Iterable:
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
def cursor_iter(
    cursor: AsyncIterable[T], 
    /, 
    factory: Callable[[tuple[str, ...], T], R] = identity_row, 
) -> AsyncIterable[R]:
    ...
@overload
def cursor_iter(
    cursor: Iterable[T], 
    /, 
    factory: Callable[[tuple[str, ...], T], R] = identity_row, 
) -> Iterable[tuple]:
    ...
def cursor_iter(
    cursor: AsyncIterable[T] | Iterable[T], 
    /, 
    factory: Callable[[tuple[str, ...], T], R] = identity_row, 
) -> AsyncIterable[R] | Iterable[R]:
    if factory is identity_row:
        return cursor
    fields = cursor_fields(cursor)
    if isinstance(cursor, AsyncIterable):
        return (factory(fields, row) async for row in cursor)
    else:
        return (factory(fields, row) for row in cursor)


@overload
def cursor_tuple_iter(
    cursor: AsyncIterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterable[tuple]:
    ...
@overload
def cursor_tuple_iter(
    cursor: Iterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> Iterable[tuple]:
    ...
def cursor_tuple_iter(
    cursor: AsyncIterable | Iterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterable[tuple] | Iterable[tuple]:
    fields = cursor_fields(cursor)
    field_to_index = {k: i for i, k in enumerate(fields)}
    class Row(tuple):
        __fields__ = fields
        __slots__ = ()
        def __getattr__(self, attr, /):
            try:
                return self[attr]
            except KeyError as e:
                raise AttributeError(attr) from e
        def __getitem__(self, key, /):
            if isinstance(key, str):
                key = field_to_index[key]
            return super().__getitem__(key)
        def asdict(self, /) -> AttrDict:
            return AttrDict(zip(fields, self))
    match_args = []
    for i, f in enumerate(fields):
        if f.isidentifier() and not iskeyword(f):
            setattr(Row, f, property(itemgetter(i)))
            match_args.append(f)
    setattr(Row, "__match_args__", tuple(match_args))
    if isinstance(cursor, AsyncIterable):
        return (Row(map_parse(parse, row, fields)) async for row in cursor)
    else:
        return (Row(map_parse(parse, row, fields)) for row in cursor)


@overload
def cursor_dict_iter(
    cursor: AsyncIterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterable[AttrDict]:
    ...
@overload
def cursor_dict_iter(
    cursor: Iterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> Iterable[AttrDict]:
    ...
def cursor_dict_iter(
    cursor: AsyncIterable | Iterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterable[AttrDict] | Iterable[AttrDict]:
    fields = cursor_fields(cursor)
    if isinstance(cursor, AsyncIterable):
        return (AttrDict(zip(fields, map_parse(parse, row, fields))) async for row in cursor)
    else:
        return (AttrDict(zip(fields, map_parse(parse, row, fields))) for row in cursor)


@overload
def cursor_dataclass_iter(
    cursor: AsyncIterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterable[DataclassType]:
    ...
@overload
def cursor_dataclass_iter(
    cursor: Iterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> Iterable[DataclassType]:
    ...
def cursor_dataclass_iter(
    cursor: AsyncIterable | Iterable, 
    /, 
    parse: None | Callable | Mapping[int | str, Callable] = None, 
) -> AsyncIterable[DataclassType] | Iterable[DataclassType]:
    fields = cursor_fields(cursor)
    Row = dataclass(
        type("Row", (), {"__annotations__": {f: Any for f in fields}}), 
        unsafe_hash=True, 
        slots=True, 
    )
    if isinstance(cursor, AsyncIterable):
        return (Row(*map_parse(parse, row, fields)) async for row in cursor)
    else:
        return (Row(*map_parse(parse, row, fields)) for row in cursor)

