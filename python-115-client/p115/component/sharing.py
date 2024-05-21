#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Sharing"]

from collections.abc import Iterable, Iterator
from typing import Literal

from .client import check_response, P115Client


class P115Sharing:
    __slots__ = "client",

    def __init__(self, client: P115Client, /):
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
        return check_response(self.client.share_list({"limit": 1}))["count"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @check_response
    def add(
        self, 
        file_ids: int | str | Iterable[int | str], 
        /, 
        is_asc: Literal[0, 1] = 1, 
        order: str = "file_name", 
        ignore_warn: Literal[0, 1] = 1, 
    ) -> dict:
        if not isinstance(file_ids, (int, str)):
            file_ids = ",".join(map(str, file_ids))
            if not file_ids:
                raise ValueError("no `file_id` specified") 
        return self.client.share_send({
            "file_ids": file_ids, 
            "is_asc": is_asc, 
            "order": order, 
            "ignore_warn": ignore_warn, 
        })

    @check_response
    def clear(self, /) -> dict:
        return self.client.share_update({
            "share_code": ",".join(item["share_code"] for item in self), 
            "action": "cancel", 
        })

    def get(
        self, 
        code_or_id: int | str, 
        /, 
        default=None, 
    ):
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
        if limit <= 0:
            return list(self.iter(offset))
        return check_response(self.client.share_list({"offset": offset, "limit": limit}))["list"]

    @check_response
    def remove(
        self, 
        code_or_id_s: int | str | Iterable[int | str], 
        /, 
    ) -> dict:
        def share_code_of(code_or_id: int | str) -> str:
            if isinstance(code_or_id, str):
                return code_or_id
            return self[code_or_id]["share_code"]
        if isinstance(code_or_id_s, (int, str)):
            share_code = share_code_of(code_or_id_s)
        else:
            share_code = ",".join(map(share_code_of, code_or_id_s))
            if not share_code:
                raise ValueError("no `share_code` or `snap_id` specified")
        return self.client.share_update({
            "share_code": share_code, 
            "action": "cancel", 
        })

    @check_response
    def update(
        self, 
        /, 
        share_code: str, 
        **payload, 
    ) -> dict:
        return self.client.share_update({"share_code": share_code, **payload})

