# Python iterate over path tree.

## 安装

你可以通过 [pypi](https://pypi.org/project/iterdir/) 安装

```console
pip install -U iterdir
```

## 使用

### 用作模块

```python
from iterdir import iterdir
```

### 用作命令

提供一个命令行工具，用于导出目录树

```console
$ iterdir -h
usage: iterdir [-h] [-m MIN_DEPTH] [-M MAX_DEPTH]
               [-k [{inode,name,path,relpath,is_dir,stat,stat_info} ...]]
               [-s SELECT] [-se] [-o OUTPUT_FILE]
               [-hs [{shake_256,blake2b,blake2s,sha512_224,sha224,sha3_384,sha512,ripemd160,sm3,md5-sha1,sha3_256,sha3_224,sha256,sha1,sha384,sha3_512,shake_128,sha512_256,md5,crc32} ...]]
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
  -k [{inode,name,path,relpath,is_dir,stat,stat_info} ...], --keys [{inode,name,path,relpath,is_dir,stat,stat_info} ...]
                        选择输出的 key，默认输出所有可选值
  -s SELECT, --select SELECT
                        对路径进行筛选，提供一个表达式（会注入一个变量 entry，类型是 iterdir.DirEntry）或函数（会传入一个参数，类型是 iterdir.DirEntry）
  -se, --select-exec    对 -s/--select 传入的代码用 exec 运行，其中必须存在名为 select 的函数。否则，视为表达式或 lambda 函数
  -o OUTPUT_FILE, --output-file OUTPUT_FILE
                        保存到文件，此时命令行会输出进度条，根据扩展名来决定输出格式
                        - *.csv   输出一个 csv，第 1 行为表头，以后每行输出一条数据
                        - *.json  输出一个 JSON Object 的列表
                        - *       每行输出一条 JSON Object
  -hs [{shake_256,blake2b,blake2s,sha512_224,sha224,sha3_384,sha512,ripemd160,sm3,md5-sha1,sha3_256,sha3_224,sha256,sha1,sha384,sha3_512,shake_128,sha512_256,md5,crc32} ...], --hashes [{shake_256,blake2b,blake2s,sha512_224,sha224,sha3_384,sha512,ripemd160,sm3,md5-sha1,sha3_256,sha3_224,sha256,sha1,sha384,sha3_512,shake_128,sha512_256,md5,crc32} ...]
                        计算文件的哈希值，可以选择多个算法
  -dfs, --depth-first   使用深度优先搜索，否则使用广度优先
  -fl, --follow-symlinks
                        跟进符号连接，否则会把符号链接视为文件，即使它指向目录
  -v, --version         输出版本号
```
