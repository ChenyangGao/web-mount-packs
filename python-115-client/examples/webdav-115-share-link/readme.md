# 115 share link webdav

## 帮助信息

```console
$ python webdav-115-share-link -h         
usage: webdav-115-share-link_0.0.1.pyz [-h] [-cp COOKIES_PATH] [-l LINKS_FILE] [-c CONFIG] [-H HOST] [-p PORT]
                                       [-v {0,1,2,3,4,5}] [-w]

        🛸 115 share link webdav 🌌

源码地址：https://github.com/ChenyangGao/web-mount-packs/tree/main/python-115-client/examples/webdav-115-share-link

options:
  -h, --help            show this help message and exit
  -cp COOKIES_PATH, --cookies-path COOKIES_PATH
                        存储 115 登录 cookies 的文本文件的路径，默认为当前工作目录下的 '115-cookies.txt'，文本格式为
                        
                            UID=XXXX; CID=YYYY; SEID=ZZZZ
  -l LINKS_FILE, --links-file LINKS_FILE
                        包含分享链接的配置文件（必须 yaml 文件格式，utf-8 编码），
                        缺省时则用当前工作目录下的 links.yml 文件
                        
                        配置的格式，支持如下几种形式：
                        1. 单个分享链接
                        
                            link
                        
                        2. 多个分享链接，但需要有名字
                        
                            链接1: link1
                            链接2: link2
                            链接3: link3
                        
                        3. 多个分享链接，支持多层目录结构
                        
                            一级目录:
                                链接1: link1
                                二级目录:
                                    链接2: link2
                            链接3: link3
                        
                        支持以下几种格式的链接（括号内的字符表示可有可无）：
                            - http(s)://115.com/s/{share_code}?password={receive_code}(#)
                            - http(s)://share.115.com/{share_code}?password={receive_code}(#)
                            - (/){share_code}-{receive_code}(/)
  -c CONFIG, --config CONFIG
                        WsgiDav 的配置文件（必须 yaml 文件格式，UTF-8编码），
                        缺省时则用当前工作目录下的 wsgidav.yaml 文件，不存在时会自动创建，
                        命令行的 --host|-H、--port|-p|-P 和 --verbose|-v 有更高优先级
  -H HOST, --host HOST  主机地址，默认值：'0.0.0.0'，你也可以用 'localhost'、'127.0.0.1' 或者其它
  -p PORT, -P PORT, --port PORT
                        端口号，默认值：80
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
                            针对 -cp/--cookies-path: 默认是 115-cookies.txt，更新cookie
                            针对 -l/--links-file:    默认是 links.yml，更新分享链接
                            针对 -c/--config:        默认是 wsgidav.yaml，更新配置文件，会重启服务器（慎用）
                        
                        因为有些用户提到，找不到配置文件，所以我额外增加了一个挂载目录，在 webdav 服务的 /_workdir 路径，默认情况下配置文件在这个目录里面，你可以单独挂载此路径，然后修改配置文件
```

## 打包程序

```console
$ bash webdav-115-share-link/pack.sh 
Created a package file located in 
	/path/to/webdav-115-share-link_x.y.z.pyz
```

## Docker 运行

> 配置文件会在 `~/webdav-115-share-link` 中生成，你可以进行修改。
>   - 115-cookies.txt: 保存 cookies 的文本文件
>   - wsgidav.yaml: [wsgidav](https://github.com/mar10/wsgidav) 的 [配置文件](https://wsgidav.readthedocs.io/en/latest/user_guide_configure.html)
>   - links.yml: 115 分享链接的配置文件

### 1. docker compose 运行

首先你需要进入这个项目的目录下

```console
cd /path/to/webdav-115-share-link
```

第 1 次运行需要扫码登录，所以不要后台运行

```console
docker compose up
```

扫码登录成功，本地就有 cookie 缓存，可以输入 <keyboard>CTRL</keyboard>-<keyboard>C</keyboard> 结束进程，以后就可以指定后台运行

```console
docker compose up -d
```

### 2. docker run 运行

首先你需要进入这个项目的目录下

```console
cd /path/to/webdav-115-share-link
```

然后构建镜像，这里取名为 `chenyanggao/webdav-115-share-link`

```console
docker build --rm -t chenyanggao/webdav-115-share-link 
```

以后你就可以直接运行镜像了。

第 1 次运行需要扫码登录，所以不要后台运行

```console
docker run --rm -it \
    -p 8000:8000 \
    -v ~/webdav-115-share-link:/etc/webdav-115-share-link \
    --name="webdav-115-share-link" \
    chenyanggao/webdav-115-share-link
```

扫码登录成功，本地就有 cookie 缓存，可以输入 <keyboard>CTRL</keyboard>-<keyboard>C</keyboard> 结束进程，以后就可以指定后台运行

```console
docker run -d \
    -p 8000:8000 \
    -v ~/webdav-115-share-link:/etc/webdav-115-share-link \
    --restart=always \
    --name="webdav-115-share-link" \
    chenyanggao/webdav-115-share-link
```

如果第 1 次也想要后台运行，而且以后也运行相同的命令，可以运行下面的命令，在 docker 后台看运行日志，有二维码可以扫

```console
docker run -d -t \
    -p 8000:8000 \
    -v ~/webdav-115-share-link:/etc/webdav-115-share-link \
    --restart=always \
    --name="webdav-115-share-link" \
    chenyanggao/webdav-115-share-link
```

