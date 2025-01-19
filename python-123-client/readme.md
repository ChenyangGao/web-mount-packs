# Python 123 网盘客户端

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/python-123-client)
![PyPI - Version](https://img.shields.io/pypi/v/python-123-client)
![PyPI - Downloads](https://img.shields.io/pypi/dm/python-123-client)
![PyPI - Format](https://img.shields.io/pypi/format/python-123-client)
![PyPI - Status](https://img.shields.io/pypi/status/python-123-client)

## 安装

你可以从 [pypi](https://pypi.org/project/python-123-client/) 安装最新版本

```console
pip install -U python-123-client
```

## 入门介绍

### 1. 导入模块和创建实例

导入模块

```python
from p123 import P123Client
```

创建客户端对象，需要传入 JWT <kbd>token</kbd>

```python
token = "..."
client = P123Client(token=token)
```

你也可以用账户和密码登录

```python
passport = "..." # 手机号或者邮箱
password = "..." # 密码
client = P123Client(passport, password)
```

### 2. 接口调用

所有需要直接或间接执行 HTTP 请求的接口，都有同步和异步的调用方式，且默认是采用 POST 发送 JSON 请求数据

```python
# 同步调用
client.method(payload)
client.method(payload, async_=False)

# 异步调用
await client.method(payload, async_=True)
```

从根本上讲，除了几个 `staticmethod`，它们都会调用 `P123Client.request`

```python
url = "https://www.123pan.com/api/someapi"
response = client.request(url=url, json={...})
```

当你需要构建自己的扩展模块，以增加一些新的 123 web 接口时，就需要用到此方法了

```python
from collections.abc import Coroutine
from typing import overload, Any, Literal

from p123 import P123Client

class MyCustom123Client(P123Client):

    @overload
    def foo(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def foo(
        self, 
        payload: dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def foo(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        api = "https://www.123pan.com/api/foo"
        return self.request(
            api, 
            method="GET", 
            params=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def bar(
        self, 
        payload: dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def bar(
        self, 
        payload: dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def bar(
        self, 
        payload: dict, 
        /, 
        async_: bool = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        api = "https://www.123pan.com/api/bar"
        return self.request(
            api, 
            method="POST", 
            json=payload, 
            async_=async_, 
            **request_kwargs, 
        )
```

### 3. 检查响应

接口被调用后，如果返回的是 dict 类型的数据（说明原本是 JSON），则可以用 `p123.check_response` 执行检查。首先会查看其中名为 "code" 的键的对应值，如果为 0 或 200 或者不存在，则原样返回被检查的数据；否则，抛出一个 `p123.P123OSError` 的实例。

```python
from p123 import check_response

# 检查同步调用
data = check_response(client.method(payload))
# 检查异步调用
data = check_response(await client.method(payload, async_=True))
```

### 4. 辅助工具

一些简单的封装工具可能是必要的，特别是那种实现起来代码量比较少，可以封装成单个函数的。我把平常使用过程中，积累的一些经验具体化为一组工具函数。这些工具函数分别有着不同的功能，如果组合起来使用，或许能解决很多问题。

```python
from p123 import tool
```
