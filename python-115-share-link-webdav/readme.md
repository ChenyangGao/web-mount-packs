# 115 分享链接 webdav 挂载工具

## 帮助信息

```console
$ python python-115-share-link-webdav -h
usage: python-115-share-link-webdav [-h] [-ck COOKIE_PATH] [-l LINKS_FILE]
                                    [-c CONFIG] [-H HOST] [-p PORT]
                                    [-v {0,1,2,3,4,5}]

    115 分享链接 webdav 挂载工具 (version: x.y.z)

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
  -H HOST, --host HOST  端口号，默认 0.0.0.0
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
```

## 打包程序

```console
$ bash python-115-share-link-webdav/pack.sh 
Created a package file located in 
	/path/to/python-115-share-link-webdav_x.y.z.pyz
```
