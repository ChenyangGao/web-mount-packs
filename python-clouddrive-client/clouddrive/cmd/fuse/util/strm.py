#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["parse"]

import sys

from collections import defaultdict, ChainMap
from collections.abc import Callable, Iterator, MutableMapping
from functools import partial
from importlib import import_module
from importlib.machinery import all_suffixes as importlib_all_suffixes
from operator import attrgetter
from os import chdir, fsdecode, getcwd, PathLike
from os.path import abspath, basename, dirname, isdir, splitext
from re import compile as re_compile, Match
from runpy import run_path
from textwrap import dedent
from typing import cast, Final, Literal, NamedTuple
from types import ModuleType
from urllib.parse import urljoin
from zipfile import is_zipfile

from clouddrive import CloudDrivePath


PARSERS: Final[dict[str, Callable]] = {}
CRE_finditer_flags_count: Final[Callable[[str], Iterator[Match]]] = re_compile(
    "(?P<range>(?P<begin>\d+)-(?P<end>\d+)(?:-(?P<step>\d+))?)|(?P<global>(?P<ge>\d*)g)|(?P<neq>(?P<sign>[<>!]?=?)(?P<num>\d+))"
).finditer
CRE_match_bare_lambda: Final[Callable[[str], None | Match]] = re_compile(
    "lambda[ \t]*:"
).match


def bind_function_registry(
    m: MutableMapping, 
    /, 
    default_key_func: Callable = attrgetter("__name__"), 
) -> Callable:
    def register(func_or_key, /, key=None):
        if not callable(func_or_key):
            return partial(register, key=func_or_key)
        if key is None:
            key = default_key_func(func_or_key)
        m[key] = func_or_key
        return func_or_key
    return register


def make_resub_check_count(flags: str) -> None | Literal[True] | Callable:
    flag_global = False
    ls_ge: list[int] = []
    ls_le: list[int] = []
    set_eq: set[int] = set()
    set_ne: set[int] = set()

    for match in CRE_finditer_flags_count(flags):
        match match.lastgroup:
            case "range":
                begin, end = int(match["begin"]), int(match["end"])
                if begin == end:
                    set_eq.add(begin)
                    continue
                step = match["step"]
                if step:
                    step = int(step)
                    if step == 0:
                        step = 1
                else:
                    step = 1
                if begin < end:
                    rng = range(begin, end+1, step)
                else:
                    rng = range(begin, end-1, -step)
                set_eq.update(rng)
            case "global":
                num = match["ge"]
                if num:
                    ls_ge.append(num)
                else:
                    flag_global = True
            case "neq":
                num = int(match["num"])
                match match["sign"]:
                    case ">":
                        ls_ge.append(num+1)
                    case ">=":
                        ls_ge.append(num)
                    case "<":
                        ls_le.append(num-1)
                    case "<=":
                        ls_le.append(num)
                    case "" | "=":
                        set_eq.add(num)
                    case "!" | "!=":
                        set_ne.add(num)
    all_check = []
    if ls_ge:
        all_check.append(f"{max(ls_ge)} <= no")
    if ls_le:
        all_check.append(f"no <= {min(ls_le)}")
    set_ne -= set_eq
    if set_ne:
        all_check.append(f"no not in {frozenset(set_ne)}")
    if all_check:
        check = " and ".join(all_check)
        if set_eq:
            check = f"no in {frozenset(set_eq)} or " + check
        return eval("lambda no: " + check)
    elif flag_global:
        return True
    elif not set_eq:
        return None
    else:
        return lambda no: no in set_eq


class ResubSplitResult(NamedTuple):
    pattern: str
    repl: str
    flags: str
    reflags: str
    check_count: None | Literal[True] | Callable


def split_resub_expr(expr: str) -> ResubSplitResult:
    pattern = repl = flags = reflags = ""
    check_count = None
    if not expr:
        return ResubSplitResult(pattern, repl, flags, reflags, check_count)
    sep = expr[0]
    if sep == "\\":
        parts = expr[1:].split(sep, 2)
    else:
        pat = re_compile(rf"{sep}([^\\{sep}]*(?:\\.[^\\{sep}]*)*)")
        parts = []
        start = 0
        for m, _ in zip(pat.finditer(expr), range(2)):
            parts.append(m[1])
            start = m.end()
        parts.append(expr[start+1:])
        if len(parts) > 0:
            parts[0] = parts[0].replace(f"\\{sep}", sep)
        if len(parts) > 1:
            parts[1] = parts[1].replace(f"\\{sep}", sep)
    match parts:
        case [pattern]:
            ...
        case [pattern, repl]:
            ...
        case [pattern, repl, flags]:
            check_count = make_resub_check_count(flags)
            f_set, _, f_unset = flags.rpartition("-")
            reflags = "".join(filter(f_set.__contains__, "aiLmsux"))
            rf_unset = "".join(filter(f_unset.__contains__, "imsx"))
            if rf_unset:
                reflags = "-" + rf_unset
    return ResubSplitResult(pattern, repl, flags, reflags, check_count)


def load_any_module(
    *modules: str, 
    package: None | str = None, 
) -> None | ModuleType:
    pop_module = sys.modules.pop
    if package:
        package_start = package + "."
        modules_old = {
            name: pop_module(name) 
            for name in tuple(sys.modules) 
            if name == package or name.startswith(package_start)
        }
    else:
        modules_old = {
            name: pop_module(name) 
            for name in modules 
            if name in sys.modules
        }
    for module in modules:
        try:
            if package:
                if module in ("", "."):
                    mod = import_module(package)
                else:
                    mod = import_module("."+module, package)
            else:
                mod = import_module(module)
        except:
            pass
        else:
            # NOTE ensure that it is not a `Namespace`
            if mod.__file__:
                return mod
    return None


def load_module_from_path(
    path: bytes | str | PathLike, 
    try_modules_in: tuple[str, ...] = (), 
) -> None | ModuleType:
    path = abspath(fsdecode(path))
    sys_path_old = sys.path
    sys_modules_old = sys.modules
    try:
        sys.modules = sys_modules_old.copy()
        if isdir(path):
            sys.path = [dirname(path), *sys_path_old]
            package = basename(path)
            return load_any_module("", *try_modules_in, package=package)
        elif is_zipfile(path):
            sys.path = [path, *sys_path_old]
            return load_any_module("__init__", *try_modules_in)
        elif path.endswith(tuple(importlib_all_suffixes())):
            cwd_old = getcwd()
            chdir(dirname(path))
            try:
                sys.path = ["", *sys_path_old]
                module = splitext(basename(path))[0]
                return import_module(module)
            finally:
                chdir(cwd_old)
        return None
    finally:
        sys.modules = sys_modules_old
        sys.path = sys_path_old


register: Final = bind_function_registry(PARSERS)


@register("base-url")
def parse_base_url(base_url: str, /, globals: dict) -> Callable:
    def out(path: CloudDrivePath):
        return urljoin(base_url, path.relative_to())
    return out


@register("expr")
def parse_expression(expr: str | PathLike, /, globals: dict) -> Callable:
    if isinstance(expr, PathLike):
        return parse_expression(open(expr, encoding="utf-8").read(), globals)
    code = compile(expr.strip(), "-", "eval")
    def out(path: CloudDrivePath):
        return eval(code, globals, {"path": path})
    return out


@register("fstring")
def parse_fstring(expr: str | PathLike, /, globals: dict) -> Callable:
    if isinstance(expr, PathLike):
        return parse_fstring(open(expr, encoding="utf-8").read(), globals)
    return parse_expression("f%r" % expr, globals)


@register("lambda")
def parse_lambda(expr: str | PathLike, /, globals: dict) -> Callable:
    if isinstance(expr, PathLike):
        return parse_lambda(open(expr, encoding="utf-8").read(), globals)
    expr = expr.strip()
    if (match := CRE_match_bare_lambda(expr)):
        return parse_expression(expr[match.end():], globals)
    if not expr.startswith("lambda "):
        expr = "lambda " + expr
    return eval(expr, globals)


@register("stmt")
def parse_statement(script: str | PathLike, /, globals: dict) -> Callable:
    if isinstance(script, PathLike):
        return parse_statement(open(script, encoding="utf-8").read(), globals)
    code = compile(dedent(script).strip().removesuffix(">>> "), "-", "exec")
    def out(path: CloudDrivePath):
        ns: dict = {"path": path}
        eval(code, globals, ns)
        try:
            return ns["url"]
        except KeyError:
            for out in reversed(ns.values()):
                return out
    return out


@register("file")
def parse_file(script: str | PathLike, /, globals: dict) -> None | Callable:
    if isinstance(script, PathLike):
        globals = run_path(fsdecode(script), init_globals=globals, run_name="__main__")
    else:
        script = dedent(script).removesuffix(">>> ").replace("\n>>> ", "\n")
        if script: 
            globals.setdefault("__name__", "__main__")
            exec(script, globals)
    return globals.get("run") or globals.get("convert")


@register("module")
def parse_module(script: str | PathLike, /, globals: dict) -> Callable:
    if isinstance(script, PathLike):
        import builtins
        builtins_globals = builtins.__dict__
        builtins_globals_copy = builtins_globals.copy()
        try:
            builtins_globals.update(globals)
            mod = load_module_from_path(script, try_modules_in=("run", "convert"))
            if mod:
                globals.update(mod.__dict__)
            globals["__module__"] = mod
            return parse_file("", globals)
        finally:
            builtins_globals.clear()
            builtins_globals.update(builtins_globals_copy)
    globals.setdefault("__name__", "-")
    return parse_file(script, globals)


@register("resub")
def parse_resub_expr(expr: str | PathLike, /, globals: dict) -> Callable:
    if isinstance(expr, PathLike):
        return parse_resub_expr(open(expr, encoding="utf-8").read(), globals)
    pattern, repl, flags, reflags, check_count = split_resub_expr(expr)
    count = int(not check_count)
    if not callable(check_count):
        check_count = lambda no: True
    if reflags:
        pattern = f"(?{reflags}:{pattern})"
    sub = re_compile(pattern).sub
    def new_repl():
        no = 0
        def do_repl(m):
            nonlocal check_count, no
            no += 1
            if not cast(Callable, check_count)(no):
                return m[0]
            map_: MutableMapping = {"_": m[0], "_0": m[0], "_i": no}
            map_.update((f"_{i}", v or "") for i, v in enumerate(m.groups(), 1))
            map_.update((k, v or "") for k, v in m.groupdict().items())
            map_ = ChainMap(map_, globals, defaultdict(str))
            if "e" in flags:
                return eval("f%r" % repl, None, map_)
            elif "f" in flags:
                return repl.format(
                    m.group(), 
                    *m.groups(), 
                    **{
                        k: v for k, v in map_.items() 
                        if isinstance(k, str) and k.isidentifier()
                    }, 
                )
            elif "F" in flags:
                return repl.format_map(map_)
            elif "%%" in flags:
                return repl % map_
            elif "%" in flags:
                return repl % (m.group(), *m.groups())
            else:
                return m.expand(repl)
        return do_repl
    def out(path: CloudDrivePath):
        return sub(new_repl(), path.get_url(), count=count)
    return out


def parse(
    script: str | PathLike, 
    /, 
    globals: None | dict = None, 
    *, 
    init_globals: None | str | PathLike = None, 
    code_type: str = "expr", 
) -> None | Callable:
    if code_type not in PARSERS:
        return None
    if globals is None:
        globals = {"__name__": "__main__"}
    if isinstance(init_globals, PathLike):
        run_path(fsdecode(init_globals), globals, "__main__")
    elif init_globals:
        exec(init_globals, globals)
    return PARSERS[code_type](script, globals)

