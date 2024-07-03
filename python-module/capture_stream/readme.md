# Capture video stream, save as screenshots.

## Installation

You can install from [pypi](https://pypi.org/project/capture_stream/)

```console
pip install -U capture_stream
```

## Usage

### As a Module

```python
>>> import capture_stream
>>> help(capture_stream)

Help on package capture_stream:

NAME
    capture_stream - # encoding: utf-8

PACKAGE CONTENTS
    __main__

FUNCTIONS
    cv_capture(url: str, start: int = 0, stop: None | int = None, step: int = 1, prefix: str = 'frame_', dir_to_save: str = '')
        从 url 读取视频流，保存图片到本地，jpg 图片格式
        
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
    
    cv_capture_iter(url: str, start: int = 0, stop: None | int = None, step: int = 1) -> collections.abc.Iterator[tuple[int, numpy.ndarray]]
        从 url 读取视频流，返回帧的迭代器
        
        :param url: 视频链接
        :param start: 开始索引（从 0 开始编号）
        :param stop:  结束索引（不含此帧），如果 stop 为 None 则到视频结束
        :param step:  索引递增步长
        
        :return: (帧索引序号, 图片数据) 的元组的迭代器
        
        从第 start 帧开始，到第 stop 帧结束，以 step 帧递增
            - 如果 step <= 0，只截取 start 那一帧
            - 如果 stop 为 None，则从 start 到视频结束
            - 否则，跳过此视频

DATA
    __all__ = ['cv_capture_iter', 'cv_capture']

VERSION
    (0, 0, 1)

AUTHOR
    ChenyangGao <https://chenyanggao.github.io>

FILE
    /path/to/capture_stream/__init__.py
```

### As a Command Line

You can use this module to capture screenshots for video steam.

```console
$ capture_stream -h
usage: capture_stream [-h] [-s START] [-t STOP] [-st STEP] [-p PREFIX] [-d DIR_TO_SAVE] [-v] url

从 url 读取视频流，为某些帧截图

positional arguments:
  url                   视频的 url

options:
  -h, --help            show this help message and exit
  -s START, --start START
                        开始帧的索引，从 0 开始编号，默认值：0
  -t STOP, --stop STOP  结束帧的索引（不含），默认为到视频结束
  -st STEP, --step STEP
                        帧的索引递增步长，如果小于等于 0 则只截取 start 那一帧，默认值：1
  -p PREFIX, --prefix PREFIX
                        生成图片的名称的前缀，文件名会被保存为 f'{prefix}{frame_number}.jpg'，frame_number 是帧的索引序号，默认无前缀
  -d DIR_TO_SAVE, --dir-to-save DIR_TO_SAVE
                        把生成的 jpg 保存到此目录，默认值：当前工作目录
  -v, --version         输出版本号
```
