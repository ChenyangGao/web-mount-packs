#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Offline"]

from asyncio import run
from collections.abc import Callable, Iterable, Iterator
from hashlib import sha1
from time import time
from types import MappingProxyType

from magnet2torrent import Magnet2Torrent # type: ignore

from .client import check_response, P115Client


class P115Offline:
    __slots__ = ("client", "_sign_time")

    client: P115Client
    _sign_time: MappingProxyType

    def __init__(self, /, client: str | P115Client):
        if isinstance(client, str):
            client = P115Client(client)
        self.client = client

    def __contains__(self, hash: str, /) -> bool:
        return any(item["info_hash"] == hash for item in self)

    def __delitem__(self, hash: str, /):
        return self.remove(hash)

    def __getitem__(self, hash: str, /) -> dict:
        for item in self:
            if item["info_hash"] == hash:
                return item
        raise LookupError(f"no such hash: {hash!r}")

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        return check_response(self.client.offline_list())["count"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @property
    def sign_time(self, /) -> MappingProxyType:
        try:
            sign_time = self._sign_time
            if time() - sign_time["time"] < 30 * 60:
                return sign_time
        except AttributeError:
            pass
        info = check_response(self.client.offline_info())
        sign_time = self._sign_time = MappingProxyType({"sign": info["sign"], "time": info["time"]})
        return sign_time

    def add(
        self, 
        urls: str | Iterable[str], 
        /, 
        pid: None | int = None, 
        savepath: None | str = None, 
    ) -> dict:
        payload: dict
        if isinstance(urls, str):
            payload = {"url": urls}
            method = self.client.offline_add_url
        else:
            payload = {f"url[{i}]": url for i, url in enumerate(urls)}
            if not payload:
                raise ValueError("no `url` specified")
            method = self.client.offline_add_urls
        payload.update(self.sign_time)
        if pid is not None:
            payload["wp_path_id"] = pid
        if savepath:
            payload["savepath"] = savepath
        return check_response(method(payload))

    def add_torrent(
        self, 
        torrent_or_magnet_or_sha1_or_fid: int | bytes | str, 
        /, 
        pid: None | int = None, 
        savepath: None | str = None, 
        predicate: None | str | Callable[[dict], bool] = None, 
    ) -> dict:
        resp = check_response(self.torrent_info(torrent_or_magnet_or_sha1_or_fid))
        if predicate is None:
            wanted = ",".join(
                str(i) for i, info in enumerate(resp["torrent_filelist_web"])
                if info["wanted"]
            )
        elif isinstance(predicate, str):
            wanted = predicate
        else:
            wanted = ",".join(
                str(i) for i, info in enumerate(resp["torrent_filelist_web"]) 
                if predicate(info)
            )
        payload = {
            "info_hash": resp["info_hash"], 
            "wanted": wanted, 
            "savepath": resp["torrent_name"] if savepath is None else savepath, 
        }
        if pid is not None:
            payload["wp_path_id"] = pid
        payload.update(self.sign_time)
        return check_response(self.client.offline_add_torrent(payload))

    # TOOD: 使用 enum
    def clear(self, /, flag: int = 1) -> dict:
        """清空离线任务列表

        :param flag: 操作目标
            - 0: 已完成
            - 1: 全部（默认值）
            - 2: 已失败
            - 3: 进行中
            - 4: 已完成+删除源文件
            - 5: 全部+删除源文件
        """
        return check_response(self.client.offline_clear(flag))

    def get(self, hash: str, /, default=None):
        return next((item for item in self if item["info_hash"] == hash), default)

    def iter(self, /, start_page: int = 1) -> Iterator[dict]:
        if start_page < 1:
            page = 1
        else:
            page = start_page
        resp = check_response(self.client.offline_list(page))
        if not resp["tasks"]:
            return
        yield from resp["tasks"]
        page_count = resp["page_count"]
        if page_count <= page:
            return
        count = resp["count"]
        for page in range(page + 1, page_count + 1):
            resp = check_response(self.client.offline_list(page))
            if count != resp["count"]:
                raise RuntimeError("detected count changes during iteration")
            if not resp["tasks"]:
                return
            yield from resp["tasks"]

    def list(self, /, page: int = 0) -> list[dict]:
        if page <= 0:
            return list(self.iter())
        return check_response(self.client.offline_list(page))["tasks"]

    def remove(
        self, 
        hashes: str | Iterable[str], 
        /, 
        remove_files: bool = False, 
    ) -> dict:
        if isinstance(hashes, str):
            payload = {"hash[0]": hashes}
        else:
            payload = {f"hash[{i}]": h for i, h in enumerate(hashes)}
            if not payload:
                raise ValueError("no `hash` specified")
        if remove_files:
            payload["flag"] = "1"
        payload.update(self.sign_time)
        return check_response(self.client.offline_remove(payload))

    def torrent_info(self, torrent_or_magnet_or_sha1_or_fid: int | bytes | str, /) -> dict:
        torrent = None
        if isinstance(torrent_or_magnet_or_sha1_or_fid, int):
            fid = torrent_or_magnet_or_sha1_or_fid
            resp = check_response(self.client.fs_file(fid))
            sha = resp["data"][0]["sha1"]
        elif isinstance(torrent_or_magnet_or_sha1_or_fid, bytes):
            torrent = torrent_or_magnet_or_sha1_or_fid
        elif torrent_or_magnet_or_sha1_or_fid.startswith("magnet:?xt=urn:btih:"):
            m2t = Magnet2Torrent(torrent_or_magnet_or_sha1_or_fid)
            torrent = run(m2t.retrieve_torrent())[1]
        else:
            sha = torrent_or_magnet_or_sha1_or_fid
        if torrent is None:
            resp = check_response(self.client.offline_torrent_info(sha))
        else:
            sha = sha1(torrent).hexdigest()
            try:
                resp = check_response(self.client.offline_torrent_info(sha))
            except:
                name = f"{sha}.torrent"
                check_response(self.client.upload_file_sample(torrent, name, 0))
                resp = check_response(self.client.offline_torrent_info(sha))
        resp["sha1"] = sha
        return resp

