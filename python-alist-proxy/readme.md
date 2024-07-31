# Python alist proxy and monitor.

## 安装

你可以从 [pypi](https://pypi.org/project/alist_proxy/) 安装

```console
pip install -U alist_proxy
```

## 用法

### 作为模块使用

```python
>>> import alist_proxy
>>> help(alist_proxy)
Help on package alist_proxy:

NAME
    alist_proxy - # encoding: utf-8

PACKAGE CONTENTS
    __main__

FUNCTIONS
    make_application(base_url: str = 'http://localhost:5244', collect: None | collections.abc.Callable[[dict], typing.Any] = None, project: None | collections.abc.Callable[[dict], typing.Any] = None, methods: list[str] = ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH', 'MKCOL', 'COPY', 'MOVE', 'PROPFIND', 'PROPPATCH', 'LOCK', 'UNLOCK', 'REPORT', 'ACL'], threaded: bool = False) -> blacksheep.server.application.Application
        创建一个 blacksheep 应用，用于反向代理 alist，并持续收集每个请求事件的消息
        
        :param base_url: alist 的 base_url
        :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
        :param project: 调用以对请求事件的消息进行映射处理，如果结果为 None，则丢弃此消息
        :param methods: 需要监听的 HTTP 方法集
        :param threaded: collect 和 project，如果不是 async 函数，就放到单独的线程中运行
        
        :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    
    make_application_with_fs_event_stream(alist_token: str, base_url: str = 'http://localhost:5244', redis_host: str = 'localhost', redis_port: int = 6379, redis_key: str = 'alist:fs')
        只收集和文件系统操作有关的事件，存储到 redis streams，并且可以通过 websocket 拉取
        
        :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
        :param base_url: alist 的 base_url
        :param redis_host: redis 服务所在的主机
        :param redis_port: redis 服务的端口
        :param redis_key: redis streams 的键名
        
        :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    
    make_application_with_fs_events(alist_token: str, base_url: str = 'http://localhost:5244', collect: None | collections.abc.Callable[[dict], typing.Any] = None, threaded: bool = False) -> blacksheep.server.application.Application
        只收集和文件系统操作有关的事件
        
        :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
        :param base_url: alist 的 base_url
        :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
        :param threaded: collect 如果不是 async 函数，就放到单独的线程中运行
        
        :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行

DATA
    __all__ = ['make_application', 'make_application_with_fs_events', 'make_application_with_fs_event_stream']

VERSION
    (0, 0, 4)

AUTHOR
    ChenyangGao <https://chenyanggao.github.io>
```

### 命令行使用

```console
$ alist-proxy -h
usage: alist-proxy [-h] [-H HOST] [-p PORT] [-b BASE_URL] [-t TOKEN] [-nr] [-rh REDIS_HOST] [-rp REDIS_PORT] [-rk REDIS_KEY] [-d] [-v]

		🌍🚢 alist 网络代理抓包 🕷️🕸️

options:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -p PORT, --port PORT  端口号，默认值：5245
  -b BASE_URL, --base-url BASE_URL
                        被代理的 alist 服务的 base_url，默认值：'http://localhost:5244'
  -t TOKEN, --token TOKEN
                        alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
  -nr, --no-redis       不使用 redis，直接输出到控制台，主要用于调试
  -rh REDIS_HOST, --redis-host REDIS_HOST
                        redis 服务所在的主机，默认值: 'localhost'
  -rp REDIS_PORT, --redis-port REDIS_PORT
                        redis 服务的端口，默认值: 6379
  -rk REDIS_KEY, --redis-key REDIS_KEY
                        redis streams 的键名，默认值: 'alist:fs'
  -d, --debug           启用 debug 模式（会输出更详细的信息）
  -v, --version         输出版本号

$ alist-proxy
INFO:     Started server process [62319]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5245 (Press CTRL+C to quit)
```

#### 启动准备

首先要求有一个正在运行中的 alist 服务，假设地址为 http://localhost:5244

再有一个正在运行中的 redis 服务，假设地址为 http://localhost:6379

然后启动此程序的命令行，然后在浏览器或 webdav 挂载软件访问 http://localhost:5245 ，就会自动往 redis 服务上，一个键为 'alist:fs' 的 streams 上实时添加数据。

在命令行中提供 alist 的 token 是很有必要的，这样就可以监控后台的 复制、上传、离线下载转存 的事件。

#### websocket 接口

如果你在命令行指定了 -nr/--no-redis 参数，则不会把数据推送到 redis，而是直接输出到控制台（命令行），这便于你在没有部署好 redis 的情况下做一些观察实验。但只有当启用了 redis （默认行为），才可以通过 websocket 访问 <kbd>/pull</kbd> 接口，例如

```python
from asyncio import run
from json import loads

import websockets

async def pull():
    uri = "ws://localhost:5245/pull"
    async with websockets.connect(uri) as websocket:
        while True:
            data = loads(await websocket.recv())
            print(f"Received: {data}")

run(pull())
```

这个 <kbd>/pull</kbd> 接口支持 3 个查询参数，均可省略

- `lastid`: 从这个 id（不含）开始读取。省略时，如果指定了非空的 `group`，则继续这个组的读取进度，否则从当前开始（不管以前）读取。如果要从头开始读取，指定 '0' 即可
- `group`: 组名称。如果组不存在，则自动创建。
- `name`: 消费者名称。

#### 事件说明

命令行程序只采集和文件系统操作有关的事件消息

你可以从 <kbd>/pull</kbd> 接口拉取 json 格式的数据。这些数据有几个共同的字段

1. category: 任务类别。有 3 个可能的值：
    - <kbd>web</kbd>: 由网页直接调用接口成功后产生
    - <kbd>dav</kbd>: 通过 webdav 的成功操作产生
    - <kbd>task</kbd>: 监控后台任务，由执行成功的任务产生
2. type: 任务类型。可能的取值如下：
    - <kbd>upload</kbd>: 上传/创建 文件
    - <kbd>rename</kbd>: 文件或目录的改名
    - <kbd>move</kbd>: 移动文件或目录（webdav 还包括改名）
    - <kbd>remove</kbd>: 删除文件或目录
    - <kbd>copy</kbd>: 复制文件或目录
    - <kbd>mkdir</kbd>: 创建空目录
    - <kbd>find</kbd>: 查询文件或目录的信息，或罗列目录
3. method: 具体的操作方法
4. payload: 和路径有关的数据，每组（由 (method, category, type) 一起确定）都有所不同

同一种 category 的各个 method 的 payload 的字段构成近似。

- <kbd>web</kbd>: payload 收集了相关的查询参数，详见 https://alist.nn.ci/guide/api/fs.html
- <kbd>dav</kbd>: 一般包含
    - <kbd>path</kbd>: 被操作的路径 
    - <kbd>is_dir</kbd>: 是否目录

    可能包含

    - <kbd>to_path</kbd>: 操作后的路径（COPY 或 MOVE）
- <kbd>task</kbd>: 目前有 3 种情况
    - <kbd>method</kbd> 为 copy，即复制，包含 
        - <kbd>src_path</kbd>: 源路径
        - <kbd>dst_path</kbd>: 目标路径
        - <kbd>src_storage</kbd>: 源所在存储
        - <kbd>dst_storage</kbd>: 目标所在存储
        - <kbd>src_dir</kbd>: 源所在目录
        - <kbd>dst_dir</kbd>: 目标所在目录
        - <kbd>name</kbd>: 名字
        - <kbd>is_dir</kbd>: 是否目录
    - <kbd>method</kbd> 为 upload，即上传，包含
        - <kbd>path</kbd>: 目标路径
        - <kbd>dst_storage</kbd>: 目标所在存储
        - <kbd>dst_dir</kbd>: 目标所在目录
        - <kbd>name</kbd>: 名字
        - <kbd>is_dir</kbd>: 是否目录，必为 False
    - <kbd>method</kbd> 为 transfer，即离线下载后上传，包含
        - <kbd>path</kbd>: 目标路径
        - <kbd>dst_dir</kbd>: 目标所在目录
        - <kbd>name</kbd>: 名字
        - <kbd>is_dir</kbd>: 是否目录，必为 False
