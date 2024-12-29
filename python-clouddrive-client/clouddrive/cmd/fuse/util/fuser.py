#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["CloudDriveFuseOperations"]
__requirements__ = ["cachetools", "fusepy", "psutil", "urllib3_request"]

try:
    # pip install cachetools
    from cachetools import Cache, LRUCache, TTLCache
    # pip install fusepy
    from fuse import FUSE, Operations, fuse_get_context
    # pip install psutil
    from psutil import Process
    # pip install urllib3_request
    from urllib3 import PoolManager
    from urllib3_request import request
except ImportError:
    from subprocess import run
    from sys import executable
    run([executable, "-m", "pip", "install", "-U", *__requirements__], check=True)
    from cachetools import Cache, LRUCache, TTLCache
    from fuse import FUSE, Operations, fuse_get_context # type: ignore
    from psutil import Process
    from urllib3 import PoolManager
    from urllib3_request import request

import errno
import logging

from collections.abc import Callable, MutableMapping
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial, update_wrapper
from http.client import InvalidURL
from itertools import count
from json import dumps as json_dumps
from os import fsencode, PathLike
from pickle import dumps as pickle_dumps, loads as pickle_loads
from posixpath import join as joinpath, split as splitpath, splitext
from stat import S_IFDIR, S_IFREG
from subprocess import run
from sys import maxsize
from _thread import start_new_thread, allocate_lock
from time import sleep, time
from typing import cast, Any, Concatenate, Final, IO, ParamSpec
from unicodedata import normalize

from clouddrive import CloudDriveFileSystem, CloudDrivePath
from httpfile import HTTPFileReader
from http_request import SupportsGeturl
from yarl import URL

from .log import logger


Args = ParamSpec("Args")

urllib3_request = partial(request, pool=PoolManager(64))


def _get_process():
    pid = fuse_get_context()[-1]
    if pid <= 0:
        return "UNDETERMINED"
    return str(Process(pid))

PROCESS_STR = type("ProcessStr", (), {"__str__": staticmethod(_get_process)})()

if not hasattr(ThreadPoolExecutor, "__del__"):
    setattr(ThreadPoolExecutor, "__del__", lambda self, /: self.shutdown(cancel_futures=True))


def readdir_future_wrapper(
    self, 
    submit: Callable[..., Future], 
    cooldown: int | float = 30, 
):
    readdir = type(self).readdir
    cooldown_pool: None | MutableMapping = None
    if cooldown > 0:
        cooldown_pool = TTLCache(maxsize, ttl=cooldown)
    task_pool: dict[str, Future] = {}
    pop_task = task_pool.pop
    lock = allocate_lock()
    def wrapper(path, fh=0):
        path = normalize("NFC", path)
        refresh = cooldown_pool is None or path not in cooldown_pool
        try:
            result = [".", "..", *self._get_cache(path)]
        except KeyError:
            result = None
            refresh = True
        if refresh:
            with lock:
                try:
                    future = task_pool[path]
                except KeyError:
                    def done_callback(future: Future):
                        if cooldown_pool is not None and future.exception() is None:
                            cooldown_pool[path] = None
                        pop_task(path, None)
                    future = task_pool[path] = submit(readdir, self, path, fh)
                    future.add_done_callback(done_callback)
        if result is None:
            return future.result()
        elif refresh:
            try:
                return future.result(1)
            except TimeoutError:
                pass
        return result
    return update_wrapper(wrapper, readdir)


# Learning: 
#   - https://www.stavros.io/posts/python-fuse-filesystem/
#   - https://thepythoncorner.com/posts/2017-02-27-writing-a-fuse-filesystem-in-python/
class CloudDriveFuseOperations(Operations):

    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
        base_dir: str = "/", 
        refresh: bool = False, 
        cache: None | MutableMapping = None, 
        pickle_cache: bool = False, 
        max_readdir_workers: int = 5, 
        max_readdir_cooldown: float = 30, 
        predicate: None | Callable[[CloudDrivePath], bool] = None, 
        strm_predicate: None | Callable[[CloudDrivePath], bool] = None, 
        strm_make: None | Callable[[CloudDrivePath], str] = None, 
        open_file: None | Callable[[CloudDrivePath], str | Callable] = None, 
        direct_open_names: None | Callable[[str], bool] = None, 
        direct_open_exes: None | Callable[[str], bool] = None, 
    ):
        self.__finalizer__: list[Callable] = []
        self._log = partial(logger.log, extra={"instance": repr(self)})

        fs = self.fs = CloudDriveFileSystem.login(origin, username, password)
        fs.chdir(base_dir)
        self.refresh = refresh
        self.pickle_cache = pickle_cache
        self.predicate = predicate
        self.strm_predicate = strm_predicate
        self.strm_make = strm_make
        self.open_file = open_file
        register = self.register_finalize = self.__finalizer__.append
        self.direct_open_names = direct_open_names
        self.direct_open_exes = direct_open_exes

        # NOTE: id generator for file handler
        self._next_fh: Callable[[], int] = count(1).__next__
        # NOTE: cache `readdir` pulled file attribute map
        if cache is None or isinstance(cache, (dict, Cache)):
            if cache is None:
                if max_readdir_cooldown <= 0:
                    cache = LRUCache(128)
                else:
                    cache = LRUCache(65536)
            self.temp_cache: None | MutableMapping = None
        else:
            self.temp_cache = LRUCache(128)
        self.cache: MutableMapping = cache
        self._fh_to_file: dict[int, tuple[IO[bytes], bytes]] = {}
        def close_all():
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
        register(close_all)
        # NOTE: multi threaded directory reading control
        executor: None | ThreadPoolExecutor = None
        if max_readdir_workers == 0:
            executor = ThreadPoolExecutor(None)
            submit = executor.submit
        elif max_readdir_workers < 0:
            from concurrenttools import run_as_thread as submit
        else:
            executor = ThreadPoolExecutor(max_readdir_workers)
            submit = executor.submit
        self.__dict__["readdir"] = readdir_future_wrapper(
            self, 
            submit=submit, 
            cooldown=max_readdir_cooldown, 
        )
        if executor is not None:
            register(partial(executor.shutdown, wait=False, cancel_futures=True))
        self.normpath_map: dict[str, str] = {}

    def __del__(self, /):
        self.close()

    def close(self, /):
        for func in self.__finalizer__:
            try:
                func()
            except BaseException as e:
                self._log(logging.ERROR, "failed to finalize with %r", func)

    def getattr(self, /, path: str, fh: int = 0, _rootattr={"st_mode": S_IFDIR | 0o555}) -> dict:
        self._log(logging.DEBUG, "getattr(path=\x1b[4;34m%r\x1b[0m, fh=%r) by \x1b[3;4m%s\x1b[0m", path, fh, PROCESS_STR)
        if path == "/":
            return _rootattr
        dir_, name = splitpath(normalize("NFC", path))
        try:
            dird = self._get_cache(dir_)
        except KeyError:
            try:
                self.readdir(dir_)
                dird = self._get_cache(dir_)
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

    def getxattr(self, /, path: str, name: str, position: int = 0):
        if path == "/":
            return b""
        fuse_attr = self.getattr(path)
        attr      = fuse_attr["_attr"]
        pathobj   = fuse_attr["_path"]
        match name:
            case "attr":
                return fsencode(json_dumps(attr, ensure_ascii=False))
            case "id":
                return fsencode(attr["id"])
            case "fileHashes":
                return fsencode(json_dumps(attr.get("fileHashes"), ensure_ascii=False))
            case "url":
                if pathobj.is_dir():
                    raise IsADirectoryError(errno.EISDIR, path)
                return fsencode(pathobj.get_url())
            case _:
                raise OSError(93, name)

    def listxattr(self, /, path: str):
        if path == "/":
            return ()
        return ("attr", "id", "fileHashes", "url")

    def open(self, /, path: str, flags: int = 0) -> int:
        self._log(logging.INFO, "open(path=\x1b[4;34m%r\x1b[0m, flags=%r) by \x1b[3;4m%s\x1b[0m", path, flags, PROCESS_STR)
        pid = fuse_get_context()[-1]
        path = self.normpath_map.get(normalize("NFC", path), path)
        if pid > 0 and (self.direct_open_names or self.direct_open_exes):
            try:
                process = Process(pid)
                exe = process.exe()
                if (
                    self.direct_open_names and self.direct_open_names(process.name().lower()) or
                    self.direct_open_exes and self.direct_open_exes(exe)
                ):
                    process.kill()
                    def push():
                        sleep(.01)
                        run([exe, self.fs.get_url(path.lstrip("/"))])
                    start_new_thread(push, ())
                    return 0
            except Exception as e:
                self._log(
                    logging.ERROR, 
                    "can't reopen process \x1b[3;4m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                    PROCESS_STR, type(e).__qualname__, e, 
                )
        return self._next_fh()

    def _open(self, path: str, /, start: int = 0):
        attr = self.getattr(path)
        path = attr["_path"]["path"]
        if attr.get("_data") is not None:
            return None, attr["_data"]
        file: None | IO[bytes]
        if self.open_file is None:
            file = cast(IO[bytes], attr["_path"].open("rb"))
        else:
            rawfile = self.open_file(attr["_path"])
            if isinstance(rawfile, bytes):
                return None, rawfile
            elif isinstance(rawfile, str) and rawfile.startswith(("http://", "https://")) or isinstance(rawfile, (SupportsGeturl, URL)):
                if isinstance(rawfile, str):
                    url = rawfile
                elif isinstance(rawfile, SupportsGeturl):
                    url = rawfile.geturl()
                else:
                    url = str(rawfile)
                file = HTTPFileReader(url, urlopen=urllib3_request)
            elif isinstance(rawfile, (str, PathLike)):
                file = open(rawfile, "rb")
            else:
                file = cast(IO[bytes], rawfile)
        if attr["st_size"] <= 2048:
            return None, file.read()
        if start == 0:
            # cache 2048 in bytes (2 KB)
            preread = file.read(2048)
        else:
            preread = b""
        return file, preread

    def read(self, /, path: str, size: int, offset: int, fh: int = 0) -> bytes:
        self._log(logging.DEBUG, "read(path=\x1b[4;34m%r\x1b[0m, size=%r, offset=%r, fh=%r) by \x1b[3;4m%s\x1b[0m", path, size, offset, fh, PROCESS_STR)
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

    def _get_cache(self, path: str, /):
        cache = self.cache
        if (temp_cache := self.temp_cache) is not None:
            try:
                return temp_cache[path]
            except KeyError:
                value = cache[path]
                if self.pickle_cache:
                    value = pickle_loads(value)
                temp_cache[path] = value
                return value
        else:
            return self.cache[path]

    def _set_cache(self, path: str, value, /):
        cache = self.cache
        if (temp_cache := self.temp_cache) is not None:
            temp_cache[path] = value
            if self.pickle_cache:
                value = pickle_dumps(value)
            cache[path] = value
        else:
            cache[path] = value

    def readdir(self, /, path: str, fh: int = 0) -> list[str]:
        self._log(logging.DEBUG, "readdir(path=\x1b[4;34m%r\x1b[0m, fh=%r) by \x1b[3;4m%s\x1b[0m", path, fh, PROCESS_STR)
        predicate = self.predicate
        strm_predicate = self.strm_predicate
        strm_make = self.strm_make
        cache = {}
        path = normalize("NFC", path)
        realpath = self.normpath_map.get(path, path)
        as_path = self.fs.as_path
        try:
            ls = self.fs.listdir_attr(realpath.lstrip("/"), refresh=self.refresh)
            for attr in ls:
                pathobj = as_path(attr)
                name    = pathobj.name
                subpath = pathobj.path
                isdir   = pathobj.is_dir()
                data = None
                if isdir:
                    size = 0
                if not isdir and strm_predicate and strm_predicate(pathobj):
                    if strm_make:
                        try:
                            url = strm_make(pathobj) or ""
                        except Exception:
                            url = ""
                        if not url:
                            self._log(
                                logging.WARNING, 
                                "can't make strm for file: \x1b[4;34m%s\x1b[0m", 
                                pathobj.relative_to(), 
                            )
                        data = url.encode("utf-8")
                    else:
                        data = pathobj.get_url(ensure_ascii=False).encode("utf-8")
                    size = len(cast(bytes, data))
                    name = splitext(name)[0] + ".strm"
                elif predicate and not predicate(pathobj):
                    continue
                else:
                    size = int(pathobj.get("size") or 0)
                normname = normalize("NFC", name)
                cache[normname] = dict(
                    st_mode=(S_IFDIR if isdir else S_IFREG) | 0o555, 
                    st_size=size, 
                    st_ctime=pathobj["ctime"], 
                    st_mtime=pathobj["mtime"], 
                    st_atime=pathobj.get("atime") or pathobj["mtime"], 
                    _attr=attr, 
                    _path=pathobj, 
                    _data=data, 
                )
                normsubpath = joinpath(path, normname)
                if normsubpath != normalize("NFD", normsubpath):
                    self.normpath_map[normsubpath] = joinpath(realpath, name)
            self._set_cache(path, cache)
            return [".", "..", *cache]
        except BaseException as e:
            self._log(
                logging.ERROR, 
                "can't readdir: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                path, type(e).__qualname__, e, 
            )
            raise OSError(errno.EIO, path) from e

    def release(self, /, path: str, fh: int = 0):
        self._log(logging.DEBUG, "release(path=\x1b[4;34m%r\x1b[0m, fh=%r) by \x1b[3;4m%s\x1b[0m", path, fh, PROCESS_STR)
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

