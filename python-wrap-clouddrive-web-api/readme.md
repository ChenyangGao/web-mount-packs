# clouddrive web API 的 Python 封装

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/clouddrive)
![PyPI - Version](https://img.shields.io/pypi/v/clouddrive)
![PyPI - Downloads](https://img.shields.io/pypi/dm/clouddrive)
![PyPI - Format](https://img.shields.io/pypi/format/clouddrive)
![PyPI - Status](https://img.shields.io/pypi/status/clouddrive)

## 安装

通过 [pypi](https://pypi.org/project/clouddrive/)

```console
pip install -U clouddrive
```

## 入门介绍

### 1. 导入模块和创建实例

**导入模块**

```python
from clouddrive import CloudDriveClient, CloudDriveFileSystem
```

**创建客户端对象，登录 <kbd>CloudDrive</kbd>：此处，后台服务地址: `"http://localhost:19798"`，用户名: `"test"`，密码: `"test@test"`**

> 请确保 <kbd>CloudDrive</kbd> 已经启动，并且可通过 <kbd>http://localhost:19798</kbd> 访问

```python
client = CloudDriveClient("http://localhost:19798", "test", "test@test")
```

绝大部分 <kbd>CloudDriveClient</kbd> 的方法带有 `async_` 参数，意味着它支持异步 IO。

```python
>>> import asyncio
>>> loop = asyncio.get_event_loop()

>>> from clouddrive import CloudDriveClient, CloudDriveFileSystem
>>> client = CloudDriveClient("http://localhost:19798", "test", "test@test")

>>> import CloudDrive_pb2
>>> client.FindFileByPath(CloudDrive_pb2.FindFileByPathRequest(path="/"))
id: "60512951-88d8-4b5a-bea4-fbcb5d86ce6f"
name: "/"
fullPathName: "/"
createTime {
  seconds: 1703821474
  nanos: 152897000
}
writeTime {
  seconds: 1703821474
  nanos: 152897000
}
accessTime {
  seconds: 1703821474
  nanos: 152897000
}
CloudAPI {
  name: "BaseFsApi"
}
isDirectory: true
isRoot: true

>>> client.FindFileByPath(CloudDrive_pb2.FindFileByPathRequest(path="/"), async_=True)
<coroutine object UnaryUnaryMethod.__call__ at 0x107518f20>
>>> loop.run_until_complete(client.FindFileByPath(CloudDrive_pb2.FindFileByPathRequest(path="/"), async_=True))
id: "60512951-88d8-4b5a-bea4-fbcb5d86ce6f"
name: "/"
fullPathName: "/"
createTime {
  seconds: 1703821474
  nanos: 152897000
}
writeTime {
  seconds: 1703821474
  nanos: 152897000
}
accessTime {
  seconds: 1703821474
  nanos: 152897000
}
CloudAPI {
  name: "BaseFsApi"
}
isDirectory: true
isRoot: true
```

**创建文件系统对象**

```python
fs = CloudDriveFileSystem(client)
```

或者直接在 <kbd>client</kbd> 上就可获取文件系统对象

```python
fs = client.fs
```

或者直接用 <kbd>CloudDriveFileSystem</kbd> 登录

```python
fs = CloudDriveFileSystem.login("http://localhost:19798", "test", "test@test")
```

### 2. 操作网盘使用 Python 式的文件系统方法

文件系统对象的方法，设计和行为参考了 <kbd>[os](https://docs.python.org/3/library/os.html)</kbd>、<kbd>[posixpath](https://docs.python.org/3/library/os.path.html)</kbd>、<kbd>[pathlib.Path](https://docs.python.org/3/library/pathlib.html)</kbd> 和 <kbd>[shutil](https://docs.python.org/3/library/shutil.html)</kbd> 等模块。

<kbd>clouddrive.CloudDriveFileSystem</kbd> 实现了读写的文件系统方法。

<kbd>clouddrive.CloudDrivePath</kbd> 实现了二次封装，从路径的角度来进行操作。

**使用** <kbd>getcwd</kbd> **方法，获取当前工作目录的路径，参考** <kbd>os.getcwd</kbd>

```python
>>> fs.getcwd()
'/'
```

**使用** <kbd>listdir</kbd> **方法，罗列当前目录的文件名，参考** <kbd>os.listdir</kbd>

```python
>>> fs.listdir()
['115', '阿里云盘Open']
```

**使用** <kbd>chdir</kbd> **方法，切换当前工作目录，参考** <kbd>os.chdir</kbd>

```python
>>> fs.chdir("/115")
```

**使用** <kbd>listdir_attr</kbd> **方法，罗列当前目录时，还可以获取属性**

```python
>>> fs.listdir_attr()
[{'id': '2592968610464922758',
  'name': '000阅读·乱七八糟',
  'fullPathName': '/115/000阅读·乱七八糟',
  'createTime': '2023-03-18T06:45:45Z',
  'writeTime': '2023-12-14T06:54:20Z',
  'accessTime': '2023-12-14T06:54:20Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/000阅读·乱七八糟',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2644648816430546428',
  'name': 'libgen',
  'fullPathName': '/115/libgen',
  'createTime': '2023-05-28T14:05:06Z',
  'writeTime': '2023-12-14T06:54:20Z',
  'accessTime': '2023-12-14T06:54:20Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/libgen',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2593093001609739968',
  'name': '云下载',
  'fullPathName': '/115/云下载',
  'createTime': '2023-03-18T10:52:54Z',
  'writeTime': '2023-12-16T13:58:22Z',
  'accessTime': '2023-12-16T13:58:22Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/云下载',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2580587204111760961',
  'name': '电影',
  'fullPathName': '/115/电影',
  'createTime': '2023-03-01T04:46:07Z',
  'writeTime': '2023-12-14T06:54:20Z',
  'accessTime': '2023-12-14T06:54:20Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/电影',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2614100250469596984',
  'name': '电视剧',
  'fullPathName': '/115/电视剧',
  'createTime': '2023-04-16T10:30:33Z',
  'writeTime': '2023-12-23T14:26:17Z',
  'accessTime': '2023-12-23T14:26:17Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/电视剧',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2576930424647319247',
  'name': '纪录片',
  'fullPathName': '/115/纪录片',
  'createTime': '2023-02-24T03:40:45Z',
  'writeTime': '2023-12-18T10:49:29Z',
  'accessTime': '2023-12-18T10:49:29Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/纪录片',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2580131407544188592',
  'name': '👾0号：重要资源',
  'fullPathName': '/115/👾0号：重要资源',
  'createTime': '2023-02-28T13:40:32Z',
  'writeTime': '2023-12-14T06:54:20Z',
  'accessTime': '2023-12-14T06:54:20Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/👾0号：重要资源',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2580246506904748007',
  'name': '📚1号：书籍大礼包',
  'fullPathName': '/115/📚1号：书籍大礼包',
  'createTime': '2023-02-28T17:29:12Z',
  'writeTime': '2023-12-14T06:54:20Z',
  'accessTime': '2023-12-14T06:54:20Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/📚1号：书籍大礼包',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)},
 {'id': '2673432528538303699',
  'name': '📼资料备份',
  'fullPathName': '/115/📼资料备份',
  'createTime': '2023-07-07T07:13:12Z',
  'writeTime': '2023-12-14T06:54:20Z',
  'accessTime': '2023-12-14T06:54:20Z',
  'CloudAPI': {'name': '115',
   'userName': '306576686',
   'nickName': '306576686'},
  'isDirectory': True,
  'isCloudDirectory': True,
  'canSearch': True,
  'hasDetailProperties': True,
  'canOfflineDownload': True,
  'path': '/115/📼资料备份',
  'lastest_update': datetime.datetime(2023, 12, 29, 13, 14, 2, 172632)}]
```

**使用** <kbd>listdir_path</kbd> **方法，罗列当前目录时，还可以获取** <kbd>clouddrive.CloudDrivePath</kbd> **对象**

```python
>>> fs.listdir_path()
[<clouddrive.CloudDrivePath(id='2592968610464922758', name='000阅读·乱七八糟', fullPathName='/115/000阅读·乱七八糟', createTime='2023-03-18T06:45:45Z', writeTime='2023-12-14T06:54:20Z', accessTime='2023-12-14T06:54:20Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/000阅读·乱七八糟')>,
 <clouddrive.CloudDrivePath(id='2644648816430546428', name='libgen', fullPathName='/115/libgen', createTime='2023-05-28T14:05:06Z', writeTime='2023-12-14T06:54:20Z', accessTime='2023-12-14T06:54:20Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/libgen')>,
 <clouddrive.CloudDrivePath(id='2593093001609739968', name='云下载', fullPathName='/115/云下载', createTime='2023-03-18T10:52:54Z', writeTime='2023-12-16T13:58:22Z', accessTime='2023-12-16T13:58:22Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/云下载')>,
 <clouddrive.CloudDrivePath(id='2580587204111760961', name='电影', fullPathName='/115/电影', createTime='2023-03-01T04:46:07Z', writeTime='2023-12-14T06:54:20Z', accessTime='2023-12-14T06:54:20Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/电影')>,
 <clouddrive.CloudDrivePath(id='2614100250469596984', name='电视剧', fullPathName='/115/电视剧', createTime='2023-04-16T10:30:33Z', writeTime='2023-12-23T14:26:17Z', accessTime='2023-12-23T14:26:17Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/电视剧')>,
 <clouddrive.CloudDrivePath(id='2576930424647319247', name='纪录片', fullPathName='/115/纪录片', createTime='2023-02-24T03:40:45Z', writeTime='2023-12-18T10:49:29Z', accessTime='2023-12-18T10:49:29Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/纪录片')>,
 <clouddrive.CloudDrivePath(id='2580131407544188592', name='👾0号：重要资源', fullPathName='/115/👾0号：重要资源', createTime='2023-02-28T13:40:32Z', writeTime='2023-12-14T06:54:20Z', accessTime='2023-12-14T06:54:20Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/👾0号：重要资源')>,
 <clouddrive.CloudDrivePath(id='2580246506904748007', name='📚1号：书籍大礼包', fullPathName='/115/📚1号：书籍大礼包', createTime='2023-02-28T17:29:12Z', writeTime='2023-12-14T06:54:20Z', accessTime='2023-12-14T06:54:20Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/📚1号：书籍大礼包')>,
 <clouddrive.CloudDrivePath(id='2673432528538303699', name='📼资料备份', fullPathName='/115/📼资料备份', createTime='2023-07-07T07:13:12Z', writeTime='2023-12-14T06:54:20Z', accessTime='2023-12-14T06:54:20Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, lastest_update=datetime.datetime(2023, 12, 29, 13, 15, 21, 23281), fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x105e9a850>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/115', refresh=False), path='/115/📼资料备份')>]
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
{'id': '2576931481393823441',
 'name': 'Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'fullPathName': '/115/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'size': '924544482',
 'fileType': 'File',
 'createTime': '2023-02-24T03:42:51Z',
 'writeTime': '2023-02-24T03:42:51Z',
 'accessTime': '2023-02-24T03:42:51Z',
 'CloudAPI': {'name': '115', 'userName': '306576686', 'nickName': '306576686'},
 'isCloudFile': True,
 'hasDetailProperties': True,
 'canOfflineDownload': True,
 'fileHashes': {'2': '7F4121B68A4E467ABF30A84627E20A8978895A4E'},
 'path': '/115/电视剧/欧美剧/A/A《爱、死亡和机器人》(Love.Death.and.Robot)[tt9561862]/爱、死亡和机器人S01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG（18集）/Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv',
 'lastest_update': datetime.datetime(2023, 12, 29, 13, 18, 27, 395024)}
```

**使用** <kbd>stat</kbd> **方法，获取文件或文件夹的部分，参考** <kbd>os.stat</kbd>

```python
>>> fs.stat("Love.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv")
os.stat_result(st_mode=33279, st_ino=0, st_dev=0, st_nlink=1, st_uid=0, st_gid=0, st_size=924544482, st_atime=1677210171.0, st_mtime=1677210171.0, st_ctime=1677210171.0)
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
clouddrive.util.file.HTTPFileReader('http://localhost:19798/static/http/localhost:19798/False/%2F115%2F%E7%94%B5%E8%A7%86%E5%89%A7%2F%E6%AC%A7%E7%BE%8E%E5%89%A7%2FA%2FA%E3%80%8A%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BA%E3%80%8B%28Love.Death.and.Robot%29%5Btt9561862%5D%2F%E7%88%B1%E3%80%81%E6%AD%BB%E4%BA%A1%E5%92%8C%E6%9C%BA%E5%99%A8%E4%BA%BAS01.Love.Death.and.Robots.1080p.NF.WEB-DL.DDP5.1.x264-NTG%EF%BC%8818%E9%9B%86%EF%BC%89%2FLove.Death.and.Robots.S01E01.Sonnies.Edge.1080p.NF.WEB-DL.DDP5.1.x264-NTG.mkv', urlopen=<function urlopen at 0x1069200e0>, headers=mappingproxy({'Accept-Encoding': 'identity'}))
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

**使用** <kbd>walk_path</kbd> **方法，可以遍历一个目录时，获取** <kbd>clouddrive.CloudDrivePath</kbd> 对象

```python
>>> next(fs.walk_path())
('/',
 [<clouddrive.CloudDrivePath(id='0', name='115', fullPathName='/115', createTime='2023-12-29T03:44:34.427131Z', writeTime='2023-12-29T03:44:34.427131Z', accessTime='2023-12-29T03:44:34.427131Z', CloudAPI={'name': '115', 'userName': '306576686', 'nickName': '306576686'}, isDirectory=True, isCloudRoot=True, isCloudDirectory=True, canSearch=True, hasDetailProperties=True, canOfflineDownload=True, fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x1064ee350>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/', refresh=False), path='/115')>,
  <clouddrive.CloudDrivePath(id='58188691_root', name='阿里云盘Open', fullPathName='/阿里云盘Open', createTime='2023-12-29T03:44:34.952368Z', writeTime='2023-12-29T03:44:34.952368Z', accessTime='2023-12-29T03:44:34.952368Z', CloudAPI={'name': '阿里云盘Open', 'userName': '4d1769fb91ba4752ac417f77c1da8082', 'nickName': '请设置昵称？'}, isDirectory=True, isCloudRoot=True, isCloudDirectory=True, canSearch=True, canDeletePermanently=True, fs=clouddrive.CloudDriveFileSystem(client=clouddrive.CloudDriveClient(origin='http://localhost:19798', username='2339083510@qq.com', password='******', channel=<grpc._channel.Channel object at 0x1064ee350>, async_channel=Channel('localhost', 19798, ..., path=None)), path='/', refresh=False), path='/阿里云盘Open')>],
 [])
```

**在根目录下不能创建文件，因此进入 `/115` 下，继续做实验**

```python
>>> fs.chdir("/115")
```

**使用** <kbd>mkdir</kbd> **方法，可以创建空文件夹，参考** <kbd>os.mkdir</kbd>

```python
>>> fs.mkdir("test")
'/115/test'
```

<kbd>CloudDrive</kbd> 会对文件名进行一些转换，以确保即便在 <kbd>Windows</kbd> 上文件名也是有效的。一个比较彻底的办法是，名字中如果包含 `*?:/\<>|"`，会被转换成对应的全角字符 `＊？：／＼＜＞｜＂`，尾部如果有空白符号 <code> </code>(空格)`\r\n\t\v\f\xa0` 和 点号 `.` 会被移除。

[^1]: 可以用下面 2 个帮助函数，来解释这一行为：
```python
def normalize_name(
    s: str, 
    /, 
    _transtab = {c: c + 65248 for c in b'*?:/\\<>|"'}, 
) -> str:
    return s.translate(_transtab).rstrip(" \r\n\v\t\f\xa0.")

def normalize_path(s: str, /) -> str:
    return "/"[:s.startswith("/")] + "/".join(filter(None, map(normalize_name, s.split("/"))))
```

不妨创建一个名字很特殊的文件夹试一下

```python
>>> fs.mkdir("*?:\\<>| \r\n\v\t\f\xa0.")
'/115/＊？：《》｜'
```

可以看到返回的名字中，半角转全角，且尾部空白符号和 `.` 都被移除了。

```python
>>> fs.listdir()
['000阅读·乱七八糟',
 'libgen',
 'test',
 '云下载',
 '电影',
 '电视剧',
 '纪录片',
 '＊？：《》｜',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>rmdir</kbd> **方法，可以删除空文件夹，参考** <kbd>os.rmdir</kbd>

```python
>>> fs.rmdir('test')
>>> fs.rmdir('＊？：《》｜')
>>> fs.listdir()
['000阅读·乱七八糟',
 'libgen',
 '云下载',
 '电影',
 '电视剧',
 '纪录片',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>makedirs</kbd> **方法，可以创建多级的空目录，参考** <kbd>os.makedirs</kbd>

```python
>>> fs.makedirs("a/b/c/d", exist_ok=True)
'/115/a/b/c/d'
>>> fs.listdir()
['000阅读·乱七八糟',
 'a',
 'libgen',
 '云下载',
 '电影',
 '电视剧',
 '纪录片',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>removedirs</kbd> **方法，可以（自底向上地）删除多级的空目录，参考** <kbd>os.removedirs</kbd>

```python
>>> fs.removedirs("a/b/c/d")
>>> fs.listdir()
['000阅读·乱七八糟',
 'libgen',
 '云下载',
 '电影',
 '电视剧',
 '纪录片',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>upload</kbd> **方法上传文件（提示：文件只是上传到 <kbd>CloudDrive</kbd> 服务器上，至于 <kbd>CloudDrive</kbd> 什么时候上传完成，得等待）**

```python
>>> from io import BytesIO
>>> fs.upload(BytesIO(b"123"), "test.txt")
'/115/test.txt'
>>> fs.read_text("test.txt")
'123'
>>> fs.upload("file.py")
'/115/file.py'
>>> fs.listdir()
['000阅读·乱七八糟',
 'file.py',
 'libgen',
 'test.txt',
 '云下载',
 '电影',
 '电视剧',
 '纪录片',
 '👾0号：重要资源',
 '📚1号：书籍大礼包',
 '📼资料备份']
```

**使用** <kbd>remove</kbd> **方法可以删除文件，参考** <kbd>os.remove</kbd>

```python
>>> fs.remove("test.txt")
>>> fs.remove("file.py")
>>> fs.listdir()
['000阅读·乱七八糟',
 'libgen',
 '云下载',
 '电影',
 '电视剧',
 '纪录片',
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
>>> fs.attr("a")
{'id': '0/a',
 'name': 'a',
 'fullPathName': '/115/a',
 'fileType': 'File',
 'createTime': '2023-12-29T06:28:12.869507Z',
 'writeTime': '2023-12-29T06:28:12.869507Z',
 'accessTime': '2023-12-29T06:28:12.869507Z',
 'CloudAPI': {'name': '115', 'userName': '306576686', 'nickName': '306576686'},
 'isCloudFile': True,
 'hasDetailProperties': True,
 'canOfflineDownload': True,
 'path': '/115/a',
 'lastest_update': datetime.datetime(2023, 12, 29, 14, 28, 16, 470077)}
>>> fs.rename('a', 'b')
'/115/b'
>>> fs.attr("b")
{'id': '2800245724120349982',
 'name': 'b',
 'fullPathName': '/115/b',
 'fileType': 'File',
 'createTime': '2023-12-29T06:28:12.869507Z',
 'writeTime': '2023-12-29T06:28:12.869507Z',
 'accessTime': '2023-12-29T06:28:12.869507Z',
 'CloudAPI': {'name': '115', 'userName': '306576686', 'nickName': '306576686'},
 'isCloudFile': True,
 'hasDetailProperties': True,
 'canOfflineDownload': True,
 'fileHashes': {'2': 'da39a3ee5e6b4b0d3255bfef95601890afd80709'},
 'path': '/115/b',
 'lastest_update': datetime.datetime(2023, 12, 29, 14, 29, 18, 273151)}
```

**说明**：由于目前，<kbd>CloudDrive</kbd> 只在创建空文件夹后返回名字，而在上传和改名后，并不返回名字，而我目前也并不完全确定 <kbd>CloudDrive</kbd> 对于文件名**规范化**的完整逻辑，因此就直接返回用户传入的名字（而不进行半角转全角、清理后缀等）。如果你的名字里面可能有特殊符号，或者你不放心，就自行进行二次处理，参考 [^1]

**使用** <kbd>renames</kbd> **方法可以对文件或文件夹进行改名或移动，并且在移动后如果原来所在目录为空，则会删除那个目录，参考** <kbd>os.renames</kbd>

**使用** <kbd>replace</kbd> **方法可以对文件或文件夹进行改名或移动，并且如果原始路径上是文件，目标路径上也存在一个文件，则会先把目标路径上的文件删除，参考** <kbd>os.replace</kbd>

**使用** <kbd>move</kbd> **方法可以对文件或文件夹进行改名或移动，目标路径存在且是一个目录，则把文件移动到其中（但是目录中有同名的文件或文件夹，还是会报错），参考** <kbd>shutil.move</kbd>

### 3. 遍历文件系统和查找文件

#### 1. 获取当前目录下所有 .mkv 文件的 url

**第 1 种方法，使用** <kbd>iter</kbd>，返回 <kbd>clouddrive.CloudDrivePath</kbd> 对象的迭代器

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

<kbd>CloudDrive</kbd> 目前支持 `2` 种类型的任务，我分别进行了封装，大部分方法都支持异步调用 (`async_=True`)

- <kbd>clouddrive.CloudDriveDownloadTaskList</kbd> 封装了 `下载` 的任务列表。
- <kbd>clouddrive.CloudDriveUploadTaskList</kbd> 封装了 `上传` 的任务列表。

```python
from clouddrive import CloudDriveClient

client = CloudDriveClient("http://localhost:19798", "test", "test@test")

# 获取各种任务列表
download_tasklist = client.download_tasklist
upload_tasklist = client.upload_tasklist

# 或者自己创建实例

# 创建 下载 任务列表实例
from clouddrive import CloudDriveDownloadTaskList
download_tasklist = CloudDriveDownloadTaskList(client)

# 创建 上传 任务列表实例
from clouddrive import CloudDriveUploadTaskList
upload_tasklist = CloudDriveUploadTaskList(client)
```

## 文档

> 正在编写中
