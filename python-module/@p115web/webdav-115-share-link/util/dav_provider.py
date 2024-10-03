#!/usr/bin/env python
# coding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115ShareFilesystemProvider"]

from functools import cached_property
from hashlib import md5
from posixpath import join as joinpath, normpath
from weakref import WeakValueDictionary

from p115 import P115Client, P115ShareFileSystem, P115SharePath
import wsgidav.wsgidav_app # type: ignore # It must be imported first!!!
from wsgidav.dav_error import DAVError # type: ignore
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider # type: ignore
from yaml import load as yaml_load, Loader as yaml_Loader


class DavPathBase:

    def __getattr__(self, attr, /):
        try:
            return self.attr[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    @cached_property
    def creationdate(self, /) -> float:
        return self.time

    @cached_property
    def name(self, /) -> str:
        return self.attr["name"]

    @cached_property
    def time(self, /) -> float:
        return self.attr["time"].timestamp()

    def get_creation_date(self, /) -> float:
        return self.time

    def get_display_name(self, /) -> str:
        return self.name

    def get_last_modified(self, /) -> float:
        return self.time

    def is_link(self, /) -> bool:
        return False

    def support_modified(self, /) -> bool:
        return True


class FileResource(DavPathBase, DAVNonCollection):

    def __init__(
        self, 
        /, 
        path: str, 
        environ: dict, 
        attr: P115SharePath, 
    ):
        super().__init__(path, environ)
        self.attr = attr

    @cached_property
    def size(self, /) -> int:
        return self.attr["size"]

    @property
    def url(self, /) -> str:
        return str(self.attr.get_url())

    def get_etag(self, /) -> str:
        return "%s-%s-%s" % (
            md5(bytes(self.path, "utf-8")).hexdigest(), 
            self.time, 
            self.size, 
        )

    def get_content(self, /):
        raise DAVError(302, add_headers=[("Location", str(self.url))])

    def get_content_length(self):
        return self.size

    def get_property_value(self, /, name: str):
        if name == "{DAV:}iscollection":
            return False
        return super().get_property_value(name) 

    def support_content_length(self, /) -> bool:
        return True

    def support_etag(self):
        return True

    def support_ranges(self):
        return True


class FolderResource(DavPathBase, DAVCollection):

    def __init__(
        self, 
        /, 
        path: str, 
        environ: dict, 
        attr: P115SharePath, 
    ):
        super().__init__(path, environ)
        self.attr = attr

    @cached_property
    def children(self, /) -> dict[str, P115SharePath]:
        return {attr["name"]: attr for attr in self.attr.listdir_path()}

    def get_etag(self, /) -> str:
        return "%s-%s-%s" % (
            md5(bytes(self.path, "utf-8")).hexdigest(), 
            self.time, 
            0, 
        )

    def get_member(self, name: str) -> FileResource | FolderResource:
        if not (attr := self.children.get(name)):
            raise DAVError(404, self.path + "/" + name)
        path = joinpath(self.path, name)
        if attr.is_dir():
            return FolderResource(path, self.environ, attr)
        else:
            return FileResource(path, self.environ, attr)

    def get_member_list(self, /) -> list[FileResource | FolderResource]:
        path = self.path
        environ = self.environ
        return [
                FolderResource(joinpath(path, attr["name"]), environ, attr) 
            if attr.is_dir() else 
                FileResource(joinpath(path, attr["name"]), environ, attr)
            for attr in self.children.values()
        ]

    def get_member_names(self, /) -> list[str]:
        return list(self.children)

    def get_property_value(self, /, name: str):
        if name == "{DAV:}getcontentlength":
            return 0
        elif name == "{DAV:}iscollection":
            return True
        return super().get_property_value(name)

    def support_etag(self):
        return True


class RootResource(DavPathBase, DAVCollection):

    def __init__(
        self, 
        /, 
        path: str, 
        environ: dict, 
        fs, 
    ):
        super().__init__(path, environ)
        self.fs = fs
        self.time = 0
        if isinstance(fs, P115ShareFileSystem):
            self.time = int(fs.shareinfo["create_time"])

    def get_member(
        self, 
        /, 
        name: str, 
    ) -> RootResource | FileResource | FolderResource:
        fs = self.fs
        path = joinpath(self.path, name)
        if isinstance(fs, dict):
            if name not in fs:
                raise DAVError(404, path)
            return RootResource(path, self.environ, fs[name])
        if fs is None:
            raise DAVError(404, path)
        try:
            fs.shareinfo
        except OSError as e:
            raise DAVError(410, e)
        try:
            attr = fs.as_path(name)
        except FileNotFoundError as e:
            raise DAVError(404, e)
        if attr.is_dir():
            return FolderResource(path, self.environ, attr)
        else:
            return FileResource(path, self.environ, attr)

    def get_member_list(self, /) -> list[FileResource | FolderResource]:
        return list(map(self.get_member, self.get_member_names()))

    def get_member_names(self, /) -> list[str]:
        fs = self.fs
        if type(fs) is dict:
            return list(fs)
        if fs is None:
            return []
        try:
            fs.shareinfo
        except OSError as e:
            raise DAVError(410, e)
        return fs.listdir()

    def get_property_value(self, /, name: str):
        if name == "{DAV:}getcontentlength":
            return 0
        elif name == "{DAV:}iscollection":
            return True
        return super().get_property_value(name)


class P115ShareFilesystemProvider(DAVProvider):

    def __init__(self, /, fs):
        super().__init__()
        self.fs = fs

    @classmethod
    def from_config(cls, cookies_or_client, config_text: bytes | str, /):
        def make_fs(client: P115Client, config):
            if isinstance(config, str):
                try:
                    return P115ShareFileSystem(client, config)
                except Exception as e:
                    return None
            else:
                return {
                    name.replace("/", "｜"): make_fs(client, conf)
                    for name, conf in config.items()
                }
        if isinstance(cookies_or_client, P115Client):
            client = cookies_or_client
        else:
            client = P115Client(cookies_or_client)
        config = yaml_load(config_text, Loader=yaml_Loader)
        return cls(make_fs(client, config))

    @classmethod
    def from_config_file(cls, cookies_path, config_path, wsgidav_config_path=None, /, watch: bool = False):
        cookies_text = open(cookies_path, "r", encoding="latin-1").read()
        config_text = open(config_path, "rb", buffering=0).read()

        if not watch:
            return cls.from_config(cookies_text, config_text)

        from .watch import WatchMultiFileEventHandler

        link_to_inst: WeakValueDictionary[str, P115ShareFileSystem] = WeakValueDictionary()
        client = P115Client(cookies_text)
        config = yaml_load(config_text, Loader=yaml_Loader)

        def make_fs(config):
            if isinstance(config, str):
                if config in link_to_inst:
                    inst = link_to_inst[config]
                else:
                    try:
                        inst = link_to_inst[config] = P115ShareFileSystem(client, config)
                    except Exception as e:
                        return None
                return inst
            else:
                return {
                    name.replace("/", "｜"): make_fs(conf)
                    for name, conf in config.items() if conf
                }

        def handle_update_cookies():
            nonlocal client
            try:
                cookies_text = open(cookies_path, "rb", buffering=0).read().decode("latin-1")
                # if currently unreadable or empty file
                if not cookies_text:
                    return
                if client.cookies == cookies_text.strip():
                    return
                client_new = P115Client(cookies_text, try_login=False)
            except Exception as e:
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
                return
            # if empty config
            if config is None:
                return
            if config:
                new_fs = make_fs(config)
                instance.fs = new_fs
            else:
                instance.fs = {}

        def handle_wsgidav_config_update():
            try:
                # if currently unreadable or empty file
                if not open(wsgidav_config_path, "rb", buffering=0).read(1):
                    return
            except FileNotFoundError:
                pass
            except Exception:
                return
            from os import execl
            from sys import executable, argv
            execl(executable, executable, *argv)

        instance = cls(make_fs(config))
        handles = {
            cookies_path: handle_update_cookies, 
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
    ) -> RootResource | FolderResource | FileResource:
        fs = self.fs
        filepath = normpath(path).strip("/")
        path = "/" + filepath
        if path == "/":
            return RootResource(path, environ, fs)
        while isinstance(fs, dict):
            name, sep, filepath = filepath.partition("/")
            if name not in fs:
                raise DAVError(404, path)
            fs = fs[name]
            if not sep:
                return RootResource(path, environ, fs)
        if fs is None:
            raise DAVError(404, path)
        try:
            fs.shareinfo
        except OSError as e:
            raise DAVError(410, e)
        try:
            attr = fs.as_path(filepath)
        except FileNotFoundError:
            raise DAVError(404, path)
        if attr.is_dir():
            return FolderResource(path, environ, attr)
        else:
            return FileResource(path, environ, attr)

    def is_readonly(self, /) -> bool:
        return True

