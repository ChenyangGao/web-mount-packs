# clouddrive web API 的 Python 封装

## 安装

通过 [pypi](https://pypi.org/project/clouddrive/)

```console
pip install -U clouddrive
```

## 使用实例

实例只提供最简单的使用例子，也没有覆盖所有方法，具体建议自己看源代码阅读理解 😂。

### 1. 就像在文件系统中操作

```python
>>> # 导入模块
>>> from clouddrive import CloudDriveClient, CloudDriveFileSystem
>>> # 创建客户端对象，登录 cd2：此处，用户名是 "test"，密码是 "test@test"
>>> client = CloudDriveClient("http://localhost:19798", "test", "test@test")
>>> # 创建文件系统对象
>>> fs = CloudDriveFileSystem(client)
>>> # 或者，直接用 CloudDriveFileSystem.login 方法登录
>>> fs = CloudDriveFileSystem.login("http://localhost:19798", "test", "test@test")
>>> # 获取当前位置
>>> fs.getcwd()
'/'
>>> # 罗列当前目录，类似 os.listdir
>>> fs.listdir()
['115', '阿里云盘Open']
>>> # 使用 listdir_attr 罗列当前目录，可以获取属性
>>> fs.listdir_attr()
[<clouddrive.CloudDrivePath(id='0', name='115', fullPathName='/115', createTime='2023-10-22T16:01:44.430846Z', writeTime='2023-10-22T16:01:44.430846Z', accessTime='2023-10-22T16:01:44.430846Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudRoot=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, fs=clouddrive.CloudDriveFileSystem(client=<clouddrive.client.CloudDriveClient object at 0x1019f9350>, path='/', refresh=False), path='/115')>, <clouddrive.CloudDrivePath(id='58188691_root', name='阿里云盘Open', fullPathName='/阿里云盘Open', createTime='2023-10-22T16:01:44.964617Z', writeTime='2023-10-22T16:01:44.964617Z', accessTime='2023-10-22T16:01:44.964617Z', CloudAPI={'name': '阿里云盘Open', 'userName': '4d1769fb91ba4752ac417f77c1da8082', 'nickName': '请设置昵称？'}, isDirectory=True, isCloudRoot=True, isCloudDirectory=True, canSearch=True, canDeletePermanently=True, fs=clouddrive.CloudDriveFileSystem(client=<clouddrive.client.CloudDriveClient object at 0x1019f9350>, path='/', refresh=False), path='/阿里云盘Open')>]
>>> # 进入 "115" 目录
>>> fs.chdir("115")
>>> # 下面是我的 "115" 目录的罗列结果，你肯定和我不同😄
>>> fs.listdir()
['000阅读·乱七八糟', 'libgen', '云下载', '电影', '电视剧', '纪录片', '👾0号：重要资源', '📚1号：书籍大礼包', '📼资料备份']
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
{'id': '2576931481393823441', 'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', 'fullPathName': '/115/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', 'size': '924544482', 'fileType': 'File', 'createTime': '2023-02-24T03:42:51Z', 'writeTime': '2023-02-24T03:42:51Z', 'accessTime': '2023-02-24T03:42:51Z', 'CloudAPI': {'name': '115', 'userName': '306576686', 'nickName': '306576686'}, 'isCloudFile': True, 'hasDetailProperties': True, 'canOfflineDownload': True}
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
clouddrive.CloudDriveFile(path=<clouddrive.CloudDrivePath(fs=clouddrive.CloudDriveFileSystem(client=<clouddrive.client.CloudDriveClient object at 0x1076cb310>, path='/115/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）', refresh=False), path='/115/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', url='http://localhost:19798/static/http/localhost:19798/False/%2F115%2F%E7%94%B5%E8%A7%86%E5%89%A7%2F%E6%AC%A7%E7%BE%8E%E5%89%A7%2FA%2FA%E3%80%8A%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BA%E3%80%8B%28Love.Death.and.Robot%29%5Btt9561862%5D%2F%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BAS01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG%EF%BC%8818%E9%9B%86%EF%BC%89%2FLove.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv')>, mode='r')
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
('/', [<clouddrive.CloudDrivePath(id='0', name='115', fullPathName='/115', createTime='2023-10-22T16:01:44.430846Z', writeTime='2023-10-22T16:01:44.430846Z', accessTime='2023-10-22T16:01:44.430846Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudRoot=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, fs=clouddrive.CloudDriveFileSystem(client=<clouddrive.client.CloudDriveClient object at 0x103791450>, path='/', refresh=False), path='/115')>, <clouddrive.CloudDrivePath(id='58188691_root', name='阿里云盘Open', fullPathName='/阿里云盘Open', createTime='2023-10-22T16:01:44.964617Z', writeTime='2023-10-22T16:01:44.964617Z', accessTime='2023-10-22T16:01:44.964617Z', CloudAPI={'name': '阿里云盘Open', 'userName': '4d1769fb91ba4752ac417f77c1da8082', 'nickName': '请设置昵称？'}, isDirectory=True, isCloudRoot=True, isCloudDirectory=True, canSearch=True, canDeletePermanently=True, fs=clouddrive.CloudDriveFileSystem(client=<clouddrive.client.CloudDriveClient object at 0x103791450>, path='/', refresh=False), path='/阿里云盘Open')>], [])
>>> # 获取当前目录下所有 .mkv 文件的 url，方法 1
>>> for path in fs.iterdir(max_depth=-1):
>>>     if path.name.endswith(".mkv"):
>>>         # 获取下载链接（注意：不是直链）
>>>         print(path.url)
http://localhost:19798/static/http/localhost:19798/False/%2F115%2F%E4%BA%91%E4%B8%8B%E8%BD%BD%2F57.Seconds.2023.1080p.WEB-DL.DDP5.1.H264-EniaHD%5BTGx%5D%2F57.Seconds.2023.1080p.WEB-DL.DDP5.1.H264-EniaHD.mkv
http://localhost:19798/static/http/localhost:19798/False/%2F115%2F%E4%BA%91%E4%B8%8B%E8%BD%BD%2FA.Million.Miles.Away.2023.1080p.AMZN.WEB-DL.DDP5.1.H.264-AceMovies%5BTGx%5D%2FA.Million.Miles.Away.2023.1080p.AMZN.WEB-DL.DDP5.1.H.264-AceMovies.mkv
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
