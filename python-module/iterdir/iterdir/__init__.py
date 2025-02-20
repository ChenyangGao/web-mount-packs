#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 7)
__all__ = ["DirEntry", "iterdir"]

from collections import deque
from collections.abc import Callable, Iterator
from datetime import datetime
from os import (
    fspath, lstat, scandir, stat, stat_result, 
    DirEntry as _DirEntry, PathLike, 
)
from os.path import (
    abspath, commonpath, basename, isfile, isdir, 
    islink, realpath, 
)
from typing import cast, overload, Any, Final, Never

from texttools import format_mode, format_size


STAT_FIELDS: Final = (
    "mode", "ino", "dev", "nlink", "uid", "gid",
    "size", "atime", "mtime", "ctime", 
)
STAT_ST_FIELDS: Final = tuple(
    f for f in dir(stat_result) 
    if f.startswith("st_")
)


class DirEntryMeta(type):

    def __instancecheck__(cls, inst, /):
        if isinstance(inst, _DirEntry):
            return True
        return super().__instancecheck__(inst)

    def __subclasscheck__(cls, sub, /):
        if issubclass(sub, _DirEntry):
            return True
        return super().__subclasscheck__(sub)


class DirEntry[AnyStr: (bytes, str)](metaclass=DirEntryMeta):
    __slots__ = ("name", "path")

    name: AnyStr
    path: AnyStr

    def __init__(self, /, path: AnyStr | PathLike[AnyStr]):
        if isinstance(path, (_DirEntry, DirEntry)):
            name = path.name
            path = path.path
        else:
            path = fspath(path)
            name = basename(path)
            path = abspath(path)
        super().__setattr__("name", name)
        super().__setattr__("path", path)

    def __fspath__(self, /) -> AnyStr:
        return self.path

    def __repr__(self, /) -> str:
        return f"<{type(self).__qualname__} {self.path!r}>"

    def __setattr__(self, key, val, /) -> Never:
        raise AttributeError("can't set attributes")

    def inode(self, /) -> int:
        return lstat(self.path).st_ino

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

    def stat(self, /, *, follow_symlinks: bool = True) -> stat_result:
        if follow_symlinks:
            return stat(self.path)
        else:
            return lstat(self.path)

    def stat_dict(
        self, 
        /, 
        *, 
        follow_symlinks: bool = True, 
        with_st: bool = False, 
    ) -> dict[str, Any]:
        stat = self.stat(follow_symlinks=follow_symlinks)
        if with_st:
            return dict(zip(STAT_ST_FIELDS, (getattr(stat, a) for a in STAT_ST_FIELDS)))
        else:
            return dict(zip(STAT_FIELDS, stat))

    def stat_info(self, /, *, follow_symlinks: bool = True) -> dict[str, Any]:
        stat_info: dict[str, Any] = self.stat_dict(follow_symlinks=follow_symlinks)
        stat_info["atime_str"] = str(datetime.fromtimestamp(stat_info["atime"]))
        stat_info["mtime_str"] = str(datetime.fromtimestamp(stat_info["mtime"]))
        stat_info["ctime_str"] = str(datetime.fromtimestamp(stat_info["ctime"]))
        stat_info["size_str"] = format_size(stat_info["size"])
        stat_info["mode_str"] = format_mode(stat_info["mode"])
        stat_info["path"] = self.path
        stat_info["name"] = self.name
        stat_info["is_dir"] = self.is_dir()
        stat_info["is_link"] = self.is_symlink()
        return stat_info


def _iterdir_bfs[AnyStr: (bytes, str)](
    top: DirEntry[AnyStr], 
    /, 
    isdir: Callable[[DirEntry[AnyStr]], bool], 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: None | Callable[[DirEntry[AnyStr]], None | bool] = None, 
    onerror: bool | Callable[[OSError], Any] = False, 
) -> Iterator[DirEntry[AnyStr]]:
    if min_depth <= 0:
        pred = True if predicate is None else predicate(top)
        if pred is None:
            return
        elif pred:
            yield top
        min_depth = 1
    if not max_depth or min_depth > max_depth > 0 or not isdir(top):
        return
    dq: deque[tuple[int, DirEntry[AnyStr]]] = deque()
    push, pop = dq.append, dq.popleft
    push((0, top))
    while dq:
        depth, entry = pop()
        depth += 1
        can_step_in = max_depth < 0 or depth < max_depth
        try:
            for entry in map(DirEntry, scandir(entry)):
                pred = True if predicate is None else predicate(entry)
                if pred is None:
                    continue
                elif pred and depth >= min_depth:
                    yield entry
                if can_step_in and isdir(entry):
                    push((depth, entry))
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise


def _iterdir_dfs[AnyStr: (bytes, str)](
    top: DirEntry[AnyStr], 
    /, 
    isdir: Callable[[DirEntry[AnyStr]], bool], 
    topdown: bool = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: None | Callable[[DirEntry[AnyStr]], None | bool] = None, 
    onerror: bool | Callable[[OSError], Any] = False, 
) -> Iterator[DirEntry[AnyStr]]:
    global_yield_me = True
    if min_depth > 1:
        global_yield_me = False
        min_depth -= 1
    elif min_depth <= 0:
        pred = True if predicate is None else predicate(top)
        if pred:
            yield top
        if pred is None or not isdir(top):
            return
        min_depth = 1
    if not max_depth or min_depth > max_depth > 0:
        return
    try:
        max_depth -= max_depth > 0
        for entry in map(DirEntry, scandir(top)):
            yield_me = global_yield_me
            if yield_me and predicate is not None:
                pred = predicate(entry)
                if pred is None:
                    continue
                yield_me = pred 
            if yield_me and topdown:
                yield entry
            if isdir(entry):
                yield from _iterdir_dfs(
                    entry, 
                    isdir=isdir, 
                    topdown=topdown, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    predicate=predicate, 
                    onerror=onerror, 
                )
            if yield_me and not topdown:
                yield entry
    except OSError as e:
        if callable(onerror):
            onerror(e)
        elif onerror:
            raise


@overload
def iterdir(
    top: None = None, 
    /, 
    topdown: None | bool = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: None | Callable[[DirEntry[str]], None | bool] = None, 
    onerror: bool | Callable[[OSError], Any] = False, 
    follow_symlinks: bool = False, 
) -> Iterator[DirEntry[str]]:
    ...
@overload
def iterdir[AnyStr: (bytes, str)](
    top: AnyStr | PathLike[AnyStr], 
    /, 
    topdown: None | bool = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: None | Callable[[DirEntry[AnyStr]], None | bool] = None, 
    onerror: bool | Callable[[OSError], Any] = False, 
    follow_symlinks: bool = False, 
) -> Iterator[DirEntry[AnyStr]]:
    ...
def iterdir[AnyStr: (bytes, str)](
    top: None | AnyStr | PathLike[AnyStr] = None, 
    /, 
    topdown: None | bool = True, 
    min_depth: int = 1, 
    max_depth: int = 1, 
    predicate: None | Callable[[DirEntry[AnyStr]], None | bool] = None, 
    onerror: bool | Callable[[OSError], Any] = False, 
    follow_symlinks: bool = False, 
) -> Iterator[DirEntry]:
    """遍历目录树

    :param top: 顶层目录路径，默认为当前工作目录
    :param topdown: 如果是 True，自顶向下深度优先搜索；如果是 False，自底向上深度优先搜索；如果是 None，广度优先搜索
    :param min_depth: 最小深度，`top` 本身为 0
    :param max_depth: 最大深度，< 0 时不限
    :param predicate: 调用以筛选遍历得到的路径，如果得到的结果为 None，则不输出被判断的节点，但依然搜索它的子树
    :param onerror: 处理 OSError 异常。如果是 True，抛出异常；如果是 False，忽略异常；如果是调用，以异常为参数调用之
    :param follow_symlinks: 是否跟进符号连接（如果为 False，则会把符号链接视为文件，即使它指向目录）

    :return: 遍历得到的路径的迭代器
    """
    if top is None:
        top = cast(DirEntry[AnyStr], DirEntry("."))
    else:
        top = DirEntry(top)
    if follow_symlinks:
        realtop = realpath(top)
        isdir = lambda e, /: e.is_dir(follow_symlinks=follow_symlinks) and \
                             commonpath((t := (realtop, realpath(e)))) not in t
    else:
        isdir = lambda e, /: e.is_dir(follow_symlinks=follow_symlinks)
    if topdown is None:
        return _iterdir_bfs(
            top, 
            isdir=isdir, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
        )
    else:
        return _iterdir_dfs(
            top, 
            isdir=isdir, 
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
        )

