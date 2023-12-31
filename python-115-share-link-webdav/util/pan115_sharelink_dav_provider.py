#!/usr/bin/env python
# coding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["Pan115ShareLinkFilesystemProvider"]

from hashlib import md5
from posixpath import join as joinpath, normpath
from weakref import WeakValueDictionary

import wsgidav.wsgidav_app # type: ignore # It must be imported first!!!
from wsgidav.dav_error import HTTP_FORBIDDEN, DAVError # type: ignore
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider # type: ignore
from wsgidav.util import get_module_logger # type: ignore
from yaml import load as yaml_load, Loader as yaml_Loader # NEED: pip install types-PyYAML

from .pan115 import BadRequest, LoginError, Pan115Client, Pan115ShareLinkFileSystem


_logger = get_module_logger(__name__)


class FileResource(DAVNonCollection):

    def __init__(
        self, /, 
        path: str, 
        environ: dict, 
        share_link_fs, 
        filepath: str, 
    ):
        super().__init__(path, environ)
        self.share_link_fs = share_link_fs
        self.filepath = filepath
        self.attr = attr = share_link_fs.attr(filepath)
        self.name = attr["name"]
        self.size = attr["size"]
        self.time = int(attr["time"].timestamp())

    def get_content_length(self):
        return self.size

    def get_creation_date(self):
        return self.time

    def get_display_name(self):
        return self.name

    def get_etag(self):
        return "%s-%s-%s" % (
            md5(bytes(self.filepath, "utf-8")).hexdigest(), 
            self.time, 
            self.size, 
        )

    def get_last_modified(self):
        return self.time

    def support_etag(self):
        return True

    def support_ranges(self):
        return True

    def get_content(self):
        return self.share_link_fs.open(self.filepath, "rb")

    def is_link(self, /):
        return False


class FolderResource(DAVCollection):

    def __init__(
        self, 
        /, 
        path: str, 
        environ: dict, 
        share_link_fs, 
        filepath: str, 
    ):
        super().__init__(path, environ)
        self.share_link_fs = share_link_fs
        self.filepath = filepath
        self.attr = attr = share_link_fs.attr(filepath)
        self.name = attr["name"]
        self.time = int(attr["time"].timestamp())

    def get_creation_date(self):
        return self.time

    def get_display_name(self):
        return self.name

    def get_directory_info(self):
        return None

    def get_etag(self):
        return None

    def get_last_modified(self):
        return self.time

    def get_member_names(self) -> list[str]:
        return self.share_link_fs.listdir(self.filepath)

    def get_member(self, name: str) -> FileResource | FolderResource:
        share_link_fs = self.share_link_fs
        filepath = joinpath(self.filepath, name)
        path = joinpath(self.path, name)
        if share_link_fs.isdir(filepath):
            return FolderResource(path, self.environ, share_link_fs, filepath)
        else:
            return FileResource(path, self.environ, share_link_fs, filepath)

    def is_link(self, /):
        return False


class RootResource(DAVCollection):

    def __init__(
        self, 
        /, 
        path: str, 
        environ: dict, 
        share_link_fs, 
    ):
        super().__init__(path, environ)
        self.share_link_fs = share_link_fs
        self.time = None
        if isinstance(share_link_fs, Pan115ShareLinkFileSystem):
            shareinfo = share_link_fs.__dict__.get("shareinfo")
            if shareinfo:
                self.time = int(shareinfo["create_time"])

    def get_creation_date(self):
        return self.time

    def get_last_modified(self):
        return self.time

    def get_member_names(self):
        share_link_fs = self.share_link_fs
        if type(share_link_fs) is dict:
            return list(share_link_fs)
        if share_link_fs is None:
            _logger.warn(f"{self.path!r} :: the corresponding link is not available")
            return []
        try:
            share_link_fs.shareinfo
        except BadRequest as e:
            _logger.error(f"{self.path!r} :: {type(e).__qualname__}: {e}")
            raise DAVError(HTTP_FORBIDDEN, e)
        return share_link_fs.listdir("/")

    def get_member(
        self, 
        /, 
        name: str, 
    ) -> None | RootResource | FileResource | FolderResource:
        share_link_fs = self.share_link_fs
        path = joinpath(self.path, name)
        if type(share_link_fs) is dict:
            if name not in share_link_fs:
                return None
            return RootResource(path, self.environ, share_link_fs[name])
        if share_link_fs is None:
            _logger.warn(f"{self.path!r} :: the corresponding link is not available")
            return None
        try:
            share_link_fs.shareinfo
        except BadRequest as e:
            _logger.error(f"{self.path!r} :: {type(e).__qualname__}: {e}")
            raise DAVError(HTTP_FORBIDDEN, e)
        filepath = "/" + name
        if share_link_fs.isdir(filepath):
            return FolderResource(path, self.environ, share_link_fs, filepath)
        else:
            return FileResource(path, self.environ, share_link_fs, filepath)

    def is_link(self, /):
        return False


class Pan115ShareLinkFilesystemProvider(DAVProvider):

    def __init__(self, /, share_link_fs):
        super().__init__()
        self.share_link_fs = share_link_fs

    @classmethod
    def from_config(cls, cookie_or_client, config_text: bytes | str, /):
        def make_share_link_fs(client: Pan115Client, config):
            if isinstance(config, str):
                try:
                    return Pan115ShareLinkFileSystem(client, config)
                except Exception as e:
                    _logger.error(f"{type(e).__qualname__}: {e}")
                    return None
            else:
                return {
                    name.replace("/", "｜"): make_share_link_fs(client, conf)
                    for name, conf in config.items()
                }
        if isinstance(cookie_or_client, Pan115Client):
            client = cookie_or_client
        else:
            client = Pan115Client(cookie_or_client)
        config = yaml_load(config_text, Loader=yaml_Loader)
        return cls(make_share_link_fs(client, config))

    @classmethod
    def from_config_file(cls, cookie_path, config_path, wsgidav_config_path=None, /, watch: bool = False):
        cookie_text = open(cookie_path, "r", encoding="latin-1").read()
        config_text = open(config_path, "rb", buffering=0).read()

        if not watch:
            return cls.from_config(cookie_text, config_text)

        from .watch_links import WatchMultiFileEventHandler

        link_to_inst: WeakValueDictionary[str, Pan115ShareLinkFileSystem] = WeakValueDictionary()

        def make_share_link_fs(config):
            if isinstance(config, str):
                if config in link_to_inst:
                    inst = link_to_inst[config]
                else:
                    try:
                        inst = link_to_inst[config] = Pan115ShareLinkFileSystem(client, config)
                    except Exception as e:
                        _logger.error(f"{type(e).__qualname__}: {e}")
                        return None
                return inst
            else:
                return {
                    name.replace("/", "｜"): make_share_link_fs(conf)
                    for name, conf in config.items() if conf
                }

        def handle_update_cookie():
            nonlocal client
            try:
                cookie_text = open(cookie_path, "rb", buffering=0).read().decode("latin-1")
                # if currently unreadable or empty file
                if not cookie_text:
                    return
                if client.cookie == cookie_text.strip():
                    return
                client_new = Pan115Client(cookie_text, try_login=False)
            except Exception as e:
                _logger.error(f"{type(e).__qualname__}: {e}")
                return
            client = client_new
            for inst in tuple(link_to_inst.values()):
                inst.client = client_new

        def handle_update_config():
            try:
                config_text = open(config_path, "rb", buffering=0).read()
                # if currently unreadable or empty file
                if not config_text:
                    return
                config = yaml_load(config_text, Loader=yaml_Loader)
            except Exception as e:
                _logger.error(f"{type(e).__qualname__}: {e}")
                return
            # if empty config
            if config is None:
                return
            if config:
                new_share_link_fs = make_share_link_fs(config)
                instance.share_link_fs = new_share_link_fs
            else:
                instance.share_link_fs = {}

        def handle_wsgidav_config_update():
            try:
                # if currently unreadable or empty file
                if not open(wsgidav_config_path, "rb", buffering=0).read(1):
                    return
            except FileNotFoundError:
                pass
            except Exception:
                _logger.error(f"{type(e).__qualname__}: {e}")
                return
            from os import execl
            from sys import executable, argv
            execl(executable, executable, *argv)

        client = Pan115Client(cookie_text)
        config = yaml_load(config_text, Loader=yaml_Loader)
        instance = cls(make_share_link_fs(config))

        handles = {
            cookie_path: handle_update_cookie, 
            config_path: handle_update_config, 
        }
        if wsgidav_config_path is not None:
            handles[wsgidav_config_path] = handle_wsgidav_config_update
        WatchMultiFileEventHandler.start(handles)

        return instance

    def get_resource_inst(
        self, 
        /, 
        path: str, 
        environ: dict, 
    ) -> None | RootResource | FolderResource | FileResource:
        filepath = normpath(path).strip("/")
        path = "/" + filepath
        share_link_fs = self.share_link_fs
        if path == "/":
            return RootResource(path, environ, share_link_fs)
        while type(share_link_fs) is dict:
            name, sep, filepath = filepath.partition("/")
            if name not in share_link_fs:
                return None
            share_link_fs = share_link_fs[name]
            if not sep:
                return RootResource(path, environ, share_link_fs)
        if share_link_fs is None:
            _logger.warn(f"{path!r} :: the corresponding link is not available")
            return None
        try:
            share_link_fs.shareinfo
        except BadRequest as e:
            _logger.error(f"{path!r} :: {type(e).__qualname__}: {e}")
            raise DAVError(HTTP_FORBIDDEN, e)
        filepath = "/" + filepath
        if not share_link_fs.exists(filepath):
            return None
        if share_link_fs.isdir(filepath):
            return FolderResource(path, environ, share_link_fs, filepath)
        return FileResource(path, environ, share_link_fs, filepath)

