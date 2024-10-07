# Python 115 网盘客户端.

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/p115client)
![PyPI - Version](https://img.shields.io/pypi/v/p115client)
![PyPI - Downloads](https://img.shields.io/pypi/dm/p115client)
![PyPI - Format](https://img.shields.io/pypi/format/p115client)
![PyPI - Status](https://img.shields.io/pypi/status/p115client)

## 安装

你可以从 [pypi](https://pypi.org/project/p115client/) 安装最新版本

```console
pip install -U p115client
```

## 入门介绍

### 1. 导入模块和创建实例

导入模块

```python
from p115 import P115Client
```

创建客户端对象，需要传入 <kbd>cookies</kbd>，如果不传，则需要扫码登录

```python
cookies = "UID=...; CID=...; SEID=..."
client = P115Client(cookies)
```

如果你的 <kbd>cookies</kbd> 保存在 `~/115-cookies.txt`

```python
from pathlib import Path

client = P115Client(Path("~/115-cookies.txt").expanduser())
```

如果想要在接口返回时自动捕获 405 HTTP 响应码，进行自动扫码，并把更新后的 <kbd>cookies</kbd> 写回文件，然后重试接口调用

```python
client = P115Client(Path("~/115-cookies.txt").expanduser(), check_for_relogin=True)
```

所以综上，推荐的初始化代码为

```python
from p115client import P115Client
from pathlib import Path

client = P115Client(Path("~/115-cookies.txt").expanduser(), check_for_relogin=True)
```

### 2. 接口调用

所有需要直接或间接执行 HTTP 请求的接口，都有同步和异步的调用方式

```python
# 同步调用
client.method(payload)
client.method(payload, async_=False)

# 异步调用
await client.method(payload, async_=True)
```

从根本上讲，除了几个 `staticmethod`，它们都会调用 `P115Client.request`

```python
url = "https://webapi.115.com/files"
response = client.request(url=url, params={"cid": 0, "show_dir": 1})
```

当你需要构建自己的扩展模块，以增加一些新的 115 web 接口时，就需要用到此方法了

```python
from collections.abc import Coroutine
from typing import overload, Any, Literal
from p115client import P115Client

class MyCustom115Client(P115Client):

    @overload
    def foo(self, payload: dict, async_: Literal[False] = False) -> dict:
        ...
    @overload
    def foo(self, payload: dict, async_: Literal[True]) -> Coroutine[Any, Any, dict]:
        ...
    def foo(self, payload: dict, async_: bool = False) -> dict | Coroutine[Any, Any, dict]:
        api = "https://webapi.115.com/foo"
        return self.request(api, method="GET", params=payload)

    @overload
    def bar(self, payload: dict, async_: Literal[False] = False) -> dict:
        ...
    @overload
    def bar(self, payload: dict, async_: Literal[True]) -> Coroutine[Any, Any, dict]:
        ...
    def bar(self, payload: dict, async_: bool = False) -> dict | Coroutine[Any, Any, dict]:
        api = "https://webapi.115.com/bar"
        return self.request(api, method="POST", data=payload)
```



