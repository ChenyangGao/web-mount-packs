#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["cv_capture_iter", "cv_capture"]
__version__ = (0, 0, 1)

from collections.abc import Iterator
from os import makedirs
from os.path import join as joinpath

from cv2 import imwrite, VideoCapture, CAP_PROP_POS_FRAMES
from numpy import ndarray


def cv_capture_iter(
    url: str, 
    start: int = 0, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, ndarray]]:
    """从 url 读取视频流，返回帧的迭代器

    :param url: 视频链接
    :param start: 开始索引（从 0 开始编号）
    :param stop:  结束索引（不含此帧），如果 stop 为 None 则到视频结束
    :param step:  索引递增步长

    :return: (帧索引序号, 图片数据) 的元组的迭代器

    从第 start 帧开始，到第 stop 帧结束，以 step 帧递增
        - 如果 step <= 0，只截取 start 那一帧
        - 如果 stop 为 None，则从 start 到视频结束
        - 否则，跳过此视频
    """
    if start < 0:
        start = 0
    if step <= 0:
        step = 1
        stop = start + 1
    elif stop is None:
        pass
    elif start >= stop or stop <= 0:
        return

    cap = VideoCapture(url)
    if not cap.isOpened():
        raise OSError(f"can not open video stream: {url!r}")
    try:
        if start:
            if start <= 30:
                for _ in range(1, start):
                    ret, frame = cap.read()
                    if not ret:
                        return
            else:
                cap.set(CAP_PROP_POS_FRAMES, start)
        frame_number = start
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            yield frame_number, frame
            frame_number += step
            if stop and frame_number >= stop:
                break
            if step > 1:
                if step <= 30:
                    for _ in range(1, step):
                        ret, frame = cap.read()
                        if not ret:
                            break
                else:
                    cap.set(CAP_PROP_POS_FRAMES, frame_number)
    finally:
        cap.release()


def cv_capture(
    url: str, 
    start: int = 0, 
    stop: None | int = None, 
    step: int = 1, 
    prefix: str = "frame_", 
    dir_to_save: str = "", 
):
    """从 url 读取视频流，保存图片到本地，jpg 图片格式

    :param url: 视频链接
    :param start: 开始索引（从 0 开始编号）
    :param stop:  结束索引（不含此帧），如果 stop 为 None 则到视频结束
    :param step:  索引递增步长
    :param prefix: 文件名会被保存为 f"{prefix}{frame_number}.jpg"，frame_number 是帧的索引序号
    :param dir_to_save: 把生成的 jpg 保存到此目录，默认是当前工作目录

    从第 start 帧开始，到第 stop 帧结束，以 step 帧递增
        - 如果 step <= 0，只截取 start 那一帧
        - 如果 stop 为 None，则从 start 到视频结束
        - 否则，跳过此视频
    """
    if dir_to_save:
        makedirs(dir_to_save, exist_ok=True)
    for frame_number, frame in cv_capture_iter(url, start, stop, step):
        path = joinpath(dir_to_save, f"{prefix}{frame_number}.jpg")
        imwrite(path, frame)
        print(f"Screenshot saved: {path!r}")

