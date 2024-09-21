#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__doc__ = "从 url 读取视频流，为某些帧截图"

from argparse import ArgumentParser, RawTextHelpFormatter


def parse_args(argv=None):
    parser = ArgumentParser(description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument("url", help="视频的 url")
    parser.add_argument("-s", "--start", type=int, default=0, help="开始帧的索引，从 0 开始编号，默认值：0")
    parser.add_argument("-t", "--stop", type=int, help="结束帧的索引（不含），默认为到视频结束")
    parser.add_argument("-st", "--step", type=int, default=1, help="帧的索引递增步长，如果小于等于 0 则只截取 start 那一帧，默认值：1")
    parser.add_argument("-p", "--prefix", default="", help="生成图片的名称的前缀，文件名会被保存为 f'{prefix}{frame_number}.jpg'，frame_number 是帧的索引序号，默认无前缀")
    parser.add_argument("-d", "--dir-to-save", default="", help="把生成的 jpg 保存到此目录，默认值：当前工作目录")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
    args = parser.parse_args(argv)
    if args.version:
        from capture_stream import __version__
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    return args


def main(argv=None):
    from capture_stream import cv_capture

    args = parse_args(argv)

    cv_capture(
        args.url, 
        args.start, 
        args.stop, 
        args.step, 
        prefix=args.prefix, 
        dir_to_save=args.dir_to_save, 
    )


if __name__ == "__main__":
    from pathlib import Path
    from sys import path

    path[0] = str(Path(__file__).parents[1])
    main()

