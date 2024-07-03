#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "AlistCopyTaskList", "AlistUploadTaskList", 
    "AlistOfflineDownloadTaskList", "AlistOfflineDownloadTransferTaskList", 
    "AlistAria2DownTaskList", "AlistAria2TransferTaskList", 
    "AlistQbitDownTaskList", "AlistQbitTransferTaskList", 
]

from asyncio import TaskGroup
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import cast, overload, Any, Literal

from iterutils import run_gen_step
from undefined import undefined

from ..client import check_response, AlistClient


# TODO: 为任务专门设计的类
class AlistTask:
    ...


class AlistCopyTaskList:
    "任务列表：复制"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_copy_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_copy_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_copy_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_copy_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_copy_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_copy_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_copy_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_copy_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_copy_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))


class AlistUploadTaskList:
    "任务列表：上传"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_upload_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_upload_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_upload_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_upload_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_upload_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_upload_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_upload_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_upload_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_upload_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))


class AlistOfflineDownloadTaskList:
    "任务列表：离线下载（到本地）"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_offline_download_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_offline_download_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_offline_download_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_offline_download_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_offline_download_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_offline_download_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_offline_download_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_offline_download_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_offline_download_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))


class AlistOfflineDownloadTransferTaskList:
    "任务列表：离线下载（到存储）"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_offline_download_transfer_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_offline_download_transfer_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_offline_download_transfer_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_offline_download_transfer_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_offline_download_transfer_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_offline_download_transfer_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_offline_download_transfer_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_offline_download_transfer_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_offline_download_transfer_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))


class AlistAria2DownTaskList:
    "任务列表：aria2下载任务"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_aria2_down_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_aria2_down_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_aria2_down_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_aria2_down_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_aria2_down_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_aria2_down_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_aria2_down_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_aria2_down_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_aria2_down_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))


class AlistAria2TransferTaskList:
    "任务列表：aria2转存任务"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_aria2_transfer_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_aria2_transfer_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_aria2_transfer_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_aria2_transfer_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_aria2_transfer_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_aria2_transfer_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_aria2_transfer_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_aria2_transfer_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_aria2_transfer_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))


class AlistQbitDownTaskList:
    "任务列表：qbit转存任务"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_qbit_down_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_qbit_down_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_qbit_down_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_qbit_down_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_qbit_down_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_qbit_down_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_qbit_down_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_qbit_down_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_qbit_down_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))


class AlistQbitTransferTaskList:
    "任务列表：qbit转存任务"
    __slots__ = "client", "request", "async_request"

    def __init__(
        self, 
        /, 
        client: str | AlistClient, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ):
        if isinstance(client, str):
            client = AlistClient.from_auth(client)
        self.client = client
        self.request = request
        self.async_request = async_request

    def __contains__(self, tid: str, /) -> bool:
        return self.exists(tid)

    def __delitem__(self, tid: str, /):
        self.remove(tid)

    def __getitem__(self, tid: str, /) -> dict:
        return self.get(tid, default=undefined)

    def __aiter__(self, /) -> AsyncIterator[dict]:
        return self.iter(async_=True)

    def __iter__(self, /) -> Iterator[dict]:
        return self.iter()

    def __len__(self, /) -> int:
        "获取总任务数（运行中(/未完成) + 已完成）"
        return self.get_length()

    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def cancel(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "取消某个任务"
        return check_response(self.client.admin_task_qbit_transfer_cancel( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "清空任务列表"
        def gen_step():
            undone = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            cancel = self.cancel
            if async_:
                async def run():
                    async with TaskGroup() as tg:
                        create_task = tg.create_task
                        for task in undone:
                            create_task(cancel(task["id"], async_=True, **request_kwargs))
                yield run
            else:
                with ThreadPoolExecutor() as ex:
                    create_task = ex.submit
                    for task in undone:
                        create_task(cast(Callable[..., dict], cancel), task["id"], **request_kwargs)
            
            yield partial(
                self.clear_done, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_=async_)

    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已完成任务"
        return check_response(self.client.admin_task_qbit_transfer_clear_done( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除所有已成功任务"
        return check_response(self.client.admin_task_qbit_transfer_clear_succeeded( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def delete(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务"
        return check_response(self.client.admin_task_qbit_transfer_delete( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    def get(
        self, 
        /, 
        tid: str, 
        default = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        "获取某个任务信息"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_qbit_transfer_info, 
                tid, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"] == 200:
                return resp["data"]
            if default is undefined:
                raise LookupError(f"no such tid: {tid!r}")
            return default
        return run_gen_step(gen_step, async_=async_)

    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            ls = yield partial(
                self.list, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(ls)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            resp = yield partial(
                self.get, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp is not None
        return run_gen_step(gen_step, async_=async_)

    @overload
    def iter(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        "迭代获取所有任务"
        if async_:
            async def request():
                for task in (await self.list(async_=True, **request_kwargs)):
                    yield task
            return request()
        else:
            return iter(self.list(**request_kwargs))

    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有已完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_qbit_transfer_done, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有未完成任务"
        def gen_step():
            resp = yield partial(
                self.client.admin_task_qbit_transfer_undone, 
                request=self.async_request if async_ else self.request, 
                async_=async_, 
                **request_kwargs, 
            )
            return check_response(resp)["data"] or []
        return run_gen_step(gen_step, async_=async_)

    @overload
    def list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        "列出所有任务"
        def gen_step():
            undone = yield partial(
                self.list_undone, 
                async_=async_, 
                **request_kwargs, 
            )
            tasks = yield partial(
                self.list_done, 
                async_=async_, 
                **request_kwargs, 
            )
            if not tasks:
                return undone
            if undone:
                seen = {t["id"] for t in tasks}
                tasks.extend(t for t in undone if t["id"] not in seen)
            return tasks
        return run_gen_step(gen_step, async_=async_)

    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def remove(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "删除某个任务（先取消再删除）"
        def gen_step():
            yield partial(
                self.cancel, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            )
            return (yield partial(
                self.delete, 
                tid, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry(
        self, 
        /, 
        tid: str, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试某个任务"
        return check_response(self.client.admin_task_qbit_transfer_retry( # type: ignore
            tid, 
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重试所有失败任务"
        return check_response(self.client.admin_task_qbit_transfer_retry_failed( # type: ignore
            request=self.async_request if async_ else self.request, 
            async_=async_, 
            **request_kwargs, 
        ))

