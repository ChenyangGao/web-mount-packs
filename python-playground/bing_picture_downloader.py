#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["get_page", "get_id", "download"]

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Bing 图片下载 | 多线程 | powered by 'https://bing.wilii.cn/gallery'")
    parser.add_argument("-b", "--begin-date", help="开始日期，接受格式：%%Y-%%m-%%d")
    parser.add_argument("-e", "--end-date", help="结束日期（含），接受格式：%%Y-%%m-%%d")
    parser.add_argument("-m", "--max-workers", default=1, type=int, help="最大工作线程数，默认值是 1，小于等于 0 时自动确定合适值")
    parser.add_argument("-u", "--uhd", action="store_true", help="只下载高清版本 UHD")

    args = parser.parse_args()

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from posixpath import basename
from datetime import date, datetime
from json import load
from shutil import copyfileobj
from urllib.error import URLError
from urllib.request import urlopen

def get(url, timeout=5):
    while True:
        try:
            return urlopen(url, timeout=timeout)
        except (URLError, TimeoutError):
            pass

def get_page(page=1, page_size=16):
    url = f"https://api.wilii.cn/api/bing?page={page}&pageSize={page_size}"
    return load(get(url))["response"]["data"]

def get_id(id=1):
    url = f"https://api.wilii.cn/api/Bing/{id}"
    return load(get(url))["response"]

def _download_one(url, save_path):
    try:
        copyfileobj(get(url), open(save_path, "wb"))
        print("OK:", save_path)
    except:
        print("NA:", save_path)
        raise

def _resolve_download(attr, uhd=False):
    date = attr["date"]
    if date in ("2009-10-26", "2010-04-16", "2010-04-17", "2010-12-01", "2012-04-22", "2012-08-14"):
        return
    url = attr["filepath"]
    fid = url[53:-14]
    if uhd:
        if date < "2019-05-10":
            return
        resolv = "_UHD"
    elif date >= "2016-01-01":
        resolv = "_1920x1080"
    elif date >= "2013-04-20":
        resolv = "_1366x768"
    else:
        resolv = ""
    return f"{url[:-14]}{resolv}.jpg", f"{date}_OHR.{fid}{resolv}.jpg"

def download(begin_date=None, end_date=None, max_workers=1, uhd=False):
    today = date.today()
    date_begin = date(2019, 5, 10) if uhd else date(2009, 7, 13)
    if begin_date is None:
        begin_date = date_begin
    elif isinstance(begin_date, str):
        begin_date = datetime.strptime(begin_date, "%Y-%m-%d").date()
    if end_date is None:
        end_date = today
    elif isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    if begin_date > end_date:
        begin_date, end_date = end_date, begin_date
    if begin_date < date_begin:
        begin_date = date_begin
    if end_date > today:
        end_date = today
    begin_date_str = str(begin_date)
    end_date_str = str(end_date)
    start_page = (today - end_date).days // 64 + 1
    if max_workers == 1:
        pool = None
        submit = _download_one
    else:
        pool = ThreadPoolExecutor(max_workers=max_workers if max_workers > 0 else None)
        submit = partial(pool.submit, _download_one)
    try:
        while True:
            attrs = get_page(start_page, 64)
            for attr in attrs:
                date_str = attr["date"]
                if date_str > end_date_str:
                    continue
                elif date_str < begin_date_str:
                    break
                ret = _resolve_download(attr, uhd=uhd)
                if ret:
                    submit(*ret)
            else:
                if len(attrs) == 64:
                    start_page += 1
                    continue
            break
        if pool:
            with pool:
                pass
    finally:
        if pool:
            pool.shutdown(False, cancel_futures=True)

if __name__ == "__main__":
    download(**args.__dict__)

