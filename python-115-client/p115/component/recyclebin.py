#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Recyclebin"]

from collections.abc import AsyncIterator, Callable, Coroutine, Iterable, Iterator
from functools import partial
from typing import overload, Any, Literal

from asynctools import async_any, to_list
from iterutils import run_gen_step
from undefined import undefined

from .client import check_response, P115Client


class P115Recyclebin:
    "回收站"
    __slots__ = "client", "password", "request", "async_request"

    def __init__(
        self, 
        client: str | P115Client, 
        /, 
        password: int | str = "", 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = P115Client(client)
        self.client = client
        self.password = password
        self.request = request
        self.async_request = async_request

    def __contains__(self, id: int | str, /) -> bool:
        return self.has(id)

    def __delitem__(self, id: int | str, /):
        return self.remove(id)

    def __getitem__(self, id: int | str, /) -> dict:
        return self.get(id, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "计算回收站中的文件和文件夹数（不含文件夹内的递归计算）"
        return self.get_length()

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"<{name}(client={self.client!r}) at {hex(id(self))}>"

    @overload
    def clear(
        self, 
        /, 
        password: None | int | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def clear(
        self, 
        /, 
        password: None | int | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear(
        self, 
        /, 
        password: None | int | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清空回收站，如果不传入密码则用 self.password"
        if password is None:
            password = self.password
        return check_response(self.client.recyclebin_clean( # type: ignore
            {"password": password}, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    def get(
        self, 
        id: int | str, 
        /, 
        default=None, 
        *, 
        async_: Literal[False, True] = False, 
    ):
        "用 id 查询回收站中的文件信息"
        def gen_step():
            ids = str(id)
            sentinel = object()
            if async_:
                ret = yield partial(
                    anext, 
                    (item async for item in self.iter(async_=True) if item["id"] == ids), 
                    sentinel, 
                )
            else:
                ret = next(
                    (item for item in self.iter() if item["id"] == ids), 
                    sentinel, 
                )
            if ret is not sentinel:
                return ret
            if default is undefined:
                raise LookupError(f"no such id: {id!r}")
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
                self.client.recyclebin_list, 
                {"limit": 1}, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            return int(check_response(resp)["count"])
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
        def gen_step():
            ids = str(id)
            if async_:
                return (yield partial(
                    async_any, 
                    (item["id"] == ids async for item in self.iter(async_=True)), 
                ))
            else:
                return any(item["id"] == ids for item in self.iter())
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
        "迭代获取回收站的文件信息"
        if offset < 0:
            offset = 0
        if page_size <= 0:
            page_size = 1 << 10
        payload = {"offset": offset, "limit": page_size}
        if async_:
            async def request():
                count = 0
                while True:
                    resp = await self.client.recyclebin_list(
                        payload, 
                        request=self.async_request, 
                        async_=True, 
                    )
                    resp = check_response(resp)
                    if resp["offset"] != payload["offset"]:
                        return
                    if count == 0:
                        count = int(resp["count"])
                    elif count != int(resp["count"]):
                        raise RuntimeError("detected count changes during iteration")
                    for attr in resp["data"]:
                        yield attr
                    if len(resp["data"]) < resp["page_size"]:
                        return
                    payload["offset"] += resp["page_size"]
        else:
            def request():
                count = 0
                while True:
                    resp = self.client.recyclebin_list(
                        payload, 
                        request=self.request, 
                    )
                    resp = check_response(resp)
                    if resp["offset"] != payload["offset"]:
                        return
                    if count == 0:
                        count = int(resp["count"])
                    elif count != int(resp["count"]):
                        raise RuntimeError("detected count changes during iteration")
                    yield from resp["data"]
                    if len(resp["data"]) < resp["page_size"]:
                        return
                    payload["offset"] += resp["page_size"]
        return request()

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
        "获取回收站的文件信息列表"
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
                self.client.recyclebin_list, 
                {"offset": offset, "limit": limit}, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
            )
            check_response(resp)
            if resp["offset"] != offset:
                return []
            return resp["data"]
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        password: None | int | str = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        password: None | int | str = None, 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        password: None | int | str = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "从回收站删除文件（即永久删除），如果不传入密码则用 self.password"
        if isinstance(ids, (int, str)):
            payload = {"rid[0]": ids}
        else:
            payload = {f"rid[{i}]": id for i, id in enumerate(ids)}
        payload["password"] = self.password if password is None else password
        return check_response(self.client.recyclebin_clean( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

    @overload
    def revert(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        async_: Literal[False] = False, 
    ) -> dict:
        ...
    @overload
    def revert(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def revert(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        async_: Literal[False, True] = False, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "恢复已删除文件"
        if isinstance(ids, (int, str)):
            payload = {"rid[0]": ids}
        else:
            payload = {f"rid[{i}]": id for i, id in enumerate(ids)}
        return check_response(self.client.recyclebin_revert( # type: ignore
            payload, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
        ))

