# Python clouddrive reverse proxy.

## 安装

你可以从 [pypi](https://pypi.org/project/python-clouddrive-proxy/) 安装

```console
pip install -U python-clouddrive-proxy
```

## 用法

### 作为模块使用

```python
from clouddrive_proxy import make_application
```

### 命令行使用

```console
$ clouddrive-proxy -h
usage: clouddrive_proxy [-h] -u USERNAME -p PASSWORD [-115 BASE_URL_115] [-H HOST] [-P PORT] [-db DBFILE] [-d] [-v] [-l] [base-url]

        🌍🚢 clouddrive 反向代理和功能扩展 🕷️🕸️

目前实现的功能：
✅ 反向代理
✅ 115 的下载可用 p115nano302 代理，实现 302

positional arguments:
  base-url              被代理的 clouddrive 服务的 base_url，默认值：'http://localhost:19798'

options:
  -h, --help            show this help message and exit
  -u USERNAME, --username USERNAME
                        用户名
  -p PASSWORD, --password PASSWORD
                        密码
  -115 BASE_URL_115, --base-url-115 BASE_URL_115
                        115 代理下载链接，默认为 http://localhost:8000，请部署一个 https://pypi.org/project/p115nano302/
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -P PORT, --port PORT  端口号，默认值：19797
  -db DBFILE, --dbfile DBFILE
                        clouddrive 的持久化缓存的数据库文件路径或者所在目录，文件名为 dir_cache.sqlite
  -d, --debug           启用 debug 模式（会输出更详细的信息）
  -v, --version         输出版本号
  -l, --license         输出授权信息
```
