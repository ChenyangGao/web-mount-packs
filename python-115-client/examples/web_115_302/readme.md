# 115 的 302 和 webdav 服务

## 帮助信息

```console
$ python web_115_302 -h         
usage: web_115_302 [-h] [-c COOKIES] [-cp COOKIES_PATH] [-wc WEB_COOKIES] [-l] [-pc] [-ur {httpx,requests,urllib3,urlopen}] [-r ROOT]
                   [-P PASSWORD] [-H HOST] [-p PORT] [-d] [-v]

    🕸️ 获取你的 115 网盘账号上文件信息和下载链接 🕷️

🚫 注意事项：请求头需要携带 User-Agent。
如果使用 web 的下载接口，则有如下限制：
    - 大于等于 115 MB 时不能下载
    - 不能直接请求直链，需要携带特定的 Cookie 和 User-Agent

options:
  -h, --help            show this help message and exit
  -c COOKIES, --cookies COOKIES
                        115 登录 cookies，优先级高于 -cp/--cookies-path
  -cp COOKIES_PATH, --cookies-path COOKIES_PATH
                        存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一: 
                            1. 当前工作目录
                            2. 用户根目录
                            3. 此脚本所在目录
  -wc WEB_COOKIES, --web-cookies WEB_COOKIES
                        提供一个 web 的 cookies，因为目前使用的获取 .m3u8 的接口，需要 web 的 cookies 才能正确获取数据，如不提供，则将自动扫码获取
  -l, --lock-dir-methods
                        对 115 的文件系统进行增删改查的操作（但不包括上传和下载）进行加锁，限制为单线程，这样就可减少 405 响应，以降低扫码的频率
  -pc, --path-persistence-commitment
                        路径持久性承诺，只要你能保证文件不会被移动（可新增删除，但对应的路径不可被其他文件复用），打开此选项，用路径请求直链时，可节约一半时间
  -ur {httpx,requests,urllib3,urlopen}, --use-request {httpx,requests,urllib3,urlopen}
                        选择一个网络请求模块，默认值：httpx
  -r ROOT, --root ROOT  选择一个根 路径 或 id，默认值 0
  -P PASSWORD, --password PASSWORD
                        密码，如果提供了密码，那么每次访问必须携带请求参数 ?password={password}
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -p PORT, --port PORT  端口号，默认值：80
  -d, --debug           启用 debug 模式，当文件变动时自动重启 + 输出详细的错误信息
  -v, --version         输出版本号

---------- 使用说明 ----------

你可以打开浏览器进行直接访问。

1. 如果想要访问某个路径，可以通过查询接口

    GET {path}

或者

    GET ?path={path}

也可以通过 pickcode 查询

    GET ?pickcode={pickcode}

也可以通过 id 查询

    GET ?id={id}

也可以通过 sha1 查询（必是文件）

    GET ?sha1={sha1}

2. 查询文件或文件夹的信息，返回 json

    GET ?method=attr

3. 查询文件夹内所有文件和文件夹的信息，返回 json

    GET ?method=list

4. 获取文件的下载链接

    GET ?method=url

5. 查询文件或文件夹的备注

    GET ?method=desc

6. 支持的查询参数

 参数    | 类型    | 必填 | 说明
-------  | ------- | ---- | ----------
pickcode | string  | 否   | 文件或文件夹的 pickcode，优先级高于 id
id       | integer | 否   | 文件或文件夹的 id，优先级高于 sha1
sha1     | string  | 否   | 文件或文件夹的 id，优先级高于 path
path     | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
method   | string  | 否   | 0. '':     缺省值，直接下载
         |         |      | 2. 'url':  这个文件的下载链接和请求头，JSON 格式
         |         |      | 2. 'attr': 这个文件或文件夹的信息，JSON 格式
         |         |      | 3. 'list': 这个文件夹内所有文件和文件夹的信息，JSON 格式
         |         |      | 4. 'desc': 这个文件或文件夹的备注，text/html

7. 支持 webdav

在浏览器或 webdav 挂载软件 中输入（可以有个端口号） http://localhost/<dav
目前没有用户名和密码就可以浏览，支持 302
```

## 打包程序

```console
$ web_115_302/pack.sh 
Created a package file located in 
	/path/to/web_115_302_x.y.z.pyz
```

## Docker 运行

> 配置文件会在 `~/web_115_302` 中生成，你可以进行修改。
>   - <kbd>115-cookies.txt</kbd>: 保存 cookies 的文本文件

并且支持 2 个环境变量：
- <kbd>COOKIES</kbd>:    cookies，不提供则需要扫码
- <kbd>LOGIN_APP</kbd>:  登录设备，发生扫码时会用于绑定，如果不提供则和传入的 cookies 的设备一致，由 cookies 也获取不了的用默认值 "qandroid"

### 1. docker compose 运行（推荐 👍）

首先你需要进入这个项目的目录下

```console
cd /path/to/web_115_302
```

第 1 次运行需要扫码登录，所以不要后台运行

```console
docker compose up
```

扫码登录成功，本地就有 cookie 缓存，可以输入 <keyboard>CTRL</keyboard>-<keyboard>C</keyboard> 结束进程，以后就可以指定后台运行

```console
docker compose up -d
```

也可以直接把 cookies 传递给程序，则直接后台运行即可

```console
COOKIES='UID=...; CID=...; SEID=...'  docker compose up -d
```

### 2. docker run 运行

首先你需要进入这个项目的目录下

```console
cd /path/to/web_115_302
```

然后构建镜像，这里取名为 `chenyanggao/web_115_302`

```console
docker build --rm -t chenyanggao/web_115_302 
```

以后你就可以直接运行镜像了。

第 1 次运行需要扫码登录，所以不要后台运行

```console
docker run --rm -it \
    -p 8000:80 \
    -v ~/web_115_302:/etc/web_115_302 \
    --name="web_115_302" \
    chenyanggao/web_115_302
```

扫码登录成功，本地就有 cookie 缓存，可以输入 <keyboard>CTRL</keyboard>-<keyboard>C</keyboard> 结束进程，以后就可以指定后台运行

```console
docker run -d \
    -p 8000:80 \
    -v ~/web_115_302:/etc/web_115_302 \
    --restart=always \
    --name="web_115_302" \
    chenyanggao/web_115_302
```

如果第 1 次也想要后台运行，而且以后也运行相同的命令，可以运行下面的命令，在 docker 后台看运行日志，有二维码可以扫

```console
docker run -d -t \
    -p 8000:80 \
    -v ~/web_115_302:/etc/web_115_302 \
    --restart=always \
    --name="web_115_302" \
    chenyanggao/web_115_302
```
