#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["Shelf", "JsonShelf"]

from collections.abc import Mapping, MutableMapping
from dbm import open as opendb
from os import PathLike
from pickle import dumps as pickle_dumps, loads as pickle_loads

try:
    from orjson import dumps as json_dumps, loads as json_loads
except ImportError:
    try:
        from ujson import dumps, loads as json_loads
    except ImportError:
        from json import dumps, loads as json_loads
    json_dumps = lambda val: bytes(dumps(val, ensure_ascii=False), "utf-8")


class Shelf(MutableMapping):
    encode = pickle_dumps
    decode = pickle_loads

    def __init__(self, dict):
        if not isinstance(dict, PathLike) and isinstance(dict, Mapping):
            self.dict = dict
            self.__close_at_end = False
        else:
            self.dict = opendb(dict, "c", 0o666)
            self.__close_at_end = True

    def __del__(self):
        if self.__close_at_end:
            self.close()

    def __iter__(self):
        return map(self.decode, self.dict.keys())

    def __len__(self):
        return len(self.dict)

    def __contains__(self, key):
        return self.encode(key) in self.dict

    def __getitem__(self, key):
        return self.decode(self.dict[self.encode(key)])

    def __setitem__(self, key, value):
        self.dict[self.encode(key)] = self.encode(value)

    def __delitem__(self, key):
        del self.dict[self.encode(key)]

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        self.dict.sync()
        try:
            self.dict.close()
        except AttributeError:
            pass

    def iteritems(self):
        decode = self.decode
        dict = self.dict
        for k in dict:
            yield decode(k), decode(dict[k])

    @classmethod
    def open(cls, /, file, flag="c", mode=0o666):
        return cls(opendb(file, flag, mode))

    def sync(self):
        try:
            self.dict.sync()
        except AttributeError:
            pass

    def update(self, arg=None, /, **kwds):
        encode = self.encode
        if arg:
            if isinstance(arg, Mapping):
                try:
                    it = ((encode(k), encode(v)) for k, v in arg.items())
                except (AttributeError, TypeError):
                    it = ((encode(k), encode(arg[k])) for k in arg)
            else:
                it = ((encode(k), encode(v)) for k, v in arg)
            self.dict.update(it)
        if kwds:
            self.dict.update((encode(k), encode(v)) for k, v in kwds.items())


class JsonShelf(Shelf):

    @staticmethod
    def encode(val):
        if type(val) is bytes:
            return b"b" + val
        try:
            return json_dumps(val)
        except TypeError:
            return b"p" + pickle_dumps(val)

    @staticmethod
    def decode(text):
        if text.startswith(b"b"):
            return text[1:]
        elif text.startswith(b"p"):
            return pickle_loads(text[1:])
        return json_loads(text)

