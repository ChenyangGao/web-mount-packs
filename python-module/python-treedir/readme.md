# Iterate a directory in a tree-like format..

## 安装

你可以通过 [pypi](https://pypi.org/project/python-treedir/) 安装

```console
pip install -U python-treedir
```

## 使用

### 用作模块

提供了一个函数 `treedir()` 可用于遍历目录树

```python
>>> from treedir import treedir
>>> help(treedir)
Help on function treedir in module treedir:

treedir(top: Union[bytes, str, os.PathLike, ~T] = '.', /, min_depth: int = 0, max_depth: int = -1, onerror: bool | collections.abc.Callable[[OSError], typing.Any] = False, predicate: None | collections.abc.Callable[[~T], None | bool] = None, iterdir: collections.abc.Callable[[typing.Union[bytes, str, os.PathLike, ~T]], ~T] = <built-in function scandir>, is_dir: None | collections.abc.Callable[[~T], bool] = None, _depth: int = 0)
    遍历导出目录树。
    
    :param top: 根路径，默认为当前目录。
    :param min_depth: 最小深度，小于 0 时不限。参数 `top` 本身的深度为 0，它的直接跟随路径的深度是 1，以此类推。
    :param max_depth: 最大深度，小于 0 时不限。
    :param onerror: 处理 OSError 异常。如果是 True，抛出异常；如果是 False，忽略异常；如果是调用，以异常为参数调用之。
    :param predicate: 调用以筛选遍历得到的路径。
    :param iterdir: 迭代罗列目录。
    :param is_dir: 判断是不是目录，如果为 None，则从 iterdir 所得路径上调用 is_dir() 方法。
    
    :return: 没有返回值，只是在 stdout 输出目录树文本，类似 tree 命令。
```

### 用作命令

提供一个命令行工具，用于导出目录树

```console
$ treedir -h
usage: treedir [-h] [-m MIN_DEPTH] [-M MAX_DEPTH] [-s SELECT] [-se] [-fl] [-v] [top]

目录树遍历导出，树形结构

positional arguments:
  top                   根目录路径，默认为当前工作目录

options:
  -h, --help            show this help message and exit
  -m MIN_DEPTH, --min-depth MIN_DEPTH
                        最小深度，默认值 0，小于 0 时不限
  -M MAX_DEPTH, --max-depth MAX_DEPTH
                        最大深度，默认值 -1，小于 0 时不限
  -s SELECT, --select SELECT
                        对路径进行筛选，提供一个表达式（会注入一个变量 path，类型是 pathlib.Path）或函数（会传入一个参数，类型是 pathlib.Path）
  -se, --select-exec    对 -s/--select 传入的代码用 exec 运行，其中必须存在名为 select 的函数。否则，视为表达式或 lambda 函数
  -fl, --follow-symlinks
                        跟进符号连接，否则会把符号链接视为文件，即使它指向目录
  -v, --version         输出版本号
```
