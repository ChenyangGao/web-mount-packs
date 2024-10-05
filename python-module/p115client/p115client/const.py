#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all = ["AVAILABLE_APPS", "APP_TO_SSOENT", "CLIENT_API_MAP"]

from typing import Final


# NOTE: 目前可用的登录设备
AVAILABLE_APPS: Final = (
    "web", "ios", "115ios", "android", "115android", "115ipad", "tv", "qandroid", 
    "windows", "mac", "linux", "wechatmini", "alipaymini", "harmony", 
)
# NOTE: 目前已知的登录设备和对应的 ssoent
APP_TO_SSOENT: Final = {
    "web": "A1", 
    "desktop": "A1", 
    "ios": "D1", 
    "115ios": "D3", 
    "android": "F1", 
    "115android": "F3", 
    "ipad": "H1", 
    "115ipad": "H3", 
    "tv": "I1", 
    "qandroid": "M1", 
    "qios": "N1", 
    "windows": "P1", 
    "mac": "P2", 
    "linux": "P3", 
    "wechatmini": "R1", 
    "alipaymini": "R2", 
    "harmony": "S1", 
}
# NOTE: 所有已封装的 115 接口以及对应的方法名
CLIENT_API_MAP: Final[dict[str, str]] = {}

