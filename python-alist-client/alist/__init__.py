#!/usr/bin/env python3
# encoding: utf-8

"""Python AList web api wrapper.

This is a web api wrapper works with the running "alist" server, and provide some methods, 
which refer to `os`, `posixpath`, `pathlib.Path` and `shutil` modules.

- AList web api official documentation: https://alist.nn.ci/guide/api/
- AList web api online tool: https://alist-v3.apifox.cn
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 13)

from warnings import filterwarnings

filterwarnings("ignore", category=DeprecationWarning)
filterwarnings("ignore", category=SyntaxWarning)

__FALSE = False
if __FALSE:
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

# TODO: 所有类和函数都要有文档
# TODO: 所有类和函数都要有单元测试
# TODO: 上传下载都支持进度条，下载支持多线程（返回 Future）
# TODO: task 的 Future 封装，支持进度条
# TODO: storage list 封装，支持批量操作，提供一些简化配置的方法
