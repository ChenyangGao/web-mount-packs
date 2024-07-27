#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "alist_update_115_cookie", "alist_batch_add_115_share_links", 
    "alist_batch_download", "alist_batch_strm_download", 
]

import logging

from mimetypes import init
init()
from mimetypes import types_map

from asyncio import run, to_thread, Semaphore, TaskGroup
from collections import deque
from collections.abc import Callable, Container, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, aclosing
from functools import partial
from json import dumps, loads
from os import makedirs, remove, scandir, stat
from os.path import abspath, dirname, join as joinpath, normpath, splitext
from shutil import rmtree
from typing import cast

from alist import AlistClient, AlistPath
from httpx import TimeoutException


logging.basicConfig(format="[\x1b[1m%(asctime)s\x1b[0m] (\x1b[1;36m%(levelname)s\x1b[0m) \x1b[1;34m%(name)s\x1b[0m @ \x1b[0m\x1b[1;3;35m%(funcName)s\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s")
logger = logging.getLogger("alist")
logger.setLevel(logging.DEBUG)


def alist_update_115_cookies(
    client: AlistClient, 
    cookies: str, 
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
            addition["cookie"] = cookies
            storage["addition"] = dumps(addition)
            client.admin_storage_update(storage)


def alist_batch_add_115_share_links(
    client: AlistClient, 
    share_links: str | Iterable[str], 
    cookies: str, 
    mount_root: str = "/", 
):
    """批量添加 115 分享到 alist

    :param client: alist 客户端对象，例如 AlistClient(origin="http://localhost:5244", username="admin", password="123456")
    :param share_links: 一堆分享链接
    :param cookies: 115 的 cookies，格式为 'UID=...; CID=...; SEID=...'
    :param mount_root: 挂载到的根路径，默认为 "/"
    """
    try:
        from p115 import P115ShareFileSystem
        from retrytools import retry
    except ImportError:
        from sys import executable
        from subprocess import run
        run([executable, "-m", "pip", "install", "-U", "python-115", "python-retrytools"], check=True)
        from p115 import P115ShareFileSystem
        from retrytools import retry
    if isinstance(share_links, str):
        share_links = (share_links,)
    mount_root = mount_root.strip("/")
    if mount_root:
        mount_root = "/" + mount_root
    for link in share_links:
        fs = P115ShareFileSystem("", link)
        get_files = retry(fs.fs_files, retry_times=5, suppress_exceptions=TimeoutError)
        try:
            files: dict = get_files({"limit": 1}) # type: ignore
        except Exception as e:
            print(f"获取链接信息失败：{link!r}，错误原因：{type(e).__qualname__}: {e}")
            continue
        sharedata = files["data"]
        shareinfo = sharedata["shareinfo"]
        if shareinfo["forbid_reason"]:
            print(f"跳过失效链接：{shareinfo}")
            continue
        if sharedata["count"] >= 2:
            name = shareinfo["share_title"]
            root_id = ""
        else:
            item = sharedata["list"][0]
            name = item["n"]
            root_id = str(item["cid"])
        payload = {
            "mount_path": f"{mount_root}/{name}", 
            "order": 0, 
            "remark": "", 
            "cache_expiration": 30, 
            "web_proxy": False, 
            "webdav_policy": "302_redirect", 
            "down_proxy_url": "", 
            "extract_folder": "", 
            "enable_sign": False, 
            "driver": "115 Share", 
            "addition": dumps({
                'cookies': cookies,
                'qrcode_token': "", 
                'qrcode_source': "web", 
                'page_size': 20, 
                'limit_rate': None, 
                'share_code': fs.share_code, 
                'receive_code': fs.receive_code, 
                'root_folder_id': root_id, 
            })
        }
        print("-" * 40)
        print(client.admin_storage_create(payload))
        print(payload)


def alist_batch_download(
    client: None | AlistClient = None, 
    remote_dir: str = "/", 
    local_dir: str = "", 
    predicate: None | Container[str] | Callable[[AlistPath], bool] = None, 
    strm_predicate: None | Container[str] | Callable[[AlistPath], bool] = None,  
    resume: bool = True, 
    max_workers: int = 5, 
    logger = logger, 
    password: str = "", 
    sync: bool = False, 
    async_: bool = False, 
):
    """批量下载文件

    :param client: alist 客户端对象，例如 AlistClient(origin="http://localhost:5244", username="admin", password="123456")
    :param remote_dir: 需要同步的 Alist 的目录，默认为 "/"
    :param local_dir: 文件输出目录，默认为当前工作目录
    :param predicate: 断言以筛选
        1) 如果为 None，则不筛选 
        2) 如果为 Callable，则调用以筛选
        3) 如果为 Container，则用扩展名判断，不在此中的都被过滤
    :param strm_predicate: 断言以筛选，选择某些文件生成为 strm（优先级高于 predicate）
        1) 如果为 None，则无 strm
        2) 如果为 Callable，则调用以筛选
        3) 如果为 Container，则用扩展名判断，不在此中的都被过滤
    :param resume: 是否断点续传，默认为 True，如果为 False，那么总是覆盖
    :param max_workers: 最大并发数
    :param logger: 日志实例，用于输出信息，如果为 None，则不输出
    :param password: `remote_dir` 的访问密码
    :param sync: 是否同步目录结构，如果为 True，则会删除 `local_dir` 下所有不由本批下载的文件和文件夹
    :param async_: 是否异步执行
    """
    local_dir = abspath(local_dir)
    if client is None:
        client = AlistClient()
    if predicate is not None and not callable(predicate):
        predicate = cast(Callable[[AlistPath], bool], lambda path, *, _pred=predicate.__contains__: path.is_file() and _pred(path.suffix))
    if strm_predicate is None:
        pass
    elif callable(strm_predicate):
        strm_predicate = cast(Callable[[AlistPath], bool], lambda path, *, _pred=strm_predicate: path.is_file() and _pred(path.suffix))
    else:
        strm_predicate = cast(Callable[[AlistPath], bool], lambda path, *, _pred=strm_predicate.__contains__: path.is_file() and _pred(path.suffix))
    full_predicate: None | Callable[[AlistPath], bool]
    if predicate is None:
        full_predicate = strm_predicate
    elif strm_predicate is None:
        full_predicate = predicate
    else:
        full_predicate = lambda path: strm_predicate(path) or predicate(path)
    if sync:
        seen: set[str] = set()
        seen_add = seen.add
        local_dir_len = len(local_dir) + 1
    if async_:
        try:
            from aiofile import async_open
        except ImportError:
            from sys import executable
            from subprocess import run
            run([executable, "-m", "pip", "install", "-U", "aiofile"], check=True)
            from aiofile import async_open
        async_semaphore = Semaphore(max_workers)
        async def alist_batch_download_async(path: AlistPath, local_path: str):
            use_strm = strm_predicate is not None and strm_predicate(path)
            try:
                if use_strm:
                    local_path = splitext(local_path)[0] + ".strm"
                if sync:
                    seen_add(local_path[local_dir_len:])
                url = path.get_url()
                skipsize = 0
                if resume:
                    if use_strm:
                        try:
                            if open(local_path, encoding="utf-8").read() == url:
                                logger and logger.info(f"\x1b[1;33mSKIPPED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                                return
                        except FileNotFoundError:
                            pass
                    else:
                        try:
                            file_stat = stat(local_path)
                        except FileNotFoundError:
                            pass
                        else:
                            filesize = path["size"]
                            if path["ctime"] < file_stat.st_ctime:
                                if filesize == file_stat.st_size:
                                    logger and logger.info(f"\x1b[1;33mSKIPPED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                                    return
                                elif filesize < file_stat.st_size:
                                    skipsize = filesize
                if use_strm:
                    async with async_open(local_path, mode="w", encoding="utf-8") as file:
                        await file.write(url)
                    logger and logger.info(f"\x1b[1;2;32mCREATED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                else:
                    headers = {"Range": f"bytes={skipsize}-"}
                    async with async_semaphore:
                        async with (
                            aclosing(await client.request(url, "GET", headers=headers, parse=None, async_=True)) as resp, 
                            async_open(local_path, mode="ab" if skipsize else "wb") as file, 
                        ):
                            if (
                                resp.headers["Content-Type"] == "application/json; charset=utf-8" 
                                and resp.headers.get("Accept-Range") != "bytes"
                            ):
                                resp.read()
                                raise OSError(resp.json())
                            write = file.write
                            async for chunk in resp.aiter_bytes(1 << 16):
                                await write(chunk)
                    logger and logger.info(f"\x1b[1;32mDOWNLOADED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
            except:
                logger and logger.exception(f"\x1b[1;31mFAILED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
        async def request():
            async with TaskGroup() as tg:
                create_task = tg.create_task
                dir_ = "."
                async for path in client.fs.iter(
                    remote_dir, 
                    topdown=None, 
                    max_depth=-1, 
                    predicate=full_predicate, 
                    async_=True, 
                ):
                    local_path = joinpath(local_dir, normpath(path.relative_to(remote_dir)))
                    if dir_ != (dir_ := dirname(local_path)):
                        await to_thread(makedirs, dir_, exist_ok=True)
                        if sync:    
                            dir0 = dir_
                            while dir0:
                                seen_add(dir0)
                                dir0 = dirname(dir0)
                    create_task(alist_batch_download_async(path, local_path))
        return request()
    else:
        def alist_batch_download_sync(path: AlistPath, local_path: str):
            use_strm = strm_predicate is not None and strm_predicate(path)
            try:
                if use_strm:
                    local_path = splitext(local_path)[0] + ".strm"
                if sync:
                    seen_add(local_path[local_dir_len:])
                url = path.get_url()
                skipsize = 0
                if resume:
                    if use_strm:
                        try:
                            if open(local_path, encoding="utf-8").read() == url:
                                logger and logger.info(f"\x1b[1;33mSKIPPED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                                return
                        except FileNotFoundError:
                            pass
                    else:
                        try:
                            file_stat = stat(local_path)
                        except FileNotFoundError:
                            pass
                        else:
                            filesize = path["size"]
                            if path["ctime"] < file_stat.st_ctime:
                                if filesize == file_stat.st_size:
                                    logger and logger.info(f"\x1b[1;33mSKIPPED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                                    return
                                elif filesize < file_stat.st_size:
                                    skipsize = filesize
                if use_strm:
                    open(local_path, mode="w", encoding="utf-8").write(url)
                    logger and logger.info(f"\x1b[1;2;32mCREATED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                else:
                    headers = {"Range": f"bytes={skipsize}-"}
                    with (
                        closing(client.request(url, "GET", headers=headers, parse=None)) as resp, 
                        open(local_path, mode="ab" if skipsize else "wb") as file, 
                    ):
                        if (
                            resp.headers["Content-Type"] == "application/json; charset=utf-8" 
                            and resp.headers.get("Accept-Range") != "bytes"
                        ):
                            resp.read()
                            raise OSError(resp.json())
                        write = file.write
                        for chunk in resp.iter_bytes(1 << 16):
                            write(chunk)
                    logger and logger.info(f"\x1b[1;32mDOWNLOADED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
            except:
                logger and logger.exception(f"\x1b[1;31mFAILED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            with executor:
                submit = executor.submit
                dir_ = ""
                for path in client.fs.iter(
                    remote_dir, 
                    topdown=None, 
                    max_depth=-1, 
                    predicate=full_predicate, 
                ):
                    local_relpath = normpath(path.relative_to(remote_dir))
                    local_path = joinpath(local_dir, local_relpath)
                    if dir_ != (dir_ := dirname(local_relpath)):
                        makedirs(joinpath(local_dir, dir_), exist_ok=True)
                        if sync:    
                            dir0 = dir_
                            while dir0:
                                seen_add(dir0)
                                dir0 = dirname(dir0)
                    submit(alist_batch_download_sync, path, local_path)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if sync:
            dq = deque((local_dir,))
            push = dq.append
            pop = dq.pop
            while dq:
                dir_ = pop()
                for entry in scandir(dir_):
                    path = entry.path[local_dir_len:]
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if path in seen:
                                push(entry.path)
                            else:
                                rmtree(entry)
                        else:
                            if path not in seen:
                                remove(entry)
                    except OSError:
                        pass


alist_batch_strm_download = partial(
    alist_batch_download, 
    predicate=(
        {k for k, v in types_map.items() if v.startswith(("image/", "text/"))} | # type: ignore
        {".nfo", ".ass", ".idx", ".sbv", ".smi", ".srt", ".sub", ".ssa", ".txt", ".vtt"}
    ), 
    strm_predicate={
        k for k, v in types_map.items() if v.startswith("video/") # type: ignore
    }
)

# TODO: 再实现一个 alist_batch_upload
