# Alist web API 的 Python 封装

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/python-alist)
![PyPI - Version](https://img.shields.io/pypi/v/python-alist)
![PyPI - Downloads](https://img.shields.io/pypi/dm/python-alist)
![PyPI - Format](https://img.shields.io/pypi/format/python-alist)
![PyPI - Status](https://img.shields.io/pypi/status/python-alist)

- [AList web API 官方文档](https://alist.nn.ci/guide/api/)
- [AList web API 在线工具](https://alist-v3.apifox.cn)

## 安装

通过 [pypi](https://pypi.org/project/python-alist/)

```console
pip install -U python-alist
```

## 入门介绍

### 1. 导入模块和创建实例

**导入模块**

```python
from alist import AlistClient, AlistFileSystem
```

**创建客户端对象，登录 <kbd>AList</kbd>：此处，后台服务地址: `"http://localhost:5244"`，用户名: `"admin"`，密码: `"123456"`**

> 请确保 <kbd>AList</kbd> 已经启动，并且可通过 <kbd>http://localhost:5244</kbd> 访问

```python
client = AlistClient("http://localhost:5244", "admin", "123456")
```

绝大部分 <kbd>AlistClient</kbd> 的方法带有 `async_` 参数，意味着它支持异步 IO。

```python
>>> import asyncio
>>> loop = asyncio.get_event_loop()

>>> from alist import AlistClient, AlistFileSystem
>>> client = AlistClient("http://localhost:5244", "admin", "123456")

>>> client.fs_get(dict(path="/"))
{'code': 200,
 'message': 'success',
 'data': {'name': '115',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-26T12:23:59.259218+08:00',
  'created': '2023-12-26T12:23:59.259218+08:00',
  'sign': '',
  'thumb': '',
  'type': 0,
  'hashinfo': 'null',
  'hash_info': None,
  'raw_url': '',
  'readme': '',
  'header': '',
  'provider': '115 Cloud',
  'related': None}}

>>> client.fs_get(dict(path="/"), async_=True)
<coroutine object AlistClient._async_request.<locals>.request at 0x1055f0d60>
>>> loop.run_until_complete(client.fs_get(dict(path="/"), async_=True))
{'code': 200,
 'message': 'success',
 'data': {'name': 'root',
  'size': 0,
  'is_dir': True,
  'modified': '0001-01-01T00:00:00Z',
  'created': '0001-01-01T00:00:00Z',
  'sign': '',
  'thumb': '',
  'type': 0,
  'hashinfo': 'null',
  'hash_info': None,
  'raw_url': '',
  'readme': '',
  'header': '',
  'provider': 'unknown',
  'related': None}}
```

**创建文件系统对象**

```python
fs = AlistFileSystem(client)
```

或者直接在 <kbd>client</kbd> 上就可获取文件系统对象

```python
fs = client.fs
```

或者直接用 <kbd>AlistFileSystem</kbd> 登录

```python
fs = AlistFileSystem.login("http://localhost:5244", "admin", "123456")
```

### 2. 操作网盘使用 Python 式的文件系统方法

文件系统对象的方法，设计和行为参考了 <kbd>[os](https://docs.python.org/3/library/os.html)</kbd>、<kbd>[posixpath](https://docs.python.org/3/library/os.path.html)</kbd>、<kbd>[pathlib.Path](https://docs.python.org/3/library/pathlib.html)</kbd> 和 <kbd>[shutil](https://docs.python.org/3/library/shutil.html)</kbd> 等模块。

<kbd>alist.AlistFileSystem</kbd> 实现了读写的文件系统方法。

<kbd>alist.AlistPath</kbd> 实现了二次封装，从路径的角度来进行操作。

**使用** <kbd>getcwd</kbd> **方法，获取当前工作目录的路径，参考** <kbd>os.getcwd</kbd>

```python
>>> fs.getcwd()
'/'
```

**使用** <kbd>listdir</kbd> **方法，罗列当前目录的文件名，参考** <kbd>os.listdir</kbd>

```python
>>> fs.listdir()
['115', '阿里云盘']
```

**使用** <kbd>chdir</kbd> **方法，切换当前工作目录，参考** <kbd>os.chdir</kbd>

```python
>>> fs.chdir("/115")
```

**使用** <kbd>listdir_attr</kbd> **方法，罗列当前目录时，还可以获取属性**

```python
>>> fs.listdir_attr()
[{'name': '云下载',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-16T21:58:22+08:00',
  'created': '2023-03-18T18:52:54+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/云下载',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': '000阅读·乱七八糟',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-14T14:54:20+08:00',
  'created': '2023-03-18T14:45:45+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/000阅读·乱七八糟',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': '电视剧',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-23T22:26:17+08:00',
  'created': '2023-04-16T18:30:33+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/电视剧',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': '电影',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-14T14:54:20+08:00',
  'created': '2023-03-01T12:46:07+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/电影',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': '纪录片',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-18T18:49:29+08:00',
  'created': '2023-02-24T11:40:45+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/纪录片',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': 'libgen',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-14T14:54:20+08:00',
  'created': '2023-05-28T22:05:06+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/libgen',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': '👾0号：重要资源',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-14T14:54:20+08:00',
  'created': '2023-02-28T21:40:32+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/👾0号：重要资源',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': '📚1号：书籍大礼包',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-14T14:54:20+08:00',
  'created': '2023-03-01T01:29:12+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/📚1号：书籍大礼包',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)},
 {'name': '📼资料备份',
  'size': 0,
  'is_dir': True,
  'modified': '2023-12-14T14:54:20+08:00',
  'created': '2023-07-07T15:13:12+08:00',
  'sign': '',
  'thumb': '',
  'type': 1,
  'hashinfo': '{"sha1":""}',
  'hash_info': {'sha1': ''},
  'path': '/115/📼资料备份',
  'lastest_update': datetime.datetime(2023, 12, 29, 15, 50, 50, 828853)}]
```

**使用** <kbd>listdir_path</kbd> **方法，罗列当前目录时，还可以获取** <kbd>alist.AlistPath</kbd> **对象**

```python
>>> fs.listdir_path()
[<alist.AlistPath(name='云下载', size=0, is_dir=True, modified='2023-12-16T21:58:22+08:00', created='2023-03-18T18:52:54+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/云下载', password='')>,
 <alist.AlistPath(name='000阅读·乱七八糟', size=0, is_dir=True, modified='2023-12-14T14:54:20+08:00', created='2023-03-18T14:45:45+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/000阅读·乱七八糟', password='')>,
 <alist.AlistPath(name='电视剧', size=0, is_dir=True, modified='2023-12-23T22:26:17+08:00', created='2023-04-16T18:30:33+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/电视剧', password='')>,
 <alist.AlistPath(name='电影', size=0, is_dir=True, modified='2023-12-14T14:54:20+08:00', created='2023-03-01T12:46:07+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/电影', password='')>,
 <alist.AlistPath(name='纪录片', size=0, is_dir=True, modified='2023-12-18T18:49:29+08:00', created='2023-02-24T11:40:45+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/纪录片', password='')>,
 <alist.AlistPath(name='libgen', size=0, is_dir=True, modified='2023-12-14T14:54:20+08:00', created='2023-05-28T22:05:06+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/libgen', password='')>,
 <alist.AlistPath(name='👾0号：重要资源', size=0, is_dir=True, modified='2023-12-14T14:54:20+08:00', created='2023-02-28T21:40:32+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/👾0号：重要资源', password='')>,
 <alist.AlistPath(name='📚1号：书籍大礼包', size=0, is_dir=True, modified='2023-12-14T14:54:20+08:00', created='2023-03-01T01:29:12+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/📚1号：书籍大礼包', password='')>,
 <alist.AlistPath(name='📼资料备份', size=0, is_dir=True, modified='2023-12-14T14:54:20+08:00', created='2023-07-07T15:13:12+08:00', sign='', thumb='', type=1, hashinfo='{"sha1":""}', hash_info={'sha1': ''}, lastest_update=datetime.datetime(2023, 12, 29, 15, 51, 11, 817697), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115', refresh=False, request_kwargs={}), path='/115/📼资料备份', password='')>]
```

**再次使用** <kbd>chdir</kbd> **，进入一些目录**

```python
>>> fs.chdir("电视剧/欧美剧/A")
>>> fs.getcwd()
'/115/电视剧/欧美剧/A'
>>> fs.listdir()
['A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]']
>>> fs.chdir("A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）")
>>> fs.listdir()
['Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass', 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv']
```

**使用** <kbd>attr</kbd> **方法，获取文件或文件夹的属性** 

```python
>>> fs.attr("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv")
{'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'size': 924544482,
 'is_dir': False,
 'modified': '2023-02-24T11:42:00+08:00',
 'created': '2023-02-24T11:42:51+08:00',
 'sign': '',
 'thumb': '',
 'type': 2,
 'hashinfo': '{"sha1":"7F4121B68A4E467ABF30A84627E20A8978895A4E"}',
 'hash_info': {'sha1': '7F4121B68A4E467ABF30A84627E20A8978895A4E'},
 'raw_url': 'http://localhost:5244/p/115/%E7%94%B5%E8%A7%86%E5%89%A7/%E6%AC%A7%E7%BE%8E%E5%89%A7/A/A%E3%80%8A%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BA%E3%80%8B%28Love.Death.and.Robot%29%5Btt9561862%5D/%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BAS01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG%EF%BC%8818%E9%9B%86%EF%BC%89/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'readme': '',
 'header': '',
 'provider': '115 Cloud',
 'related': [{'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass',
   'size': 48910,
   'is_dir': False,
   'modified': '2023-03-23T22:09:00+08:00',
   'created': '2023-03-23T22:09:09+08:00',
   'sign': '',
   'thumb': '',
   'type': 4,
   'hashinfo': '{"sha1":"30AB3A1A376DE83049B35F135A774980F5C7C558"}',
   'hash_info': {'sha1': '30AB3A1A376DE83049B35F135A774980F5C7C558'}}],
 'path': '/115/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'lastest_update': datetime.datetime(2023, 12, 29, 15, 51, 47, 591418)}
```

**使用** <kbd>stat</kbd> **方法，获取文件或文件夹的部分，参考** <kbd>os.stat</kbd>

```python
>>> fs.stat("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv")
os.stat_result(st_mode=33279, st_ino=0, st_dev=0, st_nlink=1, st_uid=0, st_gid=0, st_size=924544482, st_atime=1703836333.124217, st_mtime=1677210120.0, st_ctime=1677210171.0)
```

**使用** <kbd>open</kbd> **方法，打开一个文件（目前只支持读取，不支持写入），参考** <kbd>open</kbd>

```python
>>> f = fs.open("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass", encoding="UTF-16")
>>> f
<_io.TextIOWrapper name='Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass' encoding='UTF-16'>
```

读取此文件的前 100 个字符

```python
>>> f.read(100)
'[Script Info]\n;SrtEdit 6.3.2012.1001\n;Copyright(C) 2005-2012 Yuan Weiguo\n\nTitle: YYeTs\nOriginal Scri'
```

用完后请及时关闭文件（其实不主动关闭也可以，只要文件不被引用，就会自动关闭）

```python
>>> f.close()
```

**以二进制模式打开一个文件，此时** `mode="rb"`

```python
>>> f = fs.open("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv", "rb")
>>> f
alist.util.file.HTTPFileReader('http://localhost:5244/d/115/%E7%94%B5%E8%A7%86%E5%89%A7/%E6%AC%A7%E7%BE%8E%E5%89%A7/A/A%E3%80%8A%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BA%E3%80%8B%28Love.Death.and.Robot%29%5Btt9561862%5D/%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BAS01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG%EF%BC%8818%E9%9B%86%EF%BC%89/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', urlopen=<function urlopen at 0x105ffb560>, headers=mappingproxy({'Accept-Encoding': 'identity'}))
```

读取前 10 个字节

```python
>>> f.read(10)
b'\x1aE\xdf\xa3\xa3B\x86\x81\x01B'
```

再读取 10 个字节

```python
>>> f.read(10)
b'\xf7\x81\x01B\xf2\x81\x04B\xf3\x81'
```

当前文件偏移位置（从 0 开始计算）

```python
>>> f.tell()
20
```

把读取位置重新变为文件开头

```python
>>> f.seek(0)
0
>>> f.tell()
0
```

再次读取 20 字节，应该等于上面两次结果的拼接

```python
>>> f.read(20)
b'\x1aE\xdf\xa3\xa3B\x86\x81\x01B\xf7\x81\x01B\xf2\x81\x04B\xf3\x81'
>>> f.tell()
20
```

**回到根目录，我们继续其它试验**

```python
>>> fs.chdir("/")
```

**使用** <kbd>walk</kbd> **方法，可以遍历一个目录，参考** <kbd>os.walk</kbd>

```python
>>> next(fs.walk())
('/', ['115', '阿里云盘'], [])
```

**使用** <kbd>walk_path</kbd> **方法，可以遍历一个目录时，获取** <kbd>alist.AlistPath</kbd> 对象

```python
>>> next(fs.walk_path())
('/',
 [<alist.AlistPath(name='115', size=0, is_dir=True, modified='2023-12-26T12:23:59.259218+08:00', created='2023-12-26T12:23:59.259218+08:00', sign='', thumb='', type=1, hashinfo='null', hash_info=None, lastest_update=datetime.datetime(2023, 12, 29, 15, 53, 33, 430767), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/', refresh=False, request_kwargs={}), path='/115', password='')>,
  <alist.AlistPath(name='阿里云盘', size=0, is_dir=True, modified='2023-10-01T16:26:52.862197+08:00', created='2023-10-01T16:26:52.862197+08:00', sign='', thumb='', type=1, hashinfo='null', hash_info=None, lastest_update=datetime.datetime(2023, 12, 29, 15, 53, 33, 430767), fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/', refresh=False, request_kwargs={}), path='/阿里云盘', password='')>],
 [])
```

**必需在挂载的 `storage` 下才能创建文件，因此进入 `/115` 下，继续做实验**

```python
>>> fs.chdir("/115")
```

**使用** <kbd>mkdir</kbd> **方法，可以创建空文件夹，参考** <kbd>os.mkdir</kbd>

```python
>>> fs.mkdir("test")
'/115/test'
```

**使用** <kbd>rmdir</kbd> **方法，可以删除空文件夹，参考** <kbd>os.rmdir</kbd>

```python
>>> fs.rmdir('test')
>>> fs.listdir()
['云下载',
 '000阅读·乱七八糟',
 '电视剧',
 '电影',
 '纪录片',
 'libgen',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>makedirs</kbd> **方法，可以创建多级的空目录，参考** <kbd>os.makedirs</kbd>

```python
>>> fs.makedirs("a/b/c/d", exist_ok=True)
'/115/a/b/c/d'
>>> fs.listdir()
['云下载',
 '000阅读·乱七八糟',
 'a',
 '电视剧',
 '电影',
 '纪录片',
 'libgen',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>removedirs</kbd> **方法，可以（自底向上地）删除多级的空目录，参考** <kbd>os.removedirs</kbd>

```python
>>> fs.removedirs("a/b/c/d")
>>> fs.listdir()
['云下载',
 '000阅读·乱七八糟',
 '电视剧',
 '电影',
 '纪录片',
 'libgen',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>upload</kbd> **方法上传文件（提示：如果 `as_task=True`（默认为 `False`），则文件只是上传到 <kbd>AList</kbd> 服务器上，至于 <kbd>AList</kbd> 什么时候上传完成，得等待）**

**说明** 暂时，<kbd>AList</kbd> 新增文件后，并不更新缓存（但删除和改名会更新），需要强制刷新一下。

```python
>>> from io import BytesIO
>>> fs.upload(BytesIO(b"123"), "test.txt")
'/115/test.txt'
>>> _ = fs.listdir(refresh=True)
>>> fs.read_text("test.txt")
'123'
>>> fs.upload("file.py")
'/115/file.py'
>>> fs.listdir(refresh=True)
['云下载',
 '000阅读·乱七八糟',
 '电视剧',
 '电影',
 '纪录片',
 'libgen',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份',
 'file.py',
 'test.txt']
```

**使用** <kbd>remove</kbd> **方法可以删除文件，参考** <kbd>os.remove</kbd>

```python
>>> fs.remove("test.txt")
>>> fs.remove("file.py")
>>> fs.listdir()
['云下载',
 '000阅读·乱七八糟',
 '电视剧',
 '电影',
 '纪录片',
 'libgen',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>rmtree</kbd> **方法可以删除文件或文件夹，并且在删除文件夹时，也删除其中的文件和文件夹，参考** <kbd>shutil.rmtree</kbd>

```python
>>> fs.makedirs("a/b/c/d")
'/115/a/b/c/d'
>>> fs.removedirs("a")
Traceback (most recent call last):
    ...
OSError: [Errno 66] directory not empty: '/115/a'
>>> fs.rmtree("a")
```

**使用** <kbd>rename</kbd> **方法可以对文件或文件夹进行改名或移动，参考** <kbd>os.rename</kbd>

```python
>>> fs.touch("a")
'/115/a'
>>> _ = fs.listdir(refresh=True)
>>> fs.attr("a")
{'name': 'a',
 'size': 0,
 'is_dir': False,
 'modified': '2023-12-29T16:02:00+08:00',
 'created': '2023-12-29T16:02:41+08:00',
 'sign': '',
 'thumb': '',
 'type': 0,
 'hashinfo': '{"sha1":"DA39A3EE5E6B4B0D3255BFEF95601890AFD80709"}',
 'hash_info': {'sha1': 'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709'},
 'raw_url': 'http://localhost:5244/p/115/a',
 'readme': '',
 'header': '',
 'provider': '115 Cloud',
 'related': None,
 'path': '/115/a',
 'lastest_update': datetime.datetime(2023, 12, 29, 16, 3, 31, 166894)}
>>> fs.rename('a', 'b')
'/115/b'
>>> fs.attr("b")
{'name': 'b',
 'size': 0,
 'is_dir': False,
 'modified': '2023-12-29T16:03:00+08:00',
 'created': '2023-12-29T16:02:41+08:00',
 'sign': '',
 'thumb': '',
 'type': 0,
 'hashinfo': '{"sha1":"DA39A3EE5E6B4B0D3255BFEF95601890AFD80709"}',
 'hash_info': {'sha1': 'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709'},
 'raw_url': 'http://localhost:5244/p/115/b',
 'readme': '',
 'header': '',
 'provider': '115 Cloud',
 'related': None,
 'path': '/115/b',
 'lastest_update': datetime.datetime(2023, 12, 29, 16, 3, 47, 200980)}
```

**使用** <kbd>renames</kbd> **方法可以对文件或文件夹进行改名或移动，并且在移动后如果原来所在目录为空，则会删除那个目录，参考** <kbd>os.renames</kbd>

**使用** <kbd>replace</kbd> **方法可以对文件或文件夹进行改名或移动，并且如果原始路径上是文件，目标路径上也存在一个文件，则会先把目标路径上的文件删除，参考** <kbd>os.replace</kbd>

**使用** <kbd>move</kbd> **方法可以对文件或文件夹进行改名或移动，目标路径存在且是一个目录，则把文件移动到其中（但是目录中有同名的文件或文件夹，还是会报错），参考** <kbd>shutil.move</kbd>

### 3. 遍历文件系统和查找文件

#### 1. 获取当前目录下所有 .mkv 文件的 url

**第 1 种方法，使用** <kbd>iter</kbd>，返回 <kbd>alist.AlistPath</kbd> 对象的迭代器

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

### 4. 任务列表

<kbd>AList</kbd> 目前支持 `4` 种类型的任务，我分别进行了封装，大部分方法都支持异步调用 (`async_=True`)

- <kbd>alist.AlistCopyTaskList</kbd> 封装了 `复制` 的任务列表。
- <kbd>alist.AlistOfflineDownloadTaskList</kbd> 封装了 `离线下载（到本地）` 的任务列表。
- <kbd>alist.AlistOfflineDownloadTransferTaskList</kbd> 封装了 `离线下载（到存储）` 的任务列表。
- <kbd>alist.AlistUploadTaskList</kbd> 封装了 `上传` 的任务列表。
- <kbd>alist.AlistAria2DownTaskList</kbd> 封装了 `aria2下载` 的任务列表。
- <kbd>alist.AlistAria2TransferTaskList</kbd> 封装了 `aria2转存` 的任务列表。
- <kbd>alist.AlistQbitDownTaskList</kbd> 封装了 `qbit下载` 的任务列表。
- <kbd>alist.AlistQbitTransferTaskList</kbd> 封装了 `qbit转存` 的任务列表。

```python
from alist import AlistClient

client = AlistClient("http://localhost:5244", "admin", "123456")

# 获取各种任务列表
copy_tasklist = client.copy_tasklist
offline_download_tasklist = client.offline_download_tasklist
offline_download_transfer_tasklist = client.offline_download_transfer_tasklist
upload_tasklist = client.upload_tasklist
aria2_down_tasklist = client.aria2_down_tasklist
aria2_transfer_tasklist = client.aria2_transfer_tasklist
qbit_down_tasklist = client.qbit_down_tasklist
qbit_transfer_tasklist = client.qbit_transfer_tasklist

# 或者自己创建实例

# 创建 复制 任务列表实例
from alist import AlistCopyTaskList
copy_tasklist = AlistCopyTaskList(client)

# 创建 离线下载（到本地） 任务列表实例
from alist import AlistOfflineDownloadTaskList
offline_download_tasklist = AlistOfflineDownloadTaskList(client)

# 创建 离线下载（到存储） 任务列表实例
from alist import AlistOfflineDownloadTransferTaskList
offline_download_transfer_tasklist = AlistOfflineDownloadTransferTaskList(client)

# 创建 上传 任务列表实例
from alist import AlistUploadTaskList
upload_tasklist = AlistUploadTaskList(client)

# 创建 上传 任务列表实例
from alist import AlistAria2DownTaskList
aria2_down_tasklist = AlistAria2DownTaskList(client)

# 创建 上传 任务列表实例
from alist import AlistAria2TransferTaskList
aria2_transfer_tasklist = AlistAria2TransferTaskList(client)

# 创建 上传 任务列表实例
from alist import AlistQbitDownTaskList
qbit_down_tasklist = AlistQbitDownTaskList(client)

# 创建 上传 任务列表实例
from alist import AlistQbitTransferTaskList
qbit_transfer_tasklist = AlistQbitTransferTaskList(client)
```

## 文档

> 正在编写中
