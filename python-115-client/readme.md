# 115 网盘 Web API 的 Python 封装

- [115网盘](https://115.com)

## 安装

通过 [pypi](https://pypi.org/project/python-115/)

```console
pip install -U python-115
```

## 使用实例

实例只提供最简单的使用例子，也没有覆盖所有方法，具体建议自己看源代码阅读理解 😂。

### 1. 就像在文件系统中操作

```python
>>> # 导入模块
>>> from p115 import P115Client, P115FileSystem
>>> # 创建客户端对象，需要传入 cookie，如果没有，则扫码登录
>>> cookie = "UID=...;CID=...;SEID=..."
>>> client = P115Client(cookie)
>>> # 创建文件系统对象
>>> fs = P115FileSystem(client)
>>> # 或者直接在 client 上就可获取 fs
>>> fs = client.fs
>>> # 获取当前位置
>>> fs.getcwd()
'/'
>>> # 罗列当前目录，类似 os.listdir
>>> fs.listdir()
['云下载', '000阅读·乱七八糟', '电视剧', '电影', '纪录片', 'libgen', '👾0号：重要资源', '📚1号：书籍大礼包', '📼资料备份']
>>> # 使用 listdir_attr 罗列当前目录，可以获取属性
>>> fs.listdir_attr()
[<p115.P115Path(name='云下载', is_dir=True, size=None, id=2593093001609739968, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 4, 10, 54, 17), utime=datetime.datetime(2023, 12, 10, 21, 37, 46), ptime=datetime.datetime(2023, 3, 18, 18, 52, 54), open_time=datetime.datetime(2023, 12, 10, 21, 37, 46), time=datetime.datetime(2023, 12, 4, 10, 54, 17), pick_code='fe1kl2mz1if2fl3wmx', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/云下载')>,
 <p115.P115Path(name='000阅读·乱七八糟', is_dir=True, size=None, id=2592968610464922758, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 10, 21, 23, 9), utime=datetime.datetime(2023, 12, 10, 21, 23, 9), ptime=datetime.datetime(2023, 3, 18, 14, 45, 45), open_time=datetime.datetime(2023, 12, 10, 21, 22, 50), time=datetime.datetime(2023, 12, 10, 21, 23, 9), pick_code='fccgz8vtu9xt08rmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/000阅读·乱七八糟')>,
 <p115.P115Path(name='电视剧', is_dir=True, size=None, id=2614100250469596984, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 8, 0, 33, 6), utime=datetime.datetime(2023, 12, 10, 3, 53, 52), ptime=datetime.datetime(2023, 4, 16, 18, 30, 33), open_time=datetime.datetime(2023, 12, 10, 3, 53, 52), time=datetime.datetime(2023, 12, 8, 0, 33, 6), pick_code='fdjemtliv9d5b55y6u', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/电视剧')>,
 <p115.P115Path(name='电影', is_dir=True, size=None, id=2580587204111760961, parent_id=0, sha1=None, etime=datetime.datetime(2023, 10, 7, 20, 29, 57), utime=datetime.datetime(2023, 12, 10, 3, 53, 52), ptime=datetime.datetime(2023, 3, 1, 12, 46, 7), open_time=datetime.datetime(2023, 12, 10, 3, 53, 52), time=datetime.datetime(2023, 10, 7, 20, 29, 57), pick_code='fdj4gtgvtd5p8q5y6u', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/电影')>,
 <p115.P115Path(name='纪录片', is_dir=True, size=None, id=2576930424647319247, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 10, 23, 58, 31), utime=datetime.datetime(2023, 12, 10, 23, 58, 31), ptime=datetime.datetime(2023, 2, 24, 11, 40, 45), open_time=datetime.datetime(2023, 12, 10, 23, 58, 26), time=datetime.datetime(2023, 12, 10, 23, 58, 31), pick_code='fdjagt4u21x1k35y6u', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/纪录片')>,
 <p115.P115Path(name='libgen', is_dir=True, size=None, id=2644648816430546428, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 10, 23, 39, 26), utime=datetime.datetime(2023, 12, 10, 23, 39, 30), ptime=datetime.datetime(2023, 5, 28, 22, 5, 6), open_time=datetime.datetime(2023, 12, 10, 23, 39, 30), time=datetime.datetime(2023, 12, 10, 23, 39, 26), pick_code='fcid29t51koofbrmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/libgen')>,
 <p115.P115Path(name='👾0号：重要资源', is_dir=True, size=None, id=2580131407544188592, parent_id=0, sha1=None, etime=datetime.datetime(2023, 9, 26, 11, 5, 43), utime=datetime.datetime(2023, 12, 10, 20, 34, 3), ptime=datetime.datetime(2023, 2, 28, 21, 40, 32), open_time=datetime.datetime(2023, 12, 10, 20, 34, 3), time=datetime.datetime(2023, 9, 26, 11, 5, 43), pick_code='fa8p74ih0nu1ax4fyr', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/👾0号：重要资源')>,
 <p115.P115Path(name='📚1号：书籍大礼包', is_dir=True, size=None, id=2580246506904748007, parent_id=0, sha1=None, etime=datetime.datetime(2023, 9, 2, 11, 49, 28), utime=datetime.datetime(2023, 12, 10, 3, 53, 53), ptime=datetime.datetime(2023, 3, 1, 1, 29, 12), open_time=datetime.datetime(2023, 12, 10, 3, 53, 53), time=datetime.datetime(2023, 9, 2, 11, 49, 28), pick_code='fccqsmu7225f2vrmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/📚1号：书籍大礼包')>,
 <p115.P115Path(name='📼资料备份', is_dir=True, size=None, id=2673432528538303699, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 8, 15, 58, 49), utime=datetime.datetime(2023, 12, 10, 23, 42, 42), ptime=datetime.datetime(2023, 7, 7, 15, 13, 12), open_time=datetime.datetime(2023, 12, 10, 23, 42, 42), time=datetime.datetime(2023, 12, 8, 15, 58, 49), pick_code='fcilznsigu2hczrmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/📼资料备份')>]
>>> # 进入 "电视剧/欧美剧/A" 目录
>>> fs.chdir("电视剧/欧美剧/A")
2598195078816071040
>>> fs.getcwd()
'/电视剧/欧美剧/A'
>>> # 罗列目录
>>> fs.listdir()
['A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]']
>>> fs.chdir("A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）")
2576931481024724685
>>> fs.listdir()
['Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass', 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv']
>>> # 查看一个文件的属性信息
>>> fs.attr("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv")
{'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'is_dir': False,
 'size': 924544482,
 'id': 2576931481393823441,
 'parent_id': 2576931481024724685,
 'sha1': '7F4121B68A4E467ABF30A84627E20A8978895A4E',
 'etime': datetime.datetime(2023, 2, 24, 11, 42, 51),
 'utime': datetime.datetime(2023, 12, 10, 19, 33, 18),
 'ptime': datetime.datetime(2023, 2, 24, 11, 42, 51),
 'open_time': datetime.datetime(2023, 7, 7, 0, 50, 30),
 'pick_code': 'e1cd9ptunky0dzlvx',
 'star': False}
>>> # 打开一个文本文件
>>> f = fs.open("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass", encoding="UTF-16")
>>> f
<_io.TextIOWrapper name='Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass' encoding='UTF-16'>
>>> # 读取 100 个字符
>>> f.read(100)
'[Script Info]\n;SrtEdit 6.3.2012.1001\n;Copyright(C) 2005-2012 Yuan Weiguo\n\nTitle: YYeTs\nOriginal Scri'
>>> # 关闭文件（其实不主动关闭也可以，只要文件不被引用，就会自动关闭）
>>> f.close()
>>> # 打开一个二进制文件
>>> f = fs.open("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv", "rb")
>>> f
p115.util.file.RequestsFileReader('https://cdnfhnfile.115.com/5c8b637b499f7a09e4bb06f19b09585699f0423c/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv?t=1702271345&u=306576686&s=104857600&d=vip-3747533902-e1cd9ptunky0dzlvx-1&c=2&f=1&k=4b6a8d6a81aa0119d70fcc7dc112297d&us=1048576000&uc=10&v=1', urlopen=functools.partial(<bound method Session.get of <requests.sessions.Session object at 0x10736eed0>>, stream=True), headers=mappingproxy({'Accept-Encoding': 'identity', 'Range': 'bytes=0-'}))
>>> # 读取 10 字节
>>> f.read(10)
b'\x1aE\xdf\xa3\xa3B\x86\x81\x01B'
>>> # 当前文件偏移位置（从 0 开始计算）
>>> f.tell()
10
>>> f.read(10)
b'\xf7\x81\x01B\xf2\x81\x04B\xf3\x81'
>>> f.tell()
20
>>> # 把读取位置重新变为文件开头
>>> f.seek(0)
0
>>> # 再次读取 20 字节，应该等于前两次结果的拼接
>>> f.read(20)
b'\x1aE\xdf\xa3\xa3B\x86\x81\x01B\xf7\x81\x01B\xf2\x81\x04B\xf3\x81'
>>> f.tell()
20
>>> # 回到根目录
>>> fs.chdir("/")
>>> # 使用 walk，类似 os.walk
>>> next(fs.walk())
('/',
 ['云下载',
  '纪录片',
  '👾0号：重要资源',
  '📚1号：书籍大礼包',
  '电影',
  '000阅读·乱七八糟',
  '电视剧',
  'libgen',
  '📼资料备份'],
 [])
>>> # 使用 walk_attr，可以获取属性
>>> next(fs.walk_attr())
('/',
 [<p115.P115Path(name='云下载', is_dir=True, size=None, id=2593093001609739968, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 4, 10, 54, 17), utime=datetime.datetime(2023, 12, 10, 21, 37, 46), ptime=datetime.datetime(2023, 3, 18, 18, 52, 54), open_time=datetime.datetime(2023, 12, 10, 21, 37, 46), time=datetime.datetime(2023, 12, 4, 10, 54, 17), pick_code='fe1kl2mz1if2fl3wmx', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/云下载')>,
  <p115.P115Path(name='纪录片', is_dir=True, size=None, id=2576930424647319247, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 10, 23, 58, 31), utime=datetime.datetime(2023, 12, 10, 23, 58, 31), ptime=datetime.datetime(2023, 2, 24, 11, 40, 45), open_time=datetime.datetime(2023, 12, 10, 23, 58, 26), time=datetime.datetime(2023, 12, 10, 23, 58, 31), pick_code='fdjagt4u21x1k35y6u', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/纪录片')>,
  <p115.P115Path(name='👾0号：重要资源', is_dir=True, size=None, id=2580131407544188592, parent_id=0, sha1=None, etime=datetime.datetime(2023, 9, 26, 11, 5, 43), utime=datetime.datetime(2023, 12, 10, 20, 34, 3), ptime=datetime.datetime(2023, 2, 28, 21, 40, 32), open_time=datetime.datetime(2023, 12, 10, 20, 34, 3), time=datetime.datetime(2023, 9, 26, 11, 5, 43), pick_code='fa8p74ih0nu1ax4fyr', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/👾0号：重要资源')>,
  <p115.P115Path(name='📚1号：书籍大礼包', is_dir=True, size=None, id=2580246506904748007, parent_id=0, sha1=None, etime=datetime.datetime(2023, 9, 2, 11, 49, 28), utime=datetime.datetime(2023, 12, 10, 3, 53, 53), ptime=datetime.datetime(2023, 3, 1, 1, 29, 12), open_time=datetime.datetime(2023, 12, 10, 3, 53, 53), time=datetime.datetime(2023, 9, 2, 11, 49, 28), pick_code='fccqsmu7225f2vrmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/📚1号：书籍大礼包')>,
  <p115.P115Path(name='电影', is_dir=True, size=None, id=2580587204111760961, parent_id=0, sha1=None, etime=datetime.datetime(2023, 10, 7, 20, 29, 57), utime=datetime.datetime(2023, 12, 10, 3, 53, 52), ptime=datetime.datetime(2023, 3, 1, 12, 46, 7), open_time=datetime.datetime(2023, 12, 10, 3, 53, 52), time=datetime.datetime(2023, 10, 7, 20, 29, 57), pick_code='fdj4gtgvtd5p8q5y6u', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/电影')>,
  <p115.P115Path(name='000阅读·乱七八糟', is_dir=True, size=None, id=2592968610464922758, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 10, 21, 23, 9), utime=datetime.datetime(2023, 12, 10, 21, 23, 9), ptime=datetime.datetime(2023, 3, 18, 14, 45, 45), open_time=datetime.datetime(2023, 12, 10, 21, 22, 50), time=datetime.datetime(2023, 12, 10, 21, 23, 9), pick_code='fccgz8vtu9xt08rmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/000阅读·乱七八糟')>,
  <p115.P115Path(name='电视剧', is_dir=True, size=None, id=2614100250469596984, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 8, 0, 33, 6), utime=datetime.datetime(2023, 12, 10, 3, 53, 52), ptime=datetime.datetime(2023, 4, 16, 18, 30, 33), open_time=datetime.datetime(2023, 12, 10, 3, 53, 52), time=datetime.datetime(2023, 12, 8, 0, 33, 6), pick_code='fdjemtliv9d5b55y6u', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/电视剧')>,
  <p115.P115Path(name='libgen', is_dir=True, size=None, id=2644648816430546428, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 10, 23, 39, 26), utime=datetime.datetime(2023, 12, 10, 23, 39, 30), ptime=datetime.datetime(2023, 5, 28, 22, 5, 6), open_time=datetime.datetime(2023, 12, 10, 23, 39, 30), time=datetime.datetime(2023, 12, 10, 23, 39, 26), pick_code='fcid29t51koofbrmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/libgen')>,
  <p115.P115Path(name='📼资料备份', is_dir=True, size=None, id=2673432528538303699, parent_id=0, sha1=None, etime=datetime.datetime(2023, 12, 8, 15, 58, 49), utime=datetime.datetime(2023, 12, 10, 23, 42, 42), ptime=datetime.datetime(2023, 7, 7, 15, 13, 12), open_time=datetime.datetime(2023, 12, 10, 23, 42, 42), time=datetime.datetime(2023, 12, 8, 15, 58, 49), pick_code='fcilznsigu2hczrmt6', star=False, fs=<p115.P115FileSystem(client=<p115.P115Client object at 0x107c2d450>, cid=0, path='/') at 0x107e7c990>, path='/📼资料备份')>],
 [])
>>> # 获取当前目录下所有 .mkv 文件的 url，方法 1
>>> for path in fs.iterdir(max_depth=-1):
>>>     if path.name.endswith(".mkv"):
>>>         # 获取下载链接（要么是直链，不然就是 alist 的下载链接）
>>>         print(path.url)
http://localhost:5244/d/115/%E4%BA%91%E4%B8%8B%E8%BD%BD/A.Million.Miles.Away.2023.1080p.AMZN.WEB-DL.DDP5.1.H.264-AceMovies%5BTGx%5D/A.Million.Miles.Away.2023.1080p.AMZN.WEB-DL.DDP5.1.H.264-AceMovies.mkv
http://localhost:5244/d/115/%E4%BA%91%E4%B8%8B%E8%BD%BD/About.My.Father.2023.720p.AMZN.WEBRip.800MB.x264-GalaxyRG%5BTGx%5D/About.My.Father.2023.720p.AMZN.WEBRip.800MB.x264-GalaxyRG.mkv
...
>>> # 获取当前目录下所有 .mkv 文件的 url，方法 2
>>> for path in fs.glob("**/*.mkv"):
>>>     print(path.url)
>>> # 获取当前目录下所有 .mkv 文件的 url，方法 3
>>> for path in fs.rglob("*.mkv"):
>>>     print(path.url)
```

## 文档

正在编写，不要急 。。。
