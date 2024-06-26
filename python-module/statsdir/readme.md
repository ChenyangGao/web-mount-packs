# Python statsdir.

## 安装

你可以通过 [pypi](https://pypi.org/project/statsdir/) 安装

```console
pip install -U statsdir
```

## 使用

### 用作模块

提供了一个函数 `statsdir()` 可用于遍历目录树

```python
>>> from statsdir import statsdir
>>> help(statsdir)
Help on function statsdir in module statsdir:

statsdir(top=None, /, min_depth: int = 0, max_depth: int = -1, predicate: None | collections.abc.Callable[..., None | bool] = None, onerror: bool | collections.abc.Callable[[OSError], Any] = False, follow_symlinks: bool = False, key: None | collections.abc.Callable = None) -> dict
    目录树遍历统计。
    
    :param top: 根路径，默认为当前目录。
    :param min_depth: 最小深度，小于 0 时不限。参数 `top` 本身的深度为 0，它的直接跟随路径的深度是 1，以此类推。
    :param max_depth: 最大深度，小于 0 时不限。
    :param predicate: 调用以筛选遍历得到的路径。可接受的参数与参数 `top` 的类型一致，参见 `:return:` 部分。
    :param onerror: 处理 OSError 异常。如果是 True，抛出异常；如果是 False，忽略异常；如果是调用，以异常为参数调用之。
    :param follow_symlinks: 是否跟进符号连接（如果为否，则会把符号链接视为文件，即使它指向目录）。
    :param key: 计算以得到一个 key，相同的 key 为一组，对路径进行分组统计。
    
    :return: 返回统计数据，形如
        {
            "path": str,     # 根路径 
            "total": int,    # 包含路径总数 = 目录数 + 文件数
            "dirs": int,     # 包含目录数
            "files": int,    # 包含文件数
            "size": int,     # 文件总大小（符号链接视为文件计入）
            "fmt_size": str, # 文件总大小，换算为适当的单位：B (Byte), KB (Kilobyte), MB (Megabyte), GB (Gigabyte), TB (Terabyte), PB (Petabyte), ...
            # OPTIONAL: 如果提供了 key 函数
            "keys": {
                a_key: {
                    "total": int, 
                    "dirs": int, 
                    "files": int, 
                    "size": int, 
                    "fmt_size": str, 
                }, 
                ...
            }
        }
    。
```

### 用作命令

提供一个命令行工具，用于导出目录树

```console
$ statsdir -h
usage: statsdir [-h] [-m MIN_DEPTH] [-M MAX_DEPTH] [-s SELECT] [-se] [-k KEY] [-ke] [-fl] [-v] [paths ...]

目录树遍历统计

positional arguments:
  paths                 文件夹路径，多个用空格隔开，默认从 stdin 读取

options:
  -h, --help            show this help message and exit
  -m MIN_DEPTH, --min-depth MIN_DEPTH
                        最小深度，默认值 0，小于 0 时不限
  -M MAX_DEPTH, --max-depth MAX_DEPTH
                        最大深度，默认值 -1，小于 0 时不限
  -s SELECT, --select SELECT
                        对路径进行筛选，提供一个表达式（会注入一个变量 path，类型是 pathlib.Path）或函数（会传入一个参数，类型是 pathlib.Path）
  -se, --select-exec    对 -s/--select 传入的代码用 exec 运行，其中必须存在名为 select 的函数。否则，视为表达式或 lambda 函数
  -k KEY, --key KEY     对路径进行分组统计，提供一个表达式（会注入一个变量 path，类型是 pathlib.Path）或函数（会传入一个参数，类型是 pathlib.Path）
  -ke, --key-exec       对 -k/--key 传入的代码用 exec 运行，其中必须存在名为 key 的函数。否则，视为表达式或 lambda 函数
  -fl, --follow-symlinks
                        跟进符号连接，否则会把符号链接视为文件，即使它指向目录
  -v, --version         输出版本
```
