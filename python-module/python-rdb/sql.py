#!/usr/bin/env python3
# coding: utf-8

"""这个模块提供了一些与 RDBMS(关系数据库管理系统) 的
 SQL(结构查询语言) 生成有关的工具函数
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 6)
__all__ = [
    "make_url", "quote_enclose", "sql_deinject", "str_deinject", "strify_tuple", 
    "Encodable", "AsIs", "AsInt", "AsFloat", "AsHexInt", "AsHexStr", "AsJSON", 
    "DEFAULT_VALUE_MAP_PAIRS", "DEFAULT_TYPE_ENCODE_PAIRS", "SQLEncoder", "encode", 
    "w_and", "w_or", "w_not", "insert_values_clause", "update_set_clause", "where_clause", 
    "insert_sql", "update_sql", "delete_sql", 
]

from collections.abc import Iterable, KeysView, Mapping, Sequence, ValuesView
from itertools import chain, islice
from json import dumps
from operator import methodcaller
from typing import cast, Any, Callable
from types import MappingProxyType
from urllib.parse import quote, urlencode

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
        add("?")
        if isinstance(query_params, str):
            add(quote(query_params, safe="%=&"))
        else:
            add(urlencode(query_params))
    return "".join(url_part_list)


def quote_enclose(name: Any, quote: str = '"') -> str:
    return f"{quote}{str(name).replace(quote, quote*2)}{quote}"


def sql_deinject(value: Any) -> str:
    return str(value).replace("'", "''")


def str_deinject(value: Any) -> str:
    return "'%s'" % sql_deinject(s).replace("\\", r"\\")


def strify_tuple(
    value: Iterable, 
    encode: Callable[..., str], 
) -> str:
    if not isinstance(value, Sequence):
        value = tuple(value)
    value = cast(Sequence, value)
    if not value:
        return "(NULL)"
    return f"({','.join(map(encode, value))})"


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


encode = SQLEncoder().encode


def w_and(parts, /):
    parts = [p for p in map(str, parts) if p.strip()]
    match parts:
        case []:
            return ""
        case [val]:
            return val
        case _:
            return "(%s)" % ')AND('.join(parts)


def w_or(parts, /):
    parts = [p for p in map(str, parts) if p.strip()]
    match parts:
        case []:
            return ""
        case [val]:
            return val
        case _:
            return "(%s)" % ')OR('.join(parts)


def w_not(part, /):
    s = str(part).strip()
    if not s:
        return ""
    return f'NOT ({s})'


def _quote_table_name(
    table: Any, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    if isinstance(table, str):
        return enclose(table)
    elif isinstance(table, tuple):
        return ".".join(_quote_table_name(f, enclose) for f in table)
    else:
        return str(table)


def insert_values_clause(
    values: None | tuple | Mapping | Iterable[tuple] | Iterable[Mapping], 
    fields: tuple[str, ...] = (), 
    default: Any = None, 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    if values is None:
        return ""

    if not callable(default):
        default0 = default
        default = lambda v: default0

    def encode_sequence(value):
        if not fields:
            return "(%s)" % ",".join(map(encode, value))
        return "(%s)" % ",".join(islice(
            map(encode, chain(value, map(default, fields[len(value):]))), 
            len(fields), 
        ))

    def encode_mapping(value):
        if not fields:
            return "(%s)" % ",".join(map(encode, ValuesView(value)))
        return "(%s)" % ",".join(
            encode(value[f] if f in value else default(f))
            for f in fields
        )

    match values:
        case tuple(value):
            if not fields and not value:
                return ""
            values_str = encode_sequence(value)
        case Mapping() as value:
            if not fields and not value:
                return ""
            values_str = encode_mapping(value)
        case Iterable():
            if not isinstance(values, Sequence):
                values = tuple(values)
            values = cast(Sequence, values)
            if len(values) == 0:
                return ""
            if all(isinstance(v, Sequence) for v in values):
                if not fields:
                    keys_len = len(values[0])
                    if not keys_len:
                        return ""
                    if any(keys_len != len(v) for v in values[1:]):
                        raise ValueError(
                            "No `fields` specified and `values` is an Iterable where all elements are Sequence, "
                            "therefore it is required that all elements have equal lengths"
                        )
                values_str = ",".join(map(encode_sequence, values))
            elif all(isinstance(v, Mapping) for v in values):
                if not fields:
                    fields = tuple(values[0])
                    if not fields:
                        return ""
                    keys = set(fields)
                    if any(keys != KeysView(v) for v in values[1:]):
                        raise ValueError(
                            "No `fields` specified and `values` is an Iterable where all elements are Mapping, "
                            "therefore it is required that the keys of all elements be equal"
                        )
                values_str = ",".join(map(encode_mapping, values))
            else:
                raise TypeError("`values' is an iterable, but its elements are not all Sequence or Mapping")
        case _:
            raise TypeError(f"An uncovered type of `values`: {type(values)!r}")

    if not fields:
        return "VALUES %s" % values_str
    return "(%s) VALUES %s" % (",".join(map(enclose, fields)), values_str)


def update_set_clause(
    values: Any, 
    leading_words: str = "SET", 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    match values:
        case dict():
            set_str = ",".join(f"{enclose(f)}={encode(v)}" for f, v in values.items())
        case tuple() | list():
            set_str = ",".join(
                f"{enclose(e[0])}={encode(e[1])}" if isinstance(e, tuple) else str(e)
                for e in values
            )
        case _:
            set_str = str(values)
    if not set_str:
        return ""
    return f"{leading_words} {set_str}"


def adaptive_binop(
    field, 
    value, 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    if callable(value):
        return f"{enclose(field)}{value()}"
    elif isinstance(value, (tuple, set, frozenset)):
        val = strify_tuple(value, encode)
        logic_op = 'IN'
    else:
        val = encode(value)
        if val == "NULL":
            logic_op = 'IS'
        else:
            logic_op = '='
    return f"{enclose(field)}{logic_op}{val}"


def value_as_func_return(value):
    return lambda: value


def _join_where_conds(
    where: Any, 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    match where:
        case Callable:
            return str(where())
        case dict():
            return w_and(
                adaptive_binop(k, v, encode=encode, enclose=enclose)
                for k, v in where.items()
            )
        case MappingProxyType():
            return w_or(
                adaptive_binop(k, v, encode=encode, enclose=enclose)
                for k, v in where.items()
            )
        case list():
            return w_and(
                _join_where_conds(where2, encode=encode, enclose=enclose)
                for where2 in where
            )
        case tuple():
            return w_or(
                _join_where_conds(where2, encode=encode, enclose=enclose)
                for where2 in where
            )
        case _:
            return str(where)


def where_clause(
    values: Any, 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    where_str = _join_where_conds(values, encode=encode, enclose=enclose)
    if not where_str:
        return ""
    return f"WHERE {where_str}"


def insert_sql(
    table: Any, 
    values: None | tuple | Mapping | Iterable[tuple] | Iterable[Mapping] = None, 
    fields: tuple[str,...] = (), 
    leading_words: str = "INSERT INTO", 
    default: Any = None, 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    """基于数据，生成一个插入语句。

    :param table: 数据库表名。
    :param values: 一条数据 或者 多条数据的列表，生成用于 VALUES 子句中。
    :param fields: 所有字段。如果为 None，且第一条数据为映射类型，
        则以它的所有键作为所有字段，否则忽略。
    :param leading_words: 语句的引导词，默认是 INSERT INTO，
        在 MySQL 中还可以是 INSERT IGNORE INTO, REPLACE INTO 等。
    :param default: 当某条数据的字段没有值时，所取的默认值。
    :param enclose: 生成名称两侧的包围，默认使用 "" 进行包围。
    :param encode: 对数据编码成字符串所用的函数。

    :return: 一个 SQL 的插入语句。
    """
    return "{leading_words} {table} {values_clause}".format(
        leading_words=leading_words, 
        table=_quote_table_name(table, enclose=enclose), 
        values_clause=insert_values_clause(
            values=values, fields=fields, default=default, 
            encode=encode, enclose=enclose, 
        )
    )


def update_sql(
    table: Any, 
    set: Any, 
    where: Any = None, 
    leading_words: str = "UPDATE", 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    """基于数据，生成一个更新语句

    :param table: 数据库表名。
    :param set: 数据，生成用于 SET 子句中。
    :param where: 数据，生成用于 WHERE 子句中。
    :param leading_words: 语句的引导词，默认是 DELETE FROM。
    :param enclose: 生成名称两侧的包围，默认使用 "" 进行包围。
    :param encode: 对数据编码成字符串所用的函数。

    :return: 一个 SQL 的更新语句。
    """
    return "{leading_words} {table} {set_clause} {where_clause}".format(
        leading_words=leading_words, 
        table=_quote_table_name(table, enclose=enclose), 
        set_clause=update_set_clause(set, encode=encode, enclose=enclose), 
        where_clause=where_clause(where, encode=encode, enclose=enclose), 
    )


def delete_sql(
    table: Any, 
    where: Any = None, 
    leading_words: str = "DELETE FROM", 
    encode: Callable[[Any], str] = encode, 
    enclose: Callable[[Any], str] = quote_enclose, 
) -> str:
    """基于数据，生成一个删除语句

    :param table: 数据库表名。
    :param where: 数据，生成用于 WHERE 子句中。
    :param leading_words: 语句的引导词，默认是 DELETE FROM。
    :param enclose: 生成名称两侧的包围，默认使用 "" 进行包围。
    :param encode: 对数据编码成字符串所用的函数。

    :return: 一个 SQL 的删除语句。
    """
    return "{leading_words} {table} {where_clause}".format(
        leading_words=leading_words, 
        table=_quote_table_name(table, enclose=enclose), 
        where_clause=where_clause(where, encode=encode, enclose=enclose), 
    )

