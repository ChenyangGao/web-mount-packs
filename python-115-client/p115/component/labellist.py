#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115LabelList"]

from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from functools import partial
from typing import overload, Any, Literal

from asynctools import async_any, to_list
from iterutils import run_gen_step
from p115client import check_response
from undefined import undefined

from .client import P115Client
from .fs import P115Path


class P115LabelList:
    "标签列表"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | P115Client, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = P115Client(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, id_or_name: int | str, /) -> bool:
        return self.has(id_or_name)

    def __delitem__(self, id_or_name: int | str, /):
        self.remove(id_or_name)

    def __getitem__(self, id_or_name: int | str, /) -> dict:
        return self.get(id_or_name, default=undefined)

    def __setitem__(self, id_or_name: int | str, value: str | dict, /):
        self.edit(id_or_name, value)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "计算共有多少个标签"
        return self.get_length()

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @overload
    def add(
        self, 
        /, 
        *labels: str, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def add(
        self, 
        /, 
        *labels: str, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def add(
        self, 
        /, 
        *labels: str, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        """添加（若干个）标签
        标签的格式是 "{label_name}" 或 "{label_name}\x07{color}"，例如 "tag\x07#FF0000"
        """
        def gen_step():
            resp = yield partial(
                self.client.fs_label_add, 
                *labels, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return check_response(resp)["data"]
        return run_gen_step(gen_step, async_=async_)

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ):
        "清空标签列表"
        def gen_step():
            if async_:
                ls = yield partial(
                    to_list, 
                    (item["id"] async for item in self.iter(async_=True)), 
                )
                ids = ",".join(ls)
            else:
                ids = ",".join(item["id"] for item in self.iter())
            yield partial(
                self.client.fs_label_del, 
                ids, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def edit(
        self, 
        id_or_name: int | str, 
        /, 
        value: str | dict, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def edit(
        self, 
        id_or_name: int | str, 
        /, 
        value: str | dict, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def edit(
        self, 
        id_or_name: int | str, 
        /, 
        value: str | dict, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """用名称或 id 查询并编辑标签
        如果 value 是 str，则视为修改标签的名称，否则视为 payload
        payload:
            - name: str = <default>  # 标签名
            - color: str = <default> # 标签颜色，支持 css 颜色语法
            - sort: int = <default>  # 序号
        """
        def gen_step():
            id = yield partial(
                self.id_of, 
                id_or_name, 
                async_=async_, 
            )
            if isinstance(value, str):
                payload = {"id": id, "name": value}
            else:
                payload = {**value, "id": id}
            return (yield partial(
                self.client.fs_label_edit, 
                payload, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_)

    def get(
        self, 
        id_or_name: int | str, 
        /, 
        default=None, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        "用名称或 id 查询标签信息"
        def gen_step():
            sentinel = object()
            if isinstance(id_or_name, int):
                id = str(id_or_name)
                if async_:
                    ret = yield partial(
                        anext, 
                        (item async for item in self.iter(async_=True) if item["id"] == id), 
                        sentinel, 
                    )
                else:
                    ret = next(
                        (item for item in self.iter() if item["id"] == id), 
                        sentinel, 
                    )
            else:
                name = id_or_name
                if async_:
                    ret = yield partial(
                        anext, 
                        (item async for item in self.iter(keyword=name, async_=True) if item["name"] == name), 
                        sentinel, 
                    )
                else:
                    ret = next(
                        (item for item in self.iter(keyword=name) if item["name"] == name), 
                        sentinel, 
                    )
            if ret is not sentinel:
                return ret
            if default is undefined:
                raise LookupError(f"no such item: {id_or_name!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            resp = yield partial(
                self.client.fs_label_list, 
                {"limit": 1}, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return check_response(resp)["data"]["total"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def has(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def has(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def has(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        """用名称或 id 查询标签是否存在
        """
        def gen_step():
            if isinstance(id_or_name, int):
                resp = yield partial(
                    self.client.fs_label_edit, 
                    {"id": id_or_name}, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )
                return resp["code"] != 21005
            else:
                name = id_or_name
                if async_:
                    return (yield partial(
                        async_any, 
                        (item["name"] == name async for item in self.iter(keyword=name, async_=True)), 
                    ))
                else:
                    return any(item["name"] == name for item in self.iter(keyword=name))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def id_of(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False] = False, 
    ) -> int:
        ...
    @overload
    def id_of(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, int]:
        ...
    def id_of(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> int | Coroutine[Any, Any, int]:
        "获取名称对应的 id"
        def gen_step():
            if isinstance(id_or_name, int):
                return id_or_name
            return (yield partial(
                self.get, 
                id_or_name, 
                default=undefined, 
                async_=async_, 
            ))["id"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 11500, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 11500, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 11500, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
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
        fs_label_list = self.client.fs_label_list
        if async_:
            async def request():
                count = 0
                while True:
                    resp = await check_response(fs_label_list(
                        payload, 
                        request=self.async_request, 
                        async_=True, 
                    ))
                    total = resp["data"]["total"]
                    if count == 0:
                        count = total
                    elif count != total:
                        raise RuntimeError("detected count changes during iteration")
                    ls = resp["data"]["list"]
                    for item in ls:
                        yield item
                    if len(ls) < page_size:
                        break
                    payload["offset"] += page_size # type: ignore
        else:
            def request():
                count = 0
                while True:
                    resp = check_response(fs_label_list(
                        payload, 
                        request=self.request, 
                    ))
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
        return request()

    @overload
    def iter_files(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False] = False, 
        **search_kwargs, 
    ) -> Iterator[P115Path]:
        ...
    @overload
    def iter_files(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[True], 
        **search_kwargs, 
    ) -> AsyncIterator[P115Path]:
        ...
    def iter_files(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False, True] = False, 
        **search_kwargs, 
    ) -> Iterator[P115Path] | AsyncIterator[P115Path]:
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
        def gen_step():
            search_kwargs["file_label"] = yield partial(
                self.id_of, 
                id_or_name, 
                async_=async_, 
            )
            search_kwargs.setdefault("cid", 0)
            return (yield partial(
                self.client.fs.search, 
                **search_kwargs, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            ))
        return run_gen_step(gen_step, async_=async_, as_iter=True)

    @overload
    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        keyword: str = "", 
        sort: Literal["", "name", "create_time", "update_time"] = "", 
        order: Literal["", "asc", "desc"] = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
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
        def gen_step():
            if limit <= 0:
                if async_:
                    return (yield partial(
                        to_list, 
                        self.iter(
                            offset, 
                            keyword=keyword, 
                            sort=sort, 
                            order=order, 
                            async_=True, 
                        ), 
                    ))
                else:
                    return list(self.iter(
                        offset, 
                        keyword=keyword, 
                        sort=sort, 
                        order=order, 
                    ))
            resp = yield partial(
                self.client.fs_label_list, 
                {
                    "offset": offset, 
                    "limit": limit, 
                    "keyword": keyword, 
                    "sort": sort, 
                    "order": order, 
                }, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return check_response(resp)["data"]["list"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        id_or_name: int | str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """用名字或 id 查询并删除标签"
        """
        def gen_step():
            id = yield partial(self.id_of, id_or_name, async_=async_)
            resp = yield partial(
                self.client.fs_label_del, 
                id, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return check_response(resp)
        return run_gen_step(gen_step, async_=async_)

    set = edit

