#!/usr/bin/env python3
# coding: utf-8

"""这个模块提供了一些生成 SQL 的函数，主要针对 sqlite
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = [
    "make_url", "enclose", "sql_deinject", "str_deinject", "encode_tuple", 
    "select_sql", "insert_sql", "update_sql", "delete_sql", 
]

from collections.abc import Callable, Iterable, Mapping, Sequence, ValuesView
from itertools import chain, islice, repeat
from json import dumps
from operator import methodcaller
from typing import Any
from urllib.parse import urlencode

# TODO: 实现 2 个函数 quote 和 unquote，用来把 python 值转换为 SQL 文本字面值，适合包含在 SQL 语句中
# TODO: 实现 2 个函数 dump 和 load，用 pickle 实现，把 python 值进行序列化
# def quote(o, /) -> str:
#     if isinstance(o, str):
#         return "'%s'" % o.replace("'", "''")
#     elif isinstance(o, (bytes, bytearray)):
#         return "x'%s'" % o.hex()
#     ...
# from pickle import dumps, loads
# def dump(o, /) -> str:
#     return "x'%s'" % dumps(o).hex()
# def load(b, /) -> str:
#     if isinstance(b, str):
#         b = bytes.fromhex(b[2:-1])
#     return loads(b)

def make_url(
    protocol: Any = "sqlite3", 
    user: Any = "", 
    password: Any = "", 
    host: Any = "", 
    port: Any = "", 
    path: Any = "", 
    query_params: str | list | dict = "", 
) -> str:
    protocol_, user_, password_, host_, port_, path_ = \
        map(str, (protocol, user, password, host, port, path))
    url_part_list: list[str] = []
    add = url_part_list.append
    if not protocol_:
        raise ValueError(f"Bad <protocol>: can't be empty")
    add(protocol_)
    add("://")
    if user_ or password_:
        if user_:
            add(user_)
        if password_:
            add(":")
            add(password_)
        add("@")
    if host_:
        add(host_)
    if port_:
        add(":")
        add(port_)
    if not path_.startswith("/"):
        add("/")
    if path_:
        add(path_)
    if query_params:
        if not isinstance(query_params, str):
            query_params = urlencode(query_params)
        add("?")
        add(query_params)
    return "".join(url_part_list)


def enclose(
    name: str | tuple[str, ...], 
    enclosing: str = '"', 
) -> str:
    if isinstance(name, tuple):
        return ".".join(enclose(part, enclosing) for part in name)
    if name.isidentifier():
        return name
    return enclosing + name.replace(enclosing, enclosing * 2) + enclosing


def sql_deinject(s: str, /) -> str:
    return s.replace("'", "''")


def str_deinject(s: str, /) -> str:
    return "'%s'" % sql_deinject(s).replace("\\", r"\\")


def encode_tuple(
    values: Iterable, 
    encode: None | Callable[..., str] = None, 
) -> str:
    if encode is None:
        encode = DEFAULT_ENCODE
    return "(%s)" % (",".join(map(encode, values)) or "NULL")


class Encodable:
    encode_call: Callable[..., str] = str_deinject

    def __init__(self, value):
        self._value = value

    @property
    def value(self):
        return self._value

    def __repr__(self):
        return f"{type(self).__qualname__}({self._value!r})"

    def __str__(self):
        return self.encode()

    def encode(self) -> str:
        return type(self).encode_call(self._value)


class AsIs(Encodable):
    encode_call: Callable[..., str] = str


class AsInt(Encodable):
    @staticmethod
    def encode_call(value: Any) -> str:
        return str(int(value))


class AsFloat(Encodable):
    @staticmethod
    def encode_call(value: Any) -> str:
        return str(float(value))


class AsHexInt(Encodable):
    @staticmethod
    def encode_call(value: Any) -> str:
        try:
            return hex(value)
        except TypeError:
            if isinstance(value, (bytes, bytearray)):
                b = value
            elif isinstance(value, str):
                b = bytes(value, encoding="utf-8")
            else:
                b = bytes(value)
            return "0x" + b.hex()


class AsHexStr(Encodable):
    @staticmethod
    def encode_call(value: Any) -> str:
        try:
            return "x'%x'" % value
        except TypeError:
            if isinstance(value, (bytes, bytearray)):
                b = value
            elif isinstance(value, str):
                b = bytes(value, encoding="utf-8")
            else:
                b = bytes(value)
            return "x'%s'" % b.hex()


class AsJSON(Encodable):
    @staticmethod
    def encode_call(value: Any) -> str:
        return str_deinject(dumps(val))


DEFAULT_VALUE_MAP_PAIRS: list[tuple[Any, str | Callable[..., str]]] = [
    (None, "NULL"), 
    (True, "TRUE"), 
    (False, "FALSE"), 
]
DEFAULT_TYPE_ENCODE_PAIRS: list[tuple[type | tuple[type, ...], Callable[..., str]]] = [
    (Encodable, methodcaller("encode")), 
    ((int, float), str), 
    (str, str_deinject), 
    (__import__('numbers').Integral, AsInt.encode_call),
    ((__import__('numbers').Real, __import__('decimal').Decimal), AsFloat.encode_call),
    ((bytes, bytearray), AsHexStr.encode_call), 
    ((tuple, list, dict), AsJSON.encode_call), 
]


class SQLEncoder:

    def __init__(
        self, /, 
        value_map_pairs: list[tuple[Any, str | Callable[..., str]]] = DEFAULT_VALUE_MAP_PAIRS, 
        type_encode_pairs: list[tuple[type | tuple[type, ...], Callable[..., str]]] = DEFAULT_TYPE_ENCODE_PAIRS, 
    ):
        self.value_map_pairs = value_map_pairs
        self.type_encode_pairs = type_encode_pairs

    def default(self, value):
        return str_deinject(value)

    def encode(self, value):
        for val, map in self.value_map_pairs:
            if val is value:
                if callable(map):
                    return map(value)
                return map
            elif callable(val) and val(value):
                if callable(map):
                    return map(value)
                return map
        for typ, fn in self.type_encode_pairs:
            if isinstance(value, typ):
                try:
                    return fn(value, encode=self.encode)
                except TypeError:
                    return fn(value)
        return self.default(value)


DEFAULT_ENCODE = SQLEncoder().encode


def values_clause(
    values: tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    default: Any = None, 
    encode: Callable[[Any], str] = DEFAULT_ENCODE, 
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
        return "(%s)" % ", ".join(map(encode, values))

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
        return "(%s)" % ", ".join(map(encode, values))

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
    encode: Callable[[Any], str] = DEFAULT_ENCODE, 
) -> str:
    ncall, fields, values_str = values_clause(values, fields=fields, default=default, encode=encode)
    if not values_str:
        return ""
    if fields:
        fields_str = "(%s)" % ", ".join(map(enclose, fields))
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
    encode: Callable[[Any], str] = DEFAULT_ENCODE, 
    onerror = "default", 
) -> str:
    ncall, fields, values_str = values_clause(values, fields=fields, default=default, encode=encode)
    if not values_str:
        return ""
    table = enclose(table)
    if fields:
        fields_str = "(%s)" % ", ".join(map(enclose, fields))
    else:
        fields_str = ""
    match onerror:
        case "default":
            return f"""\
INSERT INTO {table}{fields_str}
{values_str}"""
        case "abort" | "fail" | "ignore" | "replace" | "rollback":
            return f"""\
INSERT OR {onerror.upper()} INTO {table}{fields_str}
{values_str}"""
        case "update":
            if not fields:
                raise ValueError("upsert need fields")
            set_str = "SET " + ",\n    ".join(f"{f} = excluded.{f}" for f in map(enclose, fields))
            return f"""\
INSERT INTO {table}{fields_str}
{values_str}
ON CONFLICT DO UPDATE
{set_str}"""


def _update_sql_one(
    table: str | tuple[str, ...], 
    values: tuple | Mapping, 
    fields: tuple[str, ...] = (), 
    key: str | tuple[str, ...] = "id", 
    default: Any = None, 
    encode: Callable[[Any], str] = DEFAULT_ENCODE, 
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
    return f"""\
UPDATE {table}
{set_str}
{where_str}"""


def update_sql(
    table: str | tuple[str, ...], 
    values: tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    key: str | tuple[str, ...] = "id", 
    default: Any = None, 
    encode: Callable[[Any], str] = DEFAULT_ENCODE, 
) -> str:
    if isinstance(values, (tuple, Mapping)):
        return _update_sql_one(table, values, fields=fields, key=key, default=default, encode=encode)
    ncall, fields, values_str = values_clause(values, fields=fields, default=default, encode=encode)
    if not values_str:
        return ""
    if not fields:
        raise ValueError("update need fields")
    table = enclose(table)
    fields_str = "(%s)" % ", ".join(map(enclose, fields))
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
    return f"""\
WITH data{fields_str} AS (
{values_str}
)
UPDATE {table} AS main
{set_str}
FROM data
{where_str}"""


def delete_sql(
    table: str | tuple[str, ...], 
    values: Mapping | Iterable[Mapping], 
    key: str | tuple[str, ...] = "id", 
    encode: Callable[[Any], str] = DEFAULT_ENCODE, 
) -> str:
    table = enclose(table)
    # 使用 IN 语句实现批量查询，但是如果任意一条里面存在 NULL，则退化为使用 OR AND
    return f"DELETE FROM {table} WHERE (k1, k2) IN ((v1, v2))"

# TODO: dml 支持 returning


