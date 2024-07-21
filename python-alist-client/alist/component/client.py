#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["AlistClient", "check_response"]

import errno

from asyncio import to_thread
from base64 import urlsafe_b64encode
from collections.abc import AsyncIterable, Awaitable, Callable, Coroutine, Iterable, Mapping
from functools import cached_property, partial
from hashlib import sha256
from hmac import new as hmac_new
from http.cookiejar import CookieJar
from inspect import iscoroutinefunction
from json import loads
from os import fsdecode, fstat, PathLike
from typing import overload, Any, Literal, Self
from urllib.parse import quote

from asynctools import ensure_aiter, to_list
from Crypto.Hash.MD4 import MD4Hash
from filewrap import (
    bio_chunk_iter, bio_chunk_async_iter, 
    bytes_to_chunk_iter, bytes_to_chunk_async_iter, 
    Buffer, SupportsRead, 
)
from httpfile import HTTPFileReader
from http_request import complete_url, encode_multipart_data, encode_multipart_data_async, SupportsGeturl
from http_response import get_total_length, get_content_length, is_chunked
from httpx import AsyncClient, Client, Cookies, AsyncHTTPTransport, HTTPTransport
from httpx_request import request
from iterutils import run_gen_step
from multidict import CIMultiDict
from yarl import URL


parse_json = lambda _, content: loads(content)
httpx_request = partial(request, timeout=(5, 60, 60, 5))


def ed2k_hash(file: Buffer | SupportsRead[bytes]) -> tuple[int, str]:
    block_size = 1024 * 9500
    if hasattr(file, "getbuffer"):
        file = file.getbuffer()
    if isinstance(file, Buffer):
        chunk_iter = bytes_to_chunk_iter(block_size, chunksize=block_size)
    else:
        chunk_iter = bio_chunk_iter(file, chunksize=block_size, can_buffer=True)
    block_hashes = bytearray()
    filesize = 0
    for chunk in chunk_iter:
        block_hashes += MD4Hash(chunk).digest()
        filesize += len(chunk)
    if not filesize % block_size:
        block_hashes += MD4Hash().digest()
    return filesize, MD4Hash(block_hashes).hexdigest()


async def ed2k_hash_async(file: Buffer | SupportsRead[bytes]) -> tuple[int, str]:
    block_size = 1024 * 9500
    if hasattr(file, "getbuffer"):
        file = file.getbuffer()
    if isinstance(file, Buffer):
        chunk_iter = bytes_to_chunk_async_iter(block_size, chunksize=block_size)
    else:
        chunk_iter = bio_chunk_async_iter(file, chunksize=block_size, can_buffer=True)
    block_hashes = bytearray()
    filesize = 0
    async for chunk in chunk_iter:
        block_hashes += MD4Hash(chunk).digest()
        filesize += len(chunk)
    if not filesize % block_size:
        block_hashes += MD4Hash().digest()
    return filesize, MD4Hash(block_hashes).hexdigest()


@overload
def check_response(resp: dict, /) -> dict:
    ...
@overload
def check_response(resp: Awaitable[dict], /) -> Awaitable[dict]:
    ...
def check_response(resp: dict | Awaitable[dict], /) -> dict | Awaitable[dict]:
    def check(resp: dict) -> dict:
        code = resp["code"]
        if 200 <= code < 300:
            return resp
        elif code == 401:
            raise OSError(errno.EINVAL, resp)
        elif code == 403:
            raise PermissionError(errno.EACCES, resp)
        elif code == 500:
            message = resp["message"]
            if (message.endswith("object not found") 
                or message.startswith("failed get storage: storage not found")
            ):
                raise FileNotFoundError(errno.ENOENT, resp)
            elif message.endswith("not a folder"):
                raise NotADirectoryError(errno.ENOTDIR, resp)
            elif message.endswith("not a file"):
                raise IsADirectoryError(errno.EISDIR, resp)
            elif message.endswith("file exists"):
                raise FileExistsError(errno.EEXIST, resp)
            elif message.startswith("failed get "):
                raise PermissionError(errno.EPERM, resp)
        raise OSError(errno.EIO, resp)
    if isinstance(resp, dict):
        return check(resp)
    else:
        async def check_await() -> dict:
            return check(await resp)
        return check_await()


class AlistClient:
    """AList client that encapsulates web APIs

    - AList web api official documentation: https://alist.nn.ci/guide/api/
    - AList web api online tool: https://alist-v3.apifox.cn
    """
    origin: str
    username: str
    password: str
    otp_code: str

    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:5244", 
        username: str = "", 
        password: str = "", 
        otp_code: int | str = "", 
    ):
        self.__dict__.update(
            origin=complete_url(origin), 
            username=username, 
            password=password, 
            otp_code=otp_code, 
            headers = CIMultiDict({
                "Accept": "application/json, text/plain, */*", 
                "Accept-Encoding": "gzip, deflate, br, zstd", 
                "Connection": "keep-alive", 
                "User-Agent": "Mozilla/5.0 AppleWebKit/600.0 Chrome/150.0.0.0 Safari/600.0 python-alist/*.*"
            }), 
            cookies = Cookies(), 
        )
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.origin == other.origin and self.username == other.username

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self.origin!r}, username={self.username!r}, password='******')"

    def __setattr__(self, attr, val, /):
        if attr in ("username", "password", "otp_code"):
            self.__dict__[attr] = str(val)
            if attr != "username":
                self.login()
        raise TypeError(f"can't set attribute: {attr!r}")

    @cached_property
    def base_path(self, /) -> str:
        return self.get_base_path()

    @cached_property
    def session(self, /) -> Client:
        """同步请求的 session
        """
        ns = self.__dict__
        session = Client(transport=HTTPTransport(retries=5), verify=False)
        session._headers = ns["headers"]
        session._cookies = ns["cookies"]
        return session

    @cached_property
    def async_session(self, /) -> AsyncClient:
        """异步请求的 session
        """
        ns = self.__dict__
        session = AsyncClient(transport=AsyncHTTPTransport(retries=5), verify=False)
        session._headers = ns["headers"]
        session._cookies = ns["cookies"]
        return session

    @property
    def cookiejar(self, /) -> CookieJar:
        return self.__dict__["cookies"].jar

    @property
    def headers(self, /) -> CIMultiDict:
        """请求头，无论同步还是异步请求都共用这个请求头
        """
        return self.__dict__["headers"]

    @headers.setter
    def headers(self, headers, /):
        """替换请求头，如果需要更新，请用 <client>.headers.update
        """
        headers = CIMultiDict(headers)
        default_headers = self.headers
        default_headers.clear()
        default_headers.update(headers)

    def close(self, /) -> None:
        """删除 session 和 async_session，如果它们未被引用，则会被自动清理
        """
        ns = self.__dict__
        ns.pop("session", None)
        ns.pop("async_session", None)

    def request(
        self, 
        /, 
        url: str, 
        method: str = "POST", 
        async_: Literal[False, True] = False, 
        request: None | Callable = None, 
        **request_kwargs, 
    ):
        """执行 http 请求，默认为 POST 方法（因为 alist 的大部分 web api 是 POST 的）
        在线 API 文档：https://alist-v3.apifox.cn
        """
        if not url.startswith(("http://", "https://")):
            if not url.startswith("/"):
                url = "/" + url
            url = self.origin + url
        request_kwargs.setdefault("parse", parse_json)
        if request is None:
            request_kwargs["session"] = self.async_session if async_ else self.session
            return httpx_request(
                url=url, 
                method=method, 
                async_=async_, 
                **request_kwargs, 
            )
        else:
            if (headers := request_kwargs.get("headers")):
                request_kwargs["headers"] = {**self.headers, **headers}
            else:
                request_kwargs["headers"] = self.headers
            return request(
                url=url, 
                method=method, 
                **request_kwargs, 
            )

    def login(
        self, 
        /, 
        username: str = "", 
        password: str = "", 
        otp_code: int | str = "", 
        hash_password: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        ns = self.__dict__
        if username:
            ns["username"] = username
        else:
            username = ns["username"]
        if password:
            ns["password"] = password
        else:
            password = ns["password"]
        if otp_code:
            ns["otp_code"] = otp_code
        else:
            otp_code = ns["otp_code"]
        def gen_step():
            if username:
                if hash_password:
                    method = self.auth_login_hash
                    payload = {
                        "username": username, 
                        "password": sha256(f"{password}-https://github.com/alist-org/alist".encode("utf-8")).hexdigest(), 
                        "otp_code": otp_code, 
                    }
                else:
                    method = self.auth_login
                    payload = {"username": username, "password": password, "otp_code": otp_code}
                resp = yield partial(
                    method, 
                    payload, 
                    async_=async_, 
                    **request_kwargs, 
                )
                if not 200 <= resp["code"] < 300:
                    raise OSError(errno.EINVAL, resp)
                self.headers["Authorization"] = resp["data"]["token"]
            else:
                self.headers.pop("Authorization", None)
            ns.pop("base_path", None)
        return run_gen_step(gen_step, async_=async_)

    @classmethod
    def from_auth(
        cls, 
        /, 
        auth_token: str, 
        origin: str = "http://localhost:5244", 
    ) -> Self:
        client = cls(origin)
        client.headers["Authorization"] = auth_token
        return client

    @overload
    def get_base_path(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def get_base_path(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_base_path(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            resp = yield partial(self.auth_me, async_=async_)
            return resp["data"]["base_path"]
        return run_gen_step(gen_step, async_=async_)

    # [auth](https://alist.nn.ci/guide/api/auth.html)

    @overload
    def auth_login(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_login(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_login(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """token获取
        - https://alist.nn.ci/guide/api/auth.html#post-token获取
        - https://alist-v3.apifox.cn/api-128101241
        """
        return self.request(
            "/api/auth/login", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_login_hash(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_login_hash(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_login_hash(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """token获取hash
        - https://alist.nn.ci/guide/api/auth.html#post-token获取hash
        - https://alist-v3.apifox.cn/api-128101242
        """
        return self.request(
            "/api/auth/login/hash", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_2fa_generate(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_2fa_generate(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_2fa_generate(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """生成2FA密钥
        - https://alist.nn.ci/guide/api/auth.html#post-生成2fa密钥
        - https://alist-v3.apifox.cn/api-128101243
        """
        return self.request(
            "/api/auth/2fa/generate", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """验证2FA code
        - https://alist.nn.ci/guide/api/auth.html#post-验证2fa-code
        - https://alist-v3.apifox.cn/api-128101244
        """
        return self.request(
            "/api/auth/2fa/verify", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_me(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_me(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_me(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前用户信息
        - https://alist.nn.ci/guide/api/auth.html#get-获取当前用户信息
        - https://alist-v3.apifox.cn/api-128101245
        """
        return self.request(
            "/api/me", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_me_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_me_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_me_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新当前用户信息
        """
        return self.request(
            "/api/me/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [fs](https://alist.nn.ci/guide/api/fs.html)

    @overload
    def fs_list(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_list(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出文件目录
        - https://alist.nn.ci/guide/api/fs.html#post-列出文件目录
        - https://alist-v3.apifox.cn/api-128101246
        """
        return self.request(
            "/api/fs/list", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_get(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_get(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_get(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取某个文件/目录信息
        - https://alist.nn.ci/guide/api/fs.html#post-获取某个文件-目录信息
        - https://alist-v3.apifox.cn/api-128101247
        """
        return self.request(
            "/api/fs/get", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_dirs(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_dirs(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_dirs(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录
        - https://alist.nn.ci/guide/api/fs.html#post-获取目录
        - https://alist-v3.apifox.cn/api-128101248
        """
        return self.request(
            "/api/fs/dirs", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_search(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_search(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索文件或文件夹
        - https://alist.nn.ci/guide/api/fs.html#post-搜索文件或文件夹
        - https://alist-v3.apifox.cn/api-128101249
        """
        return self.request(
            "/api/fs/search", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_mkdir(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建文件夹
        - https://alist.nn.ci/guide/api/fs.html#post-新建文件夹
        - https://alist-v3.apifox.cn/api-128101250
        """
        return self.request(
            "/api/fs/mkdir", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重命名文件
        - https://alist.nn.ci/guide/api/fs.html#post-重命名文件
        - https://alist-v3.apifox.cn/api-128101251

        NOTE: AList 改名的限制：
        1. 受到网盘的改名限制，例如如果挂载的是 115，就不能包含特殊符号 " < > ，也不能改扩展名，各个网盘限制不同
        2. 可以包含斜杠  \，但是改名后，这个文件不能被删改了，因为只能被罗列，但不能单独找到
        3. 名字里（basename）中包含 /，会被替换为 |
        """
        return self.request(
            "/api/fs/rename", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_batch_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_batch_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_batch_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量重命名
        - https://alist.nn.ci/guide/api/fs.html#post-批量重命名
        - https://alist-v3.apifox.cn/api-128101252
        """
        return self.request(
            "/api/fs/batch_rename", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_regex_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_regex_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_regex_rename(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """正则重命名
        - https://alist.nn.ci/guide/api/fs.html#post-正则重命名
        - https://alist-v3.apifox.cn/api-128101253
        """
        return self.request(
            "/api/fs/regex_rename", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_move(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动文件
        - https://alist.nn.ci/guide/api/fs.html#post-移动文件
        - https://alist-v3.apifox.cn/api-128101255
        """
        return self.request(
            "/api/fs/move", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_recursive_move(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_recursive_move(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_recursive_move(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """聚合移动
        - https://alist.nn.ci/guide/api/fs.html#post-聚合移动
        - https://alist-v3.apifox.cn/api-128101259
        """
        return self.request(
            "/api/fs/recursive_move", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_copy(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """复制文件
        - https://alist.nn.ci/guide/api/fs.html#post-复制文件
        - https://alist-v3.apifox.cn/api-128101256
        """
        return self.request(
            "/api/fs/copy", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_remove(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_remove(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_remove(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除文件或文件夹
        - https://alist.nn.ci/guide/api/fs.html#post-删除文件或文件夹
        - https://alist-v3.apifox.cn/api-128101257
        """
        return self.request(
            "/api/fs/remove", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_remove_empty_directory(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_remove_empty_directory(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_remove_empty_directory(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除空文件夹
        - https://alist.nn.ci/guide/api/fs.html#post-删除空文件夹
        - https://alist-v3.apifox.cn/api-128101258
        """
        return self.request(
            "/api/fs/remove_empty_directory", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_add_offline_download(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_add_offline_download(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_add_offline_download(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加离线下载
        - https://alist.nn.ci/guide/api/fs.html#post-添加离线下载
        - https://alist-v3.apifox.cn/api-175404336
        """
        return self.request(
            "/api/fs/add_offline_download", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_form(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_form(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_form(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """表单上传文件
        - https://alist.nn.ci/guide/api/fs.html#put-表单上传文件
        - https://alist-v3.apifox.cn/api-128101254

        NOTE: AList 上传的限制：
        1. 上传文件成功不会自动更新缓存（但新增文件夹会更新缓存）
        2. 上传时路径中包含斜杠 \\，视为路径分隔符 /
        3. 这个接口不需要预先确定上传的字节数，可以真正实现流式上传
        """
        def gen_step():
            nonlocal file
            if hasattr(file, "getbuffer"):
                try:
                    file = getattr(file, "getbuffer")()
                except TypeError:
                    pass
            if isinstance(file, Buffer):
                pass
            elif isinstance(file, SupportsRead):
                if not async_ and iscoroutinefunction(file.read):
                    raise TypeError(f"{file!r} with async read in non-async mode")
            elif isinstance(file, (str, PathLike)):
                filepath = fsdecode(file)
                if async_:
                    try:
                        from aiofile import async_open
                    except ImportError:
                        file = yield to_thread(open, filepath, "rb")
                    else:
                        async def request():
                            async with async_open(filepath, "rb") as file:
                                return self.fs_form(
                                    file, 
                                    path, 
                                    as_task=as_task, 
                                    async_=True, 
                                    **request_kwargs, 
                                )
                        return (yield request)
                else:
                    file = open(filepath, "rb")
            elif isinstance(file, (URL, SupportsGeturl)):
                if isinstance(file, URL):
                    url = str(file)
                else:
                    url = file.geturl()
                if async_:
                    try:
                        from aiohttp import request as async_request
                    except ImportError:
                        async def request():
                            async with AsyncClient() as client:
                                async with client.stream("GET", url) as resp:
                                    return self.fs_put(
                                        resp.aiter_bytes(), 
                                        path, 
                                        as_task=as_task, 
                                        async_=True, 
                                        **request_kwargs, 
                                    )
                    else:
                        async def request():
                            async with async_request("GET", url) as resp:
                                return self.fs_put(
                                    resp.content, 
                                    path, 
                                    as_task=as_task, 
                                    async_=True, 
                                    **request_kwargs, 
                                )
                    return (yield request)
                else:
                    from urllib.request import urlopen

                    with urlopen(url) as resp:
                        return self.fs_put(
                            resp, 
                            path, 
                            as_task=as_task, 
                            **request_kwargs, 
                        )
            elif async_:
                file = ensure_aiter(file)
            elif isinstance(file, AsyncIterable):
                raise TypeError(f"async iterable {file!r} in non-async mode")

            if headers := request_kwargs.get("headers"):
                headers = {**headers, "File-Path": quote(path)}
            else:
                headers = {"File-Path": quote(path)}
            request_kwargs["headers"] = headers
            if as_task:
                headers["As-Task"] = "true"
            if async_:
                update_headers, request_kwargs["data"] = encode_multipart_data_async({}, {"file": file})
            else:
                update_headers, request_kwargs["data"] = encode_multipart_data({}, {"file": file})
            headers.update(update_headers)
            return (yield partial(
                self.request, 
                "/api/fs/form", 
                "PUT", 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def fs_put(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        filesize: int = -1, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_put(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        filesize: int = -1, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_put(
        self, 
        /, 
        file: ( Buffer | SupportsRead[Buffer] | str | PathLike | 
                URL | SupportsGeturl | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        filesize: int = -1, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """流式上传文件
        - https://alist.nn.ci/guide/api/fs.html#put-流式上传文件
        - https://alist-v3.apifox.cn/api-128101260

        NOTE: AList 上传的限制：
        1. 上传文件成功不会自动更新缓存（但新增文件夹会更新缓存）
        2. 上传时路径中包含斜杠 \\，视为路径分隔符 /
        3. put 接口是流式上传，但是不支持 chunked（所以在上传前，就需要能直接确定总上传的字节数）
        """
        def gen_step():
            nonlocal file, filesize
            if hasattr(file, "getbuffer"):
                try:
                    file = getattr(file, "getbuffer")()
                except TypeError:
                    pass
            if isinstance(file, Buffer):
                if filesize < 0:
                    filesize = len(file)
            elif isinstance(file, SupportsRead):
                if not async_ and iscoroutinefunction(file.read):
                    raise TypeError(f"{file!r} with async read in non-async mode")
                if filesize < 0:
                    try:
                        filesize = fstat(getattr(file, "fileno")()).st_size
                    except Exception:
                        file = yield file.read
                        filesize = len(file)
            elif isinstance(file, (str, PathLike)):
                filepath = fsdecode(file)
                if async_:
                    try:
                        from aiofile import async_open
                    except ImportError:
                        file = yield partial(to_thread, open, filepath, "rb")
                    else:
                        async def request():
                            nonlocal filesize
                            async with async_open(filepath, "rb") as file:
                                if filesize < 0:
                                    filesize = fstat(file.file.fileno()).st_size
                                return self.fs_put(
                                    file, 
                                    path, 
                                    as_task=as_task, 
                                    filesize=filesize, 
                                    async_=True, 
                                    **request_kwargs, 
                                )
                        return (yield request)
                else:
                    file = open(filepath, "rb")
                if filesize < 0:
                    filesize = fstat(file.fileno()).st_size
            elif isinstance(file, (URL, SupportsGeturl)):
                if isinstance(file, URL):
                    url = str(file)
                else:
                    url = file.geturl()
                if async_:
                    try:
                        from aiohttp import request as async_request
                    except ImportError:
                        async def request():
                            nonlocal file, filesize
                            async with AsyncClient() as client:
                                async with client.stream("GET", url) as resp:
                                    size = filesize if filesize >= 0 else get_content_length(resp)
                                    if size is None or is_chunked(resp):
                                        file = await resp.aread()
                                        filesize = len(file)
                                    else:
                                        file = resp.aiter_bytes()
                                    return self.fs_put(
                                        file, 
                                        path, 
                                        as_task=as_task, 
                                        filesize=filesize, 
                                        async_=True, 
                                        **request_kwargs, 
                                    )
                    else:
                        async def request():
                            nonlocal file, filesize
                            async with async_request("GET", url) as resp:
                                size = filesize if filesize >= 0 else get_content_length(resp)
                                if size is None or is_chunked(resp):
                                    file = await resp.read()
                                    filesize = len(file)
                                else:
                                    file = resp.content
                                return self.fs_put(
                                    file, 
                                    path, 
                                    as_task=as_task, 
                                    filesize=filesize, 
                                    async_=True, 
                                    **request_kwargs, 
                                )
                    return (yield request)
                else:
                    from urllib.request import urlopen

                    with urlopen(url) as resp:
                        size = filesize if filesize >= 0 else get_content_length(resp)
                        if size is None or is_chunked(resp):
                            file = resp.read()
                            filesize = len(file)
                        else:
                            file = resp
                        return self.fs_put(
                            file, 
                            path, 
                            as_task=as_task, 
                            filesize=filesize, 
                            **request_kwargs, 
                        )
            elif async_:
                if filesize < 0:
                    chunks = yield partial(to_list, file)
                    filesize = sum(map(len, chunks))
                    file = ensure_aiter(chunks)
                else:
                    file = ensure_aiter(file)
            elif isinstance(file, AsyncIterable):
                raise TypeError(f"async iterable {file!r} in non-async mode")
            elif filesize < 0:
                chunks = list(file)
                filesize = sum(map(len, chunks))
                file = iter(chunks)

            if headers := request_kwargs.get("headers"):
                headers = {**headers, "File-Path": quote(path)}
            else:
                headers = {"File-Path": quote(path)}
            request_kwargs["headers"] = headers
            if as_task:
                headers["As-Task"] = "true"
            headers["Content-Length"] = str(filesize)

            if hasattr(file, "read"):
                if async_:
                    file = bio_chunk_async_iter(file)
                else:
                    file = bio_chunk_iter(file)
            request_kwargs["data"] = file

            return (yield partial(
                self.request, 
                "/api/fs/put", 
                "PUT", 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    # [public](https://alist.nn.ci/guide/api/public.html)

    @overload
    def public_settings(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def public_settings(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def public_settings(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取站点设置
        - https://alist.nn.ci/guide/api/public.html#get-获取站点设置
        - https://alist-v3.apifox.cn/api-128101263
        """
        return self.request(
            "/api/public/settings", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def public_ping(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def public_ping(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def public_ping(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        """ping检测
        - https://alist.nn.ci/guide/api/public.html#get-ping检测
        - https://alist-v3.apifox.cn/api-128101264
        """
        return self.request(
            "/ping", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin](https://alist.nn.ci/guide/api/admin/)

    # [admin/meta](https://alist.nn.ci/guide/api/admin/meta.html)

    @overload
    def admin_meta_list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出元信息
        - https://alist.nn.ci/guide/api/admin/meta.html#get-列出元信息
        - https://alist-v3.apifox.cn/api-128101265
        """
        return self.request(
            "/api/admin/meta/list", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_meta_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取元信息
        - https://alist.nn.ci/guide/api/admin/meta.html#get-获取元信息
        - https://alist-v3.apifox.cn/api-128101266
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/meta/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_meta_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新增元信息
        - https://alist.nn.ci/guide/api/admin/meta.html#post-新增元信息
        - https://alist-v3.apifox.cn/api-128101267
        """
        return self.request(
            "/api/admin/meta/create", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_meta_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新元信息
        - https://alist.nn.ci/guide/api/admin/meta.html#post-更新元信息
        - https://alist-v3.apifox.cn/api-128101268
        """
        return self.request(
            "/api/admin/meta/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_meta_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除元信息
        - https://alist.nn.ci/guide/api/admin/meta.html#post-删除元信息
        - https://alist-v3.apifox.cn/api-128101269
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/meta/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/user](https://alist.nn.ci/guide/api/admin/user.html)

    @overload
    def admin_user_list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出所有用户
        - https://alist.nn.ci/guide/api/admin/user.html#get-列出所有用户
        - https://alist-v3.apifox.cn/api-128101270
        """
        return self.request(
            "/api/admin/user/list", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出某个用户
        - https://alist.nn.ci/guide/api/admin/user.html#get-列出某个用户
        - https://alist-v3.apifox.cn/api-128101271
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/user/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建用户
        - https://alist.nn.ci/guide/api/admin/user.html#post-新建用户
        - https://alist-v3.apifox.cn/api-128101272
        """
        return self.request(
            "/api/admin/user/create", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新用户信息
        - https://alist.nn.ci/guide/api/admin/user.html#post-更新用户信息
        - https://alist-v3.apifox.cn/api-128101273
        """
        return self.request(
            "/api/admin/user/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_cancel_2fa(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_cancel_2fa(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_cancel_2fa(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消某个用户的两步验证
        - https://alist.nn.ci/guide/api/admin/user.html#post-取消某个用户的两步验证
        - https://alist-v3.apifox.cn/api-128101274
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/user/cancel_2fa", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除用户
        - https://alist.nn.ci/guide/api/admin/user.html#post-删除用户
        - https://alist-v3.apifox.cn/api-128101275
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/user/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_del_cache(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_del_cache(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_del_cache(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除用户缓存
        - https://alist.nn.ci/guide/api/admin/user.html#post-删除用户缓存
        - https://alist-v3.apifox.cn/api-128101276
        """
        if isinstance(payload, str):
            payload = {"username": payload}
        return self.request(
            "/api/admin/user/del_cache", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/storage](https://alist.nn.ci/guide/api/admin/storage.html)

    @overload
    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """创建存储
        - https://alist.nn.ci/guide/api/admin/storage.html#post-创建存储
        - https://alist-v3.apifox.cn/api-175457115
        """
        return self.request(
            "/api/admin/storage/create", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新存储
        - https://alist.nn.ci/guide/api/admin/storage.html#post-更新存储
        - https://alist-v3.apifox.cn/api-175457877
        """
        return self.request(
            "/api/admin/storage/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_storage_list(
        self, 
        /, 
        payload: dict = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_list(
        self, 
        /, 
        payload: dict = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_list(
        self, 
        /, 
        payload: dict = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出存储列表
        - https://alist.nn.ci/guide/api/admin/storage.html#get-列出存储列表
        - https://alist-v3.apifox.cn/api-128101277
        """
        return self.request(
            "/api/admin/storage/list", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_storage_enable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_enable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_enable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """启用存储
        - https://alist.nn.ci/guide/api/admin/storage.html#post-启用存储
        - https://alist-v3.apifox.cn/api-128101278
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/enable", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_storage_disable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_disable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_disable(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """禁用存储
        - https://alist.nn.ci/guide/api/admin/storage.html#post-禁用存储
        - https://alist-v3.apifox.cn/api-128101279
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/disable", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_storage_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_get(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询指定存储信息
        - https://alist.nn.ci/guide/api/admin/storage.html#get-查询指定存储信息
        - https://alist-v3.apifox.cn/api-128101281
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_storage_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除指定存储
        - https://alist.nn.ci/guide/api/admin/storage.html#post-删除指定存储
        - https://alist-v3.apifox.cn/api-128101282
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/storage/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_storage_load_all(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_load_all(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_load_all(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重新加载所有存储
        - https://alist.nn.ci/guide/api/admin/storage.html#post-重新加载所有存储
        - https://alist-v3.apifox.cn/api-128101283
        """
        return self.request(
            "/api/admin/storage/load_all", 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/driver](https://alist.nn.ci/guide/api/admin/driver.html)

    @overload
    def admin_driver_list(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_driver_list(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_driver_list(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询所有驱动配置模板列表
        - https://alist.nn.ci/guide/api/admin/driver.html#get-查询所有驱动配置模板列表
        - https://alist-v3.apifox.cn/api-128101284
        """
        return self.request(
            "/api/admin/driver/list", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_driver_names(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_driver_names(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_driver_names(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出驱动名列表
        - https://alist.nn.ci/guide/api/admin/driver.html#get-列出驱动名列表
        - https://alist-v3.apifox.cn/api-128101285
        """
        return self.request(
            "/api/admin/driver/names", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_driver_info(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_driver_info(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_driver_info(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出特定驱动信息
        - https://alist.nn.ci/guide/api/admin/driver.html#get-列出特定驱动信息
        - https://alist-v3.apifox.cn/api-128101286
        """
        if isinstance(payload, str):
            payload = {"driver": payload}
        return self.request(
            "/api/admin/driver/info", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/setting](https://alist.nn.ci/guide/api/admin/setting.html)

    @overload
    def admin_setting_list(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_list(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_list(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出设置
        - https://alist.nn.ci/guide/api/admin/setting.html#get-列出设置
        - https://alist-v3.apifox.cn/api-128101287

        group 参数的说明：
            0: 其他，包括 令牌 和 索引统计（非设置）
            1: 站点
            2: 样式
            3: 预览
            4: 全局
            5: aria2 和 qbittorrent
            6: 索引
            7: 单点登录
            8: LDAP
            9: S3 存储桶
        """
        return self.request(
            "/api/admin/setting/list", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_setting_get(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_get(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_get(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取某项设置
        - https://alist.nn.ci/guide/api/admin/setting.html#get-获取某项设置
        - https://alist-v3.apifox.cn/api-128101288
        """
        return self.request(
            "/api/admin/setting/get", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_setting_save(
        self, 
        /, 
        payload: list[dict], 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_save(
        self, 
        /, 
        payload: list[dict], 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_save(
        self, 
        /, 
        payload: list[dict], 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """保存设置
        - https://alist.nn.ci/guide/api/admin/setting.html#post-保存设置
        - https://alist-v3.apifox.cn/api-128101289
        """
        return self.request(
            "/api/admin/setting/save", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_setting_delete(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_delete(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_delete(
        self, 
        /, 
        payload: str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除设置
        - https://alist.nn.ci/guide/api/admin/setting.html#post-删除设置
        - https://alist-v3.apifox.cn/api-128101290
        """
        if isinstance(payload, str):
            payload = {"key": payload}
        return self.request(
            "/api/admin/setting/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_setting_reset_token(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_reset_token(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_reset_token(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重置令牌
        - https://alist.nn.ci/guide/api/admin/setting.html#post-重置令牌
        - https://alist-v3.apifox.cn/api-128101291
        """
        return self.request(
            "/api/admin/setting/reset_token", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_setting_set_aria2(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_set_aria2(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_set_aria2(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置aria2
        - https://alist.nn.ci/guide/api/admin/setting.html#post-设置aria2
        - https://alist-v3.apifox.cn/api-128101292
        """
        return self.request(
            "/api/admin/setting/set_aria2", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_setting_set_qbit(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_set_qbit(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_set_qbit(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置qBittorrent
        - https://alist.nn.ci/guide/api/admin/setting.html#post-设置qbittorrent
        - https://alist-v3.apifox.cn/api-128101293
        """
        return self.request(
            "/api/admin/setting/set_qbit", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/task](https://alist.nn.ci/guide/api/admin/task.html)

    @overload
    def admin_task_upload_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取任务信息
        - https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息
        - https://alist-v3.apifox.cn/api-142468741
        """
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/upload/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取已完成任务
        - https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务
        - https://alist-v3.apifox.cn/api-128101294
        """
        return self.request(
            "/api/admin/task/upload/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取未完成任务
        - https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务
        - https://alist-v3.apifox.cn/api-128101295
        """
        return self.request(
            "/api/admin/task/upload/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除任务
        - https://alist.nn.ci/guide/api/admin/task.html#post-删除任务
        - https://alist-v3.apifox.cn/api-128101296
        """
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/upload/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消任务
        - https://alist.nn.ci/guide/api/admin/task.html#post-取消任务
        - https://alist-v3.apifox.cn/api-128101297
        """
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/upload/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重试任务
        - https://alist.nn.ci/guide/api/admin/task.html#post-重试任务
        - https://alist-v3.apifox.cn/api-128101298
        """
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/upload/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重试已失败任务
        - https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务
        """
        return self.request(
            "/api/admin/task/upload/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清除已完成任务
        - https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务
        - https://alist-v3.apifox.cn/api-128101299
        """
        return self.request(
            "/api/admin/task/upload/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_upload_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_upload_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_upload_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清除已成功任务
        - https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务
        - https://alist-v3.apifox.cn/api-128101300
        """
        return self.request(
            "/api/admin/task/upload/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/copy/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/copy/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/copy/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/copy/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/copy/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/copy/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务"
        return self.request(
            "/api/admin/task/copy/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/copy/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_copy_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_copy_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_copy_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/copy/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_down/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/aria2_down/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/aria2_down/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_down/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_down/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_down/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务"
        return self.request(
            "/api/admin/task/aria2_down/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/aria2_down/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_down_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_down_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_down_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/aria2_down/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_transfer/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/aria2_transfer/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/aria2_transfer/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_transfer/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_transfer/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/aria2_transfer/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务"
        return self.request(
            "/api/admin/task/aria2_transfer/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/aria2_transfer/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_aria2_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_aria2_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_aria2_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/aria2_transfer/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_down/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/qbit_down/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/qbit_down/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_down/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_down/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_down/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务"
        return self.request(
            "/api/admin/task/qbit_down/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/qbit_down/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_down_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_down_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_down_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/qbit_down/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_transfer/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/qbit_transfer/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/qbit_transfer/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_transfer/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_transfer/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/qbit_transfer/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务"
        return self.request(
            "/api/admin/task/qbit_transfer/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/qbit_transfer/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_qbit_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_qbit_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_qbit_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/qbit_transfer/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/offline_download/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/offline_download/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务"
        return self.request(
            "/api/admin/task/offline_download/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/offline_download/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/offline_download/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_info(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-获取任务信息"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download_transfer/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取已完成任务"
        return self.request(
            "/api/admin/task/offline_download_transfer/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_undone(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_undone(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_undone(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#get-获取未完成任务"
        return self.request(
            "/api/admin/task/offline_download_transfer/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_delete(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-删除任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download_transfer/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_cancel(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-取消任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download_transfer/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_retry(
        self, 
        /, 
        payload: int | str | dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试任务"
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        return self.request(
            "/api/admin/task/offline_download_transfer/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_retry_failed(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-重试已失败任务"
        return self.request(
            "/api/admin/task/offline_download_transfer/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_clear_done(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_clear_done(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_clear_done(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已完成任务"
        return self.request(
            "/api/admin/task/offline_download_transfer/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_task_offline_download_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_task_offline_download_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_task_offline_download_transfer_clear_succeeded(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "https://alist.nn.ci/guide/api/admin/task.html#post-清除已成功任务"
        return self.request(
            "/api/admin/task/offline_download_transfer/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    # Undocumented

    @overload
    def admin_index_progress(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_progress(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_progress(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "索引构建进度"
        return self.request(
            "/api/admin/index/progress", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_index_build(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_build(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_build(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "重建索引"
        return self.request(
            "/api/admin/index/build", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_index_clear(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_clear(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_clear(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "清除索引"
        return self.request(
            "/api/admin/index/clear", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_index_stop(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_stop(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_stop(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "停止索引"
        return self.request(
            "/api/admin/index/stop", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_index_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_update(
        self, 
        /, 
        payload: dict, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        "更新索引"
        return self.request(
            "/api/admin/index/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    ########## Other Encapsulations ##########

    @staticmethod
    def calc_sign(
        text: str, 
        token: str, 
        suffix: str = "", 
    ) -> str:
        h = hmac_new(bytes(token, "utf-8"), digestmod=sha256)
        h.update(bytes(f"{text}{suffix}", "utf-8"))
        return urlsafe_b64encode(h.digest()).decode() + f"{suffix}"

    def get_url(
        self, 
        /, 
        path: str, 
        sign: str = "", 
        token: str = "", 
        expire_timestamp: int = 0, 
        ensure_ascii: bool = True, 
    ) -> str:
        """获取下载链接（非直链）
        - https://alist.nn.ci/guide/drivers/common.html#download-proxy-url
        """
        if self.base_path != "/":
            path = self.base_path + path
        if ensure_ascii:
            url = self.origin + "/d" + quote(path, safe="@[]:/!$&'()*+,;=")
        else:
            url = self.origin + "/d" + path.translate({0x23: "%23", 0x3F: "%3F"})
        if sign:
            url += "?sign=" + sign
        elif token:
            url += "?sign=" + self.calc_sign(path, token, f":{expire_timestamp}")
        return url

    # TODO: 支持异步
    def open(
        self, 
        /, 
        url: str | Callable[[], str], 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> HTTPFileReader:
        """打开下载链接，返回可读的文件对象
        """
        if async_:
            raise NotImplementedError("asynchronous mode not implemented")
        if headers is None:
            headers = self.headers
        else:
            headers = {**self.headers, **headers}
        return HTTPFileReader(
            url, 
            headers=headers, 
            start=start, 
            seek_threshold=seek_threshold, 
        )

    @overload
    def ed2k(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        name: str = "", 
        *, 
        async_: Literal[False] = False, 
    ) -> str:
        ...
    @overload
    def ed2k(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        name: str = "", 
        *, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, str]:
        ...
    def ed2k(
        self, 
        /, 
        url: str | Callable[[], str], 
        headers: None | Mapping = None, 
        name: str = "", 
        *, 
        async_: Literal[False, True] = False, 
    ) -> str | Coroutine[Any, Any, str]:
        trantab = dict(zip(b"/|", ("%2F", "%7C")))
        if async_:
            async def request():
                async with self.open(url, headers=headers, async_=True) as file: # type: ignore
                    length, ed2k = await ed2k_hash_async(file)
                return f"ed2k://|file|{(name or file.name).translate(trantab)}|{length}|{ed2k}|/"
            return request()
        else:
            with self.open(url, headers=headers) as file:
                length, ed2k = ed2k_hash(file)
            return f"ed2k://|file|{(name or file.name).translate(trantab)}|{length}|{ed2k}|/"

    @overload
    def read_bytes(
        self, 
        /, 
        url: str, 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_bytes(
        self, 
        /, 
        url: str, 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes(
        self, 
        /, 
        url: str, 
        start: int = 0, 
        stop: None | int = None, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """读取文件一定索引范围的数据
        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param start: 开始索引，可以为负数（从文件尾部开始）
        :param stop: 结束索引（不含），可以为负数（从文件尾部开始）
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        def gen_step():
            def get_bytes_range(start, stop):
                if start < 0 or (stop and stop < 0):
                    length: int = yield self.read_bytes_range(
                        url, 
                        bytes_range="-1", 
                        headers=headers, 
                        async_=async_, 
                        **{**request_kwargs, "parse": lambda resp: get_total_length(resp)}, 
                    )
                    if start < 0:
                        start += length
                    if start < 0:
                        start = 0
                    if stop is None:
                        return f"{start}-"
                    elif stop < 0:
                        stop += length
                if start >= stop:
                    return None
                return f"{start}-{stop-1}"
            bytes_range = yield from get_bytes_range(start, stop)
            if not bytes_range:
                return b""
            return (yield partial(
                self.read_bytes_range, 
                url, 
                bytes_range=bytes_range, 
                headers=headers, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @overload
    def read_bytes_range(
        self, 
        /, 
        url: str, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_bytes_range(
        self, 
        /, 
        url: str, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_bytes_range(
        self, 
        /, 
        url: str, 
        bytes_range: str = "0-", 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """读取文件一定索引范围的数据
        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param bytes_range: 索引范围，语法符合 [HTTP Range Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests)
        :param headers: 请求头
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        if headers:
            headers = {**headers, "Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        else:
            headers = {"Accept-Encoding": "identity", "Range": f"bytes={bytes_range}"}
        request_kwargs["headers"] = headers
        request_kwargs.setdefault("method", "GET")
        request_kwargs.setdefault("parse", False)
        return self.request(url, async_=async_, **request_kwargs)

    @overload
    def read_block(
        self, 
        /, 
        url: str, 
        size: int = 0, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_block(
        self, 
        /, 
        url: str, 
        size: int = 0, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_block(
        self, 
        /, 
        url: str, 
        size: int = 0, 
        offset: int = 0, 
        headers: None | Mapping = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """读取文件一定索引范围的数据
        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）
        :param size: 下载字节数（最多下载这么多字节，如果遇到 EOF，就可能较小）
        :param offset: 偏移索引，从 0 开始，可以为负数（从文件尾部开始）
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        def gen_step():
            if size <= 0:
                return b""
            return (yield self.read_bytes(
                url, 
                start=offset, 
                stop=offset+size, 
                headers=headers, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_=async_)

    @cached_property
    def fs(self, /) -> AlistFileSystem:
        return AlistFileSystem(self)

    @cached_property
    def copy_tasklist(self, /) -> AlistCopyTaskList:
        return AlistCopyTaskList(self)

    @cached_property
    def offline_download_tasklist(self, /) -> AlistOfflineDownloadTaskList:
        return AlistOfflineDownloadTaskList(self)

    @cached_property
    def offline_download_transfer_tasklist(self, /) -> AlistOfflineDownloadTransferTaskList:
        return AlistOfflineDownloadTransferTaskList(self)

    @cached_property
    def upload_tasklist(self, /) -> AlistUploadTaskList:
        return AlistUploadTaskList(self)

    @cached_property
    def aria2_down_tasklist(self, /) -> AlistAria2DownTaskList:
        return AlistAria2DownTaskList(self)

    @cached_property
    def aria2_transfer_tasklist(self, /) -> AlistAria2TransferTaskList:
        return AlistAria2TransferTaskList(self)

    @cached_property
    def qbit_down_tasklist(self, /) -> AlistQbitDownTaskList:
        return AlistQbitDownTaskList(self)

    @cached_property
    def qbit_transfer_tasklist(self, /) -> AlistQbitTransferTaskList:
        return AlistQbitTransferTaskList(self)


from .fs import AlistFileSystem
from .admin.task import (
    AlistCopyTaskList, AlistOfflineDownloadTaskList, 
    AlistOfflineDownloadTransferTaskList, AlistUploadTaskList, 
    AlistAria2DownTaskList, AlistAria2TransferTaskList, 
    AlistQbitDownTaskList, AlistQbitTransferTaskList, 
)

