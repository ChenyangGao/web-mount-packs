#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["register_maker", "make_predicate"]

from re import compile as re_compile
from runpy import run_path
from textwrap import dedent
from typing import Callable, Final, Optional


PREIDCATE_MAKERS: Final[dict[str, Callable[[str], Optional[Callable]]]] = {}


def register_maker(type: str) -> Callable:
    def register(func: Callable) -> Callable:
        PREIDCATE_MAKERS[type] = func
        return func
    return register


def make_predicate(code: str, /, type: str = "expr") -> Optional[Callable]:
    if not code:
        return None
    return PREIDCATE_MAKERS[type](code)


@register_maker("expr")
def make_predicate_expr(expr: str, /) -> Optional[Callable]:
    expr = expr.strip()
    if not expr:
        return None
    code = compile(expr, "-", "eval")
    return lambda attr: eval(code, {"attr": attr})


@register_maker("re")
def make_predicate_re(expr: str, /) -> Optional[Callable]:
    search = re_compile(expr).search
    return lambda attr: search(attr["name_all"]) is not None


@register_maker("lambda")
def make_predicate_lambda(
    expr: str, 
    /, *, 
    _cre_check=re_compile(r"lambda\b").match, 
) -> Optional[Callable]:
    expr = expr.strip()
    if not expr:
        return None
    if _cre_check(expr) is None:
        expr = "lambda " + expr
    return eval(expr, {})


@register_maker("stmt")
def make_predicate_stmt(stmt: str, /) -> Optional[Callable]:
    stmt = dedent(stmt).strip()
    if not stmt:
        return None
    code = compile(stmt, "-", "exec")
    def predicate(attr):
        try:
            eval(code, {"attr": attr})
            return True
        except:
            return False
    return predicate


@register_maker("code")
def make_predicate_code(code: str, /) -> Optional[Callable]:
    code = dedent(code).strip()
    if not code:
        return None
    ns: dict = {}
    exec(code, ns)
    return ns.get("check")


@register_maker("path")
def make_predicate_path(path: str, /) -> Optional[Callable]:
    ns = run_path(path, {}, run_name="__main__")
    return ns.get("check")

