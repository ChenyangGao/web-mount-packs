#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["check_response", "P123Client", "P123OSError"]

from collections.abc import (
    AsyncIterable, Awaitable, Buffer, Callable, Coroutine, Iterable, 
    MutableMapping, Sized, 
)
from errno import EIO
from functools import partial
from hashlib import md5
from http.cookiejar import CookieJar
from inspect import isawaitable
from os import fsdecode, fstat, PathLike
from os.path import basename
from tempfile import TemporaryFile
from typing import cast, overload, Any, Literal, Self
from uuid import uuid4

from aiofile import async_open
from asynctools import ensure_async
from property import locked_cacheproperty
from hashtools import file_digest, file_digest_async
from iterutils import run_gen_step
from filewrap import (
    bio_chunk_iter, bio_chunk_async_iter, 
    bytes_iter_to_reader, bytes_iter_to_async_reader, 
    copyfileobj, copyfileobj_async, SupportsRead, 
)
from http_request import SupportsGeturl
from yarl import URL


TANSTAB_CLEAN_name = {c: "" for c in b"\\/:*?|><"}
_httpx_request = None


class P123OSError(OSError):
    ...


def get_default_request():
    global _httpx_request
    if _httpx_request is None:
        from httpx_request import request
        _httpx_request = partial(request, timeout=(5, 60, 60, 5))
    return _httpx_request


def default_parse(resp, content: Buffer, /):
    from orjson import loads
    if isinstance(content, (bytes, bytearray, memoryview)):
        return loads(content)
    else:
        return loads(memoryview(content))


def buffer_length(b: Buffer, /) -> int:
    if isinstance(b, Sized):
        return len(b)
    else:
        return len(memoryview(b))


@overload
def check_response(resp: dict, /) -> dict:
    ...
@overload
def check_response(resp: Awaitable[dict], /) -> Coroutine[Any, Any, dict]:
    ...
def check_response(resp: dict | Awaitable[dict], /) -> dict | Coroutine[Any, Any, dict]:
    """检测 123 的某个接口的响应，如果成功则直接返回，否则根据具体情况抛出一个异常，基本上是 OSError 的实例
    """
    def check(resp, /) -> dict:
        if not isinstance(resp, dict) or resp.get("code"):
            raise P123OSError(EIO, resp)
        return resp
    if isawaitable(resp):
        async def check_await() -> dict:
            return check(await resp)
        return check_await()
    else:
        return check(resp)


class P123Client:

    def __init__(
        self, 
        /, 
        passport: int | str = "", 
        password: str = "", 
        token: str = "", 
    ):
        self.passport = passport
        self.password = password
        self.token = token
        if passport and password:
            self.login()

    @property
    def cookies(self, /):
        """请求所用的 Cookies 对象（同步和异步共用）
        """
        try:
            return self.__dict__["cookies"]
        except KeyError:
            from httpx import Cookies
            cookies = self.__dict__["cookies"] = Cookies()
            return cookies

    @property
    def cookiejar(self, /) -> CookieJar:
        """请求所用的 CookieJar 对象（同步和异步共用）
        """
        return self.cookies.jar

    @property
    def headers(self, /) -> MutableMapping:
        """请求头，无论同步还是异步请求都共用这个请求头
        """
        try:
            return self.__dict__["headers"]
        except KeyError:
            from multidict import CIMultiDict
            headers = self.__dict__["headers"] = CIMultiDict({
                "accept": "application/json, text/plain, */*", 
                "accept-encoding": "gzip, deflate", 
                "app-version": "3", 
                "connection": "keep-alive", 
                "platform": "web", 
                "user-agent": "Mozilla/5.0 AppleWebKit/600 Safari/600 Chrome/124.0.0.0", 
            })
            return headers

    @locked_cacheproperty
    def session(self, /):
        """同步请求的 session 对象
        """
        import httpx_request
        from httpx import Client, HTTPTransport, Limits
        session = Client(
            limits=Limits(max_connections=256, max_keepalive_connections=64, keepalive_expiry=10), 
            transport=HTTPTransport(retries=5), 
            verify=False, 
        )
        setattr(session, "_headers", self.headers)
        setattr(session, "_cookies", self.cookies)
        return session

    @locked_cacheproperty
    def async_session(self, /):
        """异步请求的 session 对象
        """
        import httpx_request
        from httpx import AsyncClient, AsyncHTTPTransport, Limits
        session = AsyncClient(
            limits=Limits(max_connections=256, max_keepalive_connections=64, keepalive_expiry=10), 
            transport=AsyncHTTPTransport(retries=5), 
            verify=False, 
        )
        setattr(session, "_headers", self.headers)
        setattr(session, "_cookies", self.cookies)
        return session

    @property
    def token(self, /) -> str:
        return self._token

    @token.setter
    def token(self, value: str, /):
        self._token = value
        if value:
            self.headers["authorization"] = f"Bearer {self._token}"
        else:
            self.headers.pop("authorization", None)

    @token.deleter
    def token(self, /):
        self.token = ""

    @overload
    def login(
        self, 
        /, 
        passport: int | str = "", 
        password: str = "", 
        remember: bool = True, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def login(
        self, 
        /, 
        passport: int | str = "", 
        password: str = "", 
        remember: bool = True, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def login(
        self, 
        /, 
        passport: int | str = "", 
        password: str = "", 
        remember: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        if passport:
            self.passport = passport
        else:
            passport = self.passport
        if password:
            self.password = password
        else:
            password = self.password
        def gen_step():
            if passport and password:
                resp = yield self.user_login(
                    {"passport": passport, "password": password, "remember": remember}, 
                    async_=async_, 
                    **request_kwargs, 
                )
                check_response(resp)
                self.token = resp["data"]["token"]
            return self
        return run_gen_step(gen_step, async_=async_)

    def request(
        self, 
        /, 
        url: str, 
        method: str = "POST", 
        request: None | Callable = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        """执行 HTTP 请求，默认为 POST 方法
        """
        if url.startswith("//"):
            url = "https:" + url
        elif not url.startswith(("http://", "https://")):
            if not url.startswith("/"):
                url = "/" + url
            url = "https://www.123pan.com" + url
        request_kwargs.setdefault("parse", default_parse)
        if request is None:
            request_kwargs["session"] = self.async_session if async_ else self.session
            return get_default_request()(
                url=url, 
                method=method, 
                async_=async_, 
                **request_kwargs, 
            )
        else:
            if headers := request_kwargs.get("headers"):
                request_kwargs["headers"] = {**self.headers, **headers}
            else:
                request_kwargs["headers"] = self.headers
            return request(
                url=url, 
                method=method, 
                **request_kwargs, 
            )

    @overload
    def download_info(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_info(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_info(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取下载信息

        POST https://www.123pan.com/a/api/file/download_info

        .. hint::
            即使文件已经被删除，只要还有 etag （即 md5） 就依然可以下载

            你完全可以构造这样的查询参数

            .. code:: python

                payload = {
                    "etag": "...",   # 必填，文件的 MD5
                    "fileId": 0,     # 可以随便填
                    "fileName": "a", # 随便填一个名字
                    "S3KeyFlag": str # 必填，格式为 f"{UID}-0"，UID 就是用户的 UID，可从 `P115Client.user_info` 的响应中获取
                    "size": 0,       # 可以随便填
                }

        :payload:
            - etag: str 💡 文件的 MD5 散列值
            - fileId: int | str
            - fileName: str
            - s3keyFlag: str
            - size: int
            - type: int = 0
            - driveId: int | str = 0
            - ...
        """
        api = "https://www.123pan.com/a/api/file/download_info"
        def gen_step():
            nonlocal payload
            if headers := request_kwargs.get("headers"):
                headers = dict(headers)
            else:
                headers = {}
            headers["platform"] = "android"
            request_kwargs["headers"] = headers
            if not isinstance(payload, dict):
                resp = yield self.fs_file(payload, async_=async_, **request_kwargs)
                check_response(resp)
                payload = resp["data"]["infoList"][0]
            payload = cast(dict, payload)
            payload = {"driveId": 0, "type": 0, **payload}
            return self.request(url=api, json=payload, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def download_info_batch(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_info_batch(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_info_batch(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取批量下载信息

        POST https://www.123pan.com/a/api/file/batch_download_info

        .. warning::
            会把一些文件或目录以 zip 包的形式下载，但非会员有流量限制，所以还是推荐用 `P123Client.download_info` 逐个获取下载链接并下载

        :payload:
            - fileIdList: list[FileID]

                .. code:: python

                    FileID = {
                        "fileId": int | str
                    }
        """
        api = "https://www.123pan.com/a/api/file/batch_download_info"
        if isinstance(payload, (int, str)):
            payload = {"fileIdList": [{"fileId": payload}]}
        elif not isinstance(payload, dict):
            payload = {"fileIdList": [{"fileId": fid} for fid in payload]}
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def fs_copy(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        parent_id: int | str = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        parent_id: int | str = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        parent_id: int | str = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动

        POST https://www.123pan.com/a/api/restful/goapi/v1/file/copy/async

        :payload:
            - fileList: list[File] 💡 信息可以取自 `P123Client.fs_file` 接口

                .. code:: python

                    File = { 
                        "FileId": int | str, 
                        ...
                    }

            - targetFileId: int | str = 0
        """
        api = "https://www.123pan.com/a/api/restful/goapi/v1/file/copy/async"
        def gen_step():
            nonlocal payload
            if not isinstance(payload, dict):
                resp = yield self.fs_file(payload, async_=async_, **request_kwargs)
                check_response(resp)
                payload = {"fileList": resp["data"]["infoList"]}
            payload = {"targetFileId": parent_id, **payload}
            return self.request(url=api, json=payload, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_delete(
        self, 
        payload: int | str | Iterable[int | str] | dict = 0, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_delete(
        self, 
        payload: int | str | Iterable[int | str] | dict = 0, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_delete(
        self, 
        payload: int | str | Iterable[int | str] | dict = 0, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """彻底删除

        POST https://www.123pan.com/a/api/file/delete

        :payload:
            - fileIdList: list[FileID]

                .. code:: python

                    FileID = {
                        "fileId": int | str
                    }

            - event: str = "recycleDelete"
        """
        api = "https://www.123pan.com/a/api/file/delete"
        if isinstance(payload, (int, str)):
            payload = {"fileIdList": [{"fileId": payload}]}
        elif not isinstance(payload, dict):
            payload = {"fileIdList": [{"fileId": fid} for fid in payload]}
        payload = cast(dict, payload)
        payload.setdefault("event", "recycleDelete")
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def fs_file(
        self, 
        payload: int | str | Iterable[int | str] | dict = 0, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_file(
        self, 
        payload: int | str | Iterable[int | str] | dict = 0, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_file(
        self, 
        payload: int | str | Iterable[int | str] | dict = 0, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件信息

        POST https://www.123pan.com/a/api/file/info

        :payload:
            - fileIdList: list[FileID]

                .. code:: python

                    FileID = {
                        "fileId": int | str
                    }
        """
        api = "https://www.123pan.com/a/api/file/info"
        if isinstance(payload, (int, str)):
            payload = {"fileIdList": [{"fileId": payload}]}
        elif not isinstance(payload, dict):
            payload = {"fileIdList": [{"fileId": fid} for fid in payload]}
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def fs_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        event: str = "homeListFile", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        event: str = "homeListFile", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        event: str = "homeListFile", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件列表（可搜索）

        GET https://www.123pan.com/a/api/file/list/new

        .. note::
            如果返回信息中，有 "Next" 的值为 "-1"，说明无下一页

        :payload:
            - driveId: int | str = 0
            - limit: int = 100 💡 分页大小
            - next: int = 0
            - orderBy: "file_id" | "file_name" | "update_at" | "size" = "file_id" 💡 排序依据
            - orderDirection: "asc" | "desc" = "asc" 💡 排序顺序
            - Page: int = 1 💡 第几页
            - parentFileId: int | str = 0 💡 父目录 id
            - trashed: "false" | "true" = <default>
            - inDirectSpace: "false" | "true" = "false"
            - event: str = "homeListFile" 💡 事件名称

                - "homeListFile": 全部文件
                - "recycleListFile": 回收站

            - operateType: int = <default>
            - SearchData: str = <default> 💡 搜索文本
            - OnlyLookAbnormalFile: int = <default>
        """
        api = "https://www.123pan.com/a/api/file/list/new"
        if isinstance(payload, (int, str)):
            payload = {"parentFileId": payload}
        payload = {
            "driveId": 0, 
            "limit": 100, 
            "next": 0, 
            "orderBy": "file_id", 
            "orderDirection": "asc", 
            "Page": 1, 
            "parentFileId": 0, 
            "inDirectSpace": "false", 
            "event": event, 
            **payload, 
        }
        if not payload.get("trashed"):
            match payload["event"]:
                case "recycleListFile":
                    payload["trashed"] = "true"
                case _:
                    payload["trashed"] = "false"
        return self.request(url=api, method="GET", params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_move(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        parent_id: int | str = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        parent_id: int | str = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        parent_id: int | str = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动

        POST https://www.123pan.com/a/api/file/mod_pid

        :payload:
            - fileIdList: list[FileID]

                .. code:: python

                    FileID = {
                        "fileId": int | str
                    }

            - parentFileId: int | str = 0
            - event: str = "fileMove"
        """
        api = "https://www.123pan.com/a/api/file/mod_pid"
        if isinstance(payload, (int, str)):
            payload = {"fileIdList": [{"fileId": payload}]}
        elif not isinstance(payload, dict):
            payload = {"fileIdList": [{"fileId": fid} for fid in payload]}
        payload = {
            "parentFileId": parent_id, 
            "event": "fileMove", 
            **payload, 
        }
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def fs_rename(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        payload: dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """（单个）改名

        POST https://www.123pan.com/a/api/file/rename

        :payload:
            - fileId: int | str
            - fileName: str
            - driveId: int | str = 0
            - duplicate: 0 | 1 | 2 = 0 💡 处理同名：0: 提示/忽略 1: 保留两者 2: 替换
            - event: str = "fileRename"
        """
        api = "https://www.123pan.com/a/api/file/rename"
        payload = {
            "driveId": 0, 
            "duplicate": 0, 
            "event": "fileRename", 
            **payload, 
        }
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def fs_trash(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_trash(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_trash(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        event: str = "intoRecycle", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """操作回收站

        POST https://www.123pan.com/a/api/file/trash

        :payload:
            - fileTrashInfoList: list[File] 💡 信息可以取自 `P123Client.fs_file` 接口

                .. code:: python

                    File = { 
                        "FileId": int | str, 
                        ...
                    }

            - driveId: int = 0
            - event: str = "intoRecycle" 💡 事件类型

                - "intoRecycle": 移入回收站
                - "recycleRestore": 移出回收站

            - operation: bool = <default>
        """
        api = "https://www.123pan.com/a/api/file/trash"
        if isinstance(payload, (int, str)):
            payload = {"fileTrashInfoList": [{"FileId": payload}]}
        elif not isinstance(payload, dict):
            payload = {"fileTrashInfoList": [{"FileId": fid} for fid in payload]}
        payload = {"driveId": 0, "event": event, **payload}
        if payload.get("operation") is None:
            match payload["event"]:
                case "recycleRestore":
                    payload["operation"] = False
                case _:
                    payload["operation"] = True
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def fs_trash_clear(
        self, 
        payload: dict = {"event": "recycleClear"}, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_trash_clear(
        self, 
        payload: dict = {"event": "recycleClear"}, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_trash_clear(
        self, 
        payload: dict = {"event": "recycleClear"}, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清空回收站

        POST https://www.123pan.com/a/api/file/trash_delete_all

        :payload:
            - event: str = "recycleClear"
        """
        api = "https://www.123pan.com/a/api/file/trash_delete_all"
        payload.setdefault("event", "recycleClear")
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def upload_auth(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_auth(
        self, 
        payload: dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_auth(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """认证上传信息，获取上传链接

        POST https://www.123pan.com/a/api/file/s3_upload_object/auth

        .. note::
            只能获取 1 个上传链接，用于非分块上传

        :payload:
            - bucket: str
            - key: str
            - storageNode: str
            - uploadId: str
        """
        api = "https://www.123pan.com/a/api/file/s3_upload_object/auth"
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def upload_complete(
        self, 
        payload: dict, 
        /, 
        is_multipart: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_complete(
        self, 
        payload: dict, 
        /, 
        is_multipart: bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_complete(
        self, 
        payload: dict, 
        /, 
        is_multipart: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """完成上传

        POST https://www.123pan.com/a/api/file/upload_complete/v2

        :payload:
            - fileId: int 💡 文件 id
            - bucket: str 💡 存储桶
            - key: str
            - storageNode: str
            - uploadId: str
            - isMultipart: bool = True 💡 是否分块上传
        """
        api = "https://www.123pan.com/a/api/file/upload_complete/v2"
        payload = {"isMultipart": is_multipart, **payload}
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def upload_prepare_parts(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_prepare_parts(
        self, 
        payload: dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_prepare_parts(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """认证上传信息，获取上传链接

        POST https://www.123pan.com/a/api/file/s3_repare_upload_parts_batch

        .. note::
            一次可获取 `partNumberEnd - partNumberStart` 个上传链接，用于分块上传

        :payload:
            - bucket: str
            - key: str
            - storageNode: str
            - uploadId: str
            - partNumberStart: int = 1 💡 开始的分块编号（从 0 开始编号）
            - partNumberEnd: int = <default> 💡 结束的分块编号（不含）
        """
        api = "https://www.123pan.com/a/api/file/s3_repare_upload_parts_batch"
        if "partNumberStart" not in payload:
            payload["partNumberStart"] = 1
        if "partNumberEnd" not in payload:
            payload["partNumberEnd"] = int(payload["partNumberStart"]) + 1
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def upload_list_parts(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_list_parts(
        self, 
        payload: dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_list_parts(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列已经上传的分块

        POST https://www.123pan.com/a/api/file/s3_list_upload_parts

        :payload:
            - bucket: str
            - key: str
            - storageNode: str
            - uploadId: str
        """
        api = "https://www.123pan.com/a/api/file/s3_list_upload_parts"
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def upload_request(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_request(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_request(
        self, 
        payload: str | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """请求上传，获取一些初始化信息

        POST https://www.123pan.com/a/api/file/upload_request

        .. note::
            当响应信息里面有 "Reuse" 的值为 true，说明已经存在目录或者文件秒传

        :payload:
            - fileName: str 💡 文件或目录的名字
            - driveId: int | str = 0
            - duplicate: 0 | 1 | 2 = 0 💡 处理同名：0: 提示/忽略 1: 保留两者 2: 替换
            - etag: str = "" 💡 文件的 MD5 散列值
            - parentFileId: int | str = 0 💡 父目录 id
            - size: int = 0 💡 文件大小
            - type: 0 | 1 = 1 💡 类型，如果是目录则是 1，如果是文件则是 0
            - NotReuse: bool = False 💡 不要重用（仅在 `type=1` 时有效，如果为 False，当有重名时，立即返回，此时 `duplicate` 字段无效）
            - ...
        """
        api = "https://www.123pan.com/a/api/file/upload_request"
        if isinstance(payload, str):
            payload = {"fileName": payload}
        payload = {
            "driveId": 0, 
            "duplicate": 0, 
            "etag": "", 
            "parentFileId": 0,
            "size": 0, 
            "type": 1, 
            "NotReuse": False, 
            **payload, 
        }
        if payload["size"] or payload["etag"]:
            payload["type"] = 0
        return self.request(url=api, json=payload, async_=async_, **request_kwargs)

    @overload
    def upload_file(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
        file_md5: str = "", 
        file_name: str = "", 
        file_size: int = -1, 
        parent_id: int = 0, 
        duplicate: Literal[0, 1, 2] = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        file_md5: str = "", 
        file_name: str = "", 
        file_size: int = -1, 
        parent_id: int = 0, 
        duplicate: Literal[0, 1, 2] = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file(
        self, 
        /, 
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        file_md5: str = "", 
        file_name: str = "", 
        file_size: int = -1, 
        parent_id: int = 0, 
        duplicate: Literal[0, 1, 2] = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """上传文件

        :param file: 待上传的文件

            - 如果为 `collections.abc.Buffer`，则作为二进制数据上传
            - 如果为 `filewrap.SupportsRead`，则作为可读的二进制文件上传
            - 如果为 `str` 或 `os.PathLike`，则视为路径，打开后作为文件上传
            - 如果为 `yarl.URL` 或 `http_request.SupportsGeturl` (`pip install python-http_request`)，则视为超链接，打开后作为文件上传
            - 如果为 `collections.abc.Iterable[collections.abc.Buffer]` 或 `collections.abc.AsyncIterable[collections.abc.Buffer]`，则迭代以获取二进制数据，逐步上传

        :param file_md5: 文件的 MD5 散列值
        :param file_name: 文件名
        :param file_size: 文件大小
        :param parent_id: 要上传的目标目录
        :param duplicate: 处理同名：0: 提示/忽略 1: 保留两者 2: 替换
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """ 
        def gen_step():
            nonlocal file, file_md5, file_name, file_size
            def do_upload(file):
                return self.upload_file(
                    file=file, 
                    file_md5=file_md5, 
                    file_name=file_name, 
                    file_size=file_size, 
                    parent_id=parent_id, 
                    duplicate=duplicate, 
                    async_=async_, 
                    **request_kwargs, 
                )
            try:
                file = getattr(file, "getbuffer")()
            except (AttributeError, TypeError):
                pass
            if isinstance(file, Buffer):
                file_size = buffer_length(file)
                if not file_md5:
                    file_md5 = md5(file).hexdigest()
            elif isinstance(file, (str, PathLike)):
                path = fsdecode(file)
                if not file_name:
                    file_name = basename(path)
                if async_:
                    async def request():
                        async with async_open(path, "rb") as file:
                            setattr(file, "fileno", file.file.fileno)
                            setattr(file, "seekable", lambda: True)
                            return await do_upload(file)
                    return request
                else:
                    return do_upload(open(path, "rb"))
            elif isinstance(file, SupportsRead):
                seek = getattr(file, "seek", None)
                seekable = False
                curpos = 0
                if callable(seek):
                    if async_:
                        seek = ensure_async(seek, threaded=True)
                    try:
                        seekable = getattr(file, "seekable")()
                    except (AttributeError, TypeError):
                        try:
                            curpos = yield seek(0, 1)
                            seekable = True
                        except Exception:
                            seekable = False
                if not file_md5:
                    if not seekable:
                        fsrc = file
                        file = TemporaryFile()
                        if async_:
                            yield copyfileobj_async(fsrc, file)
                        else:
                            copyfileobj(fsrc, file)
                        file.seek(0)
                        return do_upload(file)
                    try:
                        if async_:
                            file_size, hashobj = yield file_digest_async(file)
                        else:
                            file_size, hashobj = file_digest(file)
                    finally:
                        yield seek(curpos)
                    file_md5 = hashobj.hexdigest()
                if file_size < 0:
                    try:
                        fileno = getattr(file, "fileno")()
                        file_size = fstat(fileno).st_size - curpos
                    except (AttributeError, TypeError, OSError):
                        try:
                            file_size = len(file) - curpos # type: ignore
                        except TypeError:
                            if seekable:
                                try:
                                    file_size = (yield seek(0, 2)) - curpos
                                finally:
                                    yield seek(curpos)
            elif isinstance(file, (URL, SupportsGeturl)):
                if isinstance(file, URL):
                    url = str(file)
                else:
                    url = file.geturl()
                if async_:
                    from httpfile import AsyncHttpxFileReader
                    async def request():
                        file = await AsyncHttpxFileReader.new(url)
                        async with file:
                            return await do_upload(file)
                    return request
                else:
                    from httpfile import HTTPFileReader
                    with HTTPFileReader(url) as file:
                        return do_upload(file)
            elif not file_md5 or file_size < 0:
                if async_:
                    file = bytes_iter_to_async_reader(file) # type: ignore
                else:
                    file = bytes_iter_to_reader(file) # type: ignore
                return do_upload(file)
            if not file_name:
                file_name = getattr(file, "name", "")
            if file_name:
                file_name = basename(file_name).translate(TANSTAB_CLEAN_name)
            if not file_name:
                file_name = str(uuid4())
            if file_size < 0:
                file_size = getattr(file, "length", 0)
            resp = yield self.upload_request(
                {
                    "etag": file_md5, 
                    "fileName": file_name, 
                    "size": file_size, 
                    "type": 0, 
                    "duplicate": duplicate, 
                }, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["code"]:
                return resp
            upload_data = resp["data"]
            if upload_data["Reuse"]:
                return resp
            slice_size = int(upload_data["SliceSize"])
            upload_request_kwargs = {
                **request_kwargs, 
                "method": "PUT", 
                "headers": {"authorization": ""}, 
                "parse": ..., 
            }
            if file_size > slice_size:
                upload_data["partNumberStart"] = 1
                q, r = divmod(file_size, slice_size)
                upload_data["partNumberEnd"] = q + 1 + (r > 0)
                resp = yield self.upload_prepare_parts(upload_data, async_=async_, **request_kwargs)
                check_response(resp)
                d_urls = resp["data"]["presignedUrls"]
                urls = (d_urls[str(i)] for i in range(1, len(d_urls) + 1))
                if async_:
                    async def request():
                        chunks = bio_chunk_async_iter(file, chunksize=slice_size) # type: ignore
                        async for chunk in chunks:
                            await self.request(next(urls), data=chunk, async_=True, **upload_request_kwargs)
                    yield request
                else:
                    chunks = bio_chunk_iter(file, chunksize=slice_size) # type: ignore
                    for chunk, url in zip(chunks, urls):
                        self.request(url, data=chunk, **upload_request_kwargs)
            else:
                resp = yield self.upload_auth(upload_data, async_=async_, **request_kwargs)
                check_response(resp)
                url = resp["data"]["presignedUrls"]["1"]
                yield self.request(url, data=file, async_=async_, **upload_request_kwargs)
            upload_data["isMultipart"] = file_size > slice_size
            return self.upload_complete(upload_data, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_=async_)

    @overload
    def user_info(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_info(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_info(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """（单个）改名

        GET https://www.123pan.com/a/api/user/info
        """
        api = "https://www.123pan.com/a/api/user/info"
        return self.request(url=api, method="GET", async_=async_, **request_kwargs)

    @overload
    @staticmethod
    def user_login(
        payload: dict, 
        /, 
        request: None | Callable = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    @staticmethod
    def user_login(
        payload: dict, 
        /, 
        request: None | Callable = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    @staticmethod
    def user_login(
        payload: dict, 
        /, 
        request: None | Callable = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """使用账号和密码登录

        POST https://www.123pan.com/a/api/user/sign_in

        .. note::
            获取的 token 有效期 30 天

        :payload:
            - passport: int | str   💡 手机号或邮箱
            - password: str         💡 密码
            - remember: bool = True 💡 是否记住密码（不用管）
        """
        api = "https://www.123pan.com/a/api/user/sign_in"
        request_kwargs.setdefault("parse", default_parse)
        if request is None:
            return get_default_request()(url=api, method="POST", json=payload, async_=async_, **request_kwargs)
        else:
            return request(url=api, method="POST", json=payload, **request_kwargs)

