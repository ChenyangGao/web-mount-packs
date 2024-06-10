#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 9, 5)

AVAILABLE_APPS = (
    "web", "ios", "115ios", "android", "115android", "115ipad", "tv", "qandroid", 
    "windows", "mac", "linux", "wechatmini", "alipaymini", 
)

def __getattr__(attr):
    from importlib import import_module

    component = import_module('.component', package=__package__)
    all = {"__all__": component.__all__}
    for name in component.__all__:
        all[name] = getattr(component, name)
    globals().update(all)
    del globals()["__getattr__"]
    return getattr(component, attr)

