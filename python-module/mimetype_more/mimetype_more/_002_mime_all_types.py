#!/usr/bin/env python
# coding: utf-8

# See:
# - https://mimetype.io/all-types/
# - https://github.com/patrickmccallum/mimetype-io

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["data", "load"]

import mimetypes

from json import loads
from pkgutil import get_data

try:
    data = loads(get_data("mimetype_more", "002-mime-all-types.json")) # type: ignore
except Exception:
    from pathlib import Path
    from shutil import copyfileobj
    from urllib.request import urlopen
    copyfileobj(
        urlopen("https://raw.githubusercontent.com/patrickmccallum/mimetype-io/master/src/mimeData.json"), 
        (Path(__file__).parent / "002-mime-all-types.json").open("wb"), 
    )
    data = loads(get_data("mimetype_more", "002-mime-all-types.json")) # type: ignore

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
    for record in data:
        type = record["name"]
        extensions = record["fileTypes"]
        for ext in extensions:
            setitem(ext, type)
        if type in types_map_inv:
            exts = types_map_inv[type]
            for ext in extensions:
                if ext not in exts:
                    append(exts, ext)
        else:
            types_map_inv[type] = list(extensions)

