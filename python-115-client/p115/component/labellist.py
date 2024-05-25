#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115LabelList"]

from collections.abc import Iterator
from typing import Literal

from .client import check_response, P115Client
from .fs import P115Path


class P115LabelList:
    "标签列表"
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
        self.remove(id_or_name)

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
        self.edit(id_or_name, value)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "计算共有多少个标签"
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
        """添加（若干个）标签
        标签的格式是 "{label_name}" 或 "{label_name}\x07{color}"，例如 "tag\x07#FF0000"
        """
        return check_response(self.client.label_add(*labels))["data"]

    def clear(self, /):
        "清空标签列表"
        self.client.label_del(",".join(item["id"] for item in self.iter()))

    def edit(self, id_or_name: int | str, value: str | dict, /) -> dict:
        """用名称或 id 查询并编辑标签
        如果 value 是 str，则视为修改标签的名称，否则视为 payload
        payload:
            - name: str = <default>  # 标签名
            - color: str = <default> # 标签颜色，支持 css 颜色语法
            - sort: int = <default>  # 序号
        """
        id = self.id_of(id_or_name)
        if isinstance(value, str):
            payload = {"id": id, "name": value}
        else:
            payload = {**value, "id": id}
        return self.client.label_edit(payload)

    def get(self, id_or_name: int | str, /, default=None):
        "用名称或 id 查询标签信息"
        try:
            return self[id_or_name]
        except LookupError:
            return default

    def id_of(self, id_or_name: int | str, /) -> int:
        "获取名称对应的 id"
        if isinstance(id_or_name, int):
            return id_or_name
        return self[id_or_name]["id"]

    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 11500, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
    ) -> Iterator[dict]:
        """迭代获取标签信息
        :param offset: 索引偏移，从 0 开始
        :param page_size: 一页大小
        :param keyword: 搜索关键词
        :param sort: 排序字段:
            - 名称: "name"
            - 创建时间: "create_time"
            - 更新时间: "update_time"
        :param order: 排序顺序："asc"(升序), "desc"(降序)
        """
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
        **search_kwargs, 
    ) -> Iterator[P115Path]:
        """用名字或 id 搜索打上此标签的文件，返回迭代器
        search_kwargs:
            - aid: int | str = 1
            - asc: 0 | 1 = <default> # 是否升序排列
            - cid: int | str = 0 # 文件夹 id
            - count_folders: 0 | 1 = <default>
            - date: str = <default> # 筛选日期
            - fc_mix: 0 | 1 = <default> # 是否文件夹置顶，0 为置顶
            - format: str = "json" # 输出格式（不用管）
            - limit: int = 32 # 一页大小，意思就是 page_size
            - o: str = <default>
                # 用某字段排序：
                # - 文件名："file_name"
                # - 文件大小："file_size"
                # - 文件种类："file_type"
                # - 修改时间："user_utime"
                # - 创建时间："user_ptime"
                # - 上次打开时间："user_otime"
            - offset: int = 0  # 索引偏移，索引从 0 开始计算
            - pick_code: str = <default>
            - search_value: str = <default>
            - show_dir: 0 | 1 = 1
            - source: str = <default>
            - star: 0 | 1 = <default>
            - suffix: str = <default>
            - type: int | str = <default>
                # 文件类型：
                # - 所有: 0
                # - 文档: 1
                # - 图片: 2
                # - 音频: 3
                # - 视频: 4
                # - 压缩包: 5
                # - 应用: 6
                # - 书籍: 7
        """
        search_kwargs["file_label"] = self.id_of(id_or_name)
        search_kwargs.setdefault("cid", 0)
        return self.client.fs.search(**search_kwargs)

    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
    ) -> list[dict]:
        """获取标签信息列表
        :param offset: 索引偏移，从 0 开始
        :param limit: 返回数据条数，如果小于等于 0，则不限
        :param keyword: 搜索关键词
        :param sort: 排序字段:
            - 名称: "name"
            - 创建时间: "create_time"
            - 更新时间: "update_time"
        :param order: 排序顺序："asc"(升序), "desc"(降序)
        """
        if limit <= 0:
            return list(self.iter(
                offset, 
                keyword=keyword, 
                sort=sort, 
                order=order, 
            ))
        return check_response(self.client.label_list({
            "offset": offset, 
            "limit": limit, 
            "keyword": keyword, 
            "sort": sort, 
            "order": order, 
        }))["data"]["list"]

    def remove(self, id_or_name: int | str, /) -> dict:
        """用名字或 id 查询并删除标签"
        """
        return check_response(self.client.label_del(self.id_of(id_or_name)))

