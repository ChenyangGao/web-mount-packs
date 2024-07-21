#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "alist_update_115_cookie", "alist_batch_add_115_share_links", 
    "alist_batch_download_file_or_make_strm", 
]

from asyncio import run, to_thread, Semaphore, TaskGroup
from collections.abc import Callable, Container, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, aclosing
from mimetypes import types_map, init
from os import makedirs
from os.path import dirname, exists, join as joinpath, normpath, splitext
from json import dumps, loads

from alist import AlistClient, AlistPath
from httpx import TimeoutException


init()


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
            addition["cookies"] = cookies
            storage["addition"] = dumps(addition)
            client.admin_storage_update(storage)


def alist_batch_add_115_share_links(
    alist_client: AlistClient, 
    share_links: str | Iterable[str], 
    cookies: str, 
    mount_root: str = "/", 
):
    """批量添加 115 分享到 alist

    :param alist_client: alist 客户端对象，例如 AlistClient(origin="http://localhost:5244", username="admin", password="123456")
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
        print(alist_client.admin_storage_create(payload))
        print(payload)


def alist_batch_download_file_or_make_strm(
    alist_client: None | AlistClient = None, 
    alist_token: str = "", 
    alist_base_dir: str = "/", 
    output_dir: str = "", 
    strm_file_predicate: Container[str] | Callable[[AlistPath], bool] = {
        k for k, v in types_map.items() if v.startswith("video/") # type: ignore
    }, 
    download_file_predicate: Container[str] | Callable[[AlistPath], bool] = (
        {k for k, v in types_map.items() if v.startswith(("image/", "text/"))} | # type: ignore
        {".nfo", ".ass", ".idx", ".sbv", ".smi", ".srt", ".sub", ".ssa", ".vtt"}
    ), 
    overwrite: bool = False, 
    max_workers: int = 5, 
    logger = None, 
    async_: bool = False, 
):
    """批量导出 strm 和下载文件

    :param alist_client: alist 客户端对象，例如 AlistClient(origin="http://localhost:5244", username="admin", password="123456")
    :param alist_token: Alist 签名 token，默认为空
    :param alist_base_dir: 需要同步的 Alist 的目录，默认为 "/"
    :param output_dir: 文件输出目录，默认为当前工作目录
    :param strm_file_predicate: 判断是否要下载为 strm，如果为 Callable，则调用以判断，如果为 Container，则用扩展名判断
    :param download_file_predicate: 判断是否要下载为 文件，如果为 Callable，则调用以判断，如果为 Container，则用扩展名判断
    :param overwrite: 本地路径存在同名文件时是否重新生成/下载该文件，默认为 False
    :param max_workers: 最大并发数
    :param logger: 日志实例，用于输出信息
    :param async_: 是否异步执行
    """
    if alist_client is None:
        alist_client = AlistClient()
    if callable(strm_file_predicate):
        strm_predicate = strm_file_predicate
    else:
        strm_predicate = lambda path: path.suffix in strm_file_predicate
    if callable(download_file_predicate):
        down_predicate = download_file_predicate
    else:
        down_predicate = lambda path: path.suffix in download_file_predicate
    if async_:
        try:
            from aiofile import async_open
        except ImportError:
            from sys import executable
            from subprocess import run
            run([executable, "-m", "pip", "install", "-U", "aiofile"], check=True)
            from aiofile import async_open
        async_semaphore = Semaphore(max_workers)
        async def async_work(path: AlistPath):
            local_path = joinpath(output_dir, normpath(path.relative_to(alist_base_dir)))
            try:
                if not (use_strm := strm_predicate(path)) or down_predicate(path):
                    return
                if use_strm:
                    local_path = splitext(local_path)[0] + ".strm"
                if exists(local_path) and not overwrite:
                    logger and logger.info(f"跳过文件：{local_path!r}")
                    return
                url = path.get_url(token=alist_token)
                if dir_ := dirname(local_path):
                    await to_thread(makedirs, dir_, exist_ok=True)
                if use_strm:
                    async with async_open(local_path, mode="w", encoding="utf-8") as file:
                        await file.write(url)
                    logger and logger.info(f"创建文件：{local_path!r}")
                else:
                    async with async_semaphore:
                        async with (
                            aclosing(await alist_client.request(url, "GET", parse=None, async_=True)) as resp, 
                            async_open(local_path, mode="wb") as file, 
                        ):
                            write = file.write
                            async for chunk in resp.aiter_bytes(1 << 16):
                                await write(chunk)
                    logger and logger.info(f"下载文件：{local_path!r}")
            except:
                logger and logger.exception(f"下载失败: {local_path!r}")
                raise
        async def request():
            async with TaskGroup() as tg:
                create_task = tg.create_task
                async for path in alist_client.fs.iter(
                    alist_base_dir, 
                    max_depth=-1, 
                    predicate=lambda path: path.is_file(), 
                    async_=True, 
                ):
                    create_task(async_work(path))
        return request()
    else:
        def work(path: AlistPath):
            local_path = joinpath(output_dir, normpath(path.relative_to(alist_base_dir)))
            try:
                if not (use_strm := strm_predicate(path)) or down_predicate(path):
                    return
                if use_strm:
                    local_path = splitext(local_path)[0] + ".strm"
                if exists(local_path) and not overwrite:
                    logger and logger.info(f"跳过文件：{local_path!r}")
                    return
                url = path.get_url(token=alist_token)
                if dir_ := dirname(local_path):
                    makedirs(dir_, exist_ok=True)
                if use_strm:
                    open(local_path, mode="w", encoding="utf-8").write(url)
                    logger and logger.info(f"创建文件：{local_path!r}")
                else:
                    with (
                        closing(alist_client.request(url, "GET", parse=None)) as resp, 
                        open(local_path, mode="wb") as file, 
                    ):
                        write = file.write
                        for chunk in resp.iter_bytes(1 << 16):
                            write(chunk)
                    logger and logger.info(f"下载文件：{local_path!r}")
            except:
                logger and logger.exception(f"下载失败: {local_path!r}")
                raise
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            submit = executor.submit
            for path in alist_client.fs.iter(
                alist_base_dir, 
                max_depth=-1, 
                predicate=lambda path: path.is_file(), 
            ):
                submit(work, path)

