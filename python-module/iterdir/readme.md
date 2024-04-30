# Python iterate over path tree.

## 安装

你可以通过 [pypi](https://pypi.org/project/iterdir/) 安装

```console
pip install -U iterdir
```

## 使用

### 用作模块

提供了一个函数 `iterdir()` 可用于遍历目录树

```python
>>> from iterdir import iterdir
>>> help(iterdir)

Help on function iterdir in module iterdir:

iterdir(top=None, /, topdown: Optional[bool] = True, min_depth: int = 1, max_depth: int = 1, predicate: Optional[collections.abc.Callable[..., Optional[bool]]] = None, onerror: bool | collections.abc.Callable[[OSError], bool] = False, follow_symlinks: bool = False) -> collections.abc.Iterator
    遍历目录树
    
    :param top: 根路径，默认为当前目录。
    :param topdown: 如果是 True，自顶向下深度优先搜索；如果是 False，自底向上深度优先搜索；如果是 None，广度优先搜索。
    :param min_depth: 最小深度，小于 0 时不限。参数 `top` 本身的深度为 0，它的直接跟随路径的深度是 1，以此类推。
    :param max_depth: 最大深度，小于 0 时不限。
    :param predicate: 调用以筛选遍历得到的路径。可接受的参数与参数 `top` 的类型一致，参见 `:return:` 部分。
    :param onerror: 处理 OSError 异常。如果是 True，抛出异常；如果是 False，忽略异常；如果是调用，以异常为参数调用之。
    :param follow_symlinks: 是否跟进符号连接（如果为否，则会把符号链接视为文件，即使它指向目录）。
    
    :return: 遍历得到的路径的迭代器。参数 `top` 的类型：
        - 如果是 iterdir.DirEntry，则是 iterdir.DirEntry 实例的迭代器
        - 如果是 pathlib.Path，则是 pathlib.Path 实例的迭代器
        - 否则，得到 `os.fspath(top)` 相同类型的实例的迭代器
```

### 用作命令

提供一个命令行工具，用于导出目录树

```console
$ python -m iterdir -h
usage: __main__ [-h] [-m MIN_DEPTH] [-M MAX_DEPTH]
                [-k [{inode,name,path,relpath,isdir,islink,stat} ...]]
                [-t {log,json,csv}] [-d DUMP] [-de] [-s SELECT] [-se]
                [-o OUTPUT_FILE]
                [-hs [{sha256,sha3_512,sha1,sha512_256,md5,ripemd160,sha512,md5-sha1,sha3_256,sha384,sha3_384,sha512_224,sha224,sm3,shake_128,blake2s,sha3_224,blake2b,shake_256,crc32} ...]]
                [-dfs] [-fl] [-v]
                [path]

目录树信息遍历导出

positional arguments:
  path                  文件夹路径，默认为当前工作目录

options:
  -h, --help            show this help message and exit
  -m MIN_DEPTH, --min-depth MIN_DEPTH
                        最小深度，默认值 0，小于 0 时不限
  -M MAX_DEPTH, --max-depth MAX_DEPTH
                        最大深度，默认值 -1，小于 0 时不限
  -k [{inode,name,path,relpath,isdir,islink,stat} ...], --keys [{inode,name,path,relpath,isdir,islink,stat} ...]
                        选择输出的 key，默认输出所有可选值
  -t {log,json,csv}, --output-type {log,json,csv}
                        输出类型，默认为 log
                        - log   每行输出一条数据，每条数据输出为一个 json 的 object
                        - json  输出一个 json 的 list，每条数据输出为一个 json 的 object
                        - csv   输出一个 csv，第 1 行为表头，以后每行输出一条数据
  -d DUMP, --dump DUMP  (优先级高于 -k/--keys、-hs/--hashes、-t/--output-type) 调用以导出数据，如果有返回值则再行输出，尾部会添加一个 b'
                        '。
                        如果结果 result 是
                            - None，跳过
                            - bytes，输出
                            - 其它，先调用 `bytes(str(result), 'utf-8')`，再输出
                        提供一个表达式（会注入一个变量 path，类型是 pathlib.Path）或函数（会传入一个参数，类型是 pathlib.Path）    
  -de, --dump-exec      对 -d/--dump 传入的代码用 exec 运行，其中必须存在名为 dump 的函数。否则，视为表达式或 lambda 函数
  -s SELECT, --select SELECT
                        对路径进行筛选，提供一个表达式（会注入一个变量 path，类型是 pathlib.Path）或函数（会传入一个参数，类型是 pathlib.Path）
  -se, --select-exec    对 -s/--select 传入的代码用 exec 运行，其中必须存在名为 select 的函数。否则，视为表达式或 lambda 函数
  -o OUTPUT_FILE, --output-file OUTPUT_FILE
                        保存到文件，此时命令行会输出进度条
  -hs [{sha256,sha3_512,sha1,sha512_256,md5,ripemd160,sha512,md5-sha1,sha3_256,sha384,sha3_384,sha512_224,sha224,sm3,shake_128,blake2s,sha3_224,blake2b,shake_256,crc32} ...], --hashes [{sha256,sha3_512,sha1,sha512_256,md5,ripemd160,sha512,md5-sha1,sha3_256,sha384,sha3_384,sha512_224,sha224,sm3,shake_128,blake2s,sha3_224,blake2b,shake_256,crc32} ...]
                        计算文件的哈希值，可以选择多个算法
  -dfs, --depth-first   使用深度优先搜索，否则使用广度优先
  -fl, --follow-symlinks
                        跟进符号连接，否则会把符号链接视为文件，即使它指向目录
  -v, --version         输出版本
```
