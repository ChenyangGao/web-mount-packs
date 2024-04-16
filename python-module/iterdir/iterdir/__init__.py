#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["DirEntry", "iterdir"]

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from os import fspath, listdir, scandir, stat, DirEntry as _DirEntry, PathLike
from os.path import (
    abspath, commonpath, basename, isfile, isdir, islink, join as joinpath, realpath, 
)
from pathlib import Path
from typing import overload, Generic, Never, Optional, TypeVar


AnyStr = TypeVar("AnyStr", bytes, str)
PathType = TypeVar("PathType", bytes, str, PathLike)


class DirEntryMeta(type):

    def __instancecheck__(cls, inst, /):
        if isinstance(inst, _DirEntry):
            return True
        return super().__instancecheck__(inst)

    def __subclasscheck__(cls, sub, /):
        if issubclass(sub, _DirEntry):
            return True
        return super().__subclasscheck__(sub)


class DirEntry(Generic[AnyStr], metaclass=DirEntryMeta):
    __slots__ = "path",

    path: AnyStr

    def __init__(self, /, path: AnyStr | PathLike[AnyStr]):
        path = fspath(path)
        if not path:
            path = abspath(path)
        super().__setattr__("path", path)

    def __fspath__(self, /) -> AnyStr:
        return self.path

    def __repr__(self, /) -> str:
        return f"<{type(self).__qualname__} {self.path!r}>"

    def __setattr__(self, key, val, /) -> Never:
        raise AttributeError("can't set attributes")

    @property
    def name(self, /) -> AnyStr:
        return basename(self.path)

    def inode(self, /) -> int:
        return stat(self.path).st_ino

    def is_dir(self, /, *, follow_symlinks: bool = True) -> bool:
        if follow_symlinks:
            return isdir(self.path)
        else:
            return not islink(self.path) and isdir(self.path)

    def is_file(self, /, *, follow_symlinks: bool = True) -> bool:
        if follow_symlinks:
            return isfile(self.path)
        else:
            return islink(self.path) or isfile(self.path) 

    is_symlink = islink
    stat = stat


def _iterdir_bfs(
    top: PathType, 
    /, 
    is_dir: Callable[[PathType], bool], 
    iter_dir: Callable[[PathType], Iterable[PathType]], 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: Optional[Callable[[PathType], Optional[bool]]] = None, 
    onerror: Optional[bool] = None, 
    follow_symlinks: bool = False, 
) -> Iterator[PathType]:
    dq: deque[tuple[int, PathType]] = deque()
    push, pop = dq.append, dq.popleft
    push((0, top))
    while dq:
        depth, path = pop()
        if min_depth <= 0:
            pred = True if predicate is None else predicate(path)
            if pred is None:
                return
            elif pred:
                yield path
            min_depth = 1
        if depth == 0 and (not isdir(path) or 0 <= max_depth <= depth):
            return
        depth += 1
        try:
            for path in iter_dir(path):
                pred = True if predicate is None else predicate(path)
                if pred is None:
                    continue
                elif pred and depth >= min_depth:
                    yield path
                if is_dir(path) and (max_depth < 0 or depth < max_depth):
                    push((depth, path))
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise


def _iterdir_dfs(
    top: PathType, 
    /, 
    is_dir: Callable[[PathType], bool], 
    iter_dir: Callable[[PathType], Iterable[PathType]], 
    topdown: bool = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: Optional[Callable[[PathType], Optional[bool]]] = None, 
    onerror: Optional[bool] = None, 
    follow_symlinks: bool = False, 
) -> Iterator[PathType]:
    if not max_depth:
        return
    global_yield_me = True
    if min_depth > 1:
        global_yield_me = False
        min_depth -= 1
    elif min_depth <= 0:
        pred = True if predicate is None else predicate(top)
        if pred is None:
            return
        elif pred:
            yield top
        if not is_dir(top):
            return
        min_depth = 1
    if max_depth > 0:
        max_depth -= 1
    try:
        for path in iter_dir(top):
            yield_me = global_yield_me
            if yield_me and predicate is not None:
                pred = predicate(path)
                if pred is None:
                    continue
                yield_me = pred 
            if yield_me and topdown:
                yield path
            if is_dir(path):
                yield from _iterdir_dfs(
                    path, 
                    is_dir=is_dir, 
                    iter_dir=iter_dir, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                    follow_symlinks=follow_symlinks, 
                )
            if yield_me and not topdown:
                yield path
    except OSError as e:
        if callable(onerror):
            onerror(e)
        elif onerror:
            raise


@overload
def iterdir(
    top: None = None, 
    /, 
    topdown: Optional[bool] = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: Optional[Callable[[DirEntry[str]], Optional[bool]]] = None, 
    onerror: Optional[bool] = None, 
    follow_symlinks: bool = False, 
) -> Iterator[DirEntry[str]]: ...
@overload
def iterdir(
    top: DirEntry[AnyStr], 
    /, 
    topdown: Optional[bool] = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: Optional[Callable[[DirEntry[AnyStr]], Optional[bool]]] = None, 
    onerror: Optional[bool] = None, 
    follow_symlinks: bool = False, 
) -> Iterator[DirEntry[AnyStr]]: ...
@overload
def iterdir(
    top: Path, 
    /, 
    topdown: Optional[bool] = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: Optional[Callable[[Path], Optional[bool]]] = None, 
    onerror: Optional[bool] = None, 
    follow_symlinks: bool = False, 
) -> Iterator[Path]: ...
@overload
def iterdir(
    top: AnyStr, 
    /, 
    topdown: Optional[bool] = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: Optional[Callable[[AnyStr], Optional[bool]]] = None, 
    onerror: Optional[bool] = None, 
    follow_symlinks: bool = False, 
) -> Iterator[AnyStr]: ...
def iterdir(
    top = None, 
    /, 
    topdown: Optional[bool] = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: Optional[Callable[..., Optional[bool]]] = None, 
    onerror: Optional[bool] = None, 
    follow_symlinks: bool = False, 
) -> Iterator:
    if top is None:
        top = DirEntry(".")
    is_dir: Callable[[bytes | str | PathLike], bool]
    if follow_symlinks:
        realtop = realpath(top)
        is_dir = lambda p, /: (isdir(p) and (
            not islink(p) or
            commonpath(t := (realtop, realpath(p))) not in t # type: ignore
        ))
    else:
        is_dir = lambda p, /: not islink(p) and isdir(p)
    iter_dir: Callable
    if isinstance(top, DirEntry):
        iter_dir = scandir
    elif isinstance(top, Path):
        iter_dir = Path.iterdir
    else:
        top = fspath(top)
        if not top:
            top = abspath(top)
        iter_dir = lambda path, /: (joinpath(path, name) for name in listdir(path))
    if topdown is None:
        return _iterdir_bfs(
            top, 
            is_dir=is_dir, 
            iter_dir=iter_dir, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
        )
    else:
        return _iterdir_dfs(
            top, 
            is_dir=is_dir, 
            iter_dir=iter_dir, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
        )

