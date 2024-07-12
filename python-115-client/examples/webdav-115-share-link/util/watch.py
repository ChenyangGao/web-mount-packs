#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["WatchFileEventHandler", "WatchMultiFileEventHandler"]

from atexit import register
from os import lstat
from os.path import abspath, commonpath, dirname, normcase
from typing import Callable, Mapping

from watchdog.observers import Observer # type: ignore
from watchdog.events import FileSystemEventHandler # type: ignore


class WatchFileEventHandler(FileSystemEventHandler):

    def __init__(self, path: str, handle: Callable = print):
        super().__init__()
        self.path = abspath(normcase(path))
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

    def dispatch(self, event):
        if event.is_directory:
            return
        path = self.path
        if path == normcase(event.src_path):
            super().dispatch(event)
        elif hasattr(event, "dest_path"):
            if path == normcase(event.dest_path):
                super().dispatch(event)

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


class WatchMultiFileEventHandler(FileSystemEventHandler):

    def __init__(self, /, handles: Mapping[str, Callable]):
        super().__init__()
        self.handles = handles = {
            abspath(normcase(path)): handle
            for path, handle in handles.items()
        }
        self.keys = {
            path: self.get_key(path)
            for path in handles
        }

    def get_key(self, path):
        try:
            stat_result = lstat(path)
        except FileNotFoundError:
            return None
        return stat_result.st_size, stat_result.st_mtime

    def handle(self, path):
        new_key = self.get_key(path)
        if new_key is None or self.keys[path] == new_key:
            return
        self.handles[path]()
        self.keys[path] = new_key

    def dispatch(self, event):
        if event.is_directory:
            return
        if normcase(event.src_path) in self.handles:
            super().dispatch(event)
        elif hasattr(event, "dest_path"):
            if normcase(event.dest_path) in self.handles:
                super().dispatch(event)

    def on_created(self, event):
        self.handle(normcase(event.src_path))

    def on_modified(self, event):
        self.handle(normcase(event.src_path))

    def on_moved(self, event):
        if normcase(event.dest_path) in self.handles:
            self.handle(normcase(event.dest_path))

    @classmethod
    def start(cls, handles: Mapping[str, Callable], join: bool = False):
        event_handler = cls(handles)
        observer = Observer()
        observer.schedule(event_handler, commonpath([abspath(normcase(p)) for p in handles]), recursive=False)
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

