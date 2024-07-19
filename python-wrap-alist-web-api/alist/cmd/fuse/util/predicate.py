#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["register_maker", "make_predicate"]

from collections.abc import Callable
from re import compile as re_compile
from runpy import run_path
from textwrap import dedent
from typing import Final

from alist.component import AlistPath
from path_ignore_pattern import read_str, read_file, parse, ExtendedType


ConditionSourceType = AlistPath
PredicateType = Callable[[ConditionSourceType], bool]
PredicateMakerType = Callable[[str, dict], None | PredicateType]

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
    ns: None | dict = None, 
    /, 
    type: str = "expr", 
) -> None | PredicateType:
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
    _type: None | int | str | ExtendedType = None, 
) -> None | PredicateType:
    ignore = parse(read_str(expr), extended_type=_type)
    if not ignore:
        return None
    return lambda p, /: not ignore(p.path + "/"[:p.is_dir()])


@register_maker("ignore-with-mime")
def make_predicate_ignore_with_mime(
    expr: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    return make_predicate_ignore(expr, ns, _type=ExtendedType.mime) # type: ignore


@register_maker("ignore-file")
def make_predicate_ignore_file(
    path: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    expr = open(path, encoding="utf-8").read()
    return make_predicate_ignore(expr, ns)


@register_maker("ignore-file-with-mime")
def make_predicate_ignore_file_with_mime(
    path: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    expr = open(path, encoding="utf-8").read()
    return make_predicate_ignore_with_mime(expr, ns)


@register_maker("filter")
def make_predicate_filter(
    expr: str, 
    ns: dict, 
    /, 
    _type: None | int | str | ExtendedType = None, 
) -> None | PredicateType:
    ignore = parse(read_str(expr), extended_type=_type)
    if not ignore:
        return None
    return lambda p, /: ignore(p.path + "/"[:p.is_dir()])


@register_maker("filter-with-mime")
def make_predicate_filter_with_mime(
    expr: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    return make_predicate_filter(expr, ns, _type=ExtendedType.mime) # type: ignore


@register_maker("filter-file")
def make_predicate_filter_file(
    path: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    expr = open(path, encoding="utf-8").read()
    return make_predicate_filter(expr, ns)


@register_maker("filter-file-with-mime")
def make_predicate_filter_file_with_mime(
    path: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    expr = open(path, encoding="utf-8").read()
    return make_predicate_filter_with_mime(expr, ns)


@register_maker("expr")
def make_predicate_expr(
    expr: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
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
) -> None | PredicateType:
    search = re_compile(expr).search
    return lambda path: search(path["name"]) is not None


@register_maker("lambda")
def make_predicate_lambda(
    expr: str, 
    ns: dict, 
    /, *, 
    _cre_check=re_compile(r"lambda\b").match, 
) -> None | PredicateType:
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
) -> None | PredicateType:
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


@register_maker("module")
def make_predicate_code(
    code: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    code = dedent(code).strip()
    if not code:
        return None
    exec(code, ns)
    if callable(check := ns.get("check")):
        return check
    if callable(predicate := ns.get("predicate")):
        return predicate
    return None


@register_maker("file")
def make_predicate_path(
    path: str, 
    ns: dict, 
    /, 
) -> None | PredicateType:
    ns = run_path(path, ns)
    if callable(check := ns.get("check")):
        return check
    if callable(predicate := ns.get("predicate")):
        return predicate
    return None

