#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "alist_update_115_cookies", "alist_batch_add_115_share_links", 
    "alist_batch_download", "alist_batch_strm_download", 
]

import logging

from mimetypes import init
init()
from mimetypes import types_map

from asyncio import run, to_thread, Semaphore, TaskGroup
from collections import deque
from collections.abc import Callable, Container, Coroutine, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, aclosing
from functools import partial
from inspect import isawaitable
from os import makedirs, remove, scandir, stat
from os.path import abspath, dirname, join as joinpath, normpath, sep, splitext
from re import compile as re_compile
from shutil import rmtree
from typing import cast, overload, Any, Literal

from alist.component import AlistClient, AlistPath
from orjson import dumps, loads
from httpx import TimeoutException
from retrytools import retry


CRE_USERID_search = re_compile(r"(?<=\bUID=)[0-9]+").search
logging.basicConfig(format="[\x1b[1m%(asctime)s\x1b[0m] (\x1b[1;36m%(levelname)s\x1b[0m) \x1b[1;34m%(name)s\x1b[0m"
                           " @ \x1b[0m\x1b[1;3;35m%(funcName)s\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s")
logger = logging.getLogger("alist")
logger.setLevel(logging.DEBUG)


def storage_of(
    client: str | AlistClient, 
    path: str, 
) -> None | dict:
    """从 alist 获取某个路径所属的存储
    """
    if isinstance(client, str):
        client = AlistClient.from_auth(client)
    path = path.rstrip("/")
    resp = client.admin_storage_list()
    storages = resp["data"]["content"]
    selected_storage = None
    for storage in storages:
        if storage["mount_path"] == path:
            return storage
        elif path.startswith(storage["mount_path"] + "/"):
            if not selected_storage or len(selected_storage["mount_path"]) < storage["mount_path"]:
                selected_storage = storage
    return selected_storage


def alist_update_115_cookies(
    client: str | AlistClient, 
    cookies: str, 
    only_not_work: bool = False, 
):
    """更新 alist 中有关 115 的存储的 cookies
    """
    m = CRE_USERID_search(cookies)
    if m is None:
        raise ValueError(f"invalid cookies: {cookies!r}")
    user_id = m[0]
    if isinstance(client, str):
        client = AlistClient.from_auth(client)
    storages = client.admin_storage_list()["data"]["content"]
    for storage in storages:
        driver = storage["driver"]
        if driver in ("115 Cloud", "115 Share"):
            if only_not_work and storage["status"] == "work":
                continue
            addition = loads(storage["addition"])
            if driver == "115 Cloud":
                cookies_old = addition.get("cookie", "")
                m = CRE_USERID_search(cookies_old)
                if m is not None and m[0] != user_id:
                    continue
            addition["cookie"] = cookies
            storage["addition"] = dumps(addition).decode("utf-8")
            storage.pop("status", None)
            client.admin_storage_update(storage)
            logger.debug("update 115 cookies: %r", storage)


def alist_batch_add_115_share_links(
    client: str | AlistClient, 
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
    except ImportError:
        from sys import executable
        from subprocess import run
        run([executable, "-m", "pip", "install", "-U", "python-115"], check=True)
        from p115 import P115ShareFileSystem 
    if isinstance(client, str):
        client = AlistClient.from_auth(client)
    if isinstance(share_links, str):
        share_links = (share_links,)
    mount_root = mount_root.strip("/")
    if mount_root:
        mount_root = "/" + mount_root
    for link in share_links:
        fs = P115ShareFileSystem("", link)
        get_files = retry(
            fs.fs_files, # type: ignore
            retry_times=5, 
            suppress_exceptions=TimeoutError, 
        )
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
            }).decode("utf-8")
        }
        print("-" * 40)
        print(client.admin_storage_create(payload))
        print(payload)


@overload
def alist_batch_download(
    client: None | str | AlistClient = None, 
    remote_dir: str = "/", 
    local_dir: str = "", 
    predicate: None | Literal[False] | Container[str] | Callable[[AlistPath], bool] = None, 
    strm_predicate: None | Container[str] | Callable[[AlistPath], bool] = None,  
    custom_url: None | Callable[[AlistPath], str] = None, 
    password: str = "", 
    refresh: bool = False, 
    resume: bool = True, 
    max_workers: int = 1, 
    logger = logger, 
    sync: bool = False, 
    *, 
    async_: Literal[False] = False, 
) -> dict[str, bool]:
    ...
@overload
def alist_batch_download(
    client: None | str | AlistClient = None, 
    remote_dir: str = "/", 
    local_dir: str = "", 
    predicate: None | Literal[False] | Container[str] | Callable[[AlistPath], bool] = None, 
    strm_predicate: None | Container[str] | Callable[[AlistPath], bool] = None,  
    custom_url: None | Callable[[AlistPath], str] = None, 
    password: str = "", 
    refresh: bool = False, 
    resume: bool = True, 
    max_workers: int = 1, 
    logger = logger, 
    sync: bool = False, 
    *, 
    async_: Literal[True], 
) -> Coroutine[Any, Any, dict[str, bool]]:
    ...
def alist_batch_download(
    client: None | str | AlistClient = None, 
    remote_dir: str = "/", 
    local_dir: str = "", 
    predicate: None | Literal[False] | Container[str] | Callable[[AlistPath], bool] = None, 
    strm_predicate: None | Container[str] | Callable[[AlistPath], bool] = None,  
    custom_url: None | Callable[[AlistPath], str] = None, 
    password: str = "", 
    refresh: bool = False, 
    resume: bool = True, 
    max_workers: int = 1, 
    logger = logger, 
    sync: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
) -> dict[str, bool] | Coroutine[Any, Any, dict[str, bool]]:
    """批量下载文件

    :param client: alist 客户端对象，例如 AlistClient(origin="http://localhost:5244", username="admin", password="123456")
    :param remote_dir: 需要同步的 Alist 的目录，默认为 "/"
    :param local_dir: 文件输出目录，默认为当前工作目录
    :param predicate: 断言以筛选
        1) 如果为 False，则无文件会被下载
        2) 如果为 None，则全部文件都会被下载
        3) 如果为 Callable，则调用以筛选
        4) 如果为 Container，则用扩展名（要用小写字母，带前缀句点，例如 .mkv）判断，不在此中的都被过滤
    :param strm_predicate: 断言以筛选，选择某些文件生成为 strm（优先级高于 predicate）
        1) 如果为 None，则无 strm
        2) 如果为 Callable，则调用以筛选
        3) 如果为 Container，则用扩展名（要用小写字母，带前缀句点，例如 .mkv）判断，不在此中的都被过滤
    :param custom_url: 生成文件的 url，默认为 None，表示使用 alist 提供的 url
    :param password: `remote_dir` 的访问密码
    :param refresh: 是否刷新目录，刷新会更新 alist 上相应目录的缓存
    :param resume: 是否断点续传，默认为 True，如果为 False，那么总是覆盖
    :param max_workers: 下载（而非罗列目录）的最大并发数
    :param logger: 日志实例，用于输出信息，如果为 None，则不输出
    :param sync: 是否同步目录结构，如果为 True，则会在收尾时一起删除 `local_dir` 下所有不由本批下载的文件和目录
    :param async_: 是否异步执行

    :return: 所有涉及到的文件和目录和操作的成功与否的字典
    """
    if client is None:
        client = AlistClient()
    elif isinstance(client, str):
        client = AlistClient.from_auth(client)
    remote_dir = client.fs.abspath(remote_dir)
    local_dir = abspath(local_dir)
    if predicate is False or predicate is None:
        pass
    elif not callable(predicate):
        predicate = cast(Callable[[AlistPath], bool], lambda path, *, _pred=predicate.__contains__: path.is_file() and _pred(path.suffix.lower()))
    if strm_predicate is None:
        pass
    elif callable(strm_predicate):
        strm_predicate = cast(Callable[[AlistPath], bool], lambda path, *, _pred=strm_predicate: path.is_file() and _pred(path.suffix.lower()))
    else:
        strm_predicate = cast(Callable[[AlistPath], bool], lambda path, *, _pred=strm_predicate.__contains__: path.is_file() and _pred(path.suffix.lower()))
    full_predicate: None | Callable[[AlistPath], bool]
    if predicate is False:
        if strm_predicate is None:
            raise ValueError("no files will be downloaded")
        full_predicate = strm_predicate
    elif predicate is None:
        full_predicate = None
    elif strm_predicate is None:
        full_predicate = predicate
    else:
        full_predicate = lambda path: strm_predicate(path) or predicate(path)
    def onerror(e):
        if isinstance(e, (FileNotFoundError, NotADirectoryError)):
            logger and logger.exception("failed to iterdir: %s", e)
        else:
            raise e
    if sync:
        seen: dict[str, bool] = {}
        local_local_reldirlen = len(local_dir) + 1
        def clean():
            dq = deque((local_dir,))
            push = dq.append
            pop = dq.pop
            while dq:
                local_reldir = pop()
                for entry in scandir(local_reldir):
                    path = entry.path[local_local_reldirlen:]
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if path + sep in seen:
                                push(entry.path)
                            else:
                                rmtree(entry)
                        else:
                            if path not in seen:
                                remove(entry)
                    except OSError:
                        pass
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
                    seen[local_path[local_local_reldirlen:]] = False
                if custom_url is None:
                    url = path.get_url()
                else:
                    url = custom_url(path)
                    if isawaitable(url):
                        url = await url
                    if not isinstance(url, str):
                        raise ValueError(f"can't make url, got {url!r}")
                skipsize = 0
                if resume:
                    if use_strm:
                        try:
                            async with async_open(local_path, encoding="utf-8") as f:
                                if (await f.read()) == url:
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
                        async with aclosing(await client.request(url, "GET", headers=headers, parse=None, async_=True)) as resp:
                            if (
                                resp.headers["Content-Type"] == "application/json; charset=utf-8" 
                                and resp.headers.get("Accept-Range") != "bytes"
                            ):
                                resp.read()
                                raise OSError(resp.json())
                            async with async_open(local_path, mode="ab" if skipsize else "wb") as file:
                                write = file.write
                                async for chunk in resp.aiter_bytes(1 << 16):
                                    await write(chunk)
                    logger and logger.info(f"\x1b[1;32mDOWNLOADED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                if sync:
                    seen[local_path[local_local_reldirlen:]] = True
            except:
                logger and logger.exception(f"\x1b[1;31mFAILED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
        async def request():
            async with TaskGroup() as tg:
                create_task = tg.create_task
                local_reldir = "."
                async for path in client.fs.iter(
                    remote_dir, 
                    max_depth=-1, 
                    predicate=full_predicate, 
                    password=password, 
                    refresh=refresh, 
                    onerror=onerror, 
                    async_=True, 
                ):
                    local_relpath = normpath(path.relative_to(remote_dir))
                    if local_reldir != (local_reldir := dirname(local_relpath)):
                        dir_ = joinpath(local_dir, local_reldir)
                        try:
                            await to_thread(makedirs, dir_, exist_ok=True)
                        except FileExistsError:
                            await to_thread(remove, dir_)
                            await to_thread(makedirs, dir_)
                        if sync:    
                            dir0 = local_reldir
                            while dir0:
                                seen[dir0 + sep] = True
                                dir0 = dirname(dir0)
                    create_task(alist_batch_download_async(path, joinpath(local_dir, local_relpath)))
            if sync:
                await to_thread(clean)
        return request()
    else:
        def alist_batch_download_sync(path: AlistPath, local_path: str):
            use_strm = strm_predicate is not None and strm_predicate(path)
            try:
                if use_strm:
                    local_path = splitext(local_path)[0] + ".strm"
                if sync:
                    seen[local_path[local_local_reldirlen:]] = False
                if custom_url is None:
                    url = path.get_url()
                else:
                    url = custom_url(path)
                    if not isinstance(url, str):
                        raise ValueError(f"can't make url, got {url!r}")
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
                    with closing(client.request(url, "GET", headers=headers, parse=None)) as resp:
                        if (
                            resp.headers["Content-Type"] == "application/json; charset=utf-8" 
                            and resp.headers.get("Accept-Range") != "bytes"
                        ):
                            resp.read()
                            raise OSError(resp.json())
                        with open(local_path, mode="ab" if skipsize else "wb") as file:
                            write = file.write
                            for chunk in resp.iter_bytes(1 << 16):
                                write(chunk)
                    logger and logger.info(f"\x1b[1;32mDOWNLOADED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
                if sync:
                    seen[local_path[local_local_reldirlen:]] = True
            except:
                logger and logger.exception(f"\x1b[1;31mFAILED\x1b[0m: \x1b[4;34m{local_path!r}\x1b[0m")
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            with executor:
                submit = executor.submit
                local_reldir = ""
                for path in client.fs.iter(
                    remote_dir, 
                    max_depth=-1, 
                    predicate=full_predicate, 
                    password=password, 
                    refresh=refresh, 
                    onerror=onerror, 
                ):
                    local_relpath = normpath(path.relative_to(remote_dir))
                    if local_reldir != (local_reldir := dirname(local_relpath)):
                        dir_ = joinpath(local_dir, local_reldir)
                        try:
                            makedirs(dir_, exist_ok=True)
                        except FileExistsError:
                            remove(dir_)
                            makedirs(dir_, exist_ok=True)
                        if sync:    
                            dir0 = local_reldir
                            while dir0:
                                seen[dir0 + sep] = True
                                dir0 = dirname(dir0)
                    submit(alist_batch_download_sync, path, joinpath(local_dir, local_relpath))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if sync:
            clean()
        return seen


alist_batch_strm_download = partial(
    alist_batch_download, 
    predicate=(
        {
            ".avif", ".bmp", ".gif", ".heic", ".heif", ".ico", ".jpeg", ".jpg", ".png", ".psd", ".raw", 
            ".svg", ".tif", ".tiff", ".webp", 
        } | {
            k for k, v in types_map.items() if v.startswith("image/")
        } | {
            ".nfo", ".ass", ".idx", ".sbv", ".smi", ".srt", ".sub", ".ssa", ".txt", ".vtt", 
        }
    ), 
    strm_predicate=(
        {
            ".3g2", ".3gp", ".asf", ".avi", ".divx", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", 
            ".mpg", ".mts", ".ogg", ".ogv", ".rm", ".rmvb", ".swf", ".ts", ".vob", ".webm", ".wmv", ".xvid", 
        } | {
            k for k, v in types_map.items() if v.startswith("video/")
        }
    )
)

# TODO: 再实现一个 alist_batch_upload
