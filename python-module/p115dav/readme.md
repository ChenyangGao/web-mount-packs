# 115 网盘 WebDAV 和 302 直链程序.

## 安装

你可以通过 [pypi](https://pypi.org/project/p115dav/) 安装

```console
pip install -U p115dav
```

## 用法

### 命令行使用

```console
$ p115dav -h
usage: p115dav [-h] [-cp COOKIES_PATH] [-o STRM_ORIGIN] [-t TTL] [-p1 PREDICATE]
               [-t1 {ignore,ignore-file,expr,lambda,stmt,module,file,re}] [-p2 STRM_PREDICATE]
               [-t2 {filter,filter-file,expr,lambda,stmt,module,file,re}] [-fs] [-H HOST] [-P PORT] [-d] [-ass]
               [-uc UVICORN_RUN_CONFIG_PATH] [-wc WSGIDAV_CONFIG_PATH] [-l] [-v]
               [dbfile]

    🕸️ 115 网盘 WebDAV 和 302 直链程序 🕷️

positional arguments:
  dbfile                sqlite 数据库文件路径或 URI，如果不传，则自动创建临时文件

options:
  -h, --help            show this help message and exit
  -cp COOKIES_PATH, --cookies-path COOKIES_PATH
                        cookies 文件保存路径，默认为当前工作目录下的 115-cookies.txt
                        如果你需要直接传入一个 cookies 字符串，需要这样写
                        
                        .. code:: shell
                        
                            COOKIES='UID=...; CID=..., SEID=...'
                            p115dav --cookies-path <(echo "$COOKIES")
                        
  -o STRM_ORIGIN, --strm-origin STRM_ORIGIN
                        [WEBDAV] origin 或者说 base_url，用来拼接路径，获取完整链接，默认行为是自行确定
  -t TTL, --ttl TTL     缓存存活时间
                            - 如果等于 0（默认值），则总是更新
                            - 如果为 nan、inf 或者小于 0，则永远存活
                            - 如果大于 0，则存活这么久时间
  -p1 PREDICATE, --predicate PREDICATE
                        [WEBDAV] 断言，当断言的结果为 True 时，文件或目录会被显示
  -t1 {ignore,ignore-file,expr,lambda,stmt,module,file,re}, --predicate-type {ignore,ignore-file,expr,lambda,stmt,module,file,re}
                        [webdav] 断言类型，默认值为 'ignore'
                            - ignore       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 False
                                           NOTE: https://git-scm.com/docs/gitignore#_pattern_format
                            - ignore-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 False
                                           NOTE: https://git-scm.com/docs/gitignore#_pattern_format
                            - expr         表达式，会注入一个名为 path 的类 pathlib.Path 对象
                            - lambda       lambda 函数，接受一个类 pathlib.Path 对象作为参数
                            - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的类 pathlib.Path 对象
                            - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个类 pathlib.Path 对象作为参数
                            - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个类 pathlib.Path 对象作为参数
                            - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
  -p2 STRM_PREDICATE, --strm-predicate STRM_PREDICATE
                        [webdav] strm 断言（优先级高于 -p1/--predicate），当断言的结果为 True 时，文件会被显示为带有 .strm 后缀的文本文件，打开后是链接
  -t2 {filter,filter-file,expr,lambda,stmt,module,file,re}, --strm-predicate-type {filter,filter-file,expr,lambda,stmt,module,file,re}
                        [webdav] 断言类型，默认值为 'filter'
                            - filter       （默认值）gitignore 配置文本（有多个时用空格隔开），在文件路径上执行模式匹配，匹配成功则断言为 True
                                           请参考：https://git-scm.com/docs/gitignore#_pattern_format
                            - filter-file  接受一个文件路径，包含 gitignore 的配置文本（一行一个），在文件路径上执行模式匹配，匹配成功则断言为 True
                                           请参考：https://git-scm.com/docs/gitignore#_pattern_format
                            - expr         表达式，会注入一个名为 path 的类 pathlib.Path 对象
                            - lambda       lambda 函数，接受一个类 pathlib.Path 对象作为参数
                            - stmt         语句，当且仅当不抛出异常，则视为 True，会注入一个名为 path 的类 pathlib.Path 对象
                            - module       模块，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个类 pathlib.Path 对象作为参数
                            - file         文件路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个类 pathlib.Path 对象作为参数
                            - re           正则表达式，模式匹配，如果文件的名字匹配此模式，则断言为 True
  -fs, --fast-strm      快速实现 媒体筛选 和 虚拟 strm，此命令优先级较高，相当于命令行指定
                        
                            --strm-predicate-type expr \
                            --strm-predicate '(
                                path.media_type.startswith(("video/", "audio/")) and
                                path.suffix.lower() != ".ass" or
                                path.suffix.lower() in (".divx", ".iso", ".m2ts", ".swf", ".xvid")
                            )' \
                            --predicate-type expr \
                            --predicate '(
                                path.is_dir() or
                                path.media_type.startswith("image/") or
                                path.suffix.lower() in (".nfo", ".ass", ".ssa", ".srt", ".idx", ".sub", ".txt", ".vtt", ".smi")
                            )'
                        
  -H HOST, --host HOST  ip 或 hostname，默认值：'0.0.0.0'
  -P PORT, --port PORT  端口号，默认值：8000，如果为 0 则自动确定
  -d, --debug           启用 debug 模式，当文件变动时自动重启 + 输出详细的错误信息
  -ass, --load-libass   加载 libass.js，实现 ass/ssa 字幕特效
  -uc UVICORN_RUN_CONFIG_PATH, --uvicorn-run-config-path UVICORN_RUN_CONFIG_PATH
                        uvicorn 启动时的配置文件路径，会作为关键字参数传给 `uvicorn.run`，支持 JSON、YAML 或 TOML 格式，会根据扩展名确定，不能确定时视为 JSON
  -wc WSGIDAV_CONFIG_PATH, --wsgidav-config-path WSGIDAV_CONFIG_PATH
                        WsgiDAV 启动时的配置文件路径，支持 JSON、YAML 或 TOML 格式，会根据扩展名确定，不能确定时视为 JSON
                        如需样板文件，请阅读：
                        
                            https://wsgidav.readthedocs.io/en/latest/user_guide_configure.html#sample-wsgidav-yaml
                        
  -l, --license         输出授权信息
  -v, --version         输出版本号

---------- 使用说明 ----------

你可以打开浏览器进行直接访问。

1. 如果想要访问某个路径，可以通过查询接口

    GET /{path}
    GET /<share/{path}

或者

    GET ?path={path}

也可以通过 pickcode 查询（对于分享无效）

    GET ?pickcode={pickcode}

也可以通过 id 查询

    GET ?id={id}

也可以通过 sha1 查询（必是文件）（对于分享无效）

    GET ?sha1={sha1}

2. 查询文件或文件夹的信息，返回 json

    GET /<attr
    GET /<share/<attr

3. 查询文件夹内所有文件和文件夹的信息，返回 json

    GET /<list
    GET /<share/<list

4. 获取文件的下载链接

    GET /<url
    GET /<share/<url

5. 说明是否文件（如果不传此参数，则需要额外做一个检测）

💡 是文件

    GET ?file=true

💡 是目录

    GET ?file=false

6. 支持的查询参数

      参数       |  类型   | 必填 | 说明
---------------- | ------- | ---- | ----------
?pickcode={path} | string  | 否   | 文件或文件夹的 pickcode，优先级高于 id
?id={id}         | integer | 否   | 文件或文件夹的 id，优先级高于 sha1
?sha1={sha1}     | string  | 否   | 文件或文件夹的 id，优先级高于 path
?path={path}     | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
/{path}          | string  | 否   | 文件或文件夹的路径，位于 url 中的路径部分

💡 如果是分享 （路由路径以 /<share 开始），则支持的参数会少一些

    参数     | 类型    | 必填 | 说明
------------ | ------- | ---- | ----------
?id={id}     | integer | 否   | 文件或文件夹的 id，优先级高于 sha1
?sha1={sha1} | string  | 否   | 文件或文件夹的 id，优先级高于 path
?path={path} | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
/{path}      | string  | 否   | 文件或文件夹的路径，位于 url 中的路径部分

当文件被下载时，可以有其它查询参数

 参数      |  类型   | 必填 | 说明
---------  | ------- | ---- | ----------
image      | boolean | 否   | 文件是图片，可获取 CDN 链接
web        | boolean | 否   | 使用 web 接口获取下载链接（文件由服务器代理转发，不走 302）

7. 支持 webdav

在浏览器或 webdav 挂载软件 中输入

    http://localhost:8000/<dav

默认没有用户名和密码，支持 302

8. 支持分享列表

在浏览器中输入

    http://localhost:8000/<share

在浏览器或 webdav 挂载软件 中输入

    http://localhost:8000/<dav/<share
```
