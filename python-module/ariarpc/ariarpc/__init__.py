#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["json_rpc_call", "AriaRPC", "AriaXMLRPC"]

from collections.abc import Callable, Coroutine, Iterable, Mapping
from typing import cast, overload, Any, Final, Literal, Self
from uuid import uuid4
from xmlrpc.client import _Method, ServerProxy

from orjson import loads, dumps


ARIA2_METHODS: Final = [
    "addUri", "addTorrent", "getPeers", "addMetalink", "remove", "pause", "forcePause", "pauseAll", 
    "forcePauseAll", "unpause", "unpauseAll", "forceRemove", "changePosition", "tellStatus", "getUris", 
    "getFiles", "getServers", "tellActive", "tellWaiting", "tellStopped", "getOption", "changeUri", 
    "changeOption", "getGlobalOption", "changeGlobalOption", "purgeDownloadResult", "removeDownloadResult", 
    "getVersion", "getSessionInfo", "shutdown", "forceShutdown", "getGlobalStat", "saveSession", 
]
SYSTEM_METHODS: Final = ["multicall", "listMethods", "listNotifications"]
_httpx_request: None | Callable = None


def get_default_request() -> Callable:
    global _httpx_request
    if _httpx_request is None:
        from httpx import AsyncClient, AsyncHTTPTransport, Client, HTTPTransport, Limits, Timeout
        from httpx_request import request as httpx_request
        limit = Limits(max_connections=256, max_keepalive_connections=64, keepalive_expiry=10)
        timeout = Timeout(connect=5, read=60, write=60, pool=5)
        def _httpx_request(
            *args, 
            async_: bool = False, 
            session: Client = Client(
                limits=limit, 
                transport=HTTPTransport(retries=5), 
                timeout=timeout, 
                verify=False, 
            ), 
            async_session: AsyncClient = AsyncClient(
                limits=limit, 
                transport=AsyncHTTPTransport(retries=5), 
                timeout=timeout, 
                verify=False, 
            ), 
            **request_kwargs, 
        ):
            return httpx_request(
                *args, # type: ignore
                session=async_session if async_ else session, 
                async_=async_, 
                **request_kwargs, 
            )
    return cast(Callable, _httpx_request)


def json_rpc_call(
    method: str = "system.listMethods", 
    params: Iterable = (), 
    payload: Mapping = {}, 
    url: str = "http://localhost:6800/jsonrpc", 
    parse: Callable = lambda _, b: loads(b), 
    request: None | Callable = None, 
    async_: bool = False, 
    **request_kwargs, 
):
    """Execute RPC request.

    :param method: The method for the RPC call.
    :param params: The `params` parameter for the RPC call.
    :param payload: Other request parameters for the RPC call.
    :param url: The URL for the RPC call.
    :param parse: Parsing the return value, defaulting to deserialization as JSON.
    :param request: The function that performs the request.
    :param async_: Whether the execution is asynchronous.
    :param request_kwargs: Other request parameters.

    :return: The `method` interface return value.
    """
    if not isinstance(params, (tuple, list)):
        params = tuple(params)
    request_kwargs.update(
        url=url, 
        method="POST", 
        data=dumps({
            "jsonrpc": "2.0", 
            "method": method, 
            "id": f"python-script-{uuid4()}", 
            "params": params, 
            **payload, 
        }), 
    )
    if request is None:
        return get_default_request()(parse=parse, async_=async_, **request_kwargs)
    else:
        return request(parse=parse, **request_kwargs)


class AriaRPC:
    """Aria2 RPC call.

    .. note::
        https://aria2.github.io/manual/en/html/aria2c.html#methods

    :param method: The method for the RPC call.
    :param url: The URL for the RPC call. If it is an int, it is treated as local port.
    """
    def __init__(
        self, 
        /, 
        method: str = "", 
        url: int | str = "http://localhost:6800/jsonrpc", 
    ):
        if isinstance(url, int):
            url = f"http://localhost:{url}/jsonrpc"
        self._method = method
        self._url = url
        cls = type(self)
        if method == "":
            self.__dict__.update(aria2=cls("aria2", url), system=cls("system", url))
        elif method == "aria2":
            self.__dict__.update((name, cls("aria2."+name, url)) for name in ARIA2_METHODS)
        elif method == "system":
            self.__dict__.update((name, cls("system."+name, url)) for name in SYSTEM_METHODS)

    def __getattr__(self, attr: str, /) -> Self:
        method = self.method
        if method:
            method += "." + attr
        else:
            method = attr
        inst = self.__dict__[attr] = type(self)(method, self.url)
        return inst

    @overload
    def __call__(
        self, 
        /, 
        *params, 
        request: None | Callable = None, 
        async_: Literal[False] = False, 
        **payload, 
    ) -> dict:
        ...
    @overload
    def __call__(
        self, 
        /, 
        *params, 
        request: None | Callable = None, 
        async_: Literal[True], 
        **payload, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def __call__(
        self, 
        /, 
        *params, 
        request: None | Callable = None, 
        async_: Literal[False, True] = False, 
        **payload, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """Execute RPC request.

        :param params: The `params` parameter for the RPC call.
        :param request: The callable that performs the request.
        :param async_: Whether the execution is asynchronous.
        :param payload: Other request parameters for the RPC call.

        :return: The `self.method` interface return value, parsed as JSON.
        """
        return json_rpc_call(
            self.method, 
            params, 
            payload, 
            url=self.url, 
            request=request, 
            async_=async_, 
        )

    def __repr__(self, /) -> str:
        name = type(self).__qualname__
        method = self.method
        url = self.url
        return f"{name}({method=!r}, {url=!r})"

    @property
    def method(self, /) -> str:
        return self._method

    @property
    def url(self, /) -> str:
        return self._url

    @url.setter
    def url(self, url: str, /):
        self._url = url
        for obj in self.__dict__.values():
            if isinstance(obj, AriaRPC):
                obj.url = url


class Method(_Method):

    def __init__(self, send: Callable, name: str):
        super().__init__(send, name)
        if name == "aria2":
            self.__dict__.update((name, _Method(send, "aria2." + name)) for name in ARIA2_METHODS)
        elif name == "system":
            self.__dict__.update((name, _Method(send, "system." + name)) for name in SYSTEM_METHODS)


class AriaXMLRPC(ServerProxy):

    def __init__(self, /, uri: int | str = "http://localhost:6800/rpc", *args, **kwds):
        if isinstance(uri, int):
            uri = f"http://localhost:{uri}/rpc"
        super().__init__(uri, *args, **kwds)
        self.__dict__["aria2"] = self.aria2
        self.__dict__["system"] = self.system

    def __getattr__(self, name):
        return Method(self._ServerProxy__request, name)

