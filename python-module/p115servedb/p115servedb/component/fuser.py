#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["ServedbFuseOperations"]

from . import __fuse_monkey_patch

import errno
import logging

from collections.abc import Callable
from functools import partial
from itertools import count
from pathlib import Path
from posixpath import split as splitpath, splitext
from sqlite3 import connect
from stat import S_IFDIR, S_IFREG
from typing import Final, BinaryIO
from unicodedata import normalize

from fuse import FUSE, Operations # type: ignore
from httpfile import Urllib3FileReader
from p115client import P115Client
from path_predicate import MappingPath

from .log import logger
from .lrudict import LRUDict


FIELDS: Final = ("id", "name", "path", "ctime", "mtime", "sha1", "size", "pickcode", "is_dir")


# Learning: 
#   - https://www.stavros.io/posts/python-fuse-filesystem/
#   - https://thepythoncorner.com/posts/2017-02-27-writing-a-fuse-filesystem-in-python/
class ServedbFuseOperations(Operations):

    def __init__(
        self, 
        /, 
        dbfile, 
        cookies_path: str | Path = "", 
        predicate: None | Callable[[MappingPath], bool] = None, 
        strm_predicate: None | Callable[[MappingPath], bool] = None, 
        strm_origin: str = "http://localhost:8000", 
    ):
        self.con = connect(dbfile, check_same_thread=False)
        if cookies_path:
            cookies_path = Path(cookies_path)
        else:
            cookies_path = Path("115-cookies.txt")
            if not cookies_path.exists():
                cookies_path = ""
        self.client = P115Client(cookies_path, app="alipaymini", check_for_relogin=True) if cookies_path else None
        self._log = partial(logger.log, extra={"instance": repr(self)})
        self.predicate = predicate
        self.strm_predicate = strm_predicate
        self.strm_origin = strm_origin
        self._next_fh: Callable[[], int] = count(1).__next__
        self._fh_to_file: dict[int, tuple[BinaryIO, bytes]] = {}
        self.cache: LRUDict = LRUDict(1024)
        self.normpath_map: dict[str, str] = {}

    def __del__(self, /):
        self.close()

    def close(self, /):
        self.con.close()
        if self.client:
            self.client.close()
        popitem = self._fh_to_file.popitem
        while True:
            try:
                _, (file, _) = popitem()
                if file is not None:
                    file.close()
            except KeyError:
                break
            except:
                pass

    def getattr(self, /, path: str, fh: int = 0, _rootattr={"st_mode": S_IFDIR | 0o555}) -> dict:
        self._log(logging.DEBUG, "getattr(path=\x1b[4;34m%r\x1b[0m, fh=%r)", path, fh)
        if path == "/":
            return _rootattr
        dir_, name = splitpath(normalize("NFC", path))
        try:
            dird = self.cache[dir_]
        except KeyError:
            try:
                self.readdir(dir_)
                dird = self.cache[dir_]
            except BaseException as e:
                self._log(
                    logging.WARNING, 
                    "file not found: \x1b[4;34m%s\x1b[0m, since readdir failed: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                    path, dir_, type(e).__qualname__, e, 
                )
                raise OSError(errno.EIO, path) from e
        try:
            return dird[name]
        except KeyError as e:
            self._log(
                logging.WARNING, 
                "file not found: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                path, type(e).__qualname__, e, 
            )
            raise FileNotFoundError(errno.ENOENT, path) from e

    def open(self, /, path: str, flags: int = 0) -> int:
        self._log(logging.INFO, "open(path=\x1b[4;34m%r\x1b[0m, flags=%r)", path, flags)
        return self._next_fh()

    def _open(self, path: str, /, start: int = 0):
        attr = self.getattr(path)
        if attr.get("_data") is not None:
            return None, attr["_data"]
        pickcode = attr["_attr"]["pickcode"]
        if client := self.client:
            file = client.open(client.download_url(pickcode), http_file_reader_cls=Urllib3FileReader)
        else:
            file = Urllib3FileReader(f"{self.strm_origin}?pickcode={pickcode}")
        if attr["st_size"] <= 2048:
            return None, file.read()
        if start == 0:
            preread = file.read(2048)
        else:
            preread = b""
        return file, preread

    def read(self, /, path: str, size: int, offset: int, fh: int = 0) -> bytes:
        self._log(logging.DEBUG, "read(path=\x1b[4;34m%r\x1b[0m, size=%r, offset=%r, fh=%r)", path, size, offset, fh)
        if not fh:
            return b""
        try:
            try:
                file, preread = self._fh_to_file[fh]
            except KeyError:
                file, preread = self._fh_to_file[fh] = self._open(path, offset)
            cache_size = len(preread)
            if file is None:
                return preread[offset:offset+size]
            elif offset < cache_size:
                if offset + size <= cache_size:
                    return preread[offset:offset+size]
                elif file is not None:
                    file.seek(cache_size)
                    return preread[offset:] + file.read(offset+size-cache_size)
            file.seek(offset)
            return file.read(size)
        except BaseException as e:
            self._log(
                logging.ERROR, 
                "can't read file: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                path, type(e).__qualname__, e, 
            )
            raise OSError(errno.EIO, path) from e

    def readdir(self, /, path: str, fh: int = 0) -> list[str]:
        self._log(logging.DEBUG, "readdir(path=\x1b[4;34m%r\x1b[0m, fh=%r)", path, fh)
        predicate = self.predicate
        strm_predicate = self.strm_predicate
        strm_origin = self.strm_origin
        path = normalize("NFC", path)
        children: dict[str, dict] = {}
        self.cache[path] = children
        realpath = self.normpath_map.get(path, path)
        try:
            if realpath == "/":
                sql = "SELECT id, name, path, ctime, mtime, sha1, size, pickcode, is_dir FROM data WHERE parent_id = 0;"
                cur = self.con.execute(sql)
            else:
                sql = """\
SELECT id, name, path, ctime, mtime, sha1, size, pickcode, is_dir
FROM data
WHERE parent_id = (SELECT id FROM data WHERE path = ? LIMIT 1) AND name NOT IN ('', '.', '..') AND name NOT LIKE '%/%';
"""
                cur = self.con.execute(sql, (realpath,))
            for r in cur:
                attr = dict(zip(FIELDS, r))
                data = None
                size = attr.get("size") or 0
                name = attr["name"]
                path = attr["path"]
                isdir = attr["is_dir"]
                if not isdir and strm_predicate and strm_predicate(MappingPath(attr)):
                    data = f"{strm_origin}?pickcode={attr['pickcode']}".encode("utf-8")
                    size = len(data)
                    name = splitext(name)[0] + ".strm"
                    path = splitext(path)[0] + ".strm"
                elif predicate and not predicate(MappingPath(attr)):
                    continue
                normname = normalize("NFC", name)
                children[normname] = dict(
                    st_mode=(S_IFDIR if isdir else S_IFREG) | 0o555, 
                    st_size=size, 
                    st_ctime=attr["ctime"], 
                    st_mtime=attr["mtime"], 
                    _attr=attr, 
                    _data=data, 
                )
                normpath = normalize("NFC", path)
                if path != normpath:
                    self.normpath_map[normpath] = path
            return [".", "..", *children]
        except BaseException as e:
            self._log(
                logging.ERROR, 
                "can't readdir: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                path, type(e).__qualname__, e, 
            )
            raise OSError(errno.EIO, path) from e

    def release(self, /, path: str, fh: int = 0):
        self._log(logging.DEBUG, "release(path=\x1b[4;34m%r\x1b[0m, fh=%r)", path, fh)
        if not fh:
            return
        try:
            file, _ = self._fh_to_file.pop(fh)
            if file is not None:
                file.close()
        except KeyError:
            pass
        except BaseException as e:
            self._log(
                logging.ERROR, 
                "can't release file: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                path, type(e).__qualname__, e, 
            )
            raise OSError(errno.EIO, path) from e

    def run(self, /, *args, **kwds):
        return FUSE(self, *args, **kwds)

# TODO: 支持小文件缓存
# TODO: 支持 xattr
