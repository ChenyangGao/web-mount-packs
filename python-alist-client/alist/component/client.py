#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["check_response", "AlistClient"]

import errno

from asyncio import to_thread
from base64 import urlsafe_b64encode
from collections.abc import (
    AsyncIterable, Awaitable, Callable, Coroutine, Iterable, Mapping, MutableMapping, Sized
)
from functools import cached_property, partial
from hashlib import sha256
from hmac import new as hmac_new
from http.cookiejar import CookieJar
from inspect import iscoroutinefunction
from os import fsdecode, fstat, PathLike
from typing import cast, overload, Any, Literal, Self
from urllib.parse import quote

from asynctools import ensure_aiter, to_list
from ed2k import ed2k_hash, ed2k_hash_async
from filewrap import (
    bio_chunk_iter, bio_chunk_async_iter, 
    Buffer, SupportsRead, 
)
from httpfile import HTTPFileReader
from http_request import complete_url, encode_multipart_data, encode_multipart_data_async, SupportsGeturl
from http_response import get_total_length, get_content_length, is_chunked
from iterutils import run_gen_step
from property import locked_cacheproperty
from yarl import URL


# 默认的请求函数
_httpx_request = None


def get_default_request():
    global _httpx_request
    if _httpx_request is None:
        from httpx_request import request
        _httpx_request = partial(request, timeout=(5, 60, 60, 5))
    return _httpx_request


def default_parse(_, content: Buffer, /):
    from orjson import loads
    if isinstance(content, (bytes, bytearray, memoryview)):
        return loads(content)
    else:
        return loads(memoryview(content))


def dict_merge_update(m: dict, /, *ms: dict, **kwargs) -> dict:
    for m2 in (*ms, kwargs):
        if m2:
            for k in m2.keys() - m.keys():
                m[k] = m2[k]
    return m


@overload
def check_response(resp: dict, /, **extras) -> dict:
    ...
@overload
def check_response(resp: Awaitable[dict], /, **extras) -> Awaitable[dict]:
    ...
def check_response(resp: dict | Awaitable[dict], /, **extras) -> dict | Awaitable[dict]:
    def check(resp: dict) -> dict:
        code = resp["code"]
        message = resp.get("message", "")
        if extras:
            resp.update(extras)
        if 200 <= code < 300:
            return resp
        elif code == 401:
            raise OSError(errno.EINVAL, resp)
        elif code == 403:
            raise PermissionError(errno.EACCES, resp)
        elif code == 500:
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
    """AList（以及 openlist）客户端，封装所有 web 接口

    .. caution::
        有些接口是没有官方文档的

    - Router.go: https://github.com/AlistGo/alist/blob/main/server/router.go
    - AList web api official documentation: https://docs.oplist.org/guide/api/
    - AList web api online tool: https://openlist.apifox.cn
    """
    base_url: str
    username: str
    password: str
    otp_code: str

    def __init__(
        self, 
        /, 
        base_url: str = "http://localhost:5244", 
        username: str = "", 
        password: str = "", 
        otp_code: int | str = "", 
    ):
        self.__dict__.update(
            base_url=complete_url(base_url), 
            username=username, 
            password=password, 
            otp_code=otp_code, 
        )
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return (
            self is other or (
                type(self) is type(other) and 
                self.base_url == other.base_url and 
                self.username == other.username
            )
        )

    def __hash__(self, /) -> int:
        return id(self)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(base_url={self.base_url!r}, username={self.username!r}, password='******')"

    @locked_cacheproperty
    def cookies(self, /):
        """请求所用的 Cookies 对象（同步和异步共用）
        """
        from httpx import Cookies
        return Cookies()

    @locked_cacheproperty
    def headers(self, /) -> MutableMapping:
        """请求头，无论同步还是异步请求都共用这个请求头
        """
        from multidict import CIMultiDict
        return CIMultiDict({
            "accept": "application/json, text/plain, */*", 
            "accept-encoding": "gzip, deflate, br, zstd", 
            "connection": "keep-alive", 
            "user-agent": "Mozilla/5.0 AppleWebKit/600.0 Chrome/150.0.0.0 Safari/600.0", 
        })

    @property
    def cookiejar(self, /) -> CookieJar:
        """请求所用的 CookieJar 对象（同步和异步共用）
        """
        return self.cookies.jar

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

    @cached_property
    def base_path(self, /) -> str:
        return self.get_base_path()

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
        request: None | Callable = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        """执行 http 请求，默认为 POST 方法（因为 alist 的大部分 web api 是 POST 的）
        在线 API 文档：https://openlist.apifox.cn
        """
        if not url.startswith(("http://", "https://")):
            if not url.startswith("/"):
                url = "/api/" + url
            url = self.base_url + url
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
        base_url: str = "http://localhost:5244", 
    ) -> Self:
        client = cls(base_url)
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
            resp = yield partial(self.me, async_=async_)
            return resp["data"]["base_path"]
        return run_gen_step(gen_step, async_=async_)

    # [auth](https://docs.oplist.org/guide/api/auth.html)

    @overload
    def auth_login(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_login(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_login(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """token获取

        - https://docs.oplist.org/guide/api/auth.html#post-token获取
        - https://openlist.apifox.cn/api-128101241

        :payload:
            - username: str 💡 用户名
            - password: str = <default> 💡 密码
            - otp_code: str = <default> 💡 二步验证码
        """
        if not isinstance(payload, dict):
            payload = {"username": payload, "password": ""}
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_login_hash(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_login_hash(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """token获取hash

        - https://docs.oplist.org/guide/api/auth.html#post-token获取hash
        - https://openlist.apifox.cn/api-128101242

        :payload:
            - username: str 💡 用户名
            - password: str = <default> 💡 密码签名，计算方式为：

                .. code:: python

                    hashlib.sha256(f"{password}-https://github.com/alist-org/alist".encode("utf-8")).hexdigest()

            - otp_code: str = <default> 💡 二步验证码
        """
        if not isinstance(payload, dict):
            payload = {
                "username": payload, 
                "password": "263d6a3a1bc3780769ef456641d81a41ea52b66dd25fe02b5959967fd852127d", 
            }
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_2fa_generate(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_2fa_generate(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """生成2FA密钥

        - https://docs.oplist.org/guide/api/auth.html#post-生成2fa密钥
        - https://openlist.apifox.cn/api-128101243
        """
        return self.request(
            "/api/auth/2fa/generate", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_2fa_verify(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """验证2FA code

        - https://docs.oplist.org/guide/api/auth.html#post-验证2fa-code
        - https://openlist.apifox.cn/api-128101244

        :payload:
            - code: str   💡 2FA 验证码
            - secret: str 💡 2FA 密钥
        """
        return self.request(
            "/api/auth/2fa/verify", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_logout(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_logout(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_logout(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """退出登录

        （没有文档）
        """
        return self.request(
            "/api/auth/logout", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_login_ldap(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_login_ldap(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_login_ldap(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """LDAP 登录

        （没有文档）
        """
        return self.request(
            "/auth/login/ldap", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_sso(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_sso(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_sso(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """认证单点登录

        （没有文档）
        """
        return self.request(
            "/api/auth/sso", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_sso_callback(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_sso_callback(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_sso_callback(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """认证单点登录回调

        （没有文档）
        """
        return self.request(
            "/api/auth/sso_callback", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_get_sso_id(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_get_sso_id(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_get_sso_id(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取单点登录 id

        （没有文档）
        """
        return self.request(
            "/api/auth/get_sso_id", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def auth_sso_get_token(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def auth_sso_get_token(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def auth_sso_get_token(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取单点登录令牌

        （没有文档）
        """
        return self.request(
            "/api/auth/sso_get_token", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def me(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def me(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def me(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前用户信息

        - https://docs.oplist.org/guide/api/auth.html#get-获取当前用户信息
        - https://openlist.apifox.cn/api-128101245
        """
        return self.request(
            "/api/me", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def me_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def me_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def me_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新当前用户信息

        :payload:
            - username: str = <default> 💡 用户名
            - password: str = <default> 💡 密码
            - sso_id: str   = <default> 💡 单点登录 id

        （没有文档）
        """
        return self.request(
            "/api/me/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def me_sshkey_list(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def me_sshkey_list(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def me_sshkey_list(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出当前用户 SFTP 公钥

        - https://docs.oplist.org/guide/api/auth.html#get-列出当前用户-sftp-公钥
        """
        return self.request(
            "/api/me/sshkey/list", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def me_sshkey_add(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def me_sshkey_add(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def me_sshkey_add(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """给当前用户添加 SFTP 公钥

        - https://docs.oplist.org/guide/api/auth.html#post-给当前用户添加-sftp-公钥

        :payload:
            - title: str 💡 公钥名
            - key: str   💡 公钥内容
        """
        if not isinstance(payload, dict):
            method, _, name = payload.split(" ", 2)
            payload = {"title": f"{method} {name}", "key": payload}
        return self.request(
            "/api/me/sshkey/add", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def me_sshkey_delete(
        self, 
        /, 
        payload: dict | int, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def me_sshkey_delete(
        self, 
        /, 
        payload: dict | int, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def me_sshkey_delete(
        self, 
        /, 
        payload: dict | int, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除当前用户的 SFTP 公钥

        - https://docs.oplist.org/guide/api/auth.html#post-删除当前用户的-sftp-公钥

        :payload:
            - id: int 💡 公钥主键
        """
        if not isinstance(payload, dict):
            payload = {"id": payload}
        return self.request(
            "/api/me/sshkey/delete", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def authn_webauthn_begin_registration(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def authn_webauthn_begin_registration(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def authn_webauthn_begin_registration(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """WebAuthn 开始注册

        （没有文档）
        """
        return self.request(
            "/api/authn/webauthn_begin_registration", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def authn_webauthn_finish_registration(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def authn_webauthn_finish_registration(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def authn_webauthn_finish_registration(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """WebAuthn 结束注册

        （没有文档）
        """
        return self.request(
            "/api/authn/webauthn_finish_registration", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def authn_webauthn_begin_login(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def authn_webauthn_begin_login(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def authn_webauthn_begin_login(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """WebAuthn 开始登录

        （没有文档）
        """
        return self.request(
            "/api/authn/webauthn_begin_login", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def authn_webauthn_finish_login(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def authn_webauthn_finish_login(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def authn_webauthn_finish_login(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """WebAuthn 结束登录

        （没有文档）
        """
        return self.request(
            "/api/authn/webauthn_finish_login", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def authn_getcredentials(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def authn_getcredentials(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def authn_getcredentials(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """WebAuthn 获取授权

        （没有文档）
        """
        return self.request(
            "/api/authn/getcredentials", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def authn_delete_authn(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def authn_delete_authn(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def authn_delete_authn(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """WebAuthn 删除授权

        （没有文档）
        """
        return self.request(
            "/api/authn/delete_authn", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [fs](https://docs.oplist.org/guide/api/fs.html)

    @overload
    def fs_archive_decompress(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_archive_decompress(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_archive_decompress(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """压缩包解压

        :payload:
            - src_dir: str    💡 压缩文件所在目录
            - dst_dir: str    💡 解压到目标目录
            - name: list[str] 💡 待压缩到文件名列表
            - archive_pass: str = "" 💡 解压密码
            - inner_path: str = "/"  💡 压缩包内目录
            - cache_full: bool = False 💡 是否缓存完整文件
            - put_into_new_dir: bool = False 💡 是否解压到新子文件夹

        （没有文档）
        """
        if not isinstance(payload, dict):
            payload = {"path": payload}
        return self.request(
            "/api/fs/archive/decompress", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_link(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_link(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_link(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件的下载链接（可能和 /api/fs/get 得到的链接不同）

        :payload:
            - path: str
            - password: str = ""

        （没有文档）
        """
        if not isinstance(payload, dict):
            payload = {"path": payload}
        return self.request(
            "/api/fs/link", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_other(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_other(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_other(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """（没有文档）
        """
        return self.request(
            "/api/fs/other", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_list(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_list(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_list(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出文件目录

        - https://docs.oplist.org/guide/api/fs.html#post-列出文件目录
        - https://openlist.apifox.cn/api-128101246

        :payload:
            - path: str 💡 路径
            - password: str = "" 💡 密码
            - page: int = 1 💡 页数
            - per_page: int = 0 💡 每页数目
            - refresh: bool = False 💡 是否强制刷新
        """
        if not isinstance(payload, dict):
            payload = {"path": payload}
        dict_merge_update(payload, page=1, per_page=0, refresh=False)        
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_get(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_get(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取某个文件/目录信息

        - https://docs.oplist.org/guide/api/fs.html#post-获取某个文件-目录信息
        - https://openlist.apifox.cn/api-128101247

        :payload:
            - path: str 💡 路径
            - password: str = "" 💡 密码
            - refresh: bool = False 💡 是否强制刷新
        """
        if not isinstance(payload, dict):
            payload = {"path": payload}
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_dirs(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_dirs(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录

        - https://docs.oplist.org/guide/api/fs.html#post-获取目录
        - https://openlist.apifox.cn/api-128101248

        :payload:
            - path: str 💡 路径
            - password: str = "" 💡 密码
            - force_root: bool = False
        """
        if not isinstance(payload, dict):
            payload = {"path": payload}
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_search(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索文件或文件夹

        - https://docs.oplist.org/guide/api/fs.html#post-搜索文件或文件夹
        - https://openlist.apifox.cn/api-128101249

        :payload:
            - keywords: str 💡 关键词
            - parent: str = "/" 💡 搜索目录
            - scope: 0 | 1 | 2 = 0 💡 范围：0:全部 1:文件夹 2:文件
            - page: int = 1 💡 页数
            - per_page: int = 0 💡 每页数目
            - password: str = "" 💡 密码
        """
        if not isinstance(payload, dict):
            payload = {"keywords": payload}
        dict_merge_update(payload, parent="/", page=1, per_page=0)  
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建文件夹

        - https://docs.oplist.org/guide/api/fs.html#post-新建文件夹
        - https://openlist.apifox.cn/api-128101250

        :payload:
            - path: str 💡 新目录路径
        """
        if not isinstance(payload, dict):
            payload = {"path": payload}
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重命名文件

        - https://docs.oplist.org/guide/api/fs.html#post-重命名文件
        - https://openlist.apifox.cn/api-128101251

        .. note:: 
            一些限制：

            1. 受到网盘的改名限制，例如如果挂载的是 115，就不能包含特殊符号 " < > ，也不能改扩展名，各个网盘限制不同
            2. 可以包含反斜杠 \\，但是改名后，这个文件不能被删改了，因为只能被罗列，但不能单独找到
            3. 名字里（basename）中包含 /，会被替换为 |

        :payload:
            - name: str 💡 目标文件名
            - path: str 💡 源文件路径
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_batch_rename(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_batch_rename(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量重命名

        - https://docs.oplist.org/guide/api/fs.html#post-批量重命名
        - https://openlist.apifox.cn/api-128101252

        :payload:
            - src_dir: str 💡 源目录
            - rename_objects: list[RenameObject] 💡 改名列表

                .. code:: python

                    RenameObject = {
                        "src_name": str, # 原文件名
                        "new_name": str, # 新文件名
                    }
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_regex_rename(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_regex_rename(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """正则重命名

        - https://docs.oplist.org/guide/api/fs.html#post-正则重命名
        - https://openlist.apifox.cn/api-128101253

        :payload:
            - src_dir: str 💡 源目录
            - src_name_regex: str 💡 从源文件名搜索的正则表达式
            - new_name_regex: str 💡 查找后的替换规则
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动文件

        - https://docs.oplist.org/guide/api/fs.html#post-移动文件
        - https://openlist.apifox.cn/api-128101255

        :payload:
            - src_dir: str 💡 源目录
            - dst_dir: str 💡 目标目录
            - names: list[str] 💡 文件名列表
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_recursive_move(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_recursive_move(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """聚合移动

        - https://docs.oplist.org/guide/api/fs.html#post-聚合移动
        - https://openlist.apifox.cn/api-128101259

        :payload:
            - src_dir: str 💡 源目录
            - dst_dir: str 💡 目标目录
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """复制文件

        - https://docs.oplist.org/guide/api/fs.html#post-复制文件
        - https://openlist.apifox.cn/api-128101256

        :payload:
            - src_dir: str 💡 源目录
            - dst_dir: str 💡 目标目录
            - names: list[str] 💡 文件名列表
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_remove(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_remove(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除文件或文件夹

        - https://docs.oplist.org/guide/api/fs.html#post-删除文件或文件夹
        - https://openlist.apifox.cn/api-128101257

        :payload:
            - dir: str 💡 源目录
            - names: list[str] 💡 文件名列表
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_remove_empty_directory(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_remove_empty_directory(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除空文件夹

        - https://docs.oplist.org/guide/api/fs.html#post-删除空文件夹
        - https://openlist.apifox.cn/api-128101258

        :payload:
            - src_dir: str 💡 源目录
        """
        if not isinstance(payload, dict):
            payload = {"src_dir": payload}
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_add_offline_download(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_add_offline_download(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加离线下载

        - https://docs.oplist.org/guide/api/fs.html#post-添加离线下载
        - https://openlist.apifox.cn/api-175404336

        :payload:
            - urls: list[str] 💡 下载链接列表
            - path: str 💡 目标路径
            - tool: str 💡 工具，具体可选项，请先调用 `client.public_offline_download_tools()` 查看

                - "aria2"
                - "qBittorrent"
                - "SimpleHttp"
                - "Transmission"
                - "115 Cloud"
                - "PikPak"
                - "Thunder"
                - "PikPak"
                - ...

            - delete_policy: str 💡 删除策略，可选：

                - "delete_on_upload_succeed": 上传成功后删除
                - "delete_on_upload_failed": 上传失败时删除
                - "delete_never": 从不删除
                - "delete_always": 总是删除
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
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
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
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
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
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """表单上传文件

        - https://docs.oplist.org/guide/api/fs.html#put-表单上传文件
        - https://openlist.apifox.cn/api-128101254

        .. note::
            上传的限制：

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
                                return await self.fs_form(
                                    file=file, # type: ignore
                                    path=path, 
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
                            from httpx import AsyncClient
                            async with AsyncClient() as client:
                                async with client.stream("GET", url) as resp:
                                    return await self.fs_put(
                                        resp.aiter_bytes(), 
                                        path, 
                                        as_task=as_task, 
                                        async_=True, 
                                        **request_kwargs, 
                                    )
                    else:
                        async def request():
                            async with async_request("GET", url) as resp:
                                return await self.fs_put(
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
                update_headers, request_kwargs["data"] = encode_multipart_data_async({}, {"file": file}) # type: ignore
            else:
                update_headers, request_kwargs["data"] = encode_multipart_data({}, {"file": file}) # type: ignore
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
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] ), 
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
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
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
        file: ( str | PathLike | URL | SupportsGeturl | 
                Buffer | SupportsRead[Buffer] | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        path: str, 
        as_task: bool = False, 
        filesize: int = -1, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """流式上传文件

        - https://docs.oplist.org/guide/api/fs.html#put-流式上传文件
        - https://openlist.apifox.cn/api-128101260

        .. note::
            上传的限制：

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
                    if not isinstance(file, Sized):
                        file = memoryview(file)
                    filesize = len(file)
            elif isinstance(file, SupportsRead):
                if not async_ and iscoroutinefunction(file.read):
                    raise TypeError(f"{file!r} with async read in non-async mode")
                if filesize < 0:
                    try:
                        filesize = fstat(getattr(file, "fileno")()).st_size
                    except Exception:
                        file = cast(Buffer, (yield file.read))
                        if not isinstance(file, Sized):
                            file = memoryview(file)
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
                                return await self.fs_put(
                                    file, # type: ignore
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
                    filesize = fstat(file.fileno()).st_size # type: ignore
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
                            from httpx import AsyncClient
                            async with AsyncClient() as client:
                                async with client.stream("GET", url) as resp:
                                    size = filesize if filesize >= 0 else get_content_length(resp)
                                    if size is None or is_chunked(resp):
                                        file = await resp.aread()
                                        filesize = len(file)
                                    else:
                                        file = resp.aiter_bytes()
                                    return await self.fs_put(
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
                                return await self.fs_put(
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
                            file = cast(bytes, resp.read())
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

            if isinstance(file, SupportsRead):
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

    # [public](https://docs.oplist.org/guide/api/public.html)

    @overload
    def public_archive_extensions(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def public_archive_extensions(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def public_archive_extensions(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取所有压缩包扩展名

        （没有文档）
        """
        return self.request(
            "/api/public/archive_extensions", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def public_settings(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def public_settings(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def public_settings(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取站点设置

        - https://docs.oplist.org/guide/api/public.html#get-获取站点设置
        - https://openlist.apifox.cn/api-128101263
        """
        return self.request(
            "/api/public/settings", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def public_offline_download_tools(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def public_offline_download_tools(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def public_offline_download_tools(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取下载工具列表

        （没有文档）
        """
        return self.request(
            "/api/public/offline_download_tools", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def ping(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def ping(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def ping(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        """ping检测

        - https://docs.oplist.org/guide/api/public.html#get-ping检测
        - https://openlist.apifox.cn/api-128101264
        """
        return self.request(
            "/ping", 
            "GET", 
            parse=True, 
            async_=async_, 
            **request_kwargs, 
        )

    # [task](https://docs.oplist.org/guide/api/task.html)

    @overload
    def task_info(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_info(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_info(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取任务信息

        - https://docs.oplist.org/guide/api/task.html#post-获取任务信息
        - https://openlist.apifox.cn/api-142468741

        :params payload: 请求参数

            - tid: str 💡 任务 id

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        if not isinstance(payload, dict):
            payload = {"tid": payload}
        return self.request(
            f"/api/task/{category}/info", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_done(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_done(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_done(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取已完成任务

        - https://docs.oplist.org/guide/api/task.html#get-获取已完成任务
        - https://openlist.apifox.cn/api-128101294

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/done", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_undone(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_undone(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_undone(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取未完成任务

        - https://docs.oplist.org/guide/api/task.html#get-获取未完成任务
        - https://openlist.apifox.cn/api-128101295

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/undone", 
            "GET", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_delete(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_delete(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_delete(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除任务

        - https://docs.oplist.org/guide/api/task.html#post-删除任务
        - https://openlist.apifox.cn/api-128101296

        :params payload: 请求参数

            - tid: str 💡 任务 id

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        if not isinstance(payload, dict):
            payload = {"tid": payload}
        return self.request(
            f"/api/task/{category}/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_cancel(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_cancel(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_cancel(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消任务

        - https://docs.oplist.org/guide/api/task.html#post-取消任务
        - https://openlist.apifox.cn/api-128101297

        :params payload: 请求参数

            - tid: str 💡 任务 id

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        if not isinstance(payload, dict):
            payload = {"tid": payload}
        return self.request(
            f"/api/task/{category}/cancel", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_clear_done(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_clear_done(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_clear_done(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清除已完成任务

        - https://docs.oplist.org/guide/api/task.html#post-清除已完成任务
        - https://openlist.apifox.cn/api-128101299

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/clear_done", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_clear_succeeded(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_clear_succeeded(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_clear_succeeded(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清除已成功任务

        - https://docs.oplist.org/guide/api/task.html#post-清除已成功任务
        - https://openlist.apifox.cn/api-128101299

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/clear_succeeded", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_retry(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_retry(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_retry(
        self, 
        /, 
        payload: dict | str, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重试任务

        - https://docs.oplist.org/guide/api/task.html#post-重试任务
        - https://openlist.apifox.cn/api-128101298

        :params payload: 请求参数

            - tid: str 💡 任务 id

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        if not isinstance(payload, dict):
            payload = {"tid": payload}
        return self.request(
            f"/api/task/{category}/retry", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_retry_failed(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_retry_failed(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_retry_failed(
        self, 
        /, 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重试已失败任务

        - https://docs.oplist.org/guide/api/task.html#post-重试已失败任务

        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/retry_failed", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_delete_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_delete_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_delete_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除多个任务

        - https://docs.oplist.org/guide/api/task.html#post-删除多个任务

        :param payload: 任务 id 列表
        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/delete_some", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_cancel_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_cancel_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_cancel_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消多个任务

        - https://docs.oplist.org/guide/api/task.html#post-取消多个任务

        :param payload: 任务 id 列表
        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/cancel_some", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def task_retry_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def task_retry_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def task_retry_some(
        self, 
        /, 
        payload: list[str], 
        category: str = "upload", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重试多个任务

        - https://docs.oplist.org/guide/api/task.html#post-重试多个任务

        :param payload: 任务 id 列表
        :params category: 分类，可取值如下：

            - "upload": 上传
            - "copy": 复制
            - "offline_download": 离线下载
            - "offline_download_transfer": 离线下载转存
            - "decompress": 解压
            - "decompress_upload": 解压转存

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return self.request(
            f"/api/task/{category}/retry_some", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin](https://docs.oplist.org/guide/api/admin/)

    # [admin/meta](https://docs.oplist.org/guide/api/admin/meta.html)

    @overload
    def admin_meta_list(
        self, 
        /, 
        payload: dict | int = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_list(
        self, 
        /, 
        payload: dict | int = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_list(
        self, 
        /, 
        payload: dict | int = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出元信息

        - https://docs.oplist.org/guide/api/admin/meta.html#get-列出元信息
        - https://openlist.apifox.cn/api-128101265

        :paylaod:
            - page: int = <default>     💡 页数
            - per_page: int = <default> 💡 每页数目
        """
        if not isinstance(payload, dict):
            payload = {"page": payload, "per_page": 100}
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_get(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_get(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取元信息

        - https://docs.oplist.org/guide/api/admin/meta.html#get-获取元信息
        - https://openlist.apifox.cn/api-128101266

        :payload:
            - id: int 💡 元信息 id
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_create(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_create(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新增元信息

        - https://docs.oplist.org/guide/api/admin/meta.html#post-新增元信息
        - https://openlist.apifox.cn/api-128101267

        :payload:
            - id: int = <default>       💡 元信息 id
            - path: str                 💡 路径
            - password: str = <default> 💡 密码
            - p_sub: bool = <default>   💡 密码是否应用到子文件夹
            - write: bool = <default>   💡 是否开启写入
            - w_sub: bool = <default>   💡 开启写入是否应用到子文件夹
            - hide: str = <default>     💡 隐藏
            - h_sub: bool = <default>   💡 隐藏是否应用到子文件夹
            - readme: str = <default>   💡 说明
            - r_sub: bool = <default>   💡 说明是否应用到子文件夹
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新元信息

        - https://docs.oplist.org/guide/api/admin/meta.html#post-更新元信息
        - https://openlist.apifox.cn/api-128101268

        :payload:
            - id: int       💡 元信息 id
            - path: str     💡 路径
            - password: str 💡 密码
            - p_sub: bool   💡 密码是否应用到子文件夹
            - write: bool   💡 是否开启写入
            - w_sub: bool   💡 开启写入是否应用到子文件夹
            - hide: str     💡 隐藏
            - h_sub: bool   💡 隐藏是否应用到子文件夹
            - readme: str   💡 说明
            - r_sub: bool   💡 说明是否应用到子文件夹
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_meta_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_meta_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除元信息

        - https://docs.oplist.org/guide/api/admin/meta.html#post-删除元信息
        - https://openlist.apifox.cn/api-128101269

        :payload:
            - id: int 💡 元信息 id
        """
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(
            "/api/admin/meta/delete", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/user](https://docs.oplist.org/guide/api/admin/user.html)

    @overload
    def admin_user_list(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_list(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_list(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出所有用户

        - https://docs.oplist.org/guide/api/admin/user.html#get-列出所有用户
        - https://openlist.apifox.cn/api-128101270
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
        payload: dict | int | str = 1, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_get(
        self, 
        /, 
        payload: dict | int | str = 1, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_get(
        self, 
        /, 
        payload: dict | int | str = 1, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出某个用户

        - https://docs.oplist.org/guide/api/admin/user.html#get-列出某个用户
        - https://openlist.apifox.cn/api-128101271

        :payload:
            - id: int 💡 用户 id
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_create(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_create(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建用户

        - https://docs.oplist.org/guide/api/admin/user.html#post-新建用户
        - https://openlist.apifox.cn/api-128101272

        :payload:
            - id: int = <default> 💡 用户 id
            - username: str 💡 用户名
            - password: str = <default> 💡 密码
            - base_path: str = <default> 💡 基本路径
            - role: int = <default> 💡 角色
            - permission: int = <default> 💡 权限
            - disabled: bool = <default> 💡 是否禁用
            - sso_id: str = <default> 💡 单点登录 id
        """
        if not isinstance(payload, dict):
            payload = {"username": payload}
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新用户信息

        - https://docs.oplist.org/guide/api/admin/user.html#post-更新用户信息
        - https://openlist.apifox.cn/api-128101273

        :payload:
            - id: int 💡 用户 id
            - username: str = <default> 💡 用户名
            - password: str = <default> 💡 密码
            - base_path: str = <default> 💡 基本路径
            - role: int = <default> 💡 角色
            - permission: int = <default> 💡 权限
            - disabled: bool = <default> 💡 是否禁用
            - sso_id: str = <default> 💡 单点登录 id
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_cancel_2fa(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_cancel_2fa(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消某个用户的两步验证

        - https://docs.oplist.org/guide/api/admin/user.html#post-取消某个用户的两步验证
        - https://openlist.apifox.cn/api-128101274

        :payload:
            - id: int 💡 用户 id
        """
        if not isinstance(payload, dict):
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除用户

        - https://docs.oplist.org/guide/api/admin/user.html#post-删除用户
        - https://openlist.apifox.cn/api-128101275

        :payload:
            - id: int 💡 用户 id
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
        payload: dict | str = "admin", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_del_cache(
        self, 
        /, 
        payload: dict | str = "admin", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_del_cache(
        self, 
        /, 
        payload: dict | str = "admin", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除用户缓存

        - https://docs.oplist.org/guide/api/admin/user.html#post-删除用户缓存
        - https://openlist.apifox.cn/api-128101276

        :payload:
            - username: str 💡 用户名
        """
        if not isinstance(payload, dict):
            payload = {"username": payload}
        return self.request(
            "/api/admin/user/del_cache", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_sshkey_list(
        self, 
        /, 
        payload: dict | int | str = 1, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_sshkey_list(
        self, 
        /, 
        payload: dict | int | str = 1, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_sshkey_list(
        self, 
        /, 
        payload: dict | int | str = 1, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出用户的 SFTP 公钥

        - https://docs.oplist.org/guide/api/admin/user.html#get-列出用户的-sftp-公钥

        :payload:
            - uid: int 💡 用户 id
        """
        if not isinstance(payload, dict):
            payload = {"uid": payload}
        return self.request(
            "/api/admin/user/sshkey/list", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_user_sshkey_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_user_sshkey_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_user_sshkey_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除用户的 SFTP 公钥

        - https://docs.oplist.org/guide/api/admin/user.html#post-删除用户的-sftp-公钥

        :payload:
            id: int 💡 公钥主键 id
        """
        if not isinstance(payload, dict):
            payload = {"id": payload}
        return self.request(
            "/api/admin/user/sshkey/delete", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/storage](https://docs.oplist.org/guide/api/admin/storage.html)

    @overload
    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_create(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """创建存储

        - https://docs.oplist.org/guide/api/admin/storage.html#post-创建存储
        - https://openlist.apifox.cn/api-175457115

        :payload:
            - id: int = <default> 💡 存储 id
            - driver: str 💡 驱动
            - mount_path: str 💡 挂载路径
            - order: int = <default> 💡 序号
            - remark: str = <default> 💡 备注
            - cache_expiration: int = <default> 💡 缓存过期时间，单位：分钟
            - status: str = <default> 💡 状态
            - web_proxy: bool = <default> 💡 是否启用 web 代理
            - webdav_policy: str = <default> 💡 webdav 策略

                - "native_proxy":  本机代理 
                - "use_proxy_url": 使用代理地址 
                - "302_redirect":  302重定向

            - down_proxy_url: str = <default> 💡 下载代理 URL
            - order_by: str = <default> 💡 排序方式

                - "name": 名称
                - "size": 大小
                - "modified": 修改时间

            - order_direction: "" | "asc" | "desc" = <default> 💡 排序方向

                - "asc": 升序
                - "desc": 降序

            - extract_folder: "" | "front" | "back" = <default> 💡 提取目录

                - "front": 提取到最前
                - "back": 提取到最后

            - disable_index: bool = False 💡 是否禁用索引
            - enable_sign: bool = False 💡 是否启用签名
            - addition: str = "{}" 💡 额外信息，一般是一个 JSON 字符串，包含了 driver 特定的配置信息
        """
        dict_merge_update(payload, disable_index=False, enable_sign=False, addition="{}")
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_update(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新存储

        - https://docs.oplist.org/guide/api/admin/storage.html#post-更新存储
        - https://openlist.apifox.cn/api-175457877

        :payload:
            - id: int 💡 存储 id
            - driver: str 💡 驱动
            - mount_path: str 💡 挂载路径
            - order: int = <default> 💡 序号
            - remark: str = <default> 💡 备注
            - cache_expiration: int = <default> 💡 缓存过期时间，单位：分钟
            - status: str = <default> 💡 状态
            - web_proxy: bool = <default> 💡 是否启用 web 代理
            - webdav_policy: str = <default> 💡 webdav 策略

                - "native_proxy":  本机代理 
                - "use_proxy_url": 使用代理地址 
                - "302_redirect":  302重定向

            - down_proxy_url: str = <default> 💡 下载代理 URL
            - order_by: str = <default> 💡 排序方式

                - "name": 名称
                - "size": 大小
                - "modified": 修改时间

            - order_direction: "" | "asc" | "desc" = <default> 💡 排序方向

                - "asc": 升序
                - "desc": 降序

            - extract_folder: "" | "front" | "back" = <default> 💡 提取目录

                - "front": 提取到最前
                - "back": 提取到最后

            - disable_index: bool = False 💡 是否禁用索引
            - enable_sign: bool = False 💡 是否启用签名
            - addition: str = "{}" 💡 额外信息，一般是一个 JSON 字符串，包含了 driver 特定的配置信息
        """
        dict_merge_update(payload, disable_index=False, enable_sign=False, addition="{}")
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
        payload: dict | int = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_list(
        self, 
        /, 
        payload: dict | int = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_list(
        self, 
        /, 
        payload: dict | int = {"page": 1, "per_page": 0}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出存储列表

        - https://docs.oplist.org/guide/api/admin/storage.html#get-列出存储列表
        - https://openlist.apifox.cn/api-128101277

        :payload:
            - page: int = <default>     💡 页数
            - per_page: int = <default> 💡 每页数目
        """
        if not isinstance(payload, dict):
            payload = {"page": payload, "per_page": 100}
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_enable(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_enable(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """启用存储

        - https://docs.oplist.org/guide/api/admin/storage.html#post-启用存储
        - https://openlist.apifox.cn/api-128101278

        :payload:
            - id: int 💡 存储 id
        """
        if not isinstance(payload, dict):
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_disable(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_disable(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """禁用存储

        - https://docs.oplist.org/guide/api/admin/storage.html#post-禁用存储
        - https://openlist.apifox.cn/api-128101279

        :payload:
            - id: int 💡 存储 id
        """
        if not isinstance(payload, dict):
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_get(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_get(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询指定存储信息

        - https://docs.oplist.org/guide/api/admin/storage.html#get-查询指定存储信息
        - https://openlist.apifox.cn/api-128101281

        :payload:
            - id: int 💡 存储 id
        """
        if not isinstance(payload, dict):
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
        payload: dict | int | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_delete(
        self, 
        /, 
        payload: dict | int | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除指定存储

        - https://docs.oplist.org/guide/api/admin/storage.html#post-删除指定存储
        - https://openlist.apifox.cn/api-128101282

        :payload:
            - id: int 💡 存储 id
        """
        if not isinstance(payload, dict):
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_storage_load_all(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_storage_load_all(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重新加载所有存储

        - https://docs.oplist.org/guide/api/admin/storage.html#post-重新加载所有存储
        - https://openlist.apifox.cn/api-128101283
        """
        return self.request(
            "/api/admin/storage/load_all", 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/driver](https://docs.oplist.org/guide/api/admin/driver.html)

    @overload
    def admin_driver_list(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_driver_list(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_driver_list(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询所有驱动配置模板列表

        - https://docs.oplist.org/guide/api/admin/driver.html#get-查询所有驱动配置模板列表
        - https://openlist.apifox.cn/api-128101284
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_driver_names(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_driver_names(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出驱动名列表

        - https://docs.oplist.org/guide/api/admin/driver.html#get-列出驱动名列表
        - https://openlist.apifox.cn/api-128101285
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_driver_info(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_driver_info(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出特定驱动信息

        - https://docs.oplist.org/guide/api/admin/driver.html#get-列出特定驱动信息
        - https://openlist.apifox.cn/api-128101286

        :payload:
            - driver: str 💡 驱动名
        """
        if not isinstance(payload, dict):
            payload = {"driver": payload}
        return self.request(
            "/api/admin/driver/info", 
            "GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/setting](https://docs.oplist.org/guide/api/admin/setting.html)

    @overload
    def admin_setting_list(
        self, 
        /, 
        payload: dict | int | str = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_list(
        self, 
        /, 
        payload: dict | int | str = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_list(
        self, 
        /, 
        payload: dict | int | str = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """列出设置

        - https://docs.oplist.org/guide/api/admin/setting.html#get-列出设置
        - https://openlist.apifox.cn/api-128101287

        :payload:
            - group: int = <default>  💡 设置组的编号
            - groups: str = <default> 💡 多个设置组的编号，用逗号,分隔连接

                -  0: 其他，包括 令牌 和 索引统计（非设置）
                -  1: 站点
                -  2: 样式
                -  3: 预览
                -  4: 全局
                -  5: 下载
                -  6: 索引
                -  7: 单点登录
                -  8: LDAP
                -  9: S3 存储桶
                - 10: FTP
                - 11: 传输
        """
        if not isinstance(payload, dict):
            payload = {"groups": payload}
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

        - https://docs.oplist.org/guide/api/admin/setting.html#get-获取某项设置
        - https://openlist.apifox.cn/api-128101288

        :payload:
            - key: str = <default>  💡 设置名
            - keys: str = <default> 💡 多项设置名，用逗号,分隔连接
        """
        if not isinstance(payload, dict):
            payload = {"keys": payload}
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_save(
        self, 
        /, 
        payload: list[dict], 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_save(
        self, 
        /, 
        payload: list[dict], 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """保存设置

        - https://docs.oplist.org/guide/api/admin/setting.html#post-保存设置
        - https://openlist.apifox.cn/api-128101289

        :param payload: 若干设置的列表
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
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
        payload: dict | str, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_delete(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_delete(
        self, 
        /, 
        payload: dict | str, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除设置

        - https://docs.oplist.org/guide/api/admin/setting.html#post-删除设置
        - https://openlist.apifox.cn/api-128101290

        :payload:
            - key: str 💡 设置名（仅用于弃用的设置）
        """
        if not isinstance(payload, dict):
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

        - https://docs.oplist.org/guide/api/admin/setting.html#post-重置令牌
        - https://openlist.apifox.cn/api-128101291
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_set_aria2(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_set_aria2(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置 aria2

        - https://docs.oplist.org/guide/api/admin/setting.html#post-设置aria2
        - https://openlist.apifox.cn/api-128101292

        :payload:
            - uri: str    💡 aria2 地址
            - secret: str 💡 aria2 密钥
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_set_qbit(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_set_qbit(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置 qBittorrent

        - https://docs.oplist.org/guide/api/admin/setting.html#post-设置qbittorrent
        - https://openlist.apifox.cn/api-128101293

        :payload:
            - url: str    💡 qBittorrent 链接
            - secret: str 💡 做种时间
        """
        return self.request(
            "/api/admin/setting/set_qbit", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_setting_set_transmission(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_setting_set_transmission(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_setting_set_transmission(
        self, 
        /, 
        payload: dict, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置 Transmission

        （没有文档）
        """
        return self.request(
            "/api/admin/setting/set_transmission", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/index]()

    @overload
    def admin_index_progress(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_progress(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_progress(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """索引构建进度

        （没有文档）
        """
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
        payload: dict = {"max_depth": -1, "paths": ["/"]}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_build(
        self, 
        /, 
        payload: dict = {"max_depth": -1, "paths": ["/"]}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_build(
        self, 
        /, 
        payload: dict = {"max_depth": -1, "paths": ["/"]}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重建索引

        :payload:
            - max_depth: int 💡 索引深度，-1 是无限
            - paths: list[str] 💡 路径列表

        （没有文档）
        """
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
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_clear(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_clear(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清除索引

        （没有文档）
        """
        return self.request(
            "/api/admin/index/clear", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_index_stop(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_stop(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_stop(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """停止索引

        （没有文档）
        """
        return self.request(
            "/api/admin/index/stop", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_index_update(
        self, 
        /, 
        payload: dict = {"max_depth": -1, "paths": ["/"]}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_index_update(
        self, 
        /, 
        payload: dict = {"max_depth": -1, "paths": ["/"]}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_index_update(
        self, 
        /, 
        payload: dict = {"max_depth": -1, "paths": ["/"]}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新索引

        :payload:
            - max_depth: int 💡 索引深度，-1 是无限
            - paths: list[str] 💡 路径列表

        （没有文档）
        """
        return self.request(
            "/api/admin/index/update", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    # [admin/message]()

    @overload
    def admin_message_get(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_message_get(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_message_get(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取消息

        （没有文档）
        """
        return self.request(
            "/api/admin/message/get", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def admin_message_send(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def admin_message_send(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def admin_message_send(
        self, 
        /, 
        payload: dict = {}, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """发送消息

        （没有文档）
        """
        return self.request(
            "/api/admin/message/send", 
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
        - https://docs.oplist.org/guide/drivers/common.html#download-proxy-url
        """
        if self.base_path != "/":
            path = self.base_path + path
        if ensure_ascii:
            url = self.base_url + "/d" + quote(path, safe="@[]:/!$&'()*+,;=")
        else:
            url = self.base_url + "/d" + path.translate({0x23: "%23", 0x3F: "%3F"})
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
    def upload_tasklist(self, /) -> AlistUploadTaskList:
        return AlistUploadTaskList(self)

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
    def decompress_tasklist(self, /) -> AlistDecompressTaskList:
        return AlistDecompressTaskList(self)

    @cached_property
    def decompress_upload_tasklist(self, /) -> AlistDecompressUploadTaskList:
        return AlistDecompressUploadTaskList(self)


from .fs import AlistFileSystem
from .admin.task import (
    AlistCopyTaskList, AlistOfflineDownloadTaskList, 
    AlistOfflineDownloadTransferTaskList, AlistUploadTaskList, 
    AlistDecompressTaskList, AlistDecompressUploadTaskList, 
)

