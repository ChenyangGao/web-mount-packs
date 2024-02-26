#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["bencode", "bdecode", "torrent_list", "torrent_tree", "torrent_to_magnet"]

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="torrent to magnet")
    parser.add_argument("files", nargs="*", help="paths to torrent files")
    parser.add_argument("-f", "--full", action="store_true", help="append more detailed queries")
    args = parser.parse_args()
    if not args.files:
        parser.parse_args(["-h"])

from base64 import b32encode
from collections import UserString
from collections.abc import Sequence, Mapping
from functools import singledispatch
from hashlib import sha1, new as hash_new
from numbers import Integral
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
        case b"l":
            return decode_list(s, p)
        case b"d":
            return decode_dict(s, p)
        case b"i":
            return decode_int(s, p)
        case v if v in b"0123456789":
            return decode_bytes(s, p)
        case _:
            raise ValueError(f"invalid bencoded string: at {p}")


def bdecode(s, /) -> BDecodedType:
    "Decode bencode formatted bytes object."
    if isinstance(s, (bytearray, bytes, memoryview)):
        b = s
    elif hasattr(s, "getbuffer"):
        b = s.getbuffer()
    elif hasattr(s, "read"):
        b = s.read()
    else:
        b = memoryview(s).tobytes()
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


def torrent_list(data, /) -> list[str]:
    "list all files from a torrent"
    metadata = cast(dict, bdecode(data))
    info = cast(dict, metadata[b"info"])
    if b"files" in info:
        return [str(joinpath(*f[b"path"]), "utf-8") for f in info[b"files"]]
    elif b"name" in info:
        return [str(info[b"name"], "utf-8")]
    else:
        raise ValueError("invalid torrent file")


def torrent_tree(data, /) -> dict:
    "tree all files from a torrent"
    metadata = cast(dict, bdecode(data))
    info = cast(dict, metadata[b"info"])
    if b"files" in info:
        d: dict = {}
        for l in info[b"files"]:
            l = l[b"path"]
            d2 = d
            for p in l[:-1]:
                p = str(p, "utf-8")
                try:
                    d2 = d2[p]
                except KeyError:
                    d2[p] = d2 = {}
            d2[str(l[-1], "utf-8")] = None
        return d
    elif b"name" in info:
        return {str(info[b"name"], "utf-8"): None}
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
    "convert a torrent into a magnet link"
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


if __name__ == "__main__":
    from os import scandir
    from os.path import isdir
    from sys import stdout

    write = stdout.buffer.raw.write
    files = args.files
    full = args.full
    try:
        for file in files:
            if isdir(file):
                files.extend(scandir(file))
            else:
                try:
                    data = open(file, "rb").read()
                    write(torrent_to_magnet(data, full=full).encode("utf-8"))
                    write(b"\n")
                except (ValueError, LookupError):
                    pass
    except BrokenPipeError:
        from sys import stderr
        stderr.close()

