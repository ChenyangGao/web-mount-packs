#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = [
    "FetchType", "AutoCloseConnection", "AutoCloseCursor", "enclose", 
    "transact", "execute", "query", "find", "upsert_items", 
]

from collections.abc import Buffer, Callable, Iterable, Sequence
from contextlib import contextmanager, suppress
from enum import Enum
from os import PathLike
from re import compile as re_compile, IGNORECASE
from sqlite3 import connect, Connection, Cursor, ProgrammingError
from typing import Any, Final, Literal, Self


CRE_SELECT_SQL_match: Final = re_compile(r"\s*SELECT\b", IGNORECASE).match
CRE_COLNAME_sub: Final = re_compile(r" \[[^]]+\]$").sub


class FetchType(Enum):
    auto = 0
    one = 1
    any = 2
    dict = 3

    @classmethod
    def ensure(cls, val, /) -> Self:
        if isinstance(val, cls):
            return val
        if isinstance(val, str):
            try:
                return cls[val]
            except KeyError:
                pass
        return cls(val)


class AutoCloseCursor(Cursor):
    """会自动关闭 Cursor
    """
    def __del__(self, /):
        self.close()


class AutoCloseConnection(Connection):
    """会自动关闭 Connection
    """
    def __del__(self, /):
        with suppress(ProgrammingError):
            self.commit()
            self.close()

    def cursor(self, /, factory = AutoCloseCursor):
        return super().cursor(factory)


def enclose(
    name: str | Iterable[str], 
    encloser: str | tuple[str, str] = '"', 
) -> str:
    """在字段名外面添加包围符号

    :param name: 字段名，或者字段名的可迭代（将会用 '.' 进行连接）
    :param encloser: 包围符号

    :return: 处理后的字符串
    """
    if not isinstance(name, str):
        return ".".join(enclose(part, encloser) for part in name)
    if name.isidentifier():
        return name
    if isinstance(encloser, tuple):
        l, r = encloser
        return f"{l}{name}{r}"
    else:
        return f"{encloser}{name.replace(encloser, encloser * 2)}{encloser}"


@contextmanager
def transact(
    con: bytes | str | PathLike | Connection | Cursor, 
    /, 
    isolation_level: None | Literal["", "DEFERRED", "IMMEDIATE", "EXCLUSIVE"] = "", 
):
    """上下文管理器，创建一个 sqlite 数据库事务，会自动进行 commit 和 rollback

    :param con: 数据库连接或游标
    :param isolation_level: 隔离级别

    :return: 上下文管理器，返回一个游标
    """
    if isinstance(con, (bytes, PathLike)):
        with connect(con) as con:
            yield from transact.__wrapped__(con) # type: ignore
    elif isinstance(con, str):
        with connect(con, uri=con.startswith("file:")) as con:
            yield from transact.__wrapped__(con) # type: ignore
    else:
        if isinstance(con, Connection):
            cur: Cursor = con.cursor(factory=AutoCloseCursor)
        else:
            cur = con
            con = cur.connection
        if con.autocommit == 1:
            yield cur
        else:
            if con.isolation_level is None:
                if isolation_level is None:
                    yield cur
                    return
                cur.executescript(f"BEGIN {isolation_level};")
            elif isolation_level:
                cur.executescript(f"BEGIN {isolation_level};")
            try:
                yield cur
                con.commit()
            except:
                con.rollback()
                raise


def execute(
    con: Connection | Cursor, 
    /, 
    sql: str, 
    params: Any = None, 
    executemany: bool = False, 
    commit: bool = False, 
) -> Cursor:
    """执行一个 sql 语句

    :param con: 数据库连接或游标
    :param sql: sql 语句
    :param params: 参数，用于填充 sql 中的占位符，会根据具体情况选择使用 execute 或 executemany
    :param executemany: 强制使用 executemany
    :param commit: 是否在执行成功后进行 commit

    :return: 游标
    """
    if isinstance(con, Connection):
        cur: Cursor = con.cursor(factory=AutoCloseCursor)
    else:
        cur = con
        con = cur.connection
    is_iter = lambda x: isinstance(x, Iterable) and not isinstance(x, (str, Buffer))
    if executemany:
        cur.executemany(sql, params)
    elif params is None:
        cur.execute(sql)
    elif isinstance(params, (tuple, dict)):
        cur.execute(sql, params)
    elif is_iter(params):
        if not isinstance(params, Sequence) or not all(map(is_iter, params)):
            params = (e if is_iter(e) else (e,) for e in params)
        cur.executemany(sql, params)
    else:
        cur.execute(sql, (params,))
    if commit and con.autocommit != 1 and CRE_SELECT_SQL_match(sql) is None:
        con.commit()
    return cur


def query(
    con: Connection | Cursor, 
    /, 
    sql: str, 
    params: Any = None, 
    row_factory: None | int | str | FetchType | Callable[[Cursor, Any], Any] = None, 
) -> Cursor:
    """执行一个 sql 查询语句，或者 DML 语句但有 RETURNING 子句（但不会主动 commit）

    :param con: 数据库连接或游标
    :param sql: sql 语句
    :param params: 参数，用于填充 sql 中的占位符
    :param row_factory: 对数据进行处理，然后返回处理后的值

        - 如果是 Callable，则调用然后返回它的值
        - 如果是 FetchType.auto，则当数据是 tuple 且长度为 1 时，返回第 1 个为位置的值，否则返回数据本身
        - 如果是 FetchType.any，则返回数据本身
        - 如果是 FetchType.one，则返回数据中第 1 个位置的值（索引为 0）
        - 如果是 FetchType.dict，则返回字典，键从游标中获取

    :return: 游标
    """
    cursor = execute(con, sql, params)
    if row_factory is not None:
        if callable(row_factory):
            cursor.row_factory = row_factory
        else:
            match FetchType.ensure(row_factory):
                case FetchType.auto:
                    def row_factory(_, record):
                        if isinstance(record, tuple) and len(record) == 1:
                            return record[0]
                        return record
                    cursor.row_factory = row_factory
                case FetchType.one:
                    cursor.row_factory = lambda _, record: record[0]
                case FetchType.dict:
                    fields = tuple(CRE_COLNAME_sub("", f[0]) for f in cursor.description)
                    cursor.row_factory = lambda _, record: dict(zip(fields, record))
    return cursor


def find(
    con: Connection | Cursor, 
    /, 
    sql: str, 
    params: Any = None, 
    default: Any = None, 
    row_factory: int | str | FetchType | Callable[[Cursor, Any], Any] = "auto", 
) -> Any:
    """执行一个 sql 查询语句，或者 DML 语句但有 RETURNING 子句（但不会主动 commit），返回一条数据

    :param con: 数据库连接或游标
    :param sql: sql 语句
    :param params: 参数，用于填充 sql 中的占位符
    :param default: 当没有数据返回时，作为默认值返回，如果是异常对象，则进行抛出
    :param row_factory: 对数据进行处理，然后返回处理后的值

        - 如果是 Callable，则调用然后返回它的值
        - 如果是 FetchType.auto，则当数据是 tuple 且长度为 1 时，返回第 1 个为位置的值，否则返回数据本身
        - 如果是 FetchType.any，则返回数据本身
        - 如果是 FetchType.one，则返回数据中第 1 个位置的值（索引为 0）
        - 如果是 FetchType.dict，则返回字典，键从游标中获取

    :return: 查询结果的第一条数据
    """
    cursor = query(con, sql, params)
    record = cursor.fetchone()
    cursor.close()
    if record is None:
        if isinstance(default, BaseException):
            raise default
        return default
    if callable(row_factory):
        return row_factory(cursor, record)
    else:
        match FetchType.ensure(row_factory):
            case FetchType.auto:
                if isinstance(record, tuple) and len(record) == 1:
                    return record[0]
                return record
            case FetchType.one:
                return record[0]
            case FetchType.dict:
                return dict(zip((CRE_COLNAME_sub("", f[0]) for f in cursor.description), record))
            case _:
                return record


def upsert_items(
    con: Connection | Cursor, 
    items: dict | Sequence[dict], 
    /, 
    extras: None | dict = None, 
    fields: Sequence[str] = (), 
    table: str = "data", 
    commit: bool = False, 
) -> Cursor:
    """往表中插入或更新数据

    :param con: 数据库连接或游标
    :param items: 一组数据
    :param extras: 附加数据
    :param table: 表名
    :param commit: 是否提交

    :return: 游标
    """
    if isinstance(items, dict):
        items = items,
    elif not items:
        if isinstance(con, Cursor):
            return con
        else:
            return con.cursor(factory=AutoCloseCursor)
    if extras:
        items = [extras | item for item in items]
    if not fields:
        fields = tuple(items[0])
    sql = f"""\
INSERT INTO {table}({",".join(fields)})
VALUES ({",".join(map(":".__add__, fields))})
ON CONFLICT DO UPDATE SET {",".join(map("{0}=excluded.{0}".format, fields))}"""
    return execute(con, sql, items, executemany=True, commit=commit)

