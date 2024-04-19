#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["CloudDriveFuseOperations"]

try:
    # pip install cachetools
    from cachetools import TTLCache
    # pip install fusepy
    from fuse import FUSE, FuseOSError, Operations, fuse_get_context
    # pip install psutil
    from psutil import Process
except ImportError:
    from subprocess import run
    from sys import executable
    run([executable, "-m", "pip", "install", "-U", "cachetools", "fusepy", "psutil"], check=True)

    from cachetools import TTLCache
    from fuse import FUSE, FuseOSError, Operations, fuse_get_context # type: ignore
    from psutil import Process # type: ignore

import logging

from collections.abc import Callable, MutableMapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial, update_wrapper
from errno import ENOENT, EIO
from itertools import count
from posixpath import join as joinpath, split as splitpath
from stat import S_IFDIR, S_IFREG
from subprocess import run
from sys import maxsize
from threading import Event, Lock, Thread
from time import sleep, time
from typing import cast, BinaryIO, Final, Optional
from unicodedata import normalize

from clouddrive import CloudDriveFileSystem, CloudDrivePath

try:
    from .util.log import logger
except ImportError:
    from util.log import logger # type: ignore


def _get_process():
    pid = fuse_get_context()[-1]
    if pid <= 0:
        return "UNDETERMINED"
    return str(Process(pid))

PROCESS_STR = type("ProcessStr", (), {"__str__": staticmethod(_get_process)})()

if not hasattr(ThreadPoolExecutor, "__del__"):
    setattr(ThreadPoolExecutor, "__del__", lambda self, /: self.shutdown(cancel_futures=True))


def update_readdir_later(
    self, 
    executor: Optional[ThreadPoolExecutor] = None, 
    refresh_min_interval: int | float = 10, 
):
    readdir = type(self).readdir
    refresh_freq: MutableMapping = TTLCache(maxsize, ttl=refresh_min_interval)
    event_pool: dict[str, Event] = {}
    lock = Lock()
    def run_update(path, fh, /, do_refresh=True):
        with lock:
            try:
                evt = event_pool[path]
                wait_event = True
            except KeyError:
                evt = event_pool[path] = Event()
                wait_event = False
        if wait_event:
            if do_refresh:
                return
            evt.wait()
            return [".", "..", *self.cache[normalize("NFC", path)]]
        else:
            try:
                return readdir(self, path, fh)
            finally:
                event_pool.pop(path, None)
                evt.set()
    def wrapper(path, fh=0):
        while True:
            try:
                cache = self.cache[normalize("NFC", path)]
            except KeyError:
                if executor is None:
                    return run_update(path, fh)
                else:
                    future = executor.submit(run_update, path, fh)
                    return future.result()
            else:
                try:
                    if path not in refresh_freq:
                        refresh_freq[path] = None
                        if executor is None:
                            Thread(target=run_update, args=(path, fh)).start()
                        else:
                            executor.submit(run_update, path, fh)
                    return [".", "..", *cache]
                except BaseException as e:
                    self._log(
                        logging.ERROR, 
                        "can't start new thread for path: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                        path, type(e).__qualname__, e, 
                    )
                    raise FuseOSError(EIO) from e
    return update_wrapper(wrapper, readdir)


# Learn: https://www.stavros.io/posts/python-fuse-filesystem/
class CloudDriveFuseOperations(Operations):

    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:5244", 
        username: str = "", 
        password: str = "", 
        cache: Optional[MutableMapping] = None, 
        predicate: Optional[Callable[[CloudDrivePath], bool]] = None, 
        strm_predicate: Optional[Callable[[CloudDrivePath], bool]] = None, 
        max_readdir_workers: int = -1, 
        direct_open_names: Optional[Callable[[str], bool]] = None, 
        direct_open_exes: Optional[Callable[[str], bool]] = None, 
    ):
        self.__finalizer__: list[Callable] = []
        self._log = partial(logger.log, extra={"instance": repr(self)})

        self.fs = CloudDriveFileSystem.login(origin, username, password)
        self.predicate = predicate
        self.strm_predicate = strm_predicate
        register = self.register_finalize = self.__finalizer__.append
        self.direct_open_names = direct_open_names
        self.direct_open_exes = direct_open_exes

        # id generator for file handler
        self._next_fh: Callable[[], int] = count(1).__next__
        # cache `readdir` pulled file attribute map
        if cache is None:
            cache = {}
        self.cache = cache
        # cache all opened files (except in zipfile)
        self._fh_to_file: dict[int, tuple[BinaryIO, bytes]] = {}
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
        # multi threaded directory reading control
        executor: Optional[ThreadPoolExecutor]
        if max_readdir_workers < 0:
            executor = None
        elif max_readdir_workers == 0:
            executor = ThreadPoolExecutor(None)
        else:
            executor = ThreadPoolExecutor(max_readdir_workers)
        self.__dict__["readdir"] = update_readdir_later(self, executor=executor)
        if executor is not None:
            register(partial(executor.shutdown, cancel_futures=True))
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
                raise FuseOSError(EIO) from e
        try:
            return dird[name]
        except KeyError as e:
            self._log(
                logging.WARNING, 
                "file not found: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                path, type(e).__qualname__, e, 
            )
            raise FuseOSError(ENOENT) from e

    def open(self, /, path: str, flags: int = 0) -> int:
        self._log(logging.INFO, "open(path=\x1b[4;34m%r\x1b[0m, flags=%r) by \x1b[3;4m%s\x1b[0m", path, flags, PROCESS_STR)
        pid = fuse_get_context()[-1]
        if pid > 0:
            process = Process(pid)
            exe = process.exe()
            if (
                self.direct_open_names is not None and self.direct_open_names(process.name().lower()) or
                self.direct_open_exes is not None and self.direct_open_exes(exe)
            ):
                process.kill()
                def push():
                    sleep(.01)
                    run([exe, self.fs.get_url(path)])
                Thread(target=push).start()
                return 0
        return self._next_fh()

    def _open(self, path: str, /, start: int = 0):
        attr = self.getattr(path)
        path = self.normpath_map.get(normalize("NFC", path), path)
        if attr.get("_data") is not None:
            return None, attr["_data"]
        if attr["st_size"] <= 2048:
            return None, self.fs.as_path(path).read_bytes()
        file = cast(BinaryIO, self.fs.as_path(path).open("rb"))
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
            if offset < cache_size:
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
            raise FuseOSError(EIO) from e

    def readdir(self, /, path: str, fh: int = 0) -> list[str]:
        self._log(logging.DEBUG, "readdir(path=\x1b[4;34m%r\x1b[0m, fh=%r) by \x1b[3;4m%s\x1b[0m", path, fh, PROCESS_STR)
        predicate = self.predicate
        strm_predicate = self.strm_predicate
        cache = {}
        path = normalize("NFC", path)
        realpath = self.normpath_map.get(path, path)
        try:
            for pathobj in self.fs.listdir_path(realpath):
                name    = pathobj.name
                subpath = pathobj.path
                isdir   = pathobj.is_dir()
                data = None
                if predicate and not predicate(pathobj):
                    continue
                if isdir:
                    size = 0
                elif strm_predicate and strm_predicate(pathobj):
                    data = pathobj.url.encode("latin-1")
                    size = len(data)
                    name += ".strm"
                else:
                    size = int(pathobj.get("size", 0))
                normname = normalize("NFC", name)
                cache[normname] = dict(
                    st_mode=(S_IFDIR if isdir else S_IFREG) | 0o555, 
                    st_size=size, 
                    st_ctime=pathobj["ctime"], 
                    st_mtime=pathobj["mtime"], 
                    st_atime=pathobj["atime"], 
                    _data=data, 
                )
                normsubpath = joinpath(path, normname)
                if normsubpath != normalize("NFD", normsubpath):
                    self.normpath_map[normsubpath] = joinpath(realpath, name)
            self.cache[path] = cache
            return [".", "..", *cache]
        except BaseException as e:
            self._log(
                logging.ERROR, 
                "can't readdir: \x1b[4;34m%s\x1b[0m\n  |_ \x1b[1;4;31m%s\x1b[0m: %s", 
                path, type(e).__qualname__, e, 
            )
            raise FuseOSError(EIO) from e

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
            raise FuseOSError(EIO) from e

    def run(self, /, *args, **kwds):
        return FUSE(self, *args, **kwds)

