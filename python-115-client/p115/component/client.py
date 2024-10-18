#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115Client", "ExportDirStatus", "PushExtractProgress", "ExtractProgress"]

import errno

from collections.abc import Awaitable, Callable, Coroutine, Sequence
from concurrent.futures import Future
from functools import cached_property
from _thread import start_new_thread
from threading import Condition
from time import sleep
from typing import overload, Any, Literal

from p115client import check_response, P115Client as Client


class P115Client(Client):

    # TODO 支持异步
    @overload
    def fs_export_dir_future(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> ExportDirStatus:
        ...
    @overload
    def fs_export_dir_future(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, ExportDirStatus]:
        ...
    def fs_export_dir_future(
        self, 
        payload: int | str | dict, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> ExportDirStatus | Coroutine[Any, Any, ExportDirStatus]:
        """执行导出目录树，新开启一个线程，用于检查完成状态
        payload:
            file_ids: int | str   # 有多个时，用逗号 "," 隔开
            target: str = "U_1_0" # 导出目录树到这个目录
            layer_limit: int = <default> # 层级深度，自然数
        """
        if async_:
            raise NotImplementedError("asynchronous mode not implemented")
        resp = check_response(self.fs_export_dir(payload, **request_kwargs))
        return ExportDirStatus(self, resp["data"]["export_id"])

    # TODO 支持异步
    @overload
    def extract_push_future(
        self, 
        /, 
        pickcode: str, 
        secret: str,
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> None | PushExtractProgress:
        ...
    @overload
    def extract_push_future(
        self, 
        /, 
        pickcode: str, 
        secret: str,
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, None | PushExtractProgress]:
        ...
    def extract_push_future(
        self, 
        /, 
        pickcode: str, 
        secret: str = "",
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> None | PushExtractProgress | Coroutine[Any, Any, None | PushExtractProgress]:
        """执行在线解压，如果早就已经完成，返回 None，否则新开启一个线程，用于检查进度
        """
        if async_:
            raise NotImplementedError("asynchronous mode not implemented")
        resp = check_response(self.extract_push(
            {"pick_code": pickcode, "secret": secret}, 
            **request_kwargs, 
        ))
        if resp["data"]["unzip_status"] == 4:
            return None
        return PushExtractProgress(self, pickcode)

    # TODO 支持异步
    @overload
    def extract_file_future(
        self, 
        /, 
        pickcode: str, 
        paths: str | Sequence[str], 
        dirname: str, 
        to_pid: int | str,
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> ExtractProgress:
        ...
    @overload
    def extract_file_future(
        self, 
        /, 
        pickcode: str, 
        paths: str | Sequence[str], 
        dirname: str, 
        to_pid: int | str,
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, ExtractProgress]:
        ...
    def extract_file_future(
        self, 
        /, 
        pickcode: str, 
        paths: str | Sequence[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0,
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> ExtractProgress | Coroutine[Any, Any, ExtractProgress]:
        """执行在线解压到目录，新开启一个线程，用于检查进度
        """
        if async_:
            raise NotImplementedError("asynchronous mode not implemented")
        resp = check_response(self.extract_file(
            pickcode, paths, dirname, to_pid, **request_kwargs
        ))
        return ExtractProgress(self, resp["data"]["extract_id"])

    @cached_property
    def fs(self, /) -> P115FileSystem:
        """你的网盘的文件列表的封装对象
        """
        return P115FileSystem(self)

    def get_fs(
        self, 
        /, 
        password: str = "", 
        cache_id_to_readdir: bool | int = False, 
        cache_path_to_id: bool | int = False, 
        refresh: bool = True, 
        request: None | Callable = None, 
        async_request: None | Callable = None, 
    ) -> P115FileSystem:
        """新建你的网盘的文件列表的封装对象
        """
        return P115FileSystem(
            self, 
            password=password, 
            cache_id_to_readdir=cache_id_to_readdir, 
            cache_path_to_id=cache_path_to_id, 
            refresh=refresh, 
            request=request, 
            async_request=async_request, 
        )

    def get_share_fs(self, share_link: str, /, *args, **kwargs) -> P115ShareFileSystem:
        """新建一个分享链接的文件列表的封装对象
        """
        return P115ShareFileSystem(self, share_link, *args, **kwargs)

    def get_zip_fs(self, id_or_pickcode: int | str, /, *args, **kwargs) -> P115ZipFileSystem:
        """新建压缩文件（支持 zip、rar、7z）的文件列表的封装对象（这个压缩文件在你的网盘中，且已经被云解压）

        https://vip.115.com/?ct=info&ac=information
        云解压预览规则：
        1. 支持rar、zip、7z类型的压缩包云解压，其他类型的压缩包暂不支持；
        2. 支持云解压20GB以下的压缩包；
        3. 暂不支持分卷压缩包类型进行云解压，如rar.part等；
        4. 暂不支持有密码的压缩包进行在线预览。
        """
        return P115ZipFileSystem(self, id_or_pickcode, *args, **kwargs)

    @cached_property
    def label(self, /) -> P115LabelList:
        """你的标签列表的封装对象（标签是给文件或文件夹做标记的）
        """
        return P115LabelList(self)

    @cached_property
    def offline(self, /) -> P115Offline:
        """你的离线任务列表的封装对象
        """
        return P115Offline(self)

    def get_offline(self, /, *args, **kwargs) -> P115Offline:
        """新建你的离线任务列表的封装对象
        """
        return P115Offline(self, *args, **kwargs)

    @cached_property
    def recyclebin(self, /) -> P115Recyclebin:
        """你的回收站的封装对象
        """
        return P115Recyclebin(self)

    def get_recyclebin(self, /, *args, **kwargs) -> P115Recyclebin:
        """新建你的回收站的封装对象
        """
        return P115Recyclebin(self, *args, **kwargs)

    @cached_property
    def sharing(self, /) -> P115Sharing:
        """你的分享列表的封装对象
        """
        return P115Sharing(self)

    def get_sharing(self, /, *args, **kwargs) -> P115Sharing:
        """新建你的分享列表的封装对象
        """
        return P115Sharing(self, *args, **kwargs)


# TODO: 这些类再提供一个 Async 版本
class ExportDirStatus(Future):
    _condition: Condition
    _state: str

    def __init__(self, /, client: P115Client, export_id: int | str):
        super().__init__()
        self.status = 0
        self.set_running_or_notify_cancel()
        self._run_check(client, export_id)

    def __bool__(self, /) -> bool:
        return self.status == 1

    def __del__(self, /):
        self.stop()

    def stop(self, /):
        with self._condition:
            if self._state in ["RUNNING", "PENDING"]:
                self._state = "CANCELLED"
                self.set_exception(OSError(errno.ECANCELED, "canceled"))

    def _run_check(self, client, export_id: int | str, /):
        get_status = client.fs_export_dir_status
        payload = {"export_id": export_id}
        def update_progress():
            while self.running():
                try:
                    resp = get_status(payload)
                except:
                    continue
                try:
                    data = check_response(resp)["data"]
                    if data:
                        self.status = 1
                        self.set_result(data)
                        return
                except BaseException as e:
                    self.set_exception(e)
                    return
                sleep(1)
        start_new_thread(update_progress, ())


class PushExtractProgress(Future):
    _condition: Condition
    _state: str

    def __init__(self, /, client: P115Client, pickcode: str):
        super().__init__()
        self.progress = 0
        self.set_running_or_notify_cancel()
        self._run_check(client, pickcode)

    def __del__(self, /):
        self.stop()

    def __bool__(self, /) -> bool:
        return self.progress == 100

    def stop(self, /):
        with self._condition:
            if self._state in ["RUNNING", "PENDING"]:
                self._state = "CANCELLED"
                self.set_exception(OSError(errno.ECANCELED, "canceled"))

    def _run_check(self, client, pickcode: str, /):
        check = client.extract_push_progress
        payload = {"pick_code": pickcode}
        def update_progress():
            while self.running():
                try:
                    resp = check(payload)
                except:
                    continue
                try:
                    data = check_response(resp)["data"]
                    extract_status = data["extract_status"]
                    progress = extract_status["progress"]
                    if progress == 100:
                        self.set_result(data)
                        return
                    match extract_status["unzip_status"]:
                        case 1 | 2 | 4:
                            self.progress = progress
                        case 0:
                            raise OSError(errno.EIO, f"bad file format: {data!r}")
                        case 6:
                            raise OSError(errno.EINVAL, f"wrong password/secret: {data!r}")
                        case _:
                            raise OSError(errno.EIO, f"undefined error: {data!r}")
                except BaseException as e:
                    self.set_exception(e)
                    return
                sleep(1)
        start_new_thread(update_progress, ())


class ExtractProgress(Future):
    _condition: Condition
    _state: str

    def __init__(self, /, client: P115Client, extract_id: int | str):
        super().__init__()
        self.progress = 0
        self.set_running_or_notify_cancel()
        self._run_check(client, extract_id)

    def __del__(self, /):
        self.stop()

    def __bool__(self, /) -> bool:
        return self.progress == 100

    def stop(self, /):
        with self._condition:
            if self._state in ["RUNNING", "PENDING"]:
                self._state = "CANCELLED"
                self.set_exception(OSError(errno.ECANCELED, "canceled"))

    def _run_check(self, client, extract_id: int | str, /):
        check = client.extract_progress
        payload = {"extract_id": extract_id}
        def update_progress():
            while self.running():
                try:
                    resp = check(payload)
                except:
                    continue
                try:
                    data = check_response(resp)["data"]
                    if not data:
                        raise OSError(errno.EINVAL, f"no such extract_id: {extract_id}")
                    progress = data["percent"]
                    self.progress = progress
                    if progress == 100:
                        self.set_result(data)
                        return
                except BaseException as e:
                    self.set_exception(e)
                    return
                sleep(1)
        start_new_thread(update_progress, ())


from .fs import P115FileSystem
from .fs_share import P115ShareFileSystem
from .fs_zip import P115ZipFileSystem
from .labellist import P115LabelList
from .offline import P115Offline
from .recyclebin import P115Recyclebin
from .sharing import P115Sharing

# TODO: qrcode_login 的返回值，是一个 Future 对象，包含登录必要凭证、二维码链接、登录状态、返回值或报错信息等数据，并且可以被等待完成，也可以把二维码输出到命令行、浏览器、图片查看器等
# TODO: upload_file 返回一个task，初始化成功后，生成 {"bucket": bucket, "object": object, "upload_id": upload_id, "callback": callback, "partsize": partsize, "filesize": filesize}
# TODO: 支持进度条和随时暂停，基于迭代器，使用一个 flag，每次迭代检查一下
# TODO: 返回 task，支持 pause（暂停此任务，连接不释放）、stop（停止此任务，连接释放）、cancel（取消此任务）、resume（恢复），此时需要增加参数 wait
# TODO: class P115MultipartUploadTask:
#           @classmethod
#           def from_cache(cls, /, bucket, object, upload_id, callback, file): ...
