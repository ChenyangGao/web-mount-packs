# 115 网盘基于数据库的列表服务.

## 安装

你可以通过 [pypi](https://pypi.org/project/p115cipher/) 安装

```console
pip install -U p115servedb
```

## 用法

### 命令行使用

#### 开启 webdav

```console
$ servedb dav -f 115-dbfile.db
```

或者

```console
$ servedb-dav -f 115-dbfile.db
```

#### 开启 fuse

```console
$ servedb fuse -f 115-dbfile.db
```

或者

```console
$ servedb-fuse -f 115-dbfile.db
```
