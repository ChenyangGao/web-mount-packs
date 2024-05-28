#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["alist_update_115_cookie"]

from json import dumps, loads

from alist import AlistClient


def alist_update_115_cookies(
    client: AlistClient, 
    cookie: str, 
    only_not_work: bool = False, 
):
    """更新 alist 中有关 115 的存储的 cookies
    """
    storages = client.admin_storage_list()["data"]["content"]
    for storage in storages:
        if storage["driver"] in ("115 Cloud", "115 Share"):
            if only_not_work and storage["status"] == "work":
                continue
            addition = loads(storage["addition"])
            addition["cookie"] = cookie
            storage["addition"] = dumps(addition)
            client.admin_storage_update(storage)

