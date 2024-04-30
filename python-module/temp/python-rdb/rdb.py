#!/usr/bin/env python3
# coding: utf-8

"""这个模块提供了一些与 RDBMS (关系数据库管理系统) 有关的工具函数
See: https://peps.python.org/pep-0249/
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 0)
__all__ = ["is_connection", "ctx_con", "execute", "get_fields", "dict_iter"]


from contextlib import contextmanager
from typing import Iterator, Optional

from .args import Args


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
            raise TypeError("Cant't get database connection from `con`")
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


def get_fields(cursor) -> Optional[tuple[str, ...]]:
    "从一个执行了查询语句的游标上获取数据的所有字段"
    if cursor.description is None:
        return
    return tuple(f[0] for f in cursor.description)


def dict_iter(
    cursor, 
    fields: Optional[tuple[str, ...]] = None, 
) -> Iterator[dict]:
    "在一个执行了查询语句的游标上迭代：每次提供字段和数据组合成的字典"
    if not fields:
        fields = get_fields(cursor)
    if not fields:
        raise RuntimeError("No field specified")
    for row in cursor:
        yield dict(zip(fields, row))

