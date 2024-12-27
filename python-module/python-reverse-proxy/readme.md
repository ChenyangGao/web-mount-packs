# Python reverse proxy.

## 安装

你可以从 [pypi](https://pypi.org/project/python-reverse-proxy/) 安装

```console
pip install -U python-reverse-proxy
```

## 用法

### 作为模块使用

```python
from reverse_proxy import make_application
```

### 命令行使用

```console
$ proxy -h
usage: reverse_proxy [-h] [-H HOST] [-P PORT] [-m {,r,w,rw}] [-d] [-c CONFIG] [-v] [base-url]

		🌍🚢 python 反向代理服务 🕷️🕸️

positional arguments:
  base-url              被代理的服务的 base_url，默认值：'http://localhost'

options:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -P PORT, --port PORT  端口号，默认值：8888，如果为 0 则自动确定
  -m {,r,w,rw}, --ws-mode {,r,w,rw}
                        websocket 的读写模式，'r' 为可读，'w' 为可写
  -d, --debug           启用 debug 模式（会输出更详细的信息）
  -c CONFIG, --config CONFIG
                        将被作为 JSON 解析然后作为关键字参数传给 `uvicorn.run`
  -v, --version         输出版本号
```
