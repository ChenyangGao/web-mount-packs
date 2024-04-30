#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = []

from os import fspath, PathLike, path as ospath
from typing import cast, AnyStr, NamedTuple
from types import ModuleType

def stem(
    path: AnyStr | PathLike[AnyStr], 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    return path_module.splitext(path_module.basename(path))[0]

def suffix(
    path: AnyStr | PathLike[AnyStr], 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    return path_module.splitext(path)[1]

def with_dir(
    path: AnyStr | PathLike[AnyStr], 
    dir: AnyStr, 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    return path_module.join(dir, path_module.split(path)[1])

def with_name(
    path: AnyStr | PathLike[AnyStr], 
    name: AnyStr, 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    return path_module.join(path_module.split(path)[0], name)

def with_stem(
    path: AnyStr | PathLike[AnyStr], 
    stem: AnyStr, 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    dir, name = path_module.split(path)
    suffix = path_module.splitext(name)[1]
    return path_module.join(dir, stem + suffix)

def with_suffix(
    path: AnyStr | PathLike[AnyStr], 
    suffix: AnyStr, 
    ignore: bool = False, 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    path = fspath(path)
    dir, name = path_module.split(path)
    stem, suffix0 = path_module.splitext(name)
    if ignore and suffix and suffix0:
        return path
    else:
        return path_module.join(dir, stem + suffix)

def add_stem_prefix(
    path: AnyStr | PathLike[AnyStr], 
    prefix: AnyStr, 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    dir, name = path_module.split(path)
    return path_module.join(dir, prefix + name)

def add_stem_suffix(
    path: AnyStr | PathLike[AnyStr], 
    suffix: AnyStr, 
    path_module: ModuleType = ospath, 
) -> AnyStr:
    base, ext = path_module.splitext(path)
    return base + suffix + ext

def split3(
    path: AnyStr | PathLike[AnyStr], 
    path_module: ModuleType = ospath, 
) -> tuple[AnyStr, AnyStr, AnyStr]:
    dir, name = path_module.split(path)
    stem, suffix = path_module.splitext(name)
    return dir, stem, suffix

def splits(
    path: AnyStr | PathLike[AnyStr], 
    path_module: ModuleType = ospath, 
) -> list[AnyStr]:
    path = path_module.normpath(path)
    sep: AnyStr = path_module.sep if isinstance(path, str) else path_module.sep.encode()
    return path.split(sep)

def suffixes(
    path: AnyStr | PathLike[AnyStr], 
    path_module: ModuleType = ospath, 
) -> list[AnyStr]:
    name = path_module.basename(path)
    dot: AnyStr = "." if isinstance(name, str) else b"."
    if name.endswith(dot):
        return []
    return [dot + suffix for suffix in name.lstrip(dot).split(dot)[1:]]


# ospath.relpath
def relative_path(
    ref_path: AnyStr | PathLike[AnyStr], 
    rel_path: None | AnyStr | PathLike[AnyStr] = None, 
    lib: ModuleType = ospath, 
) -> AnyStr: 
    sep: AnyStr
    curdir: AnyStr
    ref_path = cast(AnyStr, fspath(ref_path))
    rel_path = cast(AnyStr, fspath(rel_path))

    if isinstance(ref_path, bytes):
        sep = cast(bytes, lib.sep.encode())
        curdir = cast(bytes, lib.curdir.encode())
        ref_path = cast(bytes, ref_path)
        if isinstance(rel_path, str):
            rel_path = rel_path.encode()
        rel_path = cast(bytes, rel_path)
    else:
        sep = cast(str, lib.sep)
        curdir = cast(str, lib.curdir)
        ref_path = cast(str, ref_path)
        if isinstance(rel_path, bytes):
            rel_path = rel_path.decode()
        rel_path = cast(str, rel_path)

    if not rel_path or rel_path == curdir or lib.isabs(ref_path):
        return ref_path

    if rel_path.endswith(sep):
        dir_path = rel_path[:-1]
    else:
        dir_path = lib.dirname(rel_path)

    if not ref_path.startswith(curdir):
        return lib.join(dir_path, ref_path)

    dir_parts = dir_path.split(sep)
    if not dir_parts[0]:
        dir_parts[0] = sep

    ref_parts = ref_path.split(sep)
    advance_count = 0
    for i, p in enumerate(ref_parts):
        if p and not p.strip(curdir):
            advance_count += len(p) - 1
            continue
        break
    else:
        i += 1

    ref_parts = ref_parts[i:]
    if advance_count:
        compensation_count = advance_count - len(dir_parts)
        if compensation_count > 0:
            dir_parts = ['../'] * compensation_count
        else:
            dir_parts = dir_parts[:-advance_count]

    return lib.join(*dir_parts, *ref_parts)






#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 0)
__all__ = [
    "char_half_to_full", "half_to_full", "escape_posix_name", 
    "escape_posix_name_by_entityref", "escape_nt_name", 
    "escape_nt_name_by_entityref", 
]


def char_half_to_full(char: str) -> str:
    "Convert half-width character to full-width character."
    code = ord(char)
    if code == 32:
        return chr(12288)
    elif 32 < code <= 126:
        return chr(code + 65248)
    else:
        return char


def half_to_full(
    char: str, 
    _table={i: char_half_to_full(chr(i)) for i in range(32, 127)}, 
) -> str:
    "Convert half-width characters to full-width characters."
    return char.translate(_table)


def escape_posix_name(s):
    return s.replace('/', '／')


def escape_posix_name_by_entityref(s):
    return s.replace('/', '&sol;')


def escape_nt_name(
    s, 
    _table={ord(c): char_half_to_full(c) for c in r'\\/:*?"<>|'}, 
):
    return s.translate(_table)


def escape_nt_name_by_entityref(
    s, 
    # NOTE: 取自 html.entities.html5
    _table=str.maketrans({
        '*': '&midast;',
        '\\': '&bsol;',
        ':': '&colon;',
        '>': '&gt;',
        '<': '&lt;',
        '?': '&quest;',
        '"': '&quot;',
        '/': '&sol;',
        '|': '&VerticalLine;',
    })
):
    return s.translate(_table)


