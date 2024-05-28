#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["register_maker", "make_predicate"]

from collections.abc import Callable
from re import compile as re_compile
from runpy import run_path
from textwrap import dedent
from typing import Final, Optional

from clouddrive import CloudDrivePath
from path_ignore_pattern import read_str, read_file, parse


ConditionSourceType = CloudDrivePath
PredicateType = Callable[[ConditionSourceType], bool]
PredicateMakerType = Callable[[str, dict], Optional[PredicateType]]

TYPE_TO_PREIDCATE_MAKERS: Final[dict[str, PredicateMakerType]] = {}


def register_maker(
    type: str, 
    /, 
) -> Callable[[PredicateMakerType], PredicateMakerType]:
    def register(func: PredicateMakerType, /) -> PredicateMakerType:
        TYPE_TO_PREIDCATE_MAKERS[type] = func
        return func
    return register


def make_predicate(
    code: str, 
    ns: Optional[dict] = None, 
    /, 
    type: str = "expr", 
) -> Optional[PredicateType]:
    if not code:
        return None
    if ns is None:
        ns = {}
    return TYPE_TO_PREIDCATE_MAKERS[type](code, ns)


@register_maker("ignore")
def make_predicate_ignore(
    expr: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    ignore = parse(read_str(expr))
    if not ignore:
        return None
    return lambda p, /: not ignore(p.path + "/"[:p.is_dir()])


@register_maker("ignore-file")
def make_predicate_ignore_file(
    path: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    ignore = parse(read_file(open(path, encoding="utf-8")))
    if not ignore:
        return None
    return lambda p, /: not ignore(p.path + "/"[:p.is_dir()])


@register_maker("filter")
def make_predicate_filter(
    expr: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    ignore = parse(read_str(expr))
    if not ignore:
        return None
    return lambda p, /: ignore(p.path + "/"[:p.is_dir()])


@register_maker("filter-file")
def make_predicate_filter_file(
    path: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    ignore = parse(read_file(open(path, encoding="utf-8")))
    if not ignore:
        return None
    return lambda p, /: ignore(p.path + "/"[:p.is_dir()])


@register_maker("expr")
def make_predicate_expr(
    expr: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    expr = expr.strip()
    if not expr:
        return None
    code = compile(expr, "-", "eval")
    return lambda path: eval(code, ns, {"path": path})


@register_maker("re")
def make_predicate_re(
    expr: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    search = re_compile(expr).search
    return lambda path: search(path["name"]) is not None


@register_maker("lambda")
def make_predicate_lambda(
    expr: str, 
    ns: dict, 
    /, *, 
    _cre_check=re_compile(r"lambda\b").match, 
) -> Optional[PredicateType]:
    expr = expr.strip()
    if not expr:
        return None
    if _cre_check(expr) is None:
        expr = "lambda " + expr
    return eval(expr, ns)


@register_maker("stmt")
def make_predicate_stmt(
    stmt: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    stmt = dedent(stmt).strip()
    if not stmt:
        return None
    code = compile(stmt, "-", "exec")
    def predicate(path):
        try:
            eval(code, ns, {"path": path})
            return True
        except:
            return False
    return predicate


@register_maker("code")
def make_predicate_code(
    code: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    code = dedent(code).strip()
    if not code:
        return None
    exec(code, ns)
    if callable(check := ns.get("check")):
        return check
    if callable(predicate := ns.get("predicate")):
        return predicate
    return None


@register_maker("path")
def make_predicate_path(
    path: str, 
    ns: dict, 
    /, 
) -> Optional[PredicateType]:
    ns = run_path(path, ns)
    if callable(check := ns.get("check")):
        return check
    if callable(predicate := ns.get("predicate")):
        return predicate
    return None

