#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 4)
__all__ = [
    "bencode", "bdecode", "dump", "load", "torrent_files", "torrent_to_magnet", 
]

from base64 import b32encode
from collections import UserString
from collections.abc import Sequence, Mapping
from functools import singledispatch
from hashlib import sha1, new as hash_new
from numbers import Integral
from os import PathLike
from posixpath import join as joinpath
from typing import cast
from urllib.parse import urlencode


BDecodedType = int | bytes | list["BDecodedType"] | dict[bytes, "BDecodedType"]


def ensure_bytes_like(o, /) -> bytes:
    if isinstance(o, (bytearray, bytes, memoryview)):
        return bytes(o)
    try:
        return memoryview(o).tobytes()
    except TypeError:
        return bytes(str(o), "utf-8")


def decode_int(
    s: bytearray | bytes | memoryview, 
    p: int = 0, 
    /, 
) -> tuple[int, int]:
    p += 1
    p2 = s.index(b"e", p)
    return int(s[p : p2]), p2 + 1


def decode_bytes(
    s: bytearray | bytes | memoryview, 
    p: int = 0, 
    /, 
) -> tuple[bytes, int]:
    colon = s.index(b":", p)
    n = int(s[p : colon])
    colon += 1
    return s[colon : colon + n], colon + n


def decode_list(
    s: bytearray | bytes | memoryview, 
    p: int = 0, 
    /, 
) -> tuple[list[BDecodedType], int]:
    l: list = []
    p += 1
    add = l.append
    while s[p:p+1] != b"e":
        v, p = decode(s, p)
        add(v)
    return l, p + 1


def decode_dict(
    s: bytearray | bytes | memoryview, 
    p: int = 0, 
    /, 
) -> tuple[dict[bytes, BDecodedType], int]:
    d: dict = {}
    p += 1
    while s[p:p+1] != b"e":
        k, p = decode_bytes(s, p)
        d[k], p = decode(s, p)
    return d, p + 1


def decode(
    s: bytearray | bytes | memoryview, 
    p: int = 0, 
    /, 
) -> tuple[BDecodedType, int]:
    match s[p:p+1]:
        case b"l": # l for list
            return decode_list(s, p)
        case b"d": # d for dict
            return decode_dict(s, p)
        case b"i": # i for integer
            return decode_int(s, p)
        case v if v in b"0123456789": # for bytes
            return decode_bytes(s, p)
        case _:
            raise ValueError(f"invalid bencoded string: at {p}")


def bdecode(data, /) -> BDecodedType:
    "Decode bencode formatted bytes object."
    if isinstance(data, (bytes, bytearray, memoryview)):
        b = data
    elif isinstance(data, (str, PathLike)):
        b = open(data, "rb").read()
    elif hasattr(data, "getbuffer"):
        b = data.getbuffer()
    elif hasattr(data, "read"):
        b = data.read()
        if isinstance(b, str):
            b = bytes(b, "utf-8")
    else:
        b = memoryview(data).tobytes()
    v, p = decode(b)
    if p != len(b):
        raise ValueError(f"invalid bencoded string: in slice({p}, {len(b)})")
    return v


encode_int = b"i%ie".__mod__
encode_bytes = lambda o, /: b"%i:%s" % (len(o), o)


@singledispatch
def encode_iter(o, /):
    yield encode_bytes(ensure_bytes_like(o))


@encode_iter.register(Integral)
def _(o, /):
    yield encode_int(o)


@encode_iter.register(bytearray)
@encode_iter.register(bytes)
@encode_iter.register(memoryview)
def _(o, /):
    yield encode_bytes(o)


@encode_iter.register(str)
@encode_iter.register(UserString)
def _(o, /):
    yield encode_bytes(bytes(o, "utf-8"))


@encode_iter.register(Sequence)
def _(o, /):
    yield b"l"
    for e in o:
        yield from encode_iter(e)
    yield b"e"


@encode_iter.register(Mapping)
def _(o, /):
    yield b"d"
    items = sorted((ensure_bytes_like(k), o[k]) for k in o)
    for k, v in items:
        yield encode_bytes(k)
        yield from encode_iter(v)
    yield b"e"


def bencode(o, fp=None, /):
    "Encode `object` into the bencode format."
    if fp is None:
        return b"".join(encode_iter(o))
    write = fp.write
    for w in encode_iter(o):
        write(w)


dump = bencode
load = bdecode


def torrent_files(data, /, tree: bool = False) -> dict:
    "show all files and their lengths for a torrent"
    metadata = cast(dict, bdecode(data))
    info = cast(dict, metadata[b"info"])
    if b"files" in info:
        if tree:
            d: dict = {}
            for f in info[b"files"]:
                parts = f[b"path"]
                d2 = d
                for p in parts[:-1]:
                    p = str(p, "utf-8")
                    try:
                        d2 = d2[p]
                    except KeyError:
                        d2[p] = d2 = {}
                d2[str(parts[-1], "utf-8")] = f[b"length"]
            return d
        else:
            return {str(joinpath(*f[b"path"]), "utf-8"): f[b"length"] for f in info[b"files"]}
    elif b"name" in info:
        return {str(info[b"name"], "utf-8"): info[b"length"]}
    else:
        raise ValueError("invalid torrent file")


def calc_infohash(info: bytes, alg: str = "btih") -> str:
    if alg == "btih":
        return b32encode(sha1(info).digest()).decode("ascii").lower()
    return hash_new(alg, info).hexdigest()


def torrent_to_magnet(
    data, 
    /, 
    full: bool = False, 
    infohash_alg: str = "btih", 
) -> str:
    "convert a torrent to a magnet link"
    metadata = cast(dict, bdecode(data))
    info = cast(dict, metadata[b"info"])
    infohash = calc_infohash(bencode(info), infohash_alg)
    urn = f"urn:{infohash_alg}:{infohash}"
    if full:
        params = {
            "xt": urn, 
            "dn": info.get(b"name"), 
            "tr": metadata.get(b"announce"), 
            "xl": info.get(b"piece length"), 
        }
        return "magnet:?" + urlencode([(k, v) for k, v in params.items() if v], safe=":/")
    else:
        return "magnet:?xt=" + urn

