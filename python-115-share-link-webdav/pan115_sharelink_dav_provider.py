#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["Pan115ShareLinkFilesystemProvider"]

from hashlib import md5
from http.cookiejar import CookieJar
from posixpath import join as joinpath, normpath

from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider
from yaml import load as yaml_load, Loader as yaml_Loader

from pan115 import HTTPFileReader, Pan115Client, Pan115ShareLinkFileSystem


class FileResource(DAVNonCollection):

    def __init__(self, path: str, environ: dict, share_link_fs, filepath):
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
        share_link_fs = self.share_link_fs
        downurl = share_link_fs.get_download_url(self.filepath)
        return HTTPFileReader(downurl, share_link_fs.client.request)

    def is_link(self, /):
        return False


class FolderResource(DAVCollection):

    def __init__(self, path: str, environ: dict, share_link_fs, filepath):
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

    def get_member_names(self):
        return self.share_link_fs.listdir(self.filepath)

    def get_member(self, name: str) -> FileResource:
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

    def __init__(self, path: str, environ: dict, share_link_fs):
        super().__init__(path, environ)
        self.share_link_fs = share_link_fs

    def get_member_names(self):
        share_link_fs = self.share_link_fs
        if type(share_link_fs) is dict:
            return list(share_link_fs)
        return share_link_fs.listdir("/")

    def get_member(self, name: str) -> FileResource:
        share_link_fs = self.share_link_fs
        path = joinpath(self.path, name)
        if type(share_link_fs) is dict:
            if name not in share_link_fs:
                return None
            return RootResource(path, self.environ, share_link_fs[name])
        filepath = "/" + name
        if share_link_fs.isdir(filepath):
            return FolderResource(path, self.environ, share_link_fs, filepath)
        else:
            return FileResource(path, self.environ, share_link_fs, filepath)

    def is_link(self, /):
        return False


class Pan115ShareLinkFilesystemProvider(DAVProvider):

    def __init__(self, share_link_fs):
        super().__init__()
        self.share_link_fs = share_link_fs

    @staticmethod
    def make_share_link_fs(client, config):
        if isinstance(config, str):
            return Pan115ShareLinkFileSystem(client, config)
        else:
            return {
                name.replace("/", "｜"): (
                    Pan115ShareLinkFileSystem(client, conf)
                    if isinstance(config, str) else
                    __class__.make_share_link_fs(client, conf)
                )
                for name, conf in config.items()
            }

    @classmethod
    def from_config(cls, cookie_or_client, config_text, /):
        if isinstance(cookie_or_client, Pan115Client):
            client = cookie_or_client
        else:
            client = Pan115Client(cookie_or_client)
        config = yaml_load(config_text, Loader=yaml_Loader)
        return cls(cls.make_share_link_fs(client, config))

    def get_resource_inst(self, path: str, environ: dict) -> FileResource:
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
        filepath = "/" + filepath
        if not share_link_fs.exists(filepath):
            return None
        if share_link_fs.isdir(filepath):
            return FolderResource(path, environ, share_link_fs, filepath)
        return FileResource(path, environ, share_link_fs, filepath)

