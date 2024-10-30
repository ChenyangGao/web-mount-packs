#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Sharing"]

from collections.abc import AsyncIterator, Callable, Coroutine, Iterable, Iterator
from functools import partial
from typing import overload, Any, Literal

from asynctools import async_any, to_list
from iterutils import run_gen_step
from p115client import check_response
from undefined import undefined

from .client import P115Client
from .fs import P115Path
from .fs_share import P115ShareFileSystem


class P115Sharing:
    "自己的分享列表"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        client: str | P115Client, 
        /, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = P115Client(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, code_or_id: int | str, /) -> bool:
        return self.has(code_or_id)

    def __delitem__(self, code_or_id: int | str, /):
        return self.remove(code_or_id)

    def __getitem__(self, code_or_id: int | str, /) -> dict:
        return self.get(code_or_id, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "计算共有多少个分享"
        return self.get_length()

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @property
    def receive_path(self, /) -> P115Path:
        return self.get_receive_path()

    @overload
    def add(
        self, 
        file_ids: int | str | Iterable[int | str], 
        /, 
        is_asc: Literal[0, 1] = 1, 
        order: str = "file_name", 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def add(
        self, 
        file_ids: int | str | Iterable[int | str], 
        /, 
        is_asc: Literal[0, 1] = 1, 
        order: str = "file_name", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def add(
        self, 
        file_ids: int | str | Iterable[int | str], 
        /, 
        is_asc: Literal[0, 1] = 1, 
        order: str = "file_name", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
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
        return check_response(self.client.share_send( # type: ignore
            {
                "file_ids": file_ids, 
                "is_asc": is_asc, 
                "order": order, 
            }, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def clear(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def clear(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清空分享列表"
        def gen_step():
            if async_:
                ls = yield partial(
                    to_list, 
                    (item["share_code"] async for item in self.iter(async_=True)), 
                )
                codes = ",".join(ls)
            else:
                codes = ",".join(item["share_code"] for item in self.iter())
            return check_response((yield partial(
                self.client.share_update, 
                {"share_code": codes, "action": "cancel"}, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def code_of(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def code_of(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def code_of(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        "获取 id 对应的分享码"
        def gen_step():
            if isinstance(code_or_id, str):
                return code_or_id
            return (yield partial(
                self.get, 
                code_or_id, 
                default=undefined, 
                async_=async_, 
            ))["share_code"]
        return run_gen_step(gen_step, async_=async_)

    def get(
        self, 
        code_or_id: int | str, 
        /, 
        default=None, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        "用分享码或 id 查询分享信息"
        def gen_step():
            if isinstance(code_or_id, str):
                resp = yield partial(
                    self.client.share_info, 
                    code_or_id, 
                    request=self.async_request if async_ else self.request, 
                    async_=async_, 
                )
                if resp["state"]:
                    return resp["data"]
                if default is not undefined:
                    return default
                raise LookupError(f"no such share_code: {code_or_id!r}, with message: {resp!r}")
            sentinel = object()
            snap_id = str(code_or_id)
            if async_:
                ret = yield partial(
                    anext, 
                    (item async for item in self.iter(async_=True) if item["snap_id"] == snap_id), 
                    sentinel, 
                )
            else:
                ret = next(
                    (item for item in self.iter() if item["snap_id"] == snap_id), 
                    sentinel, 
                )
            if ret is not sentinel:
                return ret
            if default is undefined:
                raise LookupError(f"no such snap_id: {snap_id!r}")
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
                self.client.share_list, 
                {"limit": 1}, 
                request=self.request, 
                async_request=self.async_request, 
            )
            return check_response(resp)["count"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_receive_path(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> P115Path:
        ...
    @overload
    def get_receive_path(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, P115Path]:
        ...
    def get_receive_path(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> P115Path | Coroutine[Any, Any, P115Path]:
        return self.client.get_fs(
            request=self.request, 
            async_request=self.async_request, 
        ).as_path("/我的接收", async_=async_)

    @overload
    def has(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[False] = False, 
    ) -> bool:
        ...
    @overload
    def has(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def has(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> bool | Coroutine[Any, Any, bool]:
        """用 id 或分享码查询分享是否存在
        """
        def gen_step():
            if isinstance(code_or_id, str):
                return (yield partial(
                    self.client.share_info, 
                    code_or_id, 
                    request=self.request, 
                    async_request=self.async_request, 
                ))["state"]
            snap_id = str(code_or_id)
            if async_:
                return (yield partial(
                    async_any, 
                    (item["snap_id"] == snap_id async for item in self.iter(async_=True)), 
                ))
            else:
                return any(item["snap_id"] == snap_id for item in self.iter())
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 1 << 10, 
        *, 
        async_: Literal[False] = False, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 1 << 10, 
        *, 
        async_: Literal[True], 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        offset: int = 0, 
        page_size: int = 1 << 10, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取分享信息"
        if offset < 0:
            offset = 0
        if page_size <= 0:
            page_size = 1 << 10
        payload = {"offset": offset, "limit": page_size}
        if async_:
            async def request():
                count = 0
                while True:
                    resp = await check_response(self.client.share_list(
                        payload, 
                        request=self.async_request, 
                        async_=True, 
                    ))
                    if count == 0:
                        count = resp["count"]
                    elif count != resp["count"]:
                        raise RuntimeError("detected count changes during iteration")
                    for attr in resp["list"]:
                        yield attr 
                    if len(resp["list"]) < page_size:
                        break
                    payload["offset"] += page_size
        else:
            def request():
                count = 0
                while True:
                    resp = check_response(self.client.share_list(
                        payload, 
                        request=self.request, 
                    ))
                    if count == 0:
                        count = resp["count"]
                    elif count != resp["count"]:
                        raise RuntimeError("detected count changes during iteration")
                    yield from resp["list"]
                    if len(resp["list"]) < page_size:
                        break
                    payload["offset"] += page_size
        return request()

    @overload
    def list_fs(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        *, 
        async_: Literal[False] = False, 
    ) -> list[P115ShareFileSystem]:
        ...
    @overload
    def list_fs(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[P115ShareFileSystem]]:
        ...
    def list_fs(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[P115ShareFileSystem] | Coroutine[Any, Any, list[P115ShareFileSystem]]:
        "获取分享信息列表"
        def gen_step():
            ls = yield self.list(offset, limit, async_=async_)
            client = self.client
            request = self.request
            async_request = self.async_request
            return [P115ShareFileSystem(
                client, 
                info["share_code"], 
                info["receive_code"], 
                request=request, 
                async_request=async_request, 
            ) for info in ls]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
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
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        offset: int = 0, 
        limit: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "获取分享信息列表"
        def gen_step():
            if limit <= 0:
                if async_:
                    return (yield partial(
                        to_list, 
                        self.iter(offset, async_=True), 
                    ))
                else:
                    return list(self.iter(offset))
            resp = yield partial(
                self.client.share_list, 
                {"offset": offset, "limit": limit}, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return check_response(resp)["list"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        code_or_id_s: int | str | Iterable[int | str], 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        code_or_id_s: int | str | Iterable[int | str], 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        code_or_id_s: int | str | Iterable[int | str], 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "用分享码或 id 查询并删除分享"
        def gen_step():
            if isinstance(code_or_id_s, (int, str)):
                share_code = yield partial(
                    self.code_of, 
                    code_or_id_s, 
                    async_=async_, 
                )
            else:
                if async_:
                    ls = yield partial(
                        to_list, 
                        (await self.code_of(code, async_=True) for code in code_or_id_s), # type: ignore
                    )
                    share_code = ",".join(ls)
                else:
                    share_code = ",".join(map(self.code_of, code_or_id_s))
                if not share_code:
                    raise ValueError("no `share_code` or `snap_id` specified")
            return check_response((yield partial(
                self.client.share_update, 
                {"share_code": share_code, "action": "cancel"}, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def update(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[False] = False, 
        **payload, 
    ) -> dict:
        ...
    @overload
    def update(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[True], 
        **payload, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def update(
        self, 
        code_or_id: int | str, 
        /, 
        async_: Literal[False, True] = False, 
        **payload, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """用分享码或 id 查询并更新分享信息
        payload:
            - receive_code: str = <default>         # 访问密码（口令）
            - share_duration: int = <default>       # 分享天数: 1(1天), 7(7天), -1(长期)
            - is_custom_code: 0 | 1 = <default>     # 用户自定义口令（不用管）
            - auto_fill_recvcode: 0 | 1 = <default> # 分享链接自动填充口令（不用管）
            - share_channel: int = <default>        # 分享渠道代码（不用管）
            - action: str = <default>               # 操作: 取消分享 "cancel"
        """
        def gen_step():
            payload["share_code"] = yield partial(
                self.code_of, 
                code_or_id, 
                async_=async_, 
            )
            return check_response((yield partial(
                self.client.share_update, 
                payload, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )))
        return run_gen_step(gen_step, async_=async_)

