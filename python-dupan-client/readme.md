# 百度网盘 Web API 的 Python 封装

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/python-dupan)
![PyPI - Version](https://img.shields.io/pypi/v/python-dupan)
![PyPI - Downloads](https://img.shields.io/pypi/dm/python-dupan)
![PyPI - Format](https://img.shields.io/pypi/format/python-dupan)
![PyPI - Status](https://img.shields.io/pypi/status/python-dupan)

## 安装

通过 [pypi](https://pypi.org/project/python-dupan/)

```console
pip install -U python-dupan
```

## 入门介绍

### 1. 导入模块和创建实例

**导入模块**

```python
from dupan import DuPanClient, DuPanFileSystem
```

**创建客户端对象，需要传入 <kbd>cookie</kbd>，如果不传或者 <kbd>cookie</kbd> 失效，则需要扫码登录**

```python
cookie = "BDUSS=...;STOKEN=..."
client = DuPanClient(cookie)
```

**创建文件系统对象**

```python
fs = DuPanFileSystem(client)
```

或者直接在 <kbd>client</kbd> 上就可获取文件系统对象

```python
fs = client.fs
```

或者直接用 <kbd>DuPanFileSystem</kbd> 登录

```python
fs = DuPanFileSystem.login(cookie)
```

### 2. 操作网盘使用 Python 式的文件系统方法

文件系统对象的方法，设计和行为参考了 <kbd>[os](https://docs.python.org/3/library/os.html)</kbd>、<kbd>[posixpath](https://docs.python.org/3/library/os.path.html)</kbd>、<kbd>[pathlib.Path](https://docs.python.org/3/library/pathlib.html)</kbd> 和 <kbd>[shutil](https://docs.python.org/3/library/shutil.html)</kbd> 等模块。

<kbd>dupan.DuPanFileSystem</kbd> 实现了读写的文件系统方法。


| 方法 | 说明 | 参考|
| --- | --- | --- |
| <kbd>\_\_contains\_\_()</kbd><br /><kbd>path in fs</kbd> | 判断路径是否存在 | <kbd>exists()</kbd> |
| <kbd>\_\_delitem\_\_()</kbd><br /><kbd>del fs[path]</kbd> | 删除文件或目录 | <kbd>rmtree()</kbd> |
| <kbd>\_\_getitem\_\_()</kbd><br /><kbd>fs[path]</kbd> | 获取路径对应的 <kbd>dupan.DuPanPath</kbd> 对象 | <kbd>as_path()</kbd> |
| <kbd>\_\_iter\_\_()</kbd><br /><kbd>iter(fs)</kbd> | 遍历目录，获取 <kbd>dupan.DuPanPath</kbd> 对象的迭代器 | <kbd>iter(max_depth=-1)</kbd> |
| <kbd>\_\_itruediv\_\_()</kbd><br /><kbd>fs /= path</kbd> | 切换当前工作目录 | <kbd>chdir()</kbd> |
| <kbd>\_\_len\_\_()</kbd><br /><kbd>len(fs)</kbd> | 获取当前目录的直属文件和目录数 | |
| <kbd>\_\_repr\_\_()</kbd><br /><kbd>repr(fs)</kbd> | 获取对象的字符串表示 | |
| <kbd>\_\_setitem\_\_()</kbd><br /><kbd>fs[path] = data</kbd> | 替换文件或上传目录等 | <kbd>touch()</kbd><br /><kbd>upload()</kbd><br /><kbd>upload_tree()</kbd><br /><kbd>write_bytes()</kbd><br /><kbd>write_text()</kbd> |
| <kbd>abspath()</kbd> | 获取绝对路径 | <kbd>[posixpath.abspath](https://docs.python.org/3/library/os.path.html#os.path.abspath)</kbd> |
| <kbd>as_path()</kbd> | 获取路径对应的 <kbd>dupan.DuPanPath</kbd> 对象 | |
| <kbd>attr()</kbd> | 获取文件或目录的属性 | |
| <kbd>chdir()</kbd><br /><kbd>cd()</kbd> | 切换当前工作目录 | <kbd>[os.chdir](https://docs.python.org/3/library/os.html#os.chdir)</kbd> |
| <kbd>copy()</kbd><br /><kbd>cp()</kbd> | 复制文件 | <kbd>[shutil.copy](https://docs.python.org/3/library/shutil.html#shutil.copy)</kbd> |
| <kbd>copytree()</kbd> | 复制文件或目录 | <kbd>[shutil.copytree](https://docs.python.org/3/library/shutil.html#shutil.copytree)</kbd> |
| <kbd>download()</kbd> | 下载文件 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>download_tree()</kbd> | 下载文件或目录 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>exists()</kbd> | 判断文件或目录是否存在 | <kbd>[posixpath.exists](https://docs.python.org/3/library/os.path.html#os.path.exists)</kbd> |
| <kbd>getcwd()</kbd><br /><kbd>pwd()</kbd> | 获取当前工作目录的路径 | <kbd>[os.getcwd](https://docs.python.org/3/library/os.html#os.getcwd)</kbd> |
| <kbd>get_url()</kbd> | 获取文件的下载链接 | |
| <kbd>glob()</kbd> | 遍历目录并用通配符模式筛选 | <kbd>[glob.iglob](https://docs.python.org/3/library/glob.html#glob.iglob)</kbd><br /><kbd>[pathlib.Path.glob](https://docs.python.org/3/library/pathlib.html#pathlib.Path.glob)</kbd> |
| <kbd>isdir()</kbd> | 判断是否存在且是目录 | <kbd>[posixpath.isdir](https://docs.python.org/3/library/os.path.html#os.path.isdir)</kbd> |
| <kbd>isfile()</kbd> | 判断是否存在且是文件 | <kbd>[posixpath.isfile](https://docs.python.org/3/library/os.path.html#os.path.isfile)</kbd> |
| <kbd>is_empty()</kbd> | 判断是否不存在、空文件或空目录 | |
| <kbd>iter()</kbd> | 遍历目录，获取 <kbd>dupan.DuPanPath</kbd> 对象的迭代器 | |
| <kbd>iterdir()</kbd> | 迭代目录，获取 <kbd>dupan.DuPanPath</kbd> 对象的迭代器 | <kbd>[pathlib.Path.iterdir](https://docs.python.org/3/library/pathlib.html#pathlib.Path.iterdir)</kbd> |
| <kbd>listdir()</kbd><br /><kbd>ls()</kbd> | 罗列目录，获取文件名列表 | <kbd>[os.listdir](https://docs.python.org/3/library/os.html#os.listdir)</kbd> |
| <kbd>listdir_attr()</kbd><br /><kbd>la()</kbd> | 罗列目录，获取文件属性 <kbd>dict</kbd> 列表 | |
| <kbd>listdir_path()</kbd><br /><kbd>ll()</kbd> | 罗列目录，获取 <kbd>dupan.DuPanPath</kbd> 对象列表 | |
| <kbd>makedirs()</kbd> | 创建多级的空目录 | <kbd>[os.makedirs](https://docs.python.org/3/library/os.html#os.makedirs)</kbd> |
| <kbd>mkdir()</kbd> | 创建空目录 | <kbd>[os.mkdir](https://docs.python.org/3/library/os.html#os.mkdir)</kbd> |
| <kbd>move()</kbd><br /><kbd>mv()</kbd> | 对文件或目录进行改名或移动，如果目标路径存在且是目录，则把文件移动到其中（但是目录中有同名的文件或目录，还是会报错） | <kbd>[shutil.move](https://docs.python.org/3/library/shutil.html#shutil.move)</kbd> |
| <kbd>open()</kbd> | 打开文件（只支持读，如果要写，请用 <kbd>write_bytes</kbd> 或 <kbd>upload</kbd> 替代） | <kbd>[open](https://docs.python.org/3/library/functions.html#open)</kbd><br /><kbd>[io.open](https://docs.python.org/3/library/io.html#io.open)</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_bytes()</kbd> | 读取文件为二进制 | <kbd>[pathlib.Path.read_bytes](https://docs.python.org/3/library/pathlib.html#pathlib.Path.read_bytes)</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_bytes_range()</kbd> | 读取文件为二进制 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_block()</kbd> | 读取文件为二进制 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_text()</kbd> | 读取文件为文本 | <kbd>[pathlib.Path.read_text](https://docs.python.org/3/library/pathlib.html#pathlib.Path.read_text)</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>remove()</kbd><br /><kbd>rm()</kbd> | 删除文件 | <kbd>[os.remove](https://docs.python.org/3/library/os.html#os.remove)</kbd> |
| <kbd>removedirs()</kbd> | （自底向上地）删除多级的空目录 | <kbd>[os.removedirs](https://docs.python.org/3/library/os.html#os.removedirs)</kbd> |
| <kbd>rename()</kbd> | 对文件或目录进行改名或移动 | <kbd>[os.rename](https://docs.python.org/3/library/os.html#os.rename)</kbd> |
| <kbd>renames()</kbd> | 对文件或目录进行改名或移动，然后对原来所在目录执行 <kbd>removedirs</kbd>  | <kbd>[os.renames](https://docs.python.org/3/library/os.html#os.renames)</kbd> |
| <kbd>replace()</kbd> | 对文件或目录进行改名或移动，并且如果原来路径上是文件，目标路径上也存在同名文件，则会先把后者删除 | <kbd>[os.replace](https://docs.python.org/3/library/os.html#os.replace)</kbd> |
| <kbd>rglob()</kbd> |遍历目录并用通配符模式筛选 | <kbd>[pathlib.Path.rglob](https://docs.python.org/3/library/pathlib.html#pathlib.Path.rglob)</kbd> |
| <kbd>rmdir()</kbd> | 删除空目录 | <kbd>[os.rmdir](https://docs.python.org/3/library/os.html#os.rmdir)</kbd> |
| <kbd>rmtree()</kbd> | 删除文件或目录 | <kbd>[shutil.rmtree](https://docs.python.org/3/library/shutil.html#shutil.rmtree)</kbd> |
| <kbd>scandir()</kbd> | 迭代目录，获取 <kbd>dupan.DuPanPath</kbd> 对象的迭代器 | <kbd>[os.scandir](https://docs.python.org/3/library/os.html#os.scandir)</kbd> |
| <kbd>stat()</kbd> | 获取文件状态 <kbd>[os.stat_result](https://docs.python.org/3/library/os.html#os.stat_result)</kbd> 信息  | <kbd>[os.stat](https://docs.python.org/3/library/os.html#os.stat)</kbd> |
| <kbd>touch()</kbd> | 访问路径，如果不存在则新建空文件 | <kbd>[pathlib.Path.touch](https://docs.python.org/3/library/pathlib.html#pathlib.Path.touch)</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>upload()</kbd> | 上传文件 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>upload_tree()</kbd> | 上传目录 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>unlink()</kbd> | 删除文件 | <kbd>[os.unlink](https://docs.python.org/3/library/os.html#os.unlink)</kbd> |
| <kbd>walk()</kbd> | 遍历目录，获取文件名列表 | <kbd>[os.walk](https://docs.python.org/3/library/os.html#os.walk)</kbd> |
| <kbd>walk_attr()</kbd> | 遍历目录，获取文件属性 <kbd>dict</kbd> 列表 | |
| <kbd>walk_path()</kbd> | 遍历目录，获取 <kbd>dupan.DuPanPath</kbd> 对象列表 | |
| <kbd>write_bytes()</kbd> | 向文件写入二进制 | <kbd>[pathlib.Path.write_bytes](https://docs.python.org/3/library/pathlib.html#pathlib.Path.write_bytes)</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>write_text()</kbd> | 向文件写入文本 | <kbd>[pathlib.Path.write_text](https://docs.python.org/3/library/pathlib.html#pathlib.Path.write_text)</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |

<kbd>dupan.DuPanPath</kbd> 实现了二次封装，从路径的角度来进行操作。

### 3. 遍历文件系统和查找文件

#### 1. 获取当前目录下所有 .mkv 文件的 url

**第 1 种方法，使用** <kbd>iter</kbd>，返回 <kbd>dupan.DuPanPath</kbd> 对象的迭代器

```python
for path in fs.iter(max_depth=-1):
    if path.name.endswith(".mkv"):
        print(path.url)
```

**第 2 种方法，使用** <kbd>glob</kbd>，参考 <kbd>pathlib.Path.glob</kbd> 和 <kbd>glob.iglob</kbd>，使用通配符查找

```python
for path in fs.glob("**/*.mkv"):
    print(path.url)
```

**第 3 种方法，使用** <kbd>rglob</kbd>，参考 <kbd>pathlib.Path.rglob</kbd>

```python
for path in fs.rglob("*.mkv"):
    print(path.url)
```

## 文档

> 正在编写中
