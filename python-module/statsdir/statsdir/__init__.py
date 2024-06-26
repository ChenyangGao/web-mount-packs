#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["statsdir"]

from collections.abc import Callable
from os import fspath, lstat, PathLike
from os.path import abspath, isdir, islink
from typing import Any

from iterdir import iterdir


def format_bytes(
    n: int, 
    /, 
    unit: str = "", 
    precision: int = 6, 
) -> str:
    "scale bytes to its proper byte format"
    if unit == "B" or not unit and n < 1024:
        return f"{n} B"
    b = 1
    b2 = 1024
    for u in ["K", "M", "G", "T", "P", "E", "Z", "Y"]:
        b, b2 = b2, b2 << 10
        if u == unit if unit else n < b2:
            break
    return f"%.{precision}f {u}B" % (n / b)


def statsdir(
    top = None, 
    /, 
    min_depth: int = 0, 
    max_depth: int = -1, 
    predicate: None | Callable[..., None | bool] = None, 
    onerror: bool | Callable[[OSError], Any] = False, 
    follow_symlinks: bool = False, 
    key: None | Callable = None, 
) -> dict:
    """目录树遍历统计。

    :param top: 根路径，默认为当前目录。
    :param min_depth: 最小深度，小于 0 时不限。参数 `top` 本身的深度为 0，它的直接跟随路径的深度是 1，以此类推。
    :param max_depth: 最大深度，小于 0 时不限。
    :param predicate: 调用以筛选遍历得到的路径。可接受的参数与参数 `top` 的类型一致，参见 `:return:` 部分。
    :param onerror: 处理 OSError 异常。如果是 True，抛出异常；如果是 False，忽略异常；如果是调用，以异常为参数调用之。
    :param follow_symlinks: 是否跟进符号连接（如果为否，则会把符号链接视为文件，即使它指向目录）。
    :param key: 计算以得到一个 key，相同的 key 为一组，对路径进行分组统计。

    :return: 返回统计数据，形如
        {
            "path": str,     # 根路径 
            "total": int,    # 包含路径总数 = 目录数 + 文件数
            "dirs": int,     # 包含目录数
            "files": int,    # 包含文件数
            "size": int,     # 文件总大小（符号链接视为文件计入）
            "fmt_size": str, # 文件总大小，换算为适当的单位：B (Byte), KB (Kilobyte), MB (Megabyte), GB (Gigabyte), TB (Terabyte), PB (Petabyte), ...
            # OPTIONAL: 如果提供了 key 函数
            "keys": {
                a_key: {
                    "total": int, 
                    "dirs": int, 
                    "files": int, 
                    "size": int, 
                    "fmt_size": str, 
                }, 
                ...
            }
        }
    。
    """
    d: dict = {
        "path": abspath("" if top is None else top), 
        "total": 0, 
        "dirs": 0, 
        "files": 0, 
        "size": 0, 
        "fmt_size": "", 
    }
    if key is None:
        def stats(path):
            if isdir(path) and not islink(path):
                d["dirs"] += 1
            else:
                d["files"] += 1
                d["size"] += lstat(path).st_size
    else:
        keys = d["keys"] = {}
        def stats(path):
            k = key(path)
            try:
                kd = keys[k]
            except KeyError:
                kd = keys[k] = {
                    "total": 0, 
                    "dirs": 0, 
                    "files": 0, 
                    "size": 0, 
                    "fmt_size": "", 
                }
            if isdir(path) and not islink(path):
                d["dirs"] += 1
                kd["dirs"] += 1
            else:
                d["files"] += 1
                kd["files"] += 1
                size = lstat(path).st_size
                d["size"] += size
                kd["size"] += size
    for path in iterdir(
        top, 
        min_depth=min_depth, 
        max_depth=max_depth, 
        predicate=predicate, 
        onerror=onerror, 
        follow_symlinks=follow_symlinks, 
    ):
        stats(path)
    else:
        d["total"] = d["dirs"] + d["files"]
        d["fmt_size"] = format_bytes(d["size"])
        if "keys" in d:
            for kd in d["keys"].values():
                kd["total"] = kd["dirs"] + kd["files"]
                kd["fmt_size"] = format_bytes(kd["size"])
    return d

