#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115LabelList"]

from collections.abc import Iterator
from typing import Literal

from .client import check_response, P115Client
from .fs import P115Path


class P115LabelList:
    __slots__ = "client",

    def __init__(self, client: str | P115Client, /):
        if isinstance(client, str):
            client = P115Client(client)
        self.client = client

    def __contains__(self, id_or_name: int | str, /) -> bool:
        if isinstance(id_or_name, int):
            return self.client.label_edit({"id": id_or_name})["code"] != 21005
        else:
            name = id_or_name
            return any(item["name"] == name for item in self.iter(keyword=name))

    def __delitem__(self, id_or_name: int | str, /):
        if isinstance(id_or_name, int):
            id = id_or_name
        else:
            try:
                item = self[id_or_name]
            except LookupError:
                return
            id = item["id"]
        self.client.label_del(id)

    def __getitem__(self, id_or_name: int | str, /) -> dict:
        if isinstance(id_or_name, int):
            id = str(id_or_name)
            for item in self.iter():
                if item["id"] == id:
                    return item
        else:
            name = id_or_name
            for item in self.iter(keyword=name):
                if item["name"] == name:
                    return item
        raise LookupError(f"no such id: {id!r}")

    def __setitem__(self, id_or_name: int | str, value: str | dict, /):
        if isinstance(id_or_name, int):
            id = id_or_name
        else:
            item = self[id_or_name]
            id = item["id"]
        if isinstance(value, str):
            payload = {"id": id, "name": value}
        else:
            payload = {**value, "id": id}
        self.client.label_edit(payload)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        return check_response(self.client.label_list({"limit": 1}))["data"]["total"]

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    def add(
        self, 
        /, 
        *labels: str, 
    ) -> list[dict]:
        return check_response(self.client.label_add(*labels))["data"]

    def clear(self, /):
        self.client.label_del(",".join(item["id"] for item in self.iter()))

    def get(self, id_or_name: int | str, /, default=None):
        try:
            return self[id_or_name]
        except LookupError:
            return default

    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 11500, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
    ) -> Iterator[dict]:
        if offset < 0:
            offset = 0
        if page_size <= 0:
            page_size = 11500
        payload = {
            "offset": offset, 
            "limit": page_size, 
            "keyword": keyword, 
            "sort": sort, 
            "order": order, 
        }
        count = 0
        while True:
            resp = check_response(self.client.label_list(payload))
            total = resp["data"]["total"]
            if count == 0:
                count = total
            elif count != total:
                raise RuntimeError("detected count changes during iteration")
            ls = resp["data"]["list"]
            yield from ls
            if len(ls) < page_size:
                break
            payload["offset"] += page_size # type: ignore

    def iter_files(
        self, 
        id_or_name: int | str, 
        /, 
    ) -> Iterator[P115Path]:
        if isinstance(id_or_name, int):
            id = id_or_name
        else:
            id = self[id_or_name]["id"]
        return self.client.fs.search(0, file_label=id)

    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
    ) -> list[dict]:
        if limit <= 0:
            return list(self.iter(offset, keyword=keyword, sort=sort, order=order))
        return check_response(self.client.label_list({
            "offset": offset, 
            "limit": limit, 
            "keyword": keyword, 
            "sort": sort, 
            "order": order, 
        }))["data"]["list"]

    edit = __setitem__
    remove = __delitem__

