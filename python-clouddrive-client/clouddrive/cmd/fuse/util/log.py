#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["logger", "ColoredLevelNameFormatter"]

import logging


logger = logging.getLogger("clouddrive_fuse")


class ColoredLevelNameFormatter(logging.Formatter):

    def format(self, record):
        match record.levelno:
            case logging.DEBUG:
                # blue
                record.levelname = f"\x1b[1;34m{record.levelname}\x1b[0m"
            case logging.INFO:
                # green
                record.levelname = f"\x1b[1;32m{record.levelname}\x1b[0m"
            case logging.WARNING:
                # yellow
                record.levelname = f"\x1b[1;33m{record.levelname}\x1b[0m"
            case logging.ERROR:
                # red
                record.levelname = f"\x1b[1;31m{record.levelname}\x1b[0m"
            case logging.CRITICAL:
                # magenta
                record.levelname = f"\x1b[1;35m{record.levelname}\x1b[0m"
            case _:
                # dark grey
                record.levelname = f"\x1b[1;2m{record.levelname}\x1b[0m"
        return super().format(record)


handler = logging.StreamHandler()
formatter = ColoredLevelNameFormatter(
    "[\x1b[1m%(asctime)s\x1b[0m] (%(levelname)s) \x1b[1;36m%(instance)s.\x1b[0m\x1b[1;3;32m%(funcName)s\x1b[0m"
    " @ \x1b[1;34m%(name)s\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

