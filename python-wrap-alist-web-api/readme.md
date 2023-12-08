# Alist web API 的 Python 封装

- [Alist Web API 官方文档](https://alist.nn.ci/guide/api/)

## 安装

通过 [pypi](https://pypi.org/project/python-alist/)

```console
pip install -U python-alist
```

## 使用实例

实例只提供最简单的使用例子，也没有覆盖所有方法，具体建议自己看源代码阅读理解 😂。

### 1. 就像在文件系统中操作

```python
>>> # 导入模块
>>> from alist import AlistClient, AlistFileSystem
>>> # 创建客户端对象，登录 alist：此处，用户名是 "admin"，密码是 "123456"
>>> client = AlistClient("http://localhost:5244", "admin", "123456")
>>> # 创建文件系统对象
>>> fs = AlistFileSystem(client)
>>> # 或者，直接用 AlistFileSystem.login 方法登录
>>> fs = AlistFileSystem.login("http://localhost:5244", "admin", "123456")
>>> # 获取当前位置
>>> fs.getcwd()
'/'
>>> # 罗列当前目录，类似 os.listdir
>>> fs.listdir()
['115', '阿里云盘']
>>> # 使用 listdir_attr 罗列当前目录，可以获取属性
>>> fs.listdir_attr()
[<alist.AlistPath(name='115', size=0, is_dir=True, modified='2023-10-23T19:54:21.483857+08:00', created='2023-10-23T19:54:21.483857+08:00', sign='', thumb='', type=1, hashinfo='null', hash_info=None, fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username=None, password='******'), path='/', refresh=False), path='/115', password='', attr_last_fetched=None)>, <alist.AlistPath(name='阿里云盘', size=0, is_dir=True, modified='2023-10-01T16:26:52.862197+08:00', created='2023-10-01T16:26:52.862197+08:00', sign='', thumb='', type=1, hashinfo='null', hash_info=None, fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username=None, password='******'), path='/', refresh=False), path='/阿里云盘', password='', attr_last_fetched=None)>]
>>> # 进入 "115" 目录
>>> fs.chdir("115")
>>> # 下面是我的 "115" 目录的罗列结果，你肯定和我不同😄
>>> fs.listdir()
['云下载', '000阅读·乱七八糟', '电视剧', '电影', '纪录片', 'libgen', '👾0号：重要资源', '📚1号：书籍大礼包', '📼资料备份']
>>> fs.chdir("电视剧/欧美剧/A")
>>> fs.getcwd()
'/115/电视剧/欧美剧/A'
>>> fs.listdir()
['A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]']
>>> fs.chdir("A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）")
>>> fs.listdir()
['Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass', 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv']
>>> # 查看一个文件的属性信息
>>> fs.attr("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv")
{'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', 'size': 924544482, 'is_dir': False, 'modified': '2023-02-24T11:42:00+08:00', 'created': '2023-02-24T11:42:51+08:00', 'sign': '', 'thumb': '', 'type': 2, 'hashinfo': '{"sha1":"7F4121B68A4E467ABF30A84627E20A8978895A4E"}', 'hash_info': {'sha1': '7F4121B68A4E467ABF30A84627E20A8978895A4E'}, 'raw_url': 'http://localhost:5244/p/115/%E7%94%B5%E8%A7%86%E5%89%A7/%E6%AC%A7%E7%BE%8E%E5%89%A7/A/A%E3%80%8A%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BA%E3%80%8B%28Love.Death.and.Robot%29%5Btt9561862%5D/%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BAS01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG%EF%BC%8818%E9%9B%86%EF%BC%89/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', 'readme': '', 'provider': '115 Cloud', 'related': [{'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.简体&英文.ass', 'size': 48910, 'is_dir': False, 'modified': '2023-03-23T22:09:00+08:00', 'created': '2023-03-23T22:09:09+08:00', 'sign': '', 'thumb': '', 'type': 4, 'hashinfo': '{"sha1":"30AB3A1A376DE83049B35F135A774980F5C7C558"}', 'hash_info': {'sha1': '30AB3A1A376DE83049B35F135A774980F5C7C558'}}]}
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
<alist.AlistFile(client=alist.AlistClient(origin='http://localhost:5244', username='admin', password='******'), path='/115/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', mode='r') at 0x105412290>
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
('/', ['115', '阿里云盘'], [])
>>> # 使用 walk_attr，可以获取属性
>>> next(fs.walk_attr())
('/', [<alist.AlistPath(name='115', size=0, is_dir=True, modified='2023-10-23T19:54:21.483857+08:00', created='2023-10-23T19:54:21.483857+08:00', sign='', thumb='', type=1, hashinfo='null', hash_info=None, fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username=None, password='******'), path='/', refresh=False), path='/115', password='', attr_last_fetched=None)>, <alist.AlistPath(name='阿里云盘', size=0, is_dir=True, modified='2023-10-01T16:26:52.862197+08:00', created='2023-10-01T16:26:52.862197+08:00', sign='', thumb='', type=1, hashinfo='null', hash_info=None, fs=alist.AlistFileSystem(client=alist.AlistClient(origin='http://localhost:5244', username=None, password='******'), path='/', refresh=False), path='/阿里云盘', password='', attr_last_fetched=None)>], [])
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
