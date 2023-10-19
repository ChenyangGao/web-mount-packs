#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["WatchFileEventHandler"]

from atexit import register
from os import lstat
from os.path import abspath, dirname, normcase
from re import escape
from typing import Callable

from watchdog.observers import Observer # type: ignore
from watchdog.events import RegexMatchingEventHandler, LoggingEventHandler # type: ignore


class WatchFileEventHandler(RegexMatchingEventHandler):

    def __init__(self, path: str, handle: Callable = print):
        super().__init__(
            regexes=escape(path), 
            case_sensitive=normcase("a") != normcase("A"), 
            ignore_directories=True, 
        )
        self.path = normcase(path)
        self.key = self.get_key()
        self._handle = handle

    def get_key(self):
        try:
            stat_result = lstat(self.path)
        except FileNotFoundError:
            return None
        return stat_result.st_size, stat_result.st_mtime

    def handle(self):
        new_key = self.get_key()
        if new_key is None or self.key == new_key:
            return
        self._handle(self.path)
        self.key = new_key

    def on_created(self, event):
        self.handle()

    def on_modified(self, event):
        self.handle()

    def on_moved(self, event):
        if self.path == normcase(event.dest_path):
            self.handle()

    @classmethod
    def start(cls, path: str, handle: Callable = print, join: bool = False):
        path = abspath(path)
        event_handler = cls(path, handle)
        observer = Observer()
        observer.schedule(event_handler, dirname(path), recursive=False)
        observer.start()
        if join:
            try:
                while observer.is_alive():
                    observer.join(1)
            finally:
                observer.stop()
                observer.join()
        else:
            register(observer.stop)

