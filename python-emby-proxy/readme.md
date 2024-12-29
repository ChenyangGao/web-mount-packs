# Python emby reverse proxy.

## 安装

你可以通过 [pypi](https://pypi.org/project/python-emby-proxy/) 安装

```console
pip install -U python-emby-proxy
```

## 用法

### 命令行使用

```console
$ emby-proxy -h
usage: emby-proxy [-h] [-H HOST] [-P PORT] [-d] [-c UVICORN_RUN_CONFIG_PATH] [-v] [-l] [base-url]

		📺 Emby 反向代理 🎬

positional arguments:
  base-url              被代理的 Emby 服务的 base_url，默认值：'http://localhost:8096'

options:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -P PORT, --port PORT  端口号，默认值：8097，如果为 0 则自动确定
  -d, --debug           启用调试，会输出更详细信息
  -c UVICORN_RUN_CONFIG_PATH, -uc UVICORN_RUN_CONFIG_PATH, --uvicorn-run-config-path UVICORN_RUN_CONFIG_PATH
                        uvicorn 启动时的配置文件路径，会作为关键字参数传给 `uvicorn.run`，支持 JSON、YAML 或 TOML 格式，会根据扩展名确定，不能确定时视为 JSON
  -v, --version         输出版本号
  -l, --license         输出授权信息
```
