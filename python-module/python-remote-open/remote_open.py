#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 4)
__all__ = [
    "open_ftp", "open_ftp_fs", "ftp_open_buffer", "ftp_open", 
    "open_ssh", "open_sftp", "sftp_open", 
    "open_webdav", "open_webdav_fs", "webdav_open", 
    "open_samba", "open_samba_fs", "samba_open_buffer", "samba_open", 
]
__requirements__ = ["ftputil", "paramiko", "webdav4", "pysmb"]

from contextlib import contextmanager
from glob import escape as glob_escape
from io import (
    BytesIO, BufferedReader, BufferedWriter, BufferedRandom, TextIOWrapper, 
    UnsupportedOperation, DEFAULT_BUFFER_SIZE, 
)
from posixpath import split
from ntpath import basename, dirname, join, normcase, normpath
from shutil import copyfileobj
from urllib.parse import urlsplit
from warnings import warn

# https://docs.python.org/3/library/ftplib.html
from ftplib import FTP as _FTP, FTP_TLS as _FTP_TLS
# https://ftputil.sschwarzer.net
from ftputil.host import FTPHost
from ftputil.file import FTPFile
# https://docs.paramiko.org/en/latest/
from paramiko import SSHClient, AutoAddPolicy
# https://pypi.org/project/webdav4/
from webdav4.client import Client
from webdav4.fsspec import WebdavFileSystem
# https://pysmb.readthedocs.io/en/latest/
from smb.smb_structs import OperationFailure
from smb.SMBConnection import SMBConnection


class FTP(_FTP):
    def __init__(self, /, host="", port=0, user="", passwd="", **kwargs):
        if port:
            self.port = port
        super().__init__(host, user, passwd, **kwargs)
    __init__.__doc__ = _FTP.__init__.__doc__
    __del__ = _FTP.__exit__


class FTP_TLS(_FTP_TLS):
    def __init__(self, /, host="", port=0, user="", passwd="", **kwargs):
        if port:
            self.port = port
        super().__init__(host, user, passwd, **kwargs)
    __init__.__doc__ = _FTP_TLS.__init__.__doc__
    __del__ = _FTP_TLS.__exit__


FTPHost.__del__ = FTPHost.close
FTPFile.__del__ = FTPFile.close


def open_ftp(
    hostname="127.0.0.1", 
    port=0, 
    username="anonymous", 
    password="", 
    tls=False, 
    **kwargs, 
):
    "打开并返回一个 FTP 客户端（ftplib.FTP 或 ftplib.FTP_TLS）"
    cls = FTP_TLS if tls else FTP
    return cls(hostname, port, username, password, **kwargs)


def open_ftp_fs(
    hostname="127.0.0.1", 
    port=0, 
    username="anonymous", 
    password="", 
    tls=False, 
    **kwargs, 
):
    "打开并返回一个 FTP 客户端（ftputil.FTPHost），此对象实现了一部分文件系统的接口（参考 os、os.path、shutil）"
    cls = FTP_TLS if tls else FTP
    return FTPHost(hostname, port, username, password, session_factory=cls, **kwargs)


@contextmanager
def ftp_open_buffer(
    url, 
    mode="r", 
    blocksize=DEFAULT_BUFFER_SIZE, 
    encoding=None, 
    errors=None, 
    newline=None, 
):
    "上下文管理器，用 FTP 打开一个分享链接，得到一个类文件对象，你可以对它进行读写，退出上下文管理器后自动同步到服务器"
    assert mode in ("r", "w", "a", "x", "rb", "wb", "ab", "xb", "rt", "wt", "at", "xt")
    if len(mode) == 1:
        mode += "t"
    urlp = urlsplit(url)
    scheme = urlp.scheme
    if scheme not in ("ftp", "ftps"):
        raise ValueError("Not a ftp link")
    hostname = urlp.hostname or "127.0.0.1"
    port     = int(urlp.port or 0)
    username = urlp.username or "anonymous"
    password = urlp.password
    path     = urlp.path
    dir_, file = split(path)
    ftp = open_ftp(hostname, port, username, path, tls=scheme=="ftps")
    ftp.cwd(dir_)
    m1, m2 = mode
    if m1 == "x":
        if file in ftp.nlst():
            raise FileExistsError(path)
    buffer = BytesIO()
    if m1 not in "wx":
        ftp.retrbinary("RETR " + file, buffer.write, blocksize)
        if m1 == "r":
            buffer.seek(0)
    if m2 == "b":
        f = buffer
    else:
        f = TextIOWrapper(
            buffer, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )
    yield f
    if m1 != "r":
        f.seek(0)
        ftp.storbinary("STOR " + file, buffer, blocksize)


def ftp_open(
    url, 
    mode="r", 
    buffering=None, 
    encoding=None, 
    errors=None, 
    newline=None, 
    *, 
    rest=None, 
):
    "用 FTP 打开一个分享链接，得到一个文件对象，你可以立即对其读写"
    urlp = urlsplit(url)
    scheme = urlp.scheme
    if scheme not in ("ftp", "ftps"):
        raise ValueError("Not a ftp link")
    hostname = urlp.hostname or "127.0.0.1"
    port     = int(urlp.port or 0)
    username = urlp.username or "anonymous"
    password = urlp.password
    path     = urlp.path
    ftphost = open_ftp_2(hostname, port, username, password, tls=scheme=="ftps")
    f = ftphost.open(
        path, 
        mode, 
        buffering=buffering, 
        encoding=encoding, 
        errors=errors, 
        newline=newline, 
        rest=rest, 
    )
    f.ftphost = ftphost
    return f


def open_ssh(hostname="127.0.0.1", port=22, username=None, password=None):
    "打开并返回一个 SSH 客户端（paramiko.client.SSHClient）"
    client = SSHClient()
    client.set_missing_host_key_policy(AutoAddPolicy())
    #client.load_system_host_keys()
    client.connect(hostname, port, username, password)
    return client


def open_sftp(hostname="127.0.0.1", port=22, username=None, password=None):
    "打开并返回一个 SFTP 客户端（paramiko.sftp_client.SFTP）"
    client = open_ssh(hostname, port, username, password)
    return client.open_sftp()


def sftp_open(
    url, 
    mode="r", 
    bufsize=-1, 
    encoding=None, 
    errors=None, 
    newline=None, 
):
    "用 SFTP 打开一个分享链接，得到一个文件对象，你可以立即对其读写"
    assert mode in ("r", "w", "a", "x", "rb", "wb", "ab", "xb", "rt", "wt", "at", "xt")
    if len(mode) == 1:
        mode += "t"
    urlp = urlsplit(url)
    scheme = urlp.scheme
    if scheme != "sftp":
        raise ValueError("not a sftp link")
    hostname = urlp.hostname or "127.0.0.1"
    port     = int(urlp.port or 22)
    username = urlp.username
    password = urlp.password
    path     = urlp.path
    sftp = open_sftp(hostname, port, username, password)
    # TODO: 设计一个专门的包装函数
    if mode[0] == "x":
        try:
            sftp.stat(path)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(path)
    if mode[1] == "b":
        return sftp.open(path, mode, bufsize)
    else:
        return TextIOWrapper(
            sftp.open(path, mode, bufsize), 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )


def open_webdav(baseurl="http://localhost", username="", password="", **kwargs):
    "打开并返回一个 webdav 客户端（webdav4.client.Client）"
    if username:
        auth = (username, password)
    return Client(baseurl, auth=auth, **kwargs)


def open_webdav_fs(baseurl, username="", password="", **kwargs):
    "打开并返回一个 webdav 客户端（webdav4.fsspec.WebdavFileSystem）"
    if username:
        auth = (username, password)
    return WebdavFileSystem(baseurl, auth=auth, **kwargs)


def webdav_open(
    url, 
    mode="r", 
    block_size=None, 
    encoding=None, 
    errors=None, 
    newline=None, 
    **kwargs, 
):
    "用 webdav 打开一个分享链接，得到一个文件对象，你可以立即对其读写"
    urlp = urlsplit(url)
    scheme = urlp.scheme
    if scheme not in ("http", "https", "dav", "davs"):
        raise ValueError("Not a webdav link")
    if scheme == "dav":
        scheme = "http"
    elif scheme == "davs":
        scheme = "https"
    hostname = urlp.hostname or "localhost"
    port     = urlp.port
    username = urlp.username
    password = urlp.password
    path     = urlp.path
    baseurl_parts = [scheme, "://"]
    part_add = baseurl_parts.append
    if username:
        part_add(username)
        if password:
            part_add(":")
            part_add(password)
        part_add("@")
    if hostname:
        part_add(hostname)
    if port:
        part_add(port)
    baseurl = "".join(baseurl_parts)
    webdav = open_webdav_fs(hostname, port, username, password, dir_, scheme=scheme)
    return webdav.open(
        file, 
        mode, 
        block_size, 
        encoding=encoding, 
        errors=errors, 
        newline=newline, 
        **kwargs, 
    )


SMBConnection.__del__ = SMBConnection.close


class SMBFileSystem:

    def __init__(self, /, con, share_name="", path="/"):
        self.__con = con
        self.__share_name = share_name
        if not path.startswith("/"):
            path = "/" + path
        self.__path = path

    def __repr__(self, /):
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(con={self.con!r}, share_name={self.share_name!r}, path={self.path!r})"

    def _norm_share_name(self, share_name="", /):
        if not share_name:
            share_name = self.share_name
            if not share_name:
                raise ValueError("`share_name` is unspecified")
        return share_name

    def _norm_path(self, path="", /):
        if not path:
            return self.path
        return join(self.path, path)

    def attr(self, path, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        return self.con.getAttributes(share_name, path)

    def chdir(self, path, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        try:
            attr = self.attr(path, share_name)
        except OperationFailure as e:
            raise OSError((share_name, path)) from e
        else:
            if attr.isDirectory:
                self.__share_name = share_name
                self.__path = path
            else:
                raise NotADirectoryError((share_name, path))

    @property
    def con(self, /):
        return self.__con

    def copy(self, path_old, path_new, /, share_name=""):
        raise NotImplementedError("copy")

    def copyfile(self, path_old, path_new, /, share_name=""):
        raise NotImplementedError("copyfile")

    def copymode(self, path_old, path_new, /, share_name=""):
        raise NotImplementedError("copymode")

    def copystat(self, path_old, path_new, /, share_name=""):
        raise NotImplementedError("copystat")

    def copytree(self, path_old, path_new, /, share_name=""):
        raise NotImplementedError("copytree")

    def download(self, path, local_path_or_file="", /, share_name=""):
        if hasattr(local_path_or_file, "write"):
            local_file = local_path_or_file
            if isinstance(local_file, TextIOWrapper):
                local_file = local_file.buffer
        else:
            local_path = local_path_or_file
            if not local_path:
                local_path = basename(path)
            local_file = open(local_path, "wb")
        remote_file = self.open(path, "rb", share_name=share_name)
        copyfileobj(local_file, remote_file)

    def exists(self, path, /, share_name=""):
        try:
            self.attr(path, share_name)
        except UnsupportedOperation:
            return False
        else:
            return True

    @property
    def fullpath(self):
        return join(self.storage, self.path)

    def getcwd(self, /):
        return self.path, self.storage

    def getcwd(self, /):
        return self.share_name, self.path

    def isfile(self, path, /, share_name=""):
        try:
            return not self.attr(path, share_name).isDirectory
        except OperationFailure:
            return False

    def isdir(self, path, /, share_name=""):
        try:
            return self.attr(path, share_name).isDirectory
        except OperationFailure:
            return False

    def listdir(self, path="", /, share_name="", with_attr=False):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        try:
            ls = self.con.listPath(share_name, path)[2:]
        except OperationFailure as e:
            raise OSError((share_name, path)) from e
        if with_attr:
            return ls
        return [a.filename for a in ls]

    def list_shares(self, /):
        return [s.name for s in self.con.listShares()]

    def makedirs(self, path, /, share_name="", exist_ok=False):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        if path in ("", "/"):
            return
        if share_name not in self.list_shares():
            raise OSError(f"no such share_name: {share_name!r}")
        try:
            attr = self.attr(path, share_name)
        except OperationFailure:
            pending = [path]
            while True:
                path = dirname(path)
                if path in ("", "/"):
                    break
                try:
                    attr = self.attr(path, share_name)
                except OperationFailure:
                    pending.append(path)
                else:
                    if not attr.isDirectory:
                        raise NotADirectoryError((share_name, path))
                    break
            for path in reversed(pending):
                self.con.createDirectory(share_name, path)
        else:
            if not exist_ok or not attr.isDirectory:
                raise FileExistsError((share_name, path))

    def mkdir(self, path, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        if path in ("", "/"):
            return
        try:
            attr = self.attr(path, share_name)
        except OperationFailure:
            try:
                self.con.createDirectory(share_name, path)
            except OperationFailure as e:
                raise OSError((share_name, path)) from e
        else:
            raise FileExistsError((share_name, path))

    def move(self, src, dst, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        old_path = normpath(self._norm_path(src))
        new_path = normpath(self._norm_path(dst))
        if normcase(old_path) == normcase(new_path):
            if old_path != new_path:
                self.rename(old_path, new_path, share_name)
            return (share_name, new_path)
        try:
            attr_old = self.attr(old_path, share_name)
        except UnsupportedOperation as e:
            raise FileNotFoundError((share_name, old_path)) from e
        try:
            attr_new = self.attr(new_path, share_name)
        except UnsupportedOperation as e:
            self.rename(old_path, new_path, share_name)
        else:
            if attr_new.isDirectory:
                self.rename(old_path, join(new_path, basename(old_path)), share_name)
            else:
                self.rename(old_path, new_path, share_name)
        return (share_name, new_path)

    def open(
        self, 
        path, 
        /, 
        mode="r", 
        buffering=-1, 
        encoding=None, 
        errors=None, 
        newline=None, 
        share_name="", 
    ):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        return smb_open(
            self.con, 
            share_name, 
            path, 
            mode=mode, 
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )

    @property
    def path(self, /):
        return self.__path

    def remove(self, path, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        try:
            self.con.deleteFiles(share_name, glob_escape(path))
        except OperationFailure as e:
            raise OSError((share_name, path)) from e

    def removedirs(self,  path, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        self.rmdir(path, share_name)
        while True:
            path = dirname(path)
            if path in ("", "/"):
                break
            try:
                self.con.deleteDirectory(share_name, path)
            except OperationFailure:
                break

    def rename(self, src, dst, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        old_path = self._norm_path(src)
        new_path = self._norm_path(dst)
        try:
            self.con.rename(share_name, old_path, new_path)
        except OperationFailure as e:
            raise OSError((share_name, old_path), (share_name, new_path)) from e

    def renames(self, src, dst, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        old_path = self._norm_path(src)
        new_path = self._norm_path(dst)
        if not self.exists(old_path, share_name):
            raise FileNotFoundError((share_name, old_path)) from e
        self.makedirs(dirname(new_path), share_name, exist_ok=True)
        self.rename(old_path, new_path, share_name)
        try:
            self.removedirs(dirname(old_path), share_name)
        except:
            pass

    def replace(self, src, dst, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        old_path = normpath(self._norm_path(src))
        new_path = normpath(self._norm_path(dst))
        if normcase(old_path) == normcase(new_path):
            if old_path != new_path:
                self.rename(old_path, new_path, share_name)
            return
        try:
            attr_old = self.attr(old_path, share_name)
        except UnsupportedOperation as e:
            raise FileNotFoundError((share_name, old_path)) from e
        try:
            attr_new = self.attr(new_path, share_name)
        except UnsupportedOperation as e:
            self.rename(old_path, new_path, share_name)
        else:
            if attr_old.isDirectory:
                if attr_new.isDirectory:
                    self.rmdir(new_path, share_name)
                else:
                    raise NotADirectoryError((share_name, new_path))
            elif attr_new.isDirectory:
                raise IsADirectoryError((share_name, new_path))
            else:
                self.remove(new_path, share_name)
            self.rename(old_path, new_path, share_name)

    def rmdir(self, path, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        if path in ("", "/"):
            return
        try:
            attr = self.attr(path, share_name)
            if not attr.isDirectory:
                raise NotADirectoryError((share_name, path))
            self.con.deleteDirectory(share_name, path)
        except OperationFailure as e:
            raise OSError((share_name, path)) from e

    def rmtree(self, path, /, share_name=""):
        share_name = self._norm_share_name(share_name)
        path = self._norm_path(path)
        try:
            self.con.deleteFiles(share_name, glob_escape(path), delete_matching_folders=True)
        except OperationFailure as e:
            raise OSError((share_name, path)) from e

    def scandir(self, path="", /, share_name=""):
        raise NotImplementedError(
            "`scandir(...)` is currently not supported, "
            "use `listdir(..., with_attr=True)` instead."
        )

    @property
    def share_name(self, /):
        return self.__share_name

    def stat(self, path, /, share_name=""):
        raise NotImplementedError("`stat()` is currently not supported, use `attr()` instead.")

    def upload(self, local_path_or_file, path="", /, share_name=""):
        if hasattr(local_path_or_file, "read"):
            local_file = local_path_or_file
            if isinstance(local_file, TextIOWrapper):
                local_file = local_file.buffer
        else:
            local_path = local_path_or_file
            local_file = open(local_path, "rb")
        if not path:
            path = basename(local_file.name)
        remote_file = self.open(path, "wb", share_name=share_name)
        copyfileobj(local_file, remote_file)

    unlink = remove

    def walk(self, /, top="", share_name="", topdown=True, onerror=None):
        try:
            ls = self.listdir(top, share_name, with_attr=True)
        except OSError as e:
            if callable(onerror):
                onerror(e)
            elif onerror:
                raise
            return
        dirs = []
        files = []
        for attr in ls:
            if attr.isDirectory:
                dirs.append(attr.filename)
            else:
                files.append(attr.filename)
        if topdown:
            yield top, dirs, files
            for dir_ in dirs:
                yield from self.walk(
                    join(top, dir_), 
                    share_name, 
                    topdown=True, 
                    onerror=onerror, 
                )
        else:
            for dir_ in dirs:
                yield from self.walk(
                    join(top, dir_), 
                    share_name, 
                    topdown=False, 
                    onerror=onerror, 
                )
            yield top, dirs, files


class SMBFile: # behave like `io.FileIO`

    def __init__(self, /, con, share_name, path, mode="r"):
        self.__con = con
        self.__share_name = share_name
        self.__path = path
        self.__mode = mode

        share_name = share_name.strip("/")
        if not path.startswith("/"):
            path = "/" + path
        self.__name = f"smb://{self.con.remote_name}/{share_name}{path}"

        def retrieveFromOffset(
            file_obj, 
            offset=0, 
            max_length=-1, 
            timeout=30, 
        ):
            return con.retrieveFileFromOffset(
                share_name, 
                path, 
                file_obj, 
                offset=offset, 
                max_length=max_length, 
                timeout=timeout, 
            )

        def storeFromOffset(
            file_obj, 
            offset=0, 
            truncate=False, 
            timeout=30, 
        ):
            return con.storeFileFromOffset(
                share_name, 
                path, 
                file_obj, 
                offset=offset, 
                truncate=truncate, 
                timeout=timeout, 
            )

        def getAttributes():
            return con.getAttributes(share_name, path)

        self.retrieveFromOffset = retrieveFromOffset
        self.storeFromOffset = storeFromOffset
        self.getAttributes = getAttributes

        m_main, m_update = "", False
        for c in mode:
            if c in "rwxa":
                if m_main:
                    raise ValueError(f"invalid mode: {mode!r}")
                m_main = c
            elif c == "b":
                pass
            elif c == "+":
                if m_update:
                    raise ValueError(f"invalid mode: {mode!r}")
                m_update = True
            else:
                raise ValueError(f"invalid mode: {mode!r}")

        if m_update:
            self.__readable = True
            self.__writable = True
        elif m_main == "r":
            self.__readable = True
            self.__writable = False
        else:
            self.__readable = False
            self.__writable = True
        if m_main == "r":
            try:
                getAttributes()
                self.__pos = 0
            except OperationFailure as e:
                raise OSError((share_name, path)) from e
        elif m_main == "w":
            storeFromOffset(BytesIO(b""), truncate=True)
            self.__pos = 0
        elif m_main == "a":
            try:
                self.__pos = getAttributes().file_size
            except OperationFailure:
                storeFromOffset(BytesIO(b""), truncate=True)
                self.__pos = 0
        else: # m_main == "x"
            try:
                getAttributes()
            except OperationFailure:
                storeFromOffset(BytesIO(b""), truncate=True)
                self.__pos = 0
            else:
                raise FileExistsError((share_name, path))
        self.__closed = False

    def __del__(self, /):
        self.close()

    def __enter__(self, /):
        return self

    def __exit__(self, /, *exc_info):
        self.close()
        return False

    def __iter__(self, /):
        return self

    def __next__(self, /):
        line = self.readline()
        if line:
            return line
        else:
            raise StopIteration

    def __repr__(self, /):
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(con={self.con!r}, share_name={self.share_name!r}, path={self.path!r}, mode={self.mode!r})"

    @property
    def attr(self):
        return self.con.getAttributes(self.share_name, self.path)

    def close(self, /):
        self.__closed = True

    @property
    def closed(self, /):
        return self.__closed

    @property
    def con(self, /):
        return self.__con

    @property
    def fileno(self, /):
        raise UnsupportedOperation("fileno")

    def flush(self, /):
        return NotImplemented("flush")

    def iterlines(self):
        if not self.readable:
            raise UnsupportedOperation("iterlines")
        buf = BytesIO()
        pos = self.__pos
        line = b""
        while True:
            _, nbytes = self.retrieveFromOffset(buf, pos, DEFAULT_BUFFER_SIZE)
            if not nbytes:
                self.__pos = pos
                yield line
                return
            buf.seek(0)
            while True:
                if line:
                    line += buf.readline()
                else:
                    line = buf.readline()
                if line.endswith(b"\n"):
                    self.__pos += len(line) 
                    yield line
                    line = b""
                elif nbytes < DEFAULT_BUFFER_SIZE:
                    self.__pos = pos + nbytes
                    yield line
                    return
                else:
                    buf.truncate()
                    buf.seek(0)
                    break
            pos += DEFAULT_BUFFER_SIZE

    @property
    def mode(self, /):
        return self.__mode

    @property
    def name(self, /):
        return self.__name

    @property
    def path(self, /):
        return self.__path

    def read(self, size=-1, /):
        if not self.readable:
            raise UnsupportedOperation("read")
        if size == 0:
            return b""
        buf = BytesIO()
        _, nbytes = self.retrieveFromOffset(buf, self.__pos, size)
        self.__pos += nbytes
        return buf.getvalue()

    def readable(self, /):
        return self.__readable

    def readinto(self, buffer, /):
        if not self.readable:
            raise UnsupportedOperation("readinto")
        bufsize = memoryview(buffer).nbytes
        @staticmethod
        def write(b):
            buffer[:len(b)] = b
            return len(b)
        _, nbytes = self.retrieveFromOffset(type("", (), {"write": write}), self.__pos, bufsize)
        self.__pos += nbytes
        return nbytes

    def readline(self, size=-1, /):
        if not self.readable:
            raise UnsupportedOperation("readline")
        if size == 0:
            return b""
        buf = BytesIO()
        pos = self.__pos
        while True:
            _, nbytes = self.retrieveFromOffset(buf, pos, DEFAULT_BUFFER_SIZE)
            if not nbytes:
                self.__pos = pos
                return buf.getvalue()
            buf.seek(-nbytes, 2)
            line = buf.readline()
            bufpos = buf.tell()
            if size > 0 and bufpos >= size:
                self.__pos = pos + size
                return buf.getbuffer()[:size].tobytes()
            elif line.endswith(b"\n"):
                self.__pos = pos + bufpos
                return buf.getbuffer()[:bufpos].tobytes()
            elif nbytes < DEFAULT_BUFFER_SIZE:
                self.__pos = pos + nbytes
                return buf.getvalue()
            else:
                pos += DEFAULT_BUFFER_SIZE

    def readlines(self, hint=-1, /):
        if not self.readable:
            raise UnsupportedOperation("readlines")
        if hint <= 0:
            return list(self.iterlines())
        ls = []
        total_size = 0
        for line in self.iterlines():
            ls.append(line)
            total_size += len(line)
            if total_size >= hint:
                break
        return ls

    def seek(self, pos, whence=0, /):
        if whence == 0:
            if pos < 0:
                raise ValueError(f"negative seek position: {pos!r}")
            self.__pos = pos
            return pos
        elif whence == 1:
            return self.seek(self.__pos+pos)
        elif whence == 2:
            size = self.getAttributes().file_size
            return self.seek(size+pos)
        else:
            raise ValueError(f"whence value {whence!r} unsupported")

    def seekable(self, /):
        return True

    @property
    def share_name(self, /):
        return self.__share_name

    def tell(self, /):
        return self.__pos

    def truncate(self, size=None, /):
        raise NotImplementedError("truncate")

    def writable(self, /):
        return self.__writable

    def write(self, b, /):
        if not self.writable:
            raise UnsupportedOperation("write")
        self.__pos = self.storeFromOffset(BytesIO(b), self.__pos)
        return len(b)

    def writelines(self, lines, /):
        if not self.writable:
            raise UnsupportedOperation("writelines")
        for line in lines:
            self.write(line)


def smb_open(
    con, 
    share_name, 
    path, 
    mode="r", 
    buffering=-1, 
    encoding=None, 
    errors=None, 
    newline=None, 
):
    m_main, m_str, m_update = "", "", False
    for c in mode:
        if c in "rwxa":
            if m_main:
                raise ValueError(f"invalid mode: {mode!r}")
            m_main = c
        elif c in "bt":
            if m_str:
                raise ValueError(f"invalid mode: {mode!r}")
            m_str = c
        elif c == "+":
            if m_update:
                raise ValueError(f"invalid mode: {mode!r}")
            m_update = True
        else:
            raise ValueError(f"invalid mode: {mode!r}")
    if not m_str:
        m_str = "t"
    if buffering == 0:
        if m_str == "t":
            raise ValueError("can't have unbuffered text I/O")
        return SMBFile(con, share_name, path, mode)
    line_buffering = False
    if buffering < 0:
        buffer_size = DEFAULT_BUFFER_SIZE
    elif buffering == 1:
        if m_str == "b":
            warn("line buffering (buffering=1) isn't supported in binary mode, the default buffer size will be used", RuntimeWarning)
        buffer_size = DEFAULT_BUFFER_SIZE
        line_buffering = True
    else:
        buffer_size = buffering
    raw = SMBFile(con, share_name, path, mode.replace("t", ""))
    if m_update:
        buffer = BufferedRandom(raw, buffer_size)
    elif m_main == "r":
        buffer = BufferedReader(raw, buffer_size)
    else:
        buffer = BufferedWriter(raw, buffer_size)
    if m_str == "t":
        return TextIOWrapper(
            buffer, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            line_buffering=line_buffering, 
        )
    else:
        return buffer


def open_samba(
    hostname="127.0.0.1", 
    port=139, 
    username="", 
    password="", 
    remote_name=None, 
    domain="", 
    my_name="", 
    use_ntlm_v2=True, 
    sign_options=2, 
    is_direct_tcp=False, 
):
    "打开并返回一个 Samba 客户端（smb.SMBConnection.SMBConnection）"
    if remote_name is None:
        remote_name = hostname
    con = SMBConnection(
        username, 
        password, 
        my_name, 
        remote_name, 
        domain, 
        use_ntlm_v2=use_ntlm_v2, 
        sign_options=sign_options, 
        is_direct_tcp=is_direct_tcp, 
    )
    con.connect(hostname, port)
    return con


def open_samba_fs(
    hostname="127.0.0.1", 
    port=139, 
    username="", 
    password="", 
    remote_name=None, 
    domain="", 
    my_name="", 
    use_ntlm_v2=True, 
    sign_options=2, 
    is_direct_tcp=False, 
    share_name="", 
    path="/", 
):
    "打开并返回一个 Samba 客户端（SMBFileSystem），此对象实现了一部分文件系统的接口（参考 os、os.path、shutil）"
    con = open_samba(
        hostname=hostname, 
        port=port, 
        username=username, 
        password=password, 
        remote_name=remote_name, 
        domain=domain, 
        my_name=my_name, 
        use_ntlm_v2=use_ntlm_v2, 
        sign_options=sign_options, 
        is_direct_tcp=is_direct_tcp, 
    )
    return SMBFileSystem(con, share_name, path)


@contextmanager
def samba_open_buffer(
    url, 
    mode="r", 
    encoding=None, 
    errors=None, 
    newline=None, 
):
    "上下文管理器，用 Samba 打开一个分享链接，得到一个类文件对象，你可以对它进行读写，退出上下文管理器后自动同步到服务器"
    assert mode in ("r", "w", "a", "x", "rb", "wb", "ab", "xb", "rt", "wt", "at", "xt")
    if len(mode) == 1:
        mode += "t"
    urlp = urlsplit(url)
    scheme = urlp.scheme
    if scheme != "smb":
        raise ValueError("Not a samba link")
    hostname = urlp.hostname or "127.0.0.1"
    port     = int(urlp.port or 139)
    username = urlp.username
    password = urlp.password
    fullpath = urlp.path
    if not fullpath:
        raise OSError(fullpath)
    share_name, _, path = fullpath[1:].partition("/")
    path = "/" + path
    con = open_samba(hostname, port, username, password)
    m1, m2 = mode
    if m1 == "x":
        try:
            con.getAttributes(path)
        except OperationFailure:
            pass
        else:
            raise FileExistsError(path)
    buffer = BytesIO()
    if m1 not in "wx":
        try:
            con.retrieveFile(share_name, path, buffer)
        except OperationFailure as e:
            raise FileNotFoundError(fullpath) from e
        if m1 == "r":
            buffer.seek(0)
    if m2 == "b":
        f = buffer
    else:
        f = TextIOWrapper(
            buffer, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
        )
    yield f
    if m1 != "r":
        f.seek(0)
        con.storeFile(share_name, path, buffer)


def samba_open(
    url, 
    mode="r", 
    buffering=-1, 
    encoding=None, 
    errors=None, 
    newline=None, 
):
    "用 Samba 打开一个分享链接，得到一个文件对象，你可以立即对其读写"
    urlp = urlsplit(url)
    scheme = urlp.scheme
    if scheme != "smb":
        raise ValueError("Not a samba link")
    hostname = urlp.hostname or "127.0.0.1"
    port     = int(urlp.port or 139)
    username = urlp.username
    password = urlp.password
    fullpath = urlp.path
    if not fullpath:
        raise OSError(fullpath)
    share_name, _, path = fullpath[1:].partition("/")
    path = "/" + path
    return smb_open(
        open_samba(hostname, port, username, password), 
        share_name, 
        path, 
        mode=mode, 
        buffering=buffering, 
        encoding=encoding, 
        errors=errors, 
        newline=newline, 
    )

# TODO: 静态类型检查
# TODO: 函数和类的文档
# TODO: open_* 增加一个参数 listdir=False，当 url 指向的是文件夹，如果 listdir 为真，那么罗列其中的文件，否则报错 IsADirectoryError
# TODO: url 可以有参数，作为 open_* 的关键词参数
# TODO: 支持 nfs、s3、minio 等
# TODO: SMBFileSystem 支持路径中有 . 和 ..
# TODO: SMBFile 和 SMBFileSystem 参照 alist.py，再优化一下逻辑

