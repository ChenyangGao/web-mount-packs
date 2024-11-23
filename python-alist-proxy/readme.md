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
    make_application(alist_token: str = '', base_url: str = 'http://localhost:5244', collect: None | collections.abc.Callable[[dict], typing.Any] = None, webhooks: None | collections.abc.Sequence[str] = None, project: None | collections.abc.Callable[[dict], None | dict] = None, threaded: bool = False) -> blacksheep.server.application.Application
        创建一个 blacksheep 应用，用于反向代理 alist，并持续收集每个请求事件的消息
        
        :param alist_token: alist 的 token，提供此参数可在 115 网盘遭受 405 风控时自动扫码刷新 cookies
        :param base_url: alist 的 base_url
        :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
        :param webhooks: 一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}
        :param project: 调用以对请求事件的消息进行映射处理，如果结果为 None，则丢弃此消息
        :param threaded: collect 和 project，如果不是 async 函数，就放到单独的线程中运行
        
        :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行
    
    make_application_with_fs_event_stream(alist_token: str, base_url: str = 'http://localhost:5244', db_uri: str = 'sqlite', webhooks: None | collections.abc.Sequence[str] = None)
        只收集和文件系统操作有关的事件，存储到 redis streams，并且可以通过 websocket 拉取
        
        :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
        :param base_url: alist 的 base_url
        :param db_uri: 数据库连接的 URI，格式为 "{dbtype}://{host}:{port}/{path}
        
            - dbtype: 数据库类型，目前仅支持 "sqlite"、"mongodb" 和 "redis"
            - host: （非 "sqlite"）ip 或 hostname，如果忽略，则用 "localhost"
            - port: （非 "sqlite"）端口号，如果忽略，则自动使用此数据库的默认端口号
            - path: （限 "sqlite"）文件路径，如果忽略，则为 ""（会使用一个临时文件）
        
            如果你只输入 dbtype 的名字，则视为 "{dbtype}://"
            如果你输入了值，但不能被视为 dbtype，则自动视为 path，即 "sqlite:///{path}"
        :param webhooks: 一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}
        
        :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行

    make_application_with_fs_events(alist_token: str = '', base_url: str = 'http://localhost:5244', collect: None | collections.abc.Callable[[dict], typing.Any] = None, webhooks: None | collections.abc.Sequence[str] = None, threaded: bool = False) -> blacksheep.server.application.Application
        只收集和文件系统操作有关的事件
        
        :param alist_token: alist 的 token，用来追踪后台任务列表（若不提供，则不追踪任务列表）
        :param base_url: alist 的 base_url
        :param collect: 调用以收集 alist 请求事件的消息（在 project 调用之后），如果为 None，则输出到日志
        :param webhooks: 一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}
        :param threaded: collect 如果不是 async 函数，就放到单独的线程中运行
        
        :return: 一个 blacksheep 应用，你可以二次扩展，并用 uvicorn 运行

VERSION
    (0, 0, 9)

AUTHOR
    ChenyangGao <https://chenyanggao.github.io>
```

### 命令行使用

```console
$ alist-proxy -h
usage: alist_proxy [-h] [-H HOST] [-P PORT] [-b BASE_URL] [-t TOKEN] [-u DB_URI] [-w [webhook ...]] [-d] [-v]

		🌍🚢 alist 网络代理抓包 🕷️🕸️

options:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -P PORT, --port PORT  端口号，默认值：5245
  -b BASE_URL, --base-url BASE_URL
                        被代理的 alist 服务的 base_url，默认值：'http://localhost:5244'
  -t TOKEN, --token TOKEN
                        alist 的 token，用来追踪后台任务列表和更新某些 cookies
  -u DB_URI, --db-uri DB_URI
                        数据库连接的 URI，格式为 "{dbtype}://{host}:{port}/{path}"
                            - dbtype: 数据库类型，目前仅支持 "sqlite"、"mongodb" 和 "redis"
                            - host: （非 "sqlite"）ip 或 hostname，如果忽略，则用 "localhost"
                            - port: （非 "sqlite"）端口号，如果忽略，则自动使用此数据库的默认端口号
                            - path: （限 "sqlite"）文件路径，如果忽略，则为 ""（会使用一个临时文件）
                        如果你只输入 dbtype 的名字，则视为 "{dbtype}://"
                        如果你输入了值，但不能被视为 dbtype，则自动视为 path，即 "sqlite:///{path}"
  -w [webhook ...], --webhooks [webhook ...]
                        一组 webhook 的链接，事件会用 POST 请求发送给每一个链接，响应头为 {"Content-type": "application/json; charset=utf-8"}
  -d, --debug           启用 debug 模式（会输出更详细的信息）
  -v, --version         输出版本

$ alist-proxy
INFO:     Started server process [64373]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5245 (Press CTRL+C to quit)
```

#### 启动准备

首先要求有一个正在运行中的 alist 服务，假设地址为 http://localhost:5244

然后在命令行中运行

```console
alist-proxy --base-url http://localhost:5244
```

就可以开始代理监听了。如果 --base-url 就是默认地址 http://localhost:5244，是可以省略的。

如果你还需要监听后台的 **复制**、**上传**、**离线下载转存** 事件，则需要在命令行中提供 alist 的 token。

```console
ALIST_TOKEN='alist-xxxx'
alist-proxy --token "$ALIST_TOKEN"
```

如果你需要使用 webhook，则需要指定 -w/--webhooks 参数。

如果你需要使用 websocket，则需要指定 --db-uri 参数，以将数据存储到数据库，目前只支持 sqlite、mongodb 和 redis。

#### webhook 接口

如果你指定了 -w/--webhooks 参数，就会发送事件到指定的这组链接上

```console
alist-proxy -w http://localhost:8888/webhook
```

客户端代码

```python
from flask import request, Flask

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def handle_post():
    data = request.get_json()
    print(f"Received: {data}")
    return "", 200

app.run(port=8888, threaded=True)
```

#### websocket 接口

如果你指定了 -u/--db-uri 参数，就可以使用 websocket 接口 <kbd>/pull</kbd>

```console
alist-proxy -u sqlite
```

客户端代码

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

##### redis

<kbd>/pull</kbd> 接口支持 3 个查询参数，均可省略，省略则从当前开始拉取最新数据

- `lastid`: 从这个 id（不含）开始读取。省略时，如果指定了非空的 `group`，则继续这个组的读取进度，否则从当前开始（不管以前）读取。如果要从头开始读取，指定 '0' 即可
- `group`: 组名称。如果组不存在，则自动创建。
- `name`: 消费者名称。

##### mongodb

<kbd>/pull</kbd> 接口支持 2 个查询参数，均可省略，省略则从当前开始拉取最新数据

- `lastid`: 从这个 id（不含）开始读取，是一个字符串，表示 UUID。
- `from_datetime`: 从这个时间点开始，是一个字符串。

##### sqlite

<kbd>/pull</kbd> 接口支持 2 个查询参数，均可省略，省略则从当前开始拉取最新数据

- `lastid`: 从这个 id（不含）开始读取，是一个整数，表示自增主键。
- `from_datetime`: 从这个时间点开始，是一个字符串。

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
