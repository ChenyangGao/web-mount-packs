#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="""\
基于 clouddrive 和 fuse 的虚拟 strm 文件系统 
    1. Linux 要安装 libfuse：  https://github.com/libfuse/libfuse
    2. MacOSX 要安装 MacFUSE： https://github.com/osxfuse/osxfuse
    3. Windows 要安装 WinFsp： https://github.com/winfsp/winfsp

访问源代码：
    - https://github.com/ChenyangGao/web-mount-packs/tree/main/python-wrap-clouddrive-web-api/examples/strm-fuse
""", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-o", "--origin", default="http://localhost:19798", help="clouddrive 服务器地址，默认 http://localhost:19798")
    parser.add_argument("-u", "--username", default="", help="用户名，默认为空")
    parser.add_argument("-p", "--password", default="", help="密码，默认为空")
    parser.add_argument("-d", "--debug", action="store_true", help="调试模式，会输出 DEBUG 级别的日志")
    parser.add_argument("-c", "--cache-size", default=0, type=int, help="缓存大小，如果小于等于 0，就是无限容量，默认值 0")
    parser.add_argument("-i0", "--ignore-file", help="（优先级最高）接受一个配置文件，忽略其中罗列的文件，语法用 gitignore，https://git-scm.com/docs/gitignore#_pattern_format")
    parser.add_argument("-i1", "--include-file", help="接受一个配置文件，仅罗列被它断言为真的文件，语法用 gitignore，https://git-scm.com/docs/gitignore#_pattern_format")
    parser.add_argument("--include-videos", action="store_true", help="仅罗列视频文件")
    parser.add_argument("--include-audios", action="store_true", help="仅罗列音频文件")
    parser.add_argument("--include-images", action="store_true", help="仅罗列图片文件")
    parser.add_argument("mount_point", help="挂载地址")
    args = parser.parse_args()

from errno import ENOENT
from mimetypes import guess_type
from posixpath import basename, join as joinpath
from stat import S_IFDIR, S_IFREG
from time import time
from typing import cast, Callable, MutableMapping, Optional

import help._init_mimetypes
from ignore import read_file, make_ignore

try:
    from clouddrive import CloudDriveFileSystem
    from cachetools import cached, LRUCache, TTLCache
    from dateutil.parser import parse
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
except ModuleNotFoundError:
    from os import remove
    from pkgutil import get_data
    from subprocess import run
    from sys import executable
    from tempfile import NamedTemporaryFile
    f = NamedTemporaryFile(suffix=".txt", mode="wb", buffering=0, delete=False)
    try:
        data = get_data("help", "requirements.txt")
        if not data:
            raise RuntimeError("can't find 'help/requirements.txt'")
        run([executable, "-m", "pip", "install", "-r", f.name], check=True)
    finally:
        remove(f.name)
    from clouddrive import CloudDriveFileSystem
    # pip install types-cachetools
    from cachetools import cached, LRUCache, TTLCache
    # pip install types-python-dateutil
    from dateutil.parser import parse
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn # type: ignore


def parse_as_ts(s: Optional[str] = None) -> float:
    if not s:
        return 0.0
    if s.startswith("0001-01-01"):
        return 0.0
    try:
        return parse(s).timestamp()
    except:
        return 0.0


class CloudDriveFuseOperations(LoggingMixIn, Operations):

    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
        cache_size: int = 0, 
        predicate: Optional[Callable] = None, 
    ):
        self.fs = CloudDriveFileSystem.login(origin, username, password)
        self.cache: MutableMapping = {} if cache_size <= 0 else LRUCache(cache_size)
        self.predicate = predicate

    def attr(self, path: str) -> tuple[dict, bytes]:
        try:
            return self.cache[path]
        except KeyError:
            pass
        fullpath = path
        path = path.removesuffix(".strm")
        try:
            pathobj = self.fs.as_path(path, fetch_attr=True)
        except FileNotFoundError:
            raise FuseOSError(ENOENT)
        else:
            url = pathobj.url.encode("latin-1")
            r = self.cache[fullpath] = (dict(
                st_uid=0, 
                st_gid=0, 
                st_mode=(S_IFDIR if pathobj.is_dir else S_IFREG) | 0o444, 
                st_nlink=1, 
                st_size=len(url), 
                st_ctime=parse_as_ts(pathobj.get("createTime")), 
                st_mtime=parse_as_ts(pathobj.get("writeTime")), 
                st_atime=parse_as_ts(pathobj.get("accessTime")), 
            ), url)
            return r

    def destroy(self, path: str):
        self.fs.client.close()

    def getattr(self, path: str, fh=None):
        if basename(path).startswith("."):
            raise FuseOSError(ENOENT)
        return self.attr(path)[0]

    def read(self, path: str, size: int, offset: int, fh) -> bytes:
        return self.attr(path)[1]

    @cached(TTLCache(64, ttl=10), key=lambda self, path, fh: path)
    def readdir(self, path, fh):
        cache = self.cache
        predicate = self.predicate
        ls = [".", ".."]
        for pathobj in self.fs.listdir_attr(path):
            is_dir = pathobj.is_dir
            name = pathobj["name"]
            if name.startswith("."):
                continue
            subpath = joinpath(path, name)
            if predicate:
                if is_dir:
                    subpath += "/"
                if not predicate(subpath):
                    continue
            url = pathobj.url.encode("latin-1")
            if not is_dir:
                name += ".strm"
            cache[joinpath(path, name)] = (dict(
                st_uid=0, 
                st_gid=0, 
                st_mode=(S_IFDIR if is_dir else S_IFREG) | 0o444, 
                st_nlink=1, 
                st_size=len(url), 
                st_ctime=parse_as_ts(pathobj.get("createTime")), 
                st_mtime=parse_as_ts(pathobj.get("writeTime")), 
                st_atime=parse_as_ts(pathobj.get("accessTime")), 
            ), url)
            ls.append(name)
        return ls


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    ignore: Optional[Callable] = None
    predicate: Optional[Callable] = None
    predications = []
    if args.ignore_file:
        ignorances = read_file(args.ignore_file)
        if ignorances:
            ignore = make_ignore(*ignorances)
    if args.include_file:
        inclusions = read_file(args.include_file)
        if inclusions:
            predications.append(make_ignore(*inclusions))
    if args.include_videos:
        predications.append(lambda p: (guess_type(p)[0] or "").startswith("video/"))
    if args.include_audios:
        predications.append(lambda p: (guess_type(p)[0] or "").startswith("audio/"))
    if args.include_images:
        predications.append(lambda p: (guess_type(p)[0] or "").startswith("image/"))
    if predications:
        predications.insert(0, lambda p: p.endswith("/"))
    if ignore:
        ign = ignore
        if predications:
            predicate = lambda p: not ign(p) and any(pred(p) for pred in predications)
        else:
            predicate = lambda p: not ign(p) 
    elif predications:
        predicate = lambda p: any(pred(p) for pred in predications)

    print("\n    👋 Welcome to use clouddrive strm fuse 👏\n")
    fuse = FUSE(
        CloudDriveFuseOperations(
            args.origin, 
            args.username, 
            args.password, 
            cache_size=args.cache_size, 
            predicate=predicate, 
        ),
        args.mount_point, 
        foreground=True, 
        ro=True, 
        allow_other=True, 
    )

