#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 9, 7)

from warnings import filterwarnings

filterwarnings("ignore", category=DeprecationWarning)
filterwarnings("ignore", category=SyntaxWarning)

AVAILABLE_APPS = (
    "web", "ios", "115ios", "android", "115android", "115ipad", "tv", "qandroid", 
    "windows", "mac", "linux", "wechatmini", "alipaymini", 
)

if False:
    from .component import *

def __getattr__(attr):
    from importlib import import_module

    component = import_module('.component', package=__package__)
    all = {"__all__": component.__all__}
    for name in component.__all__:
        all[name] = getattr(component, name)
    globals().update(all)
    del globals()["__getattr__"]
    return getattr(component, attr)

# TODO upload_tree 多线程和进度条，并且为每一个上传返回一个 task，可重试
# TODO 能及时处理文件已不存在
# TODO 为各个fs接口添加额外的请求参数
# TODO 115中多个文件可以在同一目录下同名，如何处理
# TODO 提供一个新的上传函数，上传如果失败，因为名字问题，则尝试用uuid名字，上传成功后，再进行改名，如果成功，删除原来的文件，不成功，则删掉上传的文件（如果上传成功了的话）
# TODO 如果压缩包尚未解压，则使用 zipfile 之类的模块，去模拟文件系统
# TODO: 为上传进度进行封装，创建 UploadTask 类
