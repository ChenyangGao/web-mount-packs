#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "AsStr", "register_convert", "encode", "enclose", 
    "select_sql", "insert_sql", "update_sql", "delete_sql", 
]

from collections.abc import Callable, Iterable, Mapping, Sequence, ValuesView
from functools import partial
from itertools import chain, islice, repeat
from typing import Any
from urllib.parse import urlencode

from orjson import dumps


VALUE_CONVERTER: list[tuple[Any, Any]] = []
TYPE_CONVERTER: list[tuple[type, Any]] = []


class AsStr:

    def __init__(self, value: Any, /):
        self.value = value

    def __str__(self, /) -> str:
        return str(self.value)


def register_convert(dest, source: Any = None, /):
    if source is None:
        return partial(register_convert, dest)
    if isinstance(dest, type):
        TYPE_CONVERTER.append((source, dest))
    else:
        VALUE_CONVERTER.append((source, dest))
    return dest


def encode(
    obj: Any, 
    /, 
    default: None | Callable = None, 
) -> str:
    if obj is None:
        return "NULL"
    elif obj is True:
        return "TRUE"
    elif obj is False:
        return "FALSE"
    if isinstance(obj, (AsStr, int, float)):
        return str(obj)
    elif isinstance(obj, str):
        return "'%s'" % obj.replace("'", "''").replace("\\", r"\\")
    elif isinstance(obj, (bytes, bytearray, memoryview)):
        return "x'%s'" % obj.hex()
    elif isinstance(obj, (dict, list, tuple)):
        return "x'%s'" % dumps(obj).hex()
    try:
        obj = obj.sql_convert()
    except (AttributeError, TypeError):
        pass
    else:
        return encode(obj, default=default)
    for source, dest in VALUE_CONVERTER:
        if obj is source or obj == source:
            if callable(dest):
                dest = dest(obj)
            return encode(dest, default=default)
    for source, dest in VALUE_CONVERTER:
        if isinstance(obj, source):
            if callable(dest):
                dest = dest(obj)
            return encode(dest, default=default)
    if callable(default):
        return encode(default(obj))
    raise TypeError(f"can't encode {obj!r}")


def encode_tuple(
    values: Iterable, 
    encode: None | Callable[[Any], str] = encode, 
    default_none: bool = False, 
) -> str:
    return "(%s)" % (", ".join(map(encode, values)) or ("NULL" if default_none else ""))


def enclose(
    name: str | tuple[str, ...], 
    enclosing: str = '"', 
) -> str:
    if isinstance(name, tuple):
        return ".".join(enclose(part, enclosing) for part in name)
    if name.isidentifier():
        return name
    return enclosing + name.replace(enclosing, enclosing * 2) + enclosing


def values_clause(
    values: tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    default: Any = None, 
    encode: Callable[[Any], str] = encode, 
) -> tuple[int, tuple[int, ...], str]:
    if isinstance(default, Mapping):
        default = default.get
    elif not callable(default):
        default = lambda key, _v=default: _v

    ncall = 0
    fields_len = len(fields)

    def encode_sequence(l: Sequence, /) -> str:
        if len(l) >= fields_len:
            values = l[:fields_len]
        else:
            values = islice(chain(l, map(default, chain(fields[len(l):], repeat("")))), fields_len)
        return encode_tuple(values, encode)

    def encode_mapping(m: Mapping, /) -> str:
        if not fields:
            try:
                values = m.values()
            except (AttributeError, TypeError):
                values = ValuesView(m)
        else:
            def get(f):
                try:
                    return m[f]
                except LookupError:
                    return default(f)
            values = map(get, fields)
        return encode_tuple(values, encode)

    def encode_one(o: Sequence | Mapping, /):
        nonlocal fields, fields_len, ncall
        ncall += 1
        if isinstance(o, Sequence):
            if ncall == 1 and not fields_len:
                fields_len = len(o)
            return encode_sequence(o)
        else:
            if ncall == 1 and not fields:
                fields = tuple(o)
                fields_len = len(fields)
            return encode_mapping(o)

    if not isinstance(values, (tuple, Mapping)):
        values_str = ",\n       ".join(map(encode_one, values))
    else:
        values_str = encode_one(values)

    if values_str:
        values_str = "VALUES " + values_str
    return ncall, fields, values_str


def select_sql(
    values: tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    default: Any = None, 
    encode: Callable[[Any], str] = encode, 
) -> str:
    ncall, fields, values_str = values_clause(values, fields=fields, default=default, encode=encode)
    if not values_str:
        return ""
    if fields:
        fields_str = encode_tuple(fields, enclose)
        return f"""\
WITH cte{fields_str} AS (
{values_str}
)
SELECT * FROM cte
"""
    else:
        return f"SELECT * FROM ({values_str})"


def insert_sql(
    table: str | tuple[str, ...], 
    values: tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    default: Any = None, 
    encode: Callable[[Any], str] = encode, 
    onerror = "default", 
    returning: bool = False, 
) -> str:
    ncall, fields, values_str = values_clause(values, fields=fields, default=default, encode=encode)
    if not values_str:
        return ""
    table = enclose(table)
    if fields:
        fields_str = encode_tuple(fields, enclose)
    else:
        fields_str = ""
    match onerror:
        case "default":
            sql = f"""\
INSERT INTO {table}{fields_str}
{values_str}"""
        case "abort" | "fail" | "ignore" | "replace" | "rollback":
            sql = f"""\
INSERT OR {onerror.upper()} INTO {table}{fields_str}
{values_str}"""
        case "update":
            if not fields:
                raise ValueError("upsert need fields")
            set_str = "SET " + ",\n    ".join(f"{f} = excluded.{f}" for f in map(enclose, fields))
            sql = f"""\
INSERT INTO {table}{fields_str}
{values_str}
ON CONFLICT DO UPDATE
{set_str}"""
    if returning:
        sql += "\nRETURNING *"
    return sql


def _update_sql_one(
    table: str | tuple[str, ...], 
    values: tuple | Mapping, 
    fields: tuple[str, ...] = (), 
    key: str | tuple[str, ...] = "id", 
    default: Any = None, 
    encode: Callable[[Any], str] = encode, 
    returning: bool = False, 
) -> str:
    if isinstance(default, Mapping):
        default = default.get
    elif not callable(default):
        default = lambda key, _v=default: _v
    if isinstance(values, tuple):
        if not fields:
            raise ValueError("update need fields")
        m = dict(zip(fields, values))
        remain_fileds_count = len(fields) - len(values)
        if remain_fileds_count > 0:
            for f in fields[-remain_fileds_count:]:
                m[f] = default(f)
    elif not fields:
        fields = tuple(values)
        m = values
    else:
        m = {}
        for f in fields:
            try:
                m[f] = values[f]
            except KeyError:
                m[f] = default(f)
    table = enclose(table)
    def make_expr(key):
        value = encode(m[key])
        op = "IS" if value == "NULL" else "="
        return f"{enclose(key)} {op} {value}"
    if isinstance(key, str):
        try:
            where_str = f"WHERE {make_expr(key)}"
        except KeyError:
            raise ValueError("there is a key that is not in the fields")
    elif not key:
        raise ValueError("no key specified")
    elif any(k not in m for k in key):
        raise ValueError("there is a key that is not in the fields")
    else:
        where_str = "WHERE " + "\n  AND ".join(map(make_expr, key))
    set_str = "SET " + ",\n    ".join(f"{enclose(f)} = {encode(m[f])}" for f in fields)
    sql = f"""\
UPDATE {table}
{set_str}
{where_str}"""
    if returning:
        sql += "\nRETURNING *"
    return sql


def update_sql(
    table: str | tuple[str, ...], 
    values: tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    key: str | tuple[str, ...] = "id", 
    default: Any = None, 
    encode: Callable[[Any], str] = encode, 
    returning: bool = False, 
) -> str:
    if isinstance(values, (tuple, Mapping)):
        return _update_sql_one(
            table, 
            values, 
            fields=fields, 
            key=key, 
            default=default, 
            encode=encode, 
            returning=returning, 
        )
    ncall, fields, values_str = values_clause(values, fields=fields, default=default, encode=encode)
    if not values_str:
        return ""
    if not fields:
        raise ValueError("update need fields")
    table = enclose(table)
    fields_str = encode_tuple(fields, enclose)
    if isinstance(key, str):
        if key not in fields:
            raise ValueError("there is a key that is not in the fields")
        key = enclose(key)
        where_str = f"WHERE main.{key} = data.{key} OR (main.{key} IS NULL AND data.{key} is NULL)"
    elif not key:
        raise ValueError("no key specified")
    elif any(k not in fields for k in key):
        raise ValueError("there is a key that is not in the fields")
    else:
        where_str = "WHERE " + "\n  AND ".join(
            f"main.{f} = data.{f} OR (main.{f} IS NULL AND data.{f} is NULL)" for f in map(enclose, key))
    set_str = "SET " + ",\n    ".join(f"{f} = data.{f}" for f in map(enclose, fields))
    sql = f"""\
WITH data{fields_str} AS (
{values_str}
)
UPDATE {table} AS main
{set_str}
FROM data
{where_str}"""
    if returning:
        sql += "\nRETURNING *"
    return sql


def delete_sql(
    table: str | tuple[str, ...], 
    values: tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    encode: Callable[[Any], str] = encode, 
    returning: bool = False, 
) -> str:
    table = enclose(table)
    if not fields:
        raise ValueError("delete need fields")
    fields_str = encode_tuple(fields, enclose)
    # 使用 IN 语句实现批量查询，但是如果任意一条里面存在 NULL，则退化为使用 OR AND
    # 所以先要尝试进行拆分，凡是字段不够或者encode以后为 NULL 的，就要单独挑出来
    # where_parts = []
    # where_parts.append("{fields_str} IN (values_str)")
    # where_parts.extend(" AND ".join(for ) for)
    # where_str = " OR ".join(where_parts)
    if not where_str:
        raise ValueError("")
    sql = f"""\
DELETE FROM {table}
WHERE {where_str}"""
    if returning:
        sql += "\nRETURNING *"
    return sql

