# 115 分享链接 webdav 挂载工具

## 帮助信息

```console
$ python python-115-share-link-webdav -h
python /Users/gcy/project_github/web-mount-packs/python-115-share-link-webdav -h            
usage: python-115-share-link-webdav [-h] [-ck COOKIE_PATH] [-l LINKS_FILE] [-c CONFIG] [-H HOST] [-p PORT] [-v {0,1,2,3,4,5}] [-w]

    115 分享链接 webdav 挂载工具

源码地址：https://github.com/ChenyangGao/web-mount-packs/tree/main/python-115-share-link-webdav

options:
  -h, --help            show this help message and exit
  -ck COOKIE_PATH, --cookie-path COOKIE_PATH
                        保存 cookie 的文件，如果没有，就扫码登录，缺省时则用当前工作目录下的 cookie.txt 文件，格式为
                        
                            UID=XXXX; CID=YYYY; SEID=ZZZZ; 
                        
  -l LINKS_FILE, --links-file LINKS_FILE
                        包含分享链接的配置文件（必须 yaml 文件格式，UTF-8编码），
                        缺省时则用当前工作目录下的 links.yml 文件
                        
                        配置的格式，支持如下几种形式：
                        1. 单个分享链接
                        
                            https://115.com/s/xxxxxxxxxxx?password=yyyy#
                        
                        2. 多个分享链接，但需要有名字
                        
                            链接1: https://115.com/s/xxxxxxxxxxx?password=yyyy#
                            链接2: https://115.com/s/xxxxxxxxxxx?password=yyyy#
                            链接3: https://115.com/s/xxxxxxxxxxx?password=yyyy#
                        
                        3. 多个分享链接，支持多层目录结构
                        
                            一级目录:
                                链接1: https://115.com/s/xxxxxxxxxxx?password=yyyy#
                                二级目录:
                                    链接2: https://115.com/s/xxxxxxxxxxx?password=yyyy#
                            链接3: https://115.com/s/xxxxxxxxxxx?password=yyyy#
                        
  -c CONFIG, --config CONFIG
                        WsgiDav 的配置文件（必须 yaml 文件格式，UTF-8编码），
                        缺省时则用当前工作目录下的 wsgidav.yaml 文件，不存在时会自动创建，
                        命令行的 --host|-H、--port|-p|-P 和 --verbose|-v 有更高优先级
  -H HOST, --host HOST  主机地址，默认 0.0.0.0，你也可以用 localhost、127.0.0.1 或者其它
  -p PORT, -P PORT, --port PORT
                        端口号，默认 8080
  -v {0,1,2,3,4,5}, --verbose {0,1,2,3,4,5}
                        输出日志信息，默认级别 3
                        
                        Set verbosity level
                        
                        Verbose Output:
                            0 - no output
                            1 - no output (excepting application exceptions)
                            2 - show warnings
                            3 - show single line request summaries (for HTTP logging)
                            4 - show additional events
                            5 - show full request/response header info (HTTP Logging)
                                request body and GET response bodies not shown
  -w, --watch-config    如果指定此参数，则会监测配置文件的变化
                            针对 -ck/--cookie-path: 默认时 cookie.txt，更新cookie
                            针对 -l/--links-file:   默认是 links.yml，更新分享链接
                            针对 -c/--config:       默认是 wsgidav.yaml，更新配置文件，会重启服务器（慎用）
                        
                        因为有些用户提到，找不到配置文件，所以我额外增加了一个挂载目录，在 webdav 服务的 /_workdir 路径，默认情况下配置文件在这个目录里面，你可以单独挂载此路径，然后修改配置文件
```

## 打包程序

```console
$ bash python-115-share-link-webdav/pack.sh 
Created a package file located in 
	/path/to/python-115-share-link-webdav_x.y.z.pyz
```

## Docker 运行

> 配置文件会在 `~/python-115-share-link-webdav` 中生成，你可以进行修改。
>   - cookie.txt: cookie文件
>   - wsgidav.yaml: [wsgidav](https://github.com/mar10/wsgidav) 的 [配置文件](https://wsgidav.readthedocs.io/en/latest/user_guide_configure.html)
>   - links.yml: 115分享链接的配置文件

### 1. 直接拉取镜像运行

直接从 [docker hub](https://hub.docker.com/repository/docker/chenyanggao/python-115-share-link-webdav) 上拉取镜像

```console
docker pull chenyanggao/python-115-share-link-webdav:latest
```

第 1 次运行需要扫码登录，所以不要后台运行

```console
docker run --rm -it \
    -p 8080:8080 \
    -v ~/python-115-share-link-webdav:/etc/python-115-share-link-webdav \
    --name="python-115-share-link-webdav" \
    chenyanggao/python-115-share-link-webdav
```

扫码登录成功，本地就有 cookie 缓存，可以输入 <keyboard>CTRL</keyboard>-<keyboard>C</keyboard> 结束进程，以后就可以指定后台运行

```console
docker run -d \
    -p 8080:8080 \
    -v ~/python-115-share-link-webdav:/etc/python-115-share-link-webdav \
    --restart=always \
    --name="python-115-share-link-webdav" \
    chenyanggao/python-115-share-link-webdav
```

如果第 1 次也想要后台运行，而且以后也运行相同的命令，可以运行下面的命令，在 docker 后台看运行日志，有二维码可以扫

```console
docker run -d -t \
    -p 8080:8080 \
    -v ~/python-115-share-link-webdav:/etc/python-115-share-link-webdav \
    --restart=always \
    --name="python-115-share-link-webdav" \
    chenyanggao/python-115-share-link-webdav
```

### 2. docker compose 运行

首先你需要进入这个项目的目录下

```console
cd /path/to/python-115-share-link-webdav
```

第 1 次运行需要扫码登录，所以不要后台运行

```console
docker compose up
```

扫码登录成功，本地就有 cookie 缓存，可以输入 <keyboard>CTRL</keyboard>-<keyboard>C</keyboard> 结束进程，以后就可以指定后台运行

```console
docker compose up -d
```

### 3. docker run 运行

首先你需要进入这个项目的目录下

```console
cd /path/to/python-115-share-link-webdav
```

然后构建镜像，这里取名为 `chenyanggao/python-115-share-link-webdav`

```console
docker build --rm -t chenyanggao/python-115-share-link-webdav 
```

以后你就可以直接运行镜像了。

第 1 次运行需要扫码登录，所以不要后台运行

```console
docker run --rm -it \
    -p 8080:8080 \
    -v ~/python-115-share-link-webdav:/etc/python-115-share-link-webdav \
    --name="python-115-share-link-webdav" \
    chenyanggao/python-115-share-link-webdav
```

扫码登录成功，本地就有 cookie 缓存，可以输入 <keyboard>CTRL</keyboard>-<keyboard>C</keyboard> 结束进程，以后就可以指定后台运行

```console
docker run -d \
    -p 8080:8080 \
    -v ~/python-115-share-link-webdav:/etc/python-115-share-link-webdav \
    --restart=always \
    --name="python-115-share-link-webdav" \
    chenyanggao/python-115-share-link-webdav
```

如果第 1 次也想要后台运行，而且以后也运行相同的命令，可以运行下面的命令，在 docker 后台看运行日志，有二维码可以扫

```console
docker run -d -t \
    -p 8080:8080 \
    -v ~/python-115-share-link-webdav:/etc/python-115-share-link-webdav \
    --restart=always \
    --name="python-115-share-link-webdav" \
    chenyanggao/python-115-share-link-webdav
```

