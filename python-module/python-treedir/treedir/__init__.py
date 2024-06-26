#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["treedir"]

from collections.abc import Callable
from os import scandir, PathLike
from itertools import chain, pairwise
from typing import cast, Any, Literal, TypeVar
from warnings import filterwarnings


filterwarnings("ignore", category=SyntaxWarning)

T = TypeVar("T", bound=Any)


def treedir(
    top: bytes | str | PathLike | T = ".", 
    /, 
    min_depth: int = 0, 
    max_depth: int = -1, 
    onerror: bool | Callable[[OSError], Any] = False, 
    predicate: None | Callable[[T], Literal[None, 1, False, True]] = None, 
    iterdir: Callable[[bytes | str | PathLike | T], T] = scandir, # type: ignore
    is_dir: None | Callable[[T], bool] = None, 
    _depth: int = 0, 
):
    """遍历导出目录树。

    :param top: 根路径，默认为当前目录。
    :param min_depth: 最小深度，小于 0 时不限。参数 `top` 本身的深度为 0，它的直接跟随路径的深度是 1，以此类推。
    :param max_depth: 最大深度，小于 0 时不限。
    :param onerror: 处理 OSError 异常。如果是 True，抛出异常；如果是 False，忽略异常；如果是调用，以异常为参数调用之。
    :param predicate: 调用以筛选遍历得到的路径。
    :param iterdir: 迭代罗列目录。
    :param is_dir: 判断是不是目录，如果为 None，则从 iterdir 所得路径上调用 is_dir() 方法。

    :return: 没有返回值，只是在 stdout 输出目录树文本，类似 tree 命令。
    """
    can_step_in: bool = max_depth < 0 or _depth < max_depth
    if _depth == 0 and min_depth <= 0:
        print(".")
    try:
        pred: Literal[None, 1, False, True] = True
        next_depth = _depth + 1
        for path, npath in pairwise(chain(iterdir(top), (None,))):
            path = cast(T, path)
            if predicate is not None:
                pred = predicate(path)
                if pred is None:
                    continue
            if next_depth >= min_depth and pred:
                print('│   ' * _depth, end="")
                if npath is not None:
                    print('├── ' + path.name)
                else:
                    print('└── ' + path.name)
                if pred is 1:
                    continue
            if can_step_in and (path.is_dir() if is_dir is None else is_dir(path)):
                treedir(
                    path, 
                    min_depth=min_depth, 
                    max_depth=max_depth, 
                    onerror=onerror, 
                    predicate=predicate, 
                    iterdir=iterdir, 
                    is_dir=is_dir, 
                    _depth=next_depth, 
                )
    except OSError as e:
        if callable(onerror):
            onerror(e)
        elif onerror:
            raise

