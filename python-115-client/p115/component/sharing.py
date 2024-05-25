#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Sharing"]

from collections.abc import Iterable, Iterator
from typing import Literal

from .client import check_response, P115Client
from .fs import P115Path


class P115Sharing:
    "自己的分享列表"
    __slots__ = "client",

    def __init__(self, client: str | P115Client, /):
        if isinstance(client, str):
            client = P115Client(client)
        self.client = client

    def __contains__(self, code_or_id: int | str, /) -> bool:
        if isinstance(code_or_id, str):
            return self.client.share_info(code_or_id)["state"]
        snap_id = str(code_or_id)
        return any(item["snap_id"] == snap_id for item in self)

    def __delitem__(self, code_or_id: int | str, /):
        return self.remove(code_or_id)

    def __getitem__(self, code_or_id: int | str, /) -> dict:
        if isinstance(code_or_id, str):
            resp = self.client.share_info(code_or_id)
            if resp["state"]:
                return resp["data"]
            raise LookupError(f"no such share_code: {code_or_id!r}, with message: {resp!r}")
        snap_id = str(code_or_id)
        for item in self:
            if item["snap_id"] == snap_id:
                return item
        raise LookupError(f"no such snap_id: {snap_id!r}")

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "计算共有多少个分享"
        return check_response(self.client.share_list({"limit": 1}))["count"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @property
    def receive_path(self, /) -> P115Path:
        return self.client.fs.as_path("我的接收")

    @check_response
    def add(
        self, 
        file_ids: int | str | Iterable[int | str], 
        /, 
        is_asc: Literal[0, 1] = 1, 
        order: str = "file_name", 
    ) -> dict:
        """创建分享链接
        :param file_ids: 文件列表，有多个时用逗号 "," 隔开或者传入可迭代器
        :param is_asc: 是否升序排列
        :param order: 用某字段排序：
            - 文件名："file_name"
            - 文件大小："file_size"
            - 文件种类："file_type"
            - 修改时间："user_utime"
            - 创建时间："user_ptime"
            - 上次打开时间："user_otime"
        """
        if not isinstance(file_ids, (int, str)):
            file_ids = ",".join(map(str, file_ids))
            if not file_ids:
                raise ValueError("no `file_id` specified") 
        return self.client.share_send({
            "file_ids": file_ids, 
            "is_asc": is_asc, 
            "order": order, 
        })

    @check_response
    def clear(self, /) -> dict:
        "清空分享列表"
        return self.client.share_update({
            "share_code": ",".join(item["share_code"] for item in self), 
            "action": "cancel", 
        })

    def code_of(self, code_or_id: int | str, /) -> str:
        "获取 id 对应的分享码"
        if isinstance(code_or_id, str):
            return code_or_id
        return self[code_or_id]["share_code"]

    def get(
        self, 
        code_or_id: int | str, 
        /, 
        default=None, 
    ):
        "用分享码或 id 查询分享信息"
        if isinstance(code_or_id, str):
            resp = self.client.share_info(code_or_id)
            if resp["state"]:
                return resp["data"]
            return default
        snap_id = str(code_or_id)
        return next((item for item in self if item["snap_id"] == snap_id), default)

    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 1 << 10, 
    ) -> Iterator[dict]:
        "迭代获取分享信息"
        if offset < 0:
            offset = 0
        if page_size <= 0:
            page_size = 1 << 10
        payload = {"offset": offset, "limit": page_size}
        count = 0
        while True:
            resp = check_response(self.client.share_list(payload))
            if count == 0:
                count = resp["count"]
            elif count != resp["count"]:
                raise RuntimeError("detected count changes during iteration")
            yield from resp["list"]
            if len(resp["list"]) < page_size:
                break
            payload["offset"] += page_size

    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
    ) -> list[dict]:
        "获取分享信息列表"
        if limit <= 0:
            return list(self.iter(offset))
        return check_response(self.client.share_list({"offset": offset, "limit": limit}))["list"]

    @check_response
    def remove(
        self, 
        code_or_id_s: int | str | Iterable[int | str], 
        /, 
    ) -> dict:
        "用分享码或 id 查询并删除分享"
        if isinstance(code_or_id_s, (int, str)):
            share_code = self.code_of(code_or_id_s)
        else:
            share_code = ",".join(map(self.code_of, code_or_id_s))
            if not share_code:
                raise ValueError("no `share_code` or `snap_id` specified")
        return self.client.share_update({
            "share_code": share_code, 
            "action": "cancel", 
        })

    @check_response
    def update(
        self, 
        code_or_id: int | str, 
        /, 
        **payload, 
    ) -> dict:
        """用分享码或 id 查询并更新分享信息
        payload:
            - receive_code: str = <default>         # 访问密码（口令）
            - share_duration: int = <default>       # 分享天数: 1(1天), 7(7天), -1(长期)
            - is_custom_code: 0 | 1 = <default>     # 用户自定义口令（不用管）
            - auto_fill_recvcode: 0 | 1 = <default> # 分享链接自动填充口令（不用管）
            - share_channel: int = <default>        # 分享渠道代码（不用管）
            - action: str = <default>               # 操作: 取消分享 "cancel"
        """
        payload["share_code"] = self.code_of(code_or_id)
        return self.client.share_update(payload)

