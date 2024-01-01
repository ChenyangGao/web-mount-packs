# 百度网盘 Web API 的 Python 封装

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/python-dupan)
![PyPI - Version](https://img.shields.io/pypi/v/python-dupan)
![PyPI - Downloads](https://img.shields.io/pypi/dm/python-dupan)
![PyPI - Format](https://img.shields.io/pypi/format/python-dupan)
![PyPI - Status](https://img.shields.io/pypi/status/python-dupan)

## 安装

通过 [pypi](https://pypi.org/project/python-dupan/)

```console
pip install -U python-dupan
```

## 入门介绍

### 1. 导入模块和创建实例

**导入模块**

```python
from dupan import DuPanClient
```

**创建客户端对象，需要传入 <kbd>cookie</kbd>，如果不传或者 <kbd>cookie</kbd> 失效，则需要扫码登录**

```python
cookie = "BDUSS=...;STOKEN=..."
client = DuPanClient(cookie)
```

## 文档

> 正在编写中
