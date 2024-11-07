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
usage: reverse-proxy [-h] [-H HOST] [-P PORT] [-b BASE_URL] [-d] [-v]

		🌍🚢 python 反向代理服务 🕷️🕸️

options:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -P PORT, --port PORT  端口号，如果不提供，则自动确定
  -b BASE_URL, --base-url BASE_URL
                        被代理的服务的 base_url，默认值：'http://localhost'
  -d, --debug           启用 debug 模式（会输出更详细的信息）
  -v, --version         输出版本号
```
