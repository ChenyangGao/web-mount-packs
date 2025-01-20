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

#### 1. 创建自定义 uri

```python
from p123 import P123Client
from p123.tool import make_uri

# TODO: 改成你自己的账户和密码
client = P123Client(passport="手机号或邮箱", password="登录密码")

# TODO: 请改成你要处理的文件 id
file_id = 15688945
print(make_uri(client, file_id))
```

#### 2. 由自定义 uri 转存文件到你的网盘

```python
from p123 import P123Client
from p123.tool import upload_uri

# TODO: 改成你自己的账户和密码
client = P123Client(passport="手机号或邮箱", password="登录密码")

uri = "123://torrentgalaxy.db|1976025090|582aa8bfb0ad8e6f512d9661f6243bdd"
print(upload_uri(client, uri, duplicate=1))
```

#### 3. 由自定义 uri 获取下载直链

```python
from p123 import P123Client
from p123.tool import get_downurl

# TODO: 改成你自己的账户和密码
client = P123Client(passport="手机号或邮箱", password="登录密码")

# 带 s3_key_flag
print(get_downurl(client, "123://torrentgalaxy.db|1976025090|582aa8bfb0ad8e6f512d9661f6243bdd?1812602326-0"))
# 不带 s3_key_flag（会转存）
print(get_downurl(client, "123://torrentgalaxy.db|1976025090|582aa8bfb0ad8e6f512d9661f6243bdd"))
```

#### 4. 直链服务

需要先安装 [fastapi](https://pypi.org/project/fastapi/)

```console
pip install 'fastapi[uvicorn]'
```

然后启动如下服务，就可以访问以获取直链了

**带 s3_key_flag**

http://localhost:8123/torrentgalaxy.db|1976025090|582aa8bfb0ad8e6f512d9661f6243bdd?1812602326-0

**不带 s3_key_flag（会转存）**

http://localhost:8123/torrentgalaxy.db|1976025090|582aa8bfb0ad8e6f512d9661f6243bdd

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from p123 import P123Client
from p123.tool import get_downurl

# TODO: 改成你自己的账户和密码
client = P123Client(passport="手机号或邮箱", password="登录密码")

app = FastAPI(debug=True)

@app.get("/{uri:path}")
@app.head("/{uri:path}")
async def index(request: Request, uri: str):
    try:
        payload = int(uri)
    except ValueError:
        if uri.count("|") < 2:
            return JSONResponse({"state": False, "message": f"bad uri: {uri!r}"}, 500)
        payload = uri
        if s3_key_flag := request.url.query:
            payload += "?" + s3_key_flag
    url = await get_downurl(client, payload, quoted=False, async_=True)
    return RedirectResponse(url, 302)

if __name__ == "__main__":
    from uvicorn import run

    run(app, host="0.0.0.0", port=8123)
```

#### 5. 遍历文件列表

**遍历网盘中的文件列表**

```python
from p123 import P123Client
from p123.tool import iterdir

# TODO: 改成你自己的账户和密码
client = P123Client(passport="手机号或邮箱", password="登录密码")

for info in iterdir(client, parent_id=0, max_depth=-1, predicate=lambda a: not a["is_dir"]):
    print(info)
```

**遍历分享中的文件列表（无需登录）**

```python
from p123.tool import share_iterdir

# TODO: 分享码
share_key = "g0n0Vv-2sbI"
# TODO: 密码
share_pwd = ""

for info in share_iterdir(share_key, share_pwd, parent_id=0, max_depth=-1, predicate=lambda a: not a["is_dir"]):
    print(info)
```
