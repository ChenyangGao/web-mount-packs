# 115 网盘 Web API 的 Python 封装

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/python-115)
![PyPI - Version](https://img.shields.io/pypi/v/python-115)
![PyPI - Downloads](https://img.shields.io/pypi/dm/python-115)
![PyPI - Format](https://img.shields.io/pypi/format/python-115)
![PyPI - Status](https://img.shields.io/pypi/status/python-115)

## 安装

通过 [pypi](https://pypi.org/project/python-115/)

```console
pip install -U python-115
```

## 入门介绍

### 1. 导入模块和创建实例

**导入模块**

```python
from p115 import P115Client, P115FileSystem
```

**创建客户端对象，需要传入 <kbd>cookie</kbd>，如果不传或者 <kbd>cookie</kbd> 失效，则需要扫码登录**

```python
cookie = "UID=...;CID=...;SEID=..."
client = P115Client(cookie)
```

**创建文件系统对象**

```python
fs = P115FileSystem(client)
```

或者直接在 <kbd>client</kbd> 上就可获取文件系统对象

```python
fs = client.fs
```

### 2. 操作网盘使用 Python 式的文件系统方法

文件系统对象的方法，设计和行为参考了 <kbd>[os](https://docs.python.org/3/library/os.html)</kbd>、<kbd>[posixpath](https://docs.python.org/3/library/os.path.html)</kbd>、<kbd>[pathlib.Path](https://docs.python.org/3/library/pathlib.html)</kbd> 和 <kbd>[shutil](https://docs.python.org/3/library/shutil.html)</kbd> 等模块。

<kbd>p115.P115FileSystem</kbd> 实现了在自己的网盘上，读写的文件系统方法

<kbd>p115.P115Path</kbd> 实现了二次封装，从路径的角度来进行操作。

**使用** <kbd>getcwd</kbd> **方法，获取当前工作目录的路径，参考** <kbd>os.getcwd</kbd>

```python
>>> fs.getcwd()
'/'
```

**使用** <kbd>getcid</kbd> **方法，获取当前工作目录的 id**

```python
>>> fs.getcid()
0
```

**使用** <kbd>listdir</kbd> **方法，罗列当前目录的文件名，参考** <kbd>os.listdir</kbd>

```python
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

**使用** <kbd>listdir_attr</kbd> **方法，罗列当前目录时，还可以获取属性**

```python
>>> fs.listdir_attr()
[{'name': '云下载',
  'is_directory': True,
  'size': None,
  'id': 2593093001609739968,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 16, 21, 58, 22),
  'utime': datetime.datetime(2023, 12, 19, 11, 29, 29),
  'ptime': datetime.datetime(2023, 3, 18, 18, 52, 54),
  'open_time': datetime.datetime(2023, 12, 19, 11, 29, 29),
  'time': datetime.datetime(2023, 12, 16, 21, 58, 22),
  'pick_code': 'fe1kl2mz1if2fl3wmx',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/云下载'},
 {'name': '000阅读·乱七八糟',
  'is_directory': True,
  'size': None,
  'id': 2592968610464922758,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'utime': datetime.datetime(2023, 12, 14, 15, 38, 18),
  'ptime': datetime.datetime(2023, 3, 18, 14, 45, 45),
  'open_time': datetime.datetime(2023, 12, 14, 13, 17, 9),
  'time': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'pick_code': 'fccgz8vtu9xt08rmt6',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/000阅读·乱七八糟'},
 {'name': '电视剧',
  'is_directory': True,
  'size': None,
  'id': 2614100250469596984,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'utime': datetime.datetime(2023, 12, 15, 0, 48, 36),
  'ptime': datetime.datetime(2023, 4, 16, 18, 30, 33),
  'open_time': datetime.datetime(2023, 12, 15, 0, 48, 36),
  'time': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'pick_code': 'fdjemtliv9d5b55y6u',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/电视剧'},
 {'name': '电影',
  'is_directory': True,
  'size': None,
  'id': 2580587204111760961,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'utime': datetime.datetime(2023, 12, 14, 15, 0, 45),
  'ptime': datetime.datetime(2023, 3, 1, 12, 46, 7),
  'open_time': datetime.datetime(2023, 12, 12, 21, 56, 25),
  'time': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'pick_code': 'fdj4gtgvtd5p8q5y6u',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/电影'},
 {'name': '纪录片',
  'is_directory': True,
  'size': None,
  'id': 2576930424647319247,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 18, 18, 49, 29),
  'utime': datetime.datetime(2023, 12, 18, 18, 49, 29),
  'ptime': datetime.datetime(2023, 2, 24, 11, 40, 45),
  'open_time': datetime.datetime(2023, 12, 13, 15, 45, 53),
  'time': datetime.datetime(2023, 12, 18, 18, 49, 29),
  'pick_code': 'fdjagt4u21x1k35y6u',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/纪录片'},
 {'name': 'libgen',
  'is_directory': True,
  'size': None,
  'id': 2644648816430546428,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'utime': datetime.datetime(2023, 12, 15, 18, 24, 57),
  'ptime': datetime.datetime(2023, 5, 28, 22, 5, 6),
  'open_time': datetime.datetime(2023, 12, 15, 18, 24, 57),
  'time': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'pick_code': 'fcid29t51koofbrmt6',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/libgen'},
 {'name': '👾0号：重要资源',
  'is_directory': True,
  'size': None,
  'id': 2580131407544188592,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'utime': datetime.datetime(2023, 12, 19, 11, 29, 45),
  'ptime': datetime.datetime(2023, 2, 28, 21, 40, 32),
  'open_time': datetime.datetime(2023, 12, 19, 11, 29, 45),
  'time': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'pick_code': 'fa8p74ih0nu1ax4fyr',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/👾0号：重要资源'},
 {'name': '📚1号：书籍大礼包',
  'is_directory': True,
  'size': None,
  'id': 2580246506904748007,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'utime': datetime.datetime(2023, 12, 19, 11, 29, 44),
  'ptime': datetime.datetime(2023, 3, 1, 1, 29, 12),
  'open_time': datetime.datetime(2023, 12, 19, 11, 29, 44),
  'time': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'pick_code': 'fccqsmu7225f2vrmt6',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/📚1号：书籍大礼包'},
 {'name': '📼资料备份',
  'is_directory': True,
  'size': None,
  'id': 2673432528538303699,
  'parent_id': 0,
  'sha1': None,
  'etime': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'utime': datetime.datetime(2023, 12, 15, 0, 12, 1),
  'ptime': datetime.datetime(2023, 7, 7, 15, 13, 12),
  'open_time': datetime.datetime(2023, 12, 15, 0, 12, 1),
  'time': datetime.datetime(2023, 12, 14, 14, 54, 20),
  'pick_code': 'fcilznsigu2hczrmt6',
  'star': False,
  'lastest_update': datetime.datetime(2023, 12, 19, 11, 30, 7, 517017),
  'path': '/📼资料备份'}]
```

**使用** <kbd>listdir_path</kbd> **方法，罗列当前目录时，还可以获取** <kbd>p115.P115Path</kbd> **对象**

```python
[<p115.P115Path(name='云下载', is_directory=True, size=None, id=2593093001609739968, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 16, 21, 58, 22), utime=datetime.datetime(2023, 12, 19, 11, 29, 29), ptime=datetime.datetime(2023, 3, 18, 18, 52, 54), open_time=datetime.datetime(2023, 12, 19, 11, 29, 29), time=datetime.datetime(2023, 12, 16, 21, 58, 22), pick_code='fe1kl2mz1if2fl3wmx', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/云下载')>,
 <p115.P115Path(name='000阅读·乱七八糟', is_directory=True, size=None, id=2592968610464922758, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 14, 15, 38, 18), ptime=datetime.datetime(2023, 3, 18, 14, 45, 45), open_time=datetime.datetime(2023, 12, 14, 13, 17, 9), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fccgz8vtu9xt08rmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/000阅读·乱七八糟')>,
 <p115.P115Path(name='电视剧', is_directory=True, size=None, id=2614100250469596984, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 15, 0, 48, 36), ptime=datetime.datetime(2023, 4, 16, 18, 30, 33), open_time=datetime.datetime(2023, 12, 15, 0, 48, 36), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fdjemtliv9d5b55y6u', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/电视剧')>,
 <p115.P115Path(name='电影', is_directory=True, size=None, id=2580587204111760961, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 14, 15, 0, 45), ptime=datetime.datetime(2023, 3, 1, 12, 46, 7), open_time=datetime.datetime(2023, 12, 12, 21, 56, 25), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fdj4gtgvtd5p8q5y6u', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/电影')>,
 <p115.P115Path(name='纪录片', is_directory=True, size=None, id=2576930424647319247, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 18, 18, 49, 29), utime=datetime.datetime(2023, 12, 18, 18, 49, 29), ptime=datetime.datetime(2023, 2, 24, 11, 40, 45), open_time=datetime.datetime(2023, 12, 13, 15, 45, 53), time=datetime.datetime(2023, 12, 18, 18, 49, 29), pick_code='fdjagt4u21x1k35y6u', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/纪录片')>,
 <p115.P115Path(name='libgen', is_directory=True, size=None, id=2644648816430546428, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 15, 18, 24, 57), ptime=datetime.datetime(2023, 5, 28, 22, 5, 6), open_time=datetime.datetime(2023, 12, 15, 18, 24, 57), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fcid29t51koofbrmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/libgen')>,
 <p115.P115Path(name='👾0号：重要资源', is_directory=True, size=None, id=2580131407544188592, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 19, 11, 29, 45), ptime=datetime.datetime(2023, 2, 28, 21, 40, 32), open_time=datetime.datetime(2023, 12, 19, 11, 29, 45), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fa8p74ih0nu1ax4fyr', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/👾0号：重要资源')>,
 <p115.P115Path(name='📚1号：书籍大礼包', is_directory=True, size=None, id=2580246506904748007, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 19, 11, 29, 44), ptime=datetime.datetime(2023, 3, 1, 1, 29, 12), open_time=datetime.datetime(2023, 12, 19, 11, 29, 44), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fccqsmu7225f2vrmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/📚1号：书籍大礼包')>,
 <p115.P115Path(name='📼资料备份', is_directory=True, size=None, id=2673432528538303699, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 15, 0, 12, 1), ptime=datetime.datetime(2023, 7, 7, 15, 13, 12), open_time=datetime.datetime(2023, 12, 15, 0, 12, 1), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fcilznsigu2hczrmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 11, 32, 18, 778700), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x106dcb190>, cid=0, path='/') at 0x108b21b90>, path='/📼资料备份')>]
```

**使用** <kbd>chdir</kbd> **方法，进入某个目录，就像** <kbd>os.chdir</kbd>

```python
>>> fs.chdir("电视剧/欧美剧/A")
2598195078816071040
>>> fs.getcwd()
'/电视剧/欧美剧/A'
>>> fs.getcid()
2598195078816071040
>>> fs.listdir()
['A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]']
>>> fs.chdir("A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）")
2576931481024724685
>>> fs.listdir()
['Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass', 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv']
```

**使用** <kbd>attr</kbd> **方法，获取文件或文件夹的属性** 

```python
>>> fs.attr("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv")
{'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'is_directory': False,
 'size': 924544482,
 'id': 2576931481393823441,
 'parent_id': 2576931481024724685,
 'sha1': '7F4121B68A4E467ABF30A84627E20A8978895A4E',
 'etime': datetime.datetime(2023, 2, 24, 11, 42, 51),
 'utime': datetime.datetime(2023, 12, 19, 0, 21, 42),
 'ptime': datetime.datetime(2023, 2, 24, 11, 42, 51),
 'open_time': datetime.datetime(2023, 7, 7, 0, 50, 30),
 'pick_code': 'djagtomczh64gx50u',
 'star': False,
 'play_long': 1034,
 'lastest_update': datetime.datetime(2023, 12, 19, 11, 41, 34, 914934),
 'path': '/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv'}
```

**使用** <kbd>stat</kbd> **方法，获取文件或文件夹的部分，参考** <kbd>os.stat</kbd>

```python
>>> fs.stat("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv")
os.stat_result(st_mode=33279, st_ino=2576931481393823441, st_dev=2576931481024724685, st_nlink=1, st_uid=306576686, st_gid=1, st_size=924544482, st_atime=1688662230.0, st_mtime=1677210171.0, st_ctime=1677210171.0)
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
p115.util.file.RequestsFileReader(<bound method P115PathBase.as_uri of <p115.P115Path(fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=2576931481024724685, path='/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）') at 0x106825810>, path='/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', id=2576931481393823441, url='https://cdnfhnfile.115.com/5c8b637b499f7a09e4bb06f19b09585699f0423c/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv?t=1703006667&u=306576686&s=104857600&d=vip-1862476304-djagtomczh64gx50u-1&c=2&f=1&k=f5ea224701acadd1bffad4a9200b23bd&us=1048576000&uc=10&v=1', url_expire_time=1703006667)>>, urlopen=<function RequestsFileReader.__init__.<locals>.urlopen_wrapper at 0x1068e2a20>, headers=mappingproxy({'Accept-Encoding': 'identity', 'Range': 'bytes=0-'}))
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
0
```

**使用** <kbd>walk</kbd> **方法，可以遍历一个目录，参考** <kbd>os.walk</kbd>

```python
>>> next(fs.walk())
('/',
 ['云下载',
  '000阅读·乱七八糟',
  '电视剧',
  '电影',
  '纪录片',
  'libgen',
  '👾0号：重要资源',
  '📚1号：书籍大礼包',
  '📼资料备份'],
 [])
```

**使用** <kbd>walk_path</kbd> **方法，可以遍历一个目录时，获取** <kbd>p115.P115Path</kbd> 对象

```python
>>> next(fs.walk_path())
('/',
 [<p115.P115Path(name='云下载', is_directory=True, size=None, id=2593093001609739968, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 16, 21, 58, 22), utime=datetime.datetime(2023, 12, 19, 11, 29, 29), ptime=datetime.datetime(2023, 3, 18, 18, 52, 54), open_time=datetime.datetime(2023, 12, 19, 11, 29, 29), time=datetime.datetime(2023, 12, 16, 21, 58, 22), pick_code='fe1kl2mz1if2fl3wmx', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/云下载')>,
  <p115.P115Path(name='000阅读·乱七八糟', is_directory=True, size=None, id=2592968610464922758, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 14, 15, 38, 18), ptime=datetime.datetime(2023, 3, 18, 14, 45, 45), open_time=datetime.datetime(2023, 12, 14, 13, 17, 9), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fccgz8vtu9xt08rmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/000阅读·乱七八糟')>,
  <p115.P115Path(name='电视剧', is_directory=True, size=None, id=2614100250469596984, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 15, 0, 48, 36), ptime=datetime.datetime(2023, 4, 16, 18, 30, 33), open_time=datetime.datetime(2023, 12, 15, 0, 48, 36), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fdjemtliv9d5b55y6u', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/电视剧')>,
  <p115.P115Path(name='电影', is_directory=True, size=None, id=2580587204111760961, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 14, 15, 0, 45), ptime=datetime.datetime(2023, 3, 1, 12, 46, 7), open_time=datetime.datetime(2023, 12, 12, 21, 56, 25), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fdj4gtgvtd5p8q5y6u', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/电影')>,
  <p115.P115Path(name='纪录片', is_directory=True, size=None, id=2576930424647319247, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 18, 18, 49, 29), utime=datetime.datetime(2023, 12, 18, 18, 49, 29), ptime=datetime.datetime(2023, 2, 24, 11, 40, 45), open_time=datetime.datetime(2023, 12, 13, 15, 45, 53), time=datetime.datetime(2023, 12, 18, 18, 49, 29), pick_code='fdjagt4u21x1k35y6u', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/纪录片')>,
  <p115.P115Path(name='libgen', is_directory=True, size=None, id=2644648816430546428, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 15, 18, 24, 57), ptime=datetime.datetime(2023, 5, 28, 22, 5, 6), open_time=datetime.datetime(2023, 12, 15, 18, 24, 57), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fcid29t51koofbrmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/libgen')>,
  <p115.P115Path(name='👾0号：重要资源', is_directory=True, size=None, id=2580131407544188592, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 19, 11, 29, 45), ptime=datetime.datetime(2023, 2, 28, 21, 40, 32), open_time=datetime.datetime(2023, 12, 19, 11, 29, 45), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fa8p74ih0nu1ax4fyr', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/👾0号：重要资源')>,
  <p115.P115Path(name='📚1号：书籍大礼包', is_directory=True, size=None, id=2580246506904748007, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 19, 11, 29, 44), ptime=datetime.datetime(2023, 3, 1, 1, 29, 12), open_time=datetime.datetime(2023, 12, 19, 11, 29, 44), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fccqsmu7225f2vrmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/📚1号：书籍大礼包')>,
  <p115.P115Path(name='📼资料备份', is_directory=True, size=None, id=2673432528538303699, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 14, 14, 54, 20), utime=datetime.datetime(2023, 12, 15, 0, 12, 1), ptime=datetime.datetime(2023, 7, 7, 15, 13, 12), open_time=datetime.datetime(2023, 12, 15, 0, 12, 1), time=datetime.datetime(2023, 12, 14, 14, 54, 20), pick_code='fcilznsigu2hczrmt6', star=False, lastest_update=datetime.datetime(2023, 12, 19, 12, 43, 23, 433377), fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x104e86050>, cid=0, path='/') at 0x106825810>, path='/📼资料备份')>],
 [])
```

**使用** <kbd>mkdir</kbd> **方法，可以创建空文件夹，参考** <kbd>os.mkdir</kbd>

```python
>>> fs.mkdir("test")
{'name': 'test',
 'is_directory': True,
 'size': None,
 'id': 2793068685969850230,
 'parent_id': 0,
 'sha1': None,
 'etime': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'utime': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'ptime': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'time': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'pick_code': 'fd4lr0lh0cqf525y6u',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 16, 48, 53, 571815),
 'path': '/test'}
```

名字中可以包含斜杠符号 `"/"`，但需要转义 `"\/"`（但我不建议在文件名中包含 `"/"`）

```python
>>> fs.mkdir("test\/2")
{'name': 'test/2',
 'is_directory': True,
 'size': None,
 'id': 2793068768899628939,
 'parent_id': 0,
 'sha1': None,
 'etime': datetime.datetime(2023, 12, 19, 16, 49, 3),
 'utime': datetime.datetime(2023, 12, 19, 16, 49, 3),
 'ptime': datetime.datetime(2023, 12, 19, 16, 49, 3),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'time': datetime.datetime(2023, 12, 19, 16, 49, 3),
 'pick_code': 'fd4lr0iehizqhn5y6u',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 16, 49, 3, 447470),
 'path': '/test\\/2'}
```

**使用** <kbd>rmdir</kbd> **方法，可以删除空文件夹，参考** <kbd>os.rmdir</kbd>

```python
>>> fs.rmdir("test")
{'name': 'test',
 'is_directory': True,
 'size': None,
 'id': 2793068685969850230,
 'parent_id': 0,
 'sha1': None,
 'etime': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'utime': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'ptime': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'time': datetime.datetime(2023, 12, 19, 16, 48, 53),
 'pick_code': 'fd4lr0lh0cqf525y6u',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 16, 49, 15, 896395),
 'path': '/test'}
```

**使用** <kbd>makedirs</kbd> **方法，可以创建多级的空目录，参考** <kbd>os.makedirs</kbd>

```python
>>> fs.makedirs("test\/2/test\/3/test\/4", exist_ok=True)
{'name': 'test/4',
 'is_directory': True,
 'size': None,
 'id': 2793068979713736021,
 'parent_id': 2793068974135311685,
 'sha1': None,
 'etime': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'utime': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'ptime': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'time': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'pick_code': 'fd4lr0njs9jm3d5y6u',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 16, 49, 28, 578537),
 'path': '/test\\/2/test\\/3/test\\/4'}
```

**使用** <kbd>removedirs</kbd> **方法，可以（自底向上地）删除多级的空目录，参考** <kbd>os.removedirs</kbd>

```python
>>> fs.removedirs("test\/2/test\/3/test\/4")
{'name': 'test/4',
 'is_directory': True,
 'size': None,
 'id': 2793068979713736021,
 'parent_id': 2793068974135311685,
 'sha1': None,
 'etime': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'utime': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'ptime': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'time': datetime.datetime(2023, 12, 19, 16, 49, 28),
 'pick_code': 'fd4lr0njs9jm3d5y6u',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 16, 49, 37, 830793),
 'path': '/test\\/2/test\\/3/test\\/4'}
```

**使用** <kbd>upload</kbd> **方法上传文件**

```python
>>> from io import BytesIO
>>> fs.upload(BytesIO(), "test.txt")
{'name': 'test.txt',
 'is_directory': False,
 'size': 0,
 'id': 2793075411108494446,
 'parent_id': 0,
 'sha1': 'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709',
 'etime': datetime.datetime(2023, 12, 19, 17, 2, 15),
 'utime': datetime.datetime(2023, 12, 19, 17, 2, 15),
 'ptime': datetime.datetime(2023, 12, 19, 17, 2, 15),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'pick_code': 'cwpyswv9pyja0dxt6',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 17, 2, 15, 355185),
 'path': '/test.txt'}
>>> fs.upload("file.py")
{'name': 'file.py',
 'is_directory': False,
 'size': 11927,
 'id': 2793075920607378515,
 'parent_id': 0,
 'sha1': 'C43B803A5F82E65BCAA9667F66939955CD0450CD',
 'etime': datetime.datetime(2023, 12, 19, 17, 3, 16),
 'utime': datetime.datetime(2023, 12, 19, 17, 3, 16),
 'ptime': datetime.datetime(2023, 12, 19, 17, 3, 16),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'pick_code': 'cwpysozr8a9andxt6',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 17, 3, 16, 204904),
 'path': '/file.py'}
```

**使用** <kbd>remove</kbd> **方法可以删除文件，参考** <kbd>os.remove</kbd>

```python
>>> fs.remove("test.txt")
{'name': 'test.txt',
 'is_directory': False,
 'size': 0,
 'id': 2793075411108494446,
 'parent_id': 0,
 'sha1': 'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709',
 'etime': datetime.datetime(2023, 12, 19, 17, 2, 15),
 'utime': datetime.datetime(2023, 12, 19, 17, 2, 15),
 'ptime': datetime.datetime(2023, 12, 19, 17, 2, 15),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'pick_code': 'cwpyswv9pyja0dxt6',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 17, 4, 25, 605253),
 'path': '/test.txt'}
```

**使用** <kbd>rmtree</kbd> **方法可以删除文件或文件夹，并且在删除文件夹时，也删除其中的文件和文件夹，参考** <kbd>shutil.rmtree</kbd>

```python
>>> fs.rmtree("file.py")
{'name': 'file.py',
 'is_directory': False,
 'size': 11927,
 'id': 2793075920607378515,
 'parent_id': 0,
 'sha1': 'C43B803A5F82E65BCAA9667F66939955CD0450CD',
 'etime': datetime.datetime(2023, 12, 19, 17, 3, 16),
 'utime': datetime.datetime(2023, 12, 19, 17, 3, 17),
 'ptime': datetime.datetime(2023, 12, 19, 17, 3, 16),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'pick_code': 'cwpysozr8a9andxt6',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 17, 5, 22, 766249),
 'path': '/file.py'}
```

**使用** <kbd>rename</kbd> **方法可以对文件或文件夹进行改名或移动，参考** <kbd>os.rename</kbd>

```python
>>> fs.touch("anyfile.mp3")
{'name': 'anyfile.mp3',
 'is_directory': False,
 'size': 0,
 'id': 2793077925249810265,
 'parent_id': 0,
 'sha1': 'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709',
 'etime': datetime.datetime(2023, 12, 19, 17, 7, 15),
 'utime': datetime.datetime(2023, 12, 19, 17, 7, 15),
 'ptime': datetime.datetime(2023, 12, 19, 17, 7, 15),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'pick_code': 'd47r0th5u0sfhx50u',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 17, 7, 15, 197968),
 'path': '/anyfile.mp3'}
>>> fs.rename("anyfile.mp3", "xyz.mp4")
{'name': 'xyz.mp4',
 'is_directory': False,
 'size': 0,
 'id': 2793078164048314194,
 'parent_id': 0,
 'sha1': 'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709',
 'etime': datetime.datetime(2023, 12, 19, 17, 7, 43),
 'utime': datetime.datetime(2023, 12, 19, 17, 7, 43),
 'ptime': datetime.datetime(2023, 12, 19, 17, 7, 43),
 'open_time': datetime.datetime(1970, 1, 1, 8, 0),
 'pick_code': 'e0bgvc5mdo6sxzlvx',
 'star': False,
 'lastest_update': datetime.datetime(2023, 12, 19, 17, 7, 43, 798793),
 'path': '/xyz.mp4'}
```

**使用** <kbd>renames</kbd> **方法可以对文件或文件夹进行改名或移动，并且在移动后如果原来所在目录为空，则会删除那个目录，参考** <kbd>os.renames</kbd>

**使用** <kbd>replace</kbd> **方法可以对文件或文件夹进行改名或移动，并且如果原始路径上是文件，目标路径上也存在一个文件，则会先把目标路径上的文件删除，参考** <kbd>os.replace</kbd>

**使用** <kbd>move</kbd> **方法可以对文件或文件夹进行改名或移动，目标路径存在且是一个目录，则把文件移动到其中（但是目录中有同名的文件或文件夹，还是会报错），参考** <kbd>shutil.move</kbd>

### 3. 遍历文件系统和查找文件

#### 1. 获取当前目录下所有 .mkv 文件的 url

**第 1 种方法，使用** <kbd>iter</kbd>，返回 <kbd>P115Path</kbd> 对象的迭代器

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

### 4. 针对分享链接的文件系统操作

<kbd>p115.P115ShareFileSystem</kbd> 实现了在<kbd>分享链接</kbd>上，只读的文件系统方法

<kbd>p115.P115SharePath</kbd> 实现了二次封装，从路径的角度来进行操作

**创建实例对象**

```python
from p115 import P115ShareFileSystem

share_link = "https://115.com/s/swzn4d53w8m?password=f247#"

share_fs = P115ShareFileSystem(client, share_link)
```

或者直接在 <kbd>client</kbd> 上就可获取

```python
share_fs = client.get_share_fs(share_link)
```

### 5. 针对压缩文件的文件系统操作

<kbd>p115.P115ZipFileSystem</kbd> 实现了在<kbd>压缩包</kbd>上，只读的文件系统方法

<kbd>p115.P115ZipPath</kbd> 实现了二次封装，从路径的角度来进行操作

**创建实例对象**

```python
from p115 import P115ZipFileSystem

pick_code = "abcdefg"

zip_fs = P115ZipFileSystem(client, pick_code)
```

或者直接在 <kbd>client</kbd> 上就可获取

```python
zip_fs = client.get_zip_fs(pick_code)
```

### 6. 针对云下载的封装

<kbd>p115.P115Offline</kbd> 实现了对于<kbd>云下载</kbd>的封装。

**创建实例对象**

```python
from p115 import P115Offline

offline = P115Offline(client)
```

或者直接在 <kbd>client</kbd> 上就可获取

```python
offline = client.offline
```

### 7. 针对回收站的封装

<kbd>p115.P115Recyclebin</kbd> 实现了对于<kbd>回收站</kbd>的封装。

**创建实例对象**

```python
from p115 import P115Recyclebin

recyclebin = P115Recyclebin(client)
```

或者直接在 <kbd>client</kbd> 上就可获取

```python
recyclebin = client.recyclebin
```

### 8. 针对分享的封装

<kbd>p115.P115Sharing</kbd> 实现了对于<kbd>分享记录</kbd>的封装。

**创建实例对象**

```python
from p115 import P115Sharing

sharing = P115Sharing(client)
```

或者直接在 <kbd>client</kbd> 上就可获取

```python
sharing = client.sharing
```

## 文档

> 正在编写中
