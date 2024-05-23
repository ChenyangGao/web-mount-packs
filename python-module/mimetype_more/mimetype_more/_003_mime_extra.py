#!/usr/bin/env python
# coding: utf-8

# See: 
# - https://gist.github.com/bj4rtmar/3fc949de5fe73ed59ca5
# - https://gist.github.com/nimasdj/801b0b1a50112ea6a997
# - https://gist.github.com/plasticbrain/3887245
# - https://www.ryadel.com/en/get-file-content-mime-type-from-extension-asp-net-mvc-core/
# - https://stackoverflow.com/questions/1735659/list-of-all-mimetypes-on-the-planet-mapped-to-file-extensions

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["data", "load"]

import mimetypes

from json import loads
from pkgutil import get_data

data = loads(get_data("mimetype_more", "003-mime-extra.json")) # type: ignore

def load(overwrite=False):
    if not mimetypes.inited:
        mimetypes.init()
    db = mimetypes._db # type: ignore
    types_map: dict[str, str] = db.types_map[1]
    types_map_inv: dict[str, list[str]] = db.types_map_inv[1]
    if overwrite:
        setitem = types_map.__setitem__
    else:
        setitem = types_map.setdefault # type: ignore
    append = list.append
    for ext, types in data:
        setitem(ext, types[0])
        for type in types:
            if type in types_map_inv:
                exts = types_map_inv[type]
                if ext not in exts:
                    append(exts, ext)
            else:
                types_map_inv[type] = [ext]

