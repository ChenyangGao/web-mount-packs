#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = [
    "AutoCloseConnection", "AutoCloseCursor", "enclose", 
    "transact", "execute", "query", "find", "upsert_items", 
]

from collections.abc import Buffer, Iterable, Sequence
from contextlib import contextmanager
from functools import partial
from os import PathLike
from re import compile as re_compile, IGNORECASE
from sqlite3 import connect, Connection, Cursor
from typing import Any, Final


CRE_SELECT_SQL_match: Final = re_compile(r"\s*SELECT\b", IGNORECASE).match


class AutoCloseCursor(Cursor):
    """会自动关闭 Cursor
    """
    def __del__(self, /):
        self.close()


class AutoCloseConnection(Connection):
    """会自动关闭 Connection
    """
    def __del__(self, /):
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
def transact(con: bytes | str | PathLike | Connection | Cursor, /):
    """上下文管理器，创建一个 sqlite 数据库事务，会自动进行 commit 和 rollback

    :param con: 数据库连接或游标

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
) -> Cursor:
    """执行一个 sql 查询(SELECT)语句

    :param con: 数据库连接或游标
    :param sql: sql 语句
    :param params: 参数，用于填充 sql 中的占位符

    :return: 游标
    """
    return execute(con, sql, params, commit=False)


def find(
    con: Connection | Cursor, 
    /, 
    sql: str, 
    params: Any = None, 
    default: Any = None, 
) -> Any:
    """执行一个 sql 查询(SELECT)语句，返回一条数据

    :param con: 数据库连接或游标
    :param sql: sql 语句
    :param params: 参数，用于填充 sql 中的占位符
    :param default: 当没有数据返回时，作为默认值返回，如果是异常对象，则进行抛出

    :return: 第 1 条查询结果，如果查询结果为只有一个元素的 tuple，则返回此元素
    """
    if (record := query(con, sql, params).fetchone()) is not None:
        if isinstance(record, tuple) and len(record) == 1:
            return record[0]
        return record
    if isinstance(default, BaseException):
        raise default
    return default


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
    executemany = not isinstance(items, dict)
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
    return execute(con, sql, items, executemany=executemany, commit=commit)

