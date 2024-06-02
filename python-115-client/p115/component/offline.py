#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Offline", "P115OfflineClearEnum"]

from asyncio import run
from collections.abc import Callable, Iterable, Iterator
from enum import Enum
from hashlib import sha1
from time import time
from types import MappingProxyType
from typing import Self

from magnet2torrent import Magnet2Torrent # type: ignore

from .client import check_response, P115Client
from .fs import P115Path


class P115OfflineClearEnum(Enum):
    completed = 0
    all = 1
    failed = 2
    downloading = 3
    completed_and_files = 4
    failed_and_files = 5

    @classmethod
    def ensure(cls, val, /) -> Self:
        if isinstance(val, cls):
            return val
        try:
            if isinstance(val, str):
                return cls[val]
        except KeyError:
            pass
        return cls(val)


class P115Offline:
    "离线任务列表"
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

    def __getitem__(self, index_or_hash: str, /) -> dict:
        for item in self:
            if item["info_hash"] == hash:
                return item
        raise LookupError(f"no such hash: {hash!r}")

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "计算共有多少个离线任务"
        return check_response(self.client.offline_list())["count"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @property
    def download_paths_raw(self, /) -> list[dict]:
        "离线下载的目录列表"
        return check_response(self.client.offline_download_path())["data"]

    @property
    def download_paths(self, /) -> list[P115Path]:
        "离线下载的目录列表"
        as_path = self.client.fs.as_path
        return [as_path(int(attr["file_id"])) for attr in self.download_paths_raw]

    @property
    @check_response
    def info(self, /) -> dict:
        "获取关于离线的限制的信息"
        return self.client.offline_info()

    @property
    def quota_info(self, /) -> dict:
        "获取当前离线配额信息（简略）"
        return self.client.offline_quota_info()

    @property
    def quota_package_info(self, /) -> dict:
        "获取当前离线配额信息（详细）"
        return self.client.offline_quota_package_info()

    @property
    def sign_time(self, /) -> MappingProxyType:
        "签名和时间等信息"
        try:
            sign_time = self._sign_time
            if time() - sign_time["time"] < 30 * 60:
                return sign_time
        except AttributeError:
            pass
        info = self.info
        sign_time = self._sign_time = MappingProxyType({"sign": info["sign"], "time": info["time"]})
        return sign_time

    @property
    def torrent_path(self, /) -> P115Path:
        "添加 BT 种子任务的默认上传路径"
        client = self.client
        return client.fs.as_path(int(client.offline_upload_torrent_path()['cid']))

    def add(
        self, 
        urls: str | Iterable[str], 
        /, 
        pid: None | int = None, 
        savepath: None | str = None, 
    ) -> dict:
        "用（1 个或若干个）链接创建离线任务"
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
        "用 BT 种子创建离线任务"
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

    def clear(
        self, 
        /, 
        flag: int | str | P115OfflineClearEnum = P115OfflineClearEnum.all, 
    ) -> dict:
        """清空离线任务列表
        :param flag: 操作目标
            - 已完成: 0, 'completed', P115OfflineClearEnum.completed
            - 全部: 1, 'all', P115OfflineClearEnum.all # 默认值
            - 已失败: 2, 'failed', P115OfflineClearEnum.failed
            - 进行中: 3, 'downloading', P115OfflineClearEnum.downloading
            - 已完成+删除源文件: 4, 'completed_and_files', P115OfflineClearEnum.completed_and_files
            - 全部+删除源文件: 5, 'failed_and_files', P115OfflineClearEnum.failed_and_files
        """
        flag = P115OfflineClearEnum(flag)
        return check_response(self.client.offline_clear(flag.value))

    def get(self, hash: str, /, default=None):
        "用 infohash 查询离线任务"
        return next((item for item in self if item["info_hash"] == hash), default)

    def iter(self, /, start_page: int = 1) -> Iterator[dict]:
        """迭代获取离线任务
        :start_page: 开始页数，从 1 开始计数，迭代从这个页数开始，到最大页数结束
        """
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
        """获取离线任务列表
        :param page: 获取第 `page` 页的数据，从 1 开始计数，如果小于等于 0 则返回全部
        """
        if page <= 0:
            return list(self.iter())
        return check_response(self.client.offline_list(page))["tasks"]

    def remove(
        self, 
        hashes: str | Iterable[str], 
        /, 
        remove_files: bool = False, 
    ) -> dict:
        """用 infohash 查询并移除（1 个或若干个）离线任务
        :param hashes: （1 个或若干个）离线任务的 infohash
        :param remove_files: 移除任务时是否也删除已转存的文件
        """
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
        """获取种子的信息
        :param torrent_or_magnet_or_sha1_or_fid: BT 种子
            - bytes: 种子的二进制数据（如果种子从未被人上传过 115，就会先被上传）
            - str:
                - 磁力链接
                - 种子文件的 sha1，但要求这个种子曾被人上传到 115
            - int: 种子文件在你的网盘上的文件 id
        """
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

