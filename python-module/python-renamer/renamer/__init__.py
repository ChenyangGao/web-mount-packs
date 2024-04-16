#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["batch_rename", "rename_with_pairs"]

from collections.abc import Callable, Iterable, Reversible, Sequence
from io import IOBase, TextIOWrapper
from itertools import count
from os import rename, fsdecode, PathLike
from os.path import abspath, join as joinpath, relpath
from pathlib import Path
from sys import stderr, stdout
from typing import cast, BinaryIO, IO, Optional, TypedDict

from filerev import file_reviter
from iterdir import iterdir
from json_write import json_log_gen_write

try:
    from orjson import loads
except ImportError:
    try:
        from ujson import loads
    except ImportError:
        from json import loads


class RenameResult(TypedDict):
    total: int
    success: int
    failed: int
    skipped: int


def batch_rename(
    top: None | bytes | str | PathLike = None, 
    getnew: Optional[Callable[[Path], bytes | str | PathLike]] = None, 
    predicate: Callable[[Path], Optional[bool]] = lambda p: not p.name.startswith(".") or None, 
    follow_symlinks: bool = False, 
    outfile: bytes | str | PathLike | IO = stdout, 
    rename: Optional[Callable] = rename, 
    use_relpath: bool = False, 
    show_progress: bool = False, 
) -> RenameResult:
    if getnew is None:
        getid = count(1).__next__
        getnew = lambda p: p.with_stem(str(getid()))
    if isinstance(outfile, PathLike) or not hasattr(outfile, "write"):
        outfile = open(outfile, "wb")
    if top is None:
        top = Path().absolute()
    else:
        top = Path(fsdecode(top)).absolute()
    toppath = str(top)
    gen = json_log_gen_write(file=outfile)
    output = gen.send
    total = success = failed = skipped = 0
    for path in iterdir(
        top, 
        topdown=False, 
        max_depth=-1, 
        predicate=predicate, 
        follow_symlinks=follow_symlinks, 
    ):
        total += 1
        try:
            pathold = str(path)
            pathnew = abspath(fsdecode(getnew(path)))
            if pathold == pathnew:
                skipped += 1
                continue
            if rename is not None:
                rename(pathold, pathnew)
            success += 1
        except Exception as exc:
            failed += 1
            print(f"{type(exc).__qualname__}: {exc}", file=stderr)
        else:
            if use_relpath:
                output((relpath(pathold, top), relpath(pathnew, top)))
            else:
                output((pathold, pathnew))
    return {"total": total, "success": success, "failed": failed, "skipped": skipped}


def rename_with_pairs(
    pairs: bytes | str | PathLike | BinaryIO | TextIOWrapper | Iterable[Sequence[str]], 
    /, 
    top: None | bytes | str | PathLike = None, 
    reverse: bool = False, 
    show_progress: bool = False, 
) -> RenameResult:
    if reverse:
        if isinstance(pairs, IOBase):
            file = pairs
            revit: Iterable[bytes | str]
            try:
                file.seek(0, 2)
            except Exception:
                revit = reversed(list(file))
            else:
                revit = file_reviter(file)
            pairs = map(loads, revit)
        elif isinstance(pairs, (bytes, str, PathLike)):
            pairs = map(loads, file_reviter(open(pairs, "rb")))
        else:
            it = cast(Iterable[Sequence[str]], pairs)
            if not isinstance(it, Reversible):
                it = list(it)
            pairs = reversed(it)
        pairs = map(reversed.__call__, pairs)
    else:
        if isinstance(pairs, IOBase):
            pairs = map(loads, pairs)
        elif isinstance(pairs, (bytes, str, PathLike)):
            pairs = map(loads, open(pairs, "rb"))
    pairs = cast(Iterable[Sequence[str]], pairs)
    if top is not None:
        top = fsdecode(top)
    if top:
        pairs = ((joinpath(top, old), joinpath(top, new)) for old, new in pairs)
    total = success = failed = skipped = 0
    for old, new in pairs:
        total += 1
        if old == new:
            skipped += 1
            continue
        try:
            rename(old, new)
            success += 1
        except Exception as exc:
            failed += 1
            print(f"{type(exc).__qualname__}: {exc}", file=stderr)
    return {"total": total, "success": success, "failed": failed, "skipped": skipped}

