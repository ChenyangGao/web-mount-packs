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

<kbd>dupan.DuPanPath</kbd> 实现了二次封装，从路径的角度来进行操作。

| 方法 | 说明 | 参考|
| --- | --- | --- |
| <kbd>abspath</kbd> | 获取绝对路径 | <kbd>posixpath.abspath</kbd> |
| <kbd>as_path</kbd> | 获取路径对应的  <kbd>dupan.DuPanPath</kbd> 对象 | |
| <kbd>attr</kbd> | 获取文件或文件夹的属性 | |
| <kbd>chdir</kbd> | 切换当前工作目录 | <kbd>os.chdir</kbd> |
| <kbd>copy</kbd> | 复制文件 | <kbd>shutil.copy</kbd> |
| <kbd>copytree</kbd> | 复制目录 | <kbd>shutil.copytree</kbd> |
| <kbd>download</kbd> | 下载文件 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>download_tree</kbd> | 下载目录 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>exists</kbd> | 判断文件或目录是否存在 | <kbd>posixpath.exists</kbd> |
| <kbd>getcwd</kbd> | 获取当前工作目录的路径 | <kbd>os.getcwd</kbd> |
| <kbd>get_url</kbd> | 获取文件的下载链接 | <kbd>os.getcwd</kbd> |
| <kbd>glob</kbd> | 用遍历一个目录并用通配符模式筛选 | <kbd>pathlib.Path.glob</kbd> |
| <kbd>isdir</kbd> | 判断是否目录 | <kbd>posixpath.isdir</kbd> |
| <kbd>isfile</kbd> | 判断是否文件 | <kbd>posixpath.isfile</kbd> |
| <kbd>is_empty</kbd> | 判断是否不存在、空文件或空文件夹 | <kbd>posixpath.isfile</kbd> |
| <kbd>iter</kbd> | 遍历一个目录 | |
| <kbd>iterdir</kbd> | 迭代一个目录 | <kbd>pathlib.Path.iterdir</kbd> |
| <kbd>listdir</kbd> | 罗列当前目录的文件名 | <kbd>os.listdir</kbd> |
| <kbd>listdir_attr</kbd> | 罗列当前目录时，还可以获取属性 | |
| <kbd>listdir_path</kbd> | 罗列当前目录时，还可以获取 <kbd>dupan.DuPanPath</kbd> 对象 | |
| <kbd>makedirs</kbd> | 创建多级的空目录 | <kbd>os.makedirs</kbd> |
| <kbd>mkdir</kbd> | 创建空文件夹 | <kbd>os.mkdir</kbd> |
| <kbd>move</kbd> | 对文件或文件夹进行改名或移动，目标路径存在且是一个目录，则把文件移动到其中（但是目录中有同名的文件或文件夹，还是会报错） | <kbd>shutil.move</kbd> |
| <kbd>open</kbd> | 打开文件（只支持读，不支持写） | <kbd>open</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_bytes</kbd> | 读取文件为二进制 | <kbd>pathlib.Path.read_bytes</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_bytes_range</kbd> | 读取文件为二进制 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_block</kbd> | 读取文件为二进制 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>read_text</kbd> | 读取文件为文本 | <kbd>pathlib.Path.read_text</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>remove</kbd> | 删除一个文件 | <kbd>os.remove</kbd> |
| <kbd>removedirs</kbd> | （自底向上地）删除多级的空目录 | <kbd>os.removedirs</kbd> |
| <kbd>rename</kbd> | 对文件或文件夹进行改名或移动 | <kbd>os.rename</kbd> |
| <kbd>renames</kbd> | 对文件或文件夹进行改名或移动，并且在移动后如果原来所在目录为空，则会删除那个目录 | <kbd>os.renames</kbd> |
| <kbd>replace</kbd> | 对文件或文件夹进行改名或移动，并且如果原始路径上是文件，目标路径上也存在一个文件，则会先把目标路径上的文件删除 | <kbd>os.replace</kbd> |
| <kbd>rglob</kbd> |用遍历一个目录并用通配符模式筛选 | <kbd>pathlib.Path.rglob</kbd> |
| <kbd>rmdir</kbd> | 删除空文件夹 | <kbd>os.rmdir</kbd> |
| <kbd>rmtree</kbd> | 删除文件或文件夹，并且在删除文件夹时，也删除其中的文件和文件夹 | <kbd>shutil.rmtree</kbd> |
| <kbd>scandir</kbd> | 迭代一个目录 | <kbd>os.scandir</kbd> |
| <kbd>stat</kbd> | 获取文件或文件夹的部分 | <kbd>os.stat</kbd> |
| <kbd>touch</kbd> | 获取文件或文件夹的部分 | <kbd>pathlib.Path.touch</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>upload</kbd> | 上传一个文件 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>upload_tree</kbd> | 上传一个目录 | <kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>ulink</kbd> | 删除一个文件 | <kbd>os.ulink</kbd> |
| <kbd>walk</kbd> | 遍历一个目录，获取文件名 | <kbd>os.walk</kbd> |
| <kbd>walk_attr</kbd> | 遍历一个目录时，获取属性字典 <kbd>dict</kbd> | |
| <kbd>walk_path</kbd> | 遍历一个目录时，获取 <kbd>dupan.DuPanPath</kbd> 对象 | |
| <kbd>write_bytes</kbd> | 向文件写入二进制 | <kbd>pathlib.Path.write_bytes</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |
| <kbd>write_text</kbd> | 向文件写入文本 | <kbd>pathlib.Path.write_text</kbd><br /><kbd style="background-color: red; color: white">暂不可用</kbd> |

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
