#!/usr/bin/env python3
# coding: utf-8

"批量采集盗火纪录片（https://dao-fire.com）的所有纪录片的基本信息和下载链接"

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__requirements__ = ["lxml", "requests"]
__all__ = ["login", "logout", "get_info", "get_download"]

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="盗火纪录片：纪录片信息和下载链接采集")
    parser.add_argument("-b", "--begin", default=0, type=int, help="开始id，小于等于 0 时（默认），就用 --outout-file 指定的文件中，最大的那个 id + 1")
    parser.add_argument("-e", "--end", default=0, type=int, help="结束id，小于或等于0（默认）时，截至最新，否则截至此id（包含）")
    parser.add_argument("-m", "--max-workers", default=0, type=int, help="多线程并发数，默认为0，小于等于 0 时，则自动确定合适的并发数")
    parser.add_argument("-o", "--output-file", default="daofire.json", help="导出的文件路径，默认为当前工作目录下的 daofire.json 文件，后缀为 .json 时视为导出格式为 JSON，否则导出为 sqlite 数据库文件")

    args = parser.parse_args()

from re import compile as re_compile
from typing import Optional
from urllib.parse import urljoin, urlparse

from requests import request, Session, adapters
from lxml.etree import iselement, Comment
from lxml.html import parse, tostring, HtmlElement, HTMLParser


# 网站首页链接
ORIGIN = "https://dao-fire.com"
# 正则表达式，替换连续多个空白符号(空格、\r、\n、\t、\v、\f、其它空白)
CRESUB_WHITE_SPACES = re_compile("\s+").sub
# 发生网络问题时，最多重试 5 次
adapters.DEFAULT_RETRIES = 5


def fetch_as_etree(
    url: str, 
    method: str = "GET", 
    session: Session = Session(), 
    **request_kwargs, 
):
    request_kwargs["stream"] = True
    headers = request_kwargs.setdefault("headers", {})
    headers["Accept-Encoding"] = "identity"
    while True:
        try:
            with session.request(method, url, **request_kwargs) as resp:
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return parse(resp.raw).getroot()
        except OSError:
            print(f"\r\x1b[K\x1b[1;31m\x1b[1mRETRY\x1b[0m: \x1b[38;5;4m\x1b[4m{url}\x1b[0m")
        except:
            raise


def login(username: str, password: str) -> Session:
    "Sign in the website and return a session."
    url = f"{ORIGIN}/login/"
    # Get csrftoken
    session = Session()
    etree = fetch_as_etree(url, session=session)
    form = etree.get_element_by_id("user_login")
    csrftoken = form.find('input[@name="csrfmiddlewaretoken"]').attrib["value"]
    # Perform login
    etree = fetch_as_etree(
        urljoin(url, form.attrib["action"]), 
        "POST", 
        session=session, 
        data={
            "csrfmiddlewaretoken": csrftoken, 
            "rememberme": 1, 
            "username": username, 
            "password": password, 
        }, 
    )
    errtag = etree.find('.//form[@id="user_login"]//label[@for="username"]')
    if errtag is not None:
        raise ValueError(errtag.text)
    return session


def logout(session: Session):
    "Sign out the website"
    session.get(f"{ORIGIN}/logout/")


def get_latest_id():
    "Try to get the current latest movie id"
    etree = fetch_as_etree(f"{ORIGIN}/bylist/newmovie")
    href = etree.find('.//div[@class="videos"]/div[@class="video"]/a').attrib['href']
    return int(urlparse(href).path.rsplit('/', 1)[-1])


# TODO: 如果需要让返回值作为 markdown 解析，部分符号需要转义，参考
#     - https://markdown.com.cn/basic-syntax/escaping-characters.html
# 另外参考这几个项目：
#     - https://pypi.org/project/html2text/
#     - https://pypi.org/project/markdownify/
#     - https://pypi.org/project/pypandoc/
#     - https://pypi.org/project/mistune/
#     - https://pypi.org/project/Markdown/
#     - https://pypi.org/project/markdown2/
#     - https://pypi.org/project/commonmark/
#     - https://pypi.org/project/marko/
#     - https://pypi.org/project/mistletoe/
#     - https://github.com/bhollis/maruku
def extract_text_content(el: HtmlElement) -> str:
    """
    """
    parts = []
    add_part = parts.append
    def add_clean_part(s):
        if s and (s := s.strip()):
            add_part(s)
    def extract(el):
        if not iselement(el) or el.tag is Comment:
            return
        tag = el.tag
        if tag == "br":
            if parts and parts[-1] != "\n\n":
                add_part("\n\n")
        elif tag == "a":
            link = el.attrib.get("href")
            link = link.replace(")", "%29") if link else ""
            text = (el.text or "").strip() + "".join(extract_text_content(sel).strip() for sel in el)
            text = text.replace("]", "&rbrack;")
            add_part(f"[{text}]({link})")
        elif tag == "img":
            link = el.attrib.get("src")
            link = link.replace(")", "%29") if link else ""
            alt = el.attrib.get("alt") or ""
            alt = alt.replace("]", "&rbrack;")
            title = el.attrib.get("title") or ""
            title = title.replace('"', "&quot;")
            add_part(f'![{alt}]({link} "{title}")')
        elif tag in ("svg", "audio", "video"):
            add_clean_part(tostring(el, encoding="utf-8", with_tail=False).decode())
        elif tag in ("script", "style", "link"):
            pass
        else:
            add_clean_part(el.text)
            for sel in el:
                extract(sel)
            if tag == "p":
                if parts and parts[-1] != "\n\n":
                    add_part("\n\n")
        add_clean_part(el.tail)
    extract(el)
    return "".join(parts)


def get_info(id: int, session=None) -> Optional[dict]:
    "Get documentary information"
    url = f"{ORIGIN}/movie/{id}"
    etree = fetch_as_etree(url)
    if etree is None:
        return None
    data = {
        "id": id, 
        "title": etree.get_element_by_id('video_title').find('h3[@class="post-title text"]').text, 
        "cover_url": etree.get_element_by_id('video_jacket_img').attrib.get("src"), 
        "info_url": f"/movie/{id}", 
        "info_data": {}
    }
    info = data["info_data"]
    video_info = etree.find('.//div[@id="video_info"]')
    for item in video_info.iterchildren('div'):
        header, *value_list = item.findall('./table//tr/td')
        key = extract_text_content(header).strip().removesuffix(':')
        info[key] = CRESUB_WHITE_SPACES(" ", "".join(extract_text_content(el) for el in value_list)).strip().replace('<br />', "\n")
    if session is not None:
        data.update(get_download(id, session))
    print(f"\r\x1b[K\x1b[1;32m\x1b[1mOK\x1b[0m: \x1b[38;5;4m\x1b[4m{url}\x1b[0m")
    return data


def get_download(id: int, session: Session) -> dict:
    "Get documentary download information"
    def extract_info(div):
        el = div.find("a")
        if el is None:
            a = div.find("span/a")
        else:
            a = el
        return {
            "badges": [el.text for el in a.xpath("preceding-sibling::*")], 
            "text": a.text, 
            "link": a.attrib["href"], 
            "extras": [el.text_content().strip() for el in a.xpath("following-sibling::*")], 
        }
    url = f"{ORIGIN}/resource/{id}"
    etree = fetch_as_etree(url, session=session)
    data = {"id": id, "download_url": f"/resource/{id}"}
    if etree is not None:
        data["download_data"] = [extract_info(div) for div in etree.cssselect(".res")]
    return data


if __name__ == "__main__":
    # NOTE: 共享账号，永久VIP
    USERNAME: str = "cyggg"
    PASSWORD: str = "12345a"

    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from itertools import cycle
    from json import dumps
    from os import cpu_count, path as ospath
    from sys import stdout
    from threading import Lock
    from time import time

    output_file = args.output_file
    if ospath.isdir(output_file):
        raise IsADirectoryError(21, f"Is a directory: {output_file!r}")
    begin = args.begin
    if begin <= 0:
        print("📚 Try to get the begin id ...")
        if not ospath.exists(output_file) or ospath.getsize(output_file) == 0:
            begin = 4
        elif output_file.endswith(".json"):
            try:
                begin = max(r["id"] for r in __import__("json").load(open(output_file, encoding="utf-8"))) + 1
            except:
                __import__("os").remove(output_file)
                begin = 4
        else:
            try:
                with __import__("sqlite3").connect(output_file) as con:
                    begin = con.execute("SELECT MAX(id) FROM data").fetchone()[0]
                    if begin is None:
                        begin = 4
                    else:
                        begin += 1
            except:
                __import__("os").remove(output_file)
                begin = 4
    else:
        begin = max(begin, 4)
    end = args.end
    if end <= 0:
        # NOTE: 不一定准确
        end = get_latest_id()
    if end <= begin:
        raise SystemExit("🤔 No need to crawl")
    rng = range(begin, end+1)
    max_workers = args.max_workers
    if max_workers <= 0:
        max_workers = min(32, (cpu_count() or 1) + 4)
    max_workers = min(len(rng), max_workers)

    if output_file.endswith(".json"):
        @contextmanager
        def ctx_writer(output_file):
            lock = Lock()

            def write(record):
                data = dumps(record, ensure_ascii=False).encode("utf-8")
                with lock:
                    if f.tell() == 0:
                        f.write(b"["+data+b"]")
                    else:
                        f.seek(-1, 2)
                        f.write(b","+data+b"]")

            if ospath.exists(output_file):
                f = open(output_file, "rb+", buffering=0)
                f.seek(0, 2)
            else:
                f = open(output_file, "wb+", buffering=0)

            with f:
                yield write
    else:
        @contextmanager
        def ctx_writer(output_file):
            from sqlite3 import connect as sqlite_connect

            fields = ('id', 'title', 'cover_url', 'info_url', 'info_data', 'download_url', 'download_data')
            sql = "INSERT INTO data (%s) VALUES (%s)" % ((",".join(fields)), ",".join("?" * len(fields)))
            lock = Lock()

            def get_field(record, name):
                value = record.get(name)
                if isinstance(value, (dict, list, tuple)):
                    value = dumps(value, ensure_ascii=False)
                return value

            def write(record):
                with lock:
                    con.execute(sql, tuple(get_field(record, f) for f in fields))
                    con.commit()

            need_init = not ospath.exists(output_file) or ospath.getsize(output_file) == 0
            with sqlite_connect(output_file) as con:
                if need_init:
                    con.executescript("""\
    BEGIN TRANSACTION;
    CREATE TABLE IF NOT EXISTS "data" (
        "id" INTEGER NOT NULL,
        "title" TEXT NOT NULL DEFAULT '',
        "cover_url" TEXT NOT NULL DEFAULT '',
        "info_url" TEXT NOT NULL DEFAULT '',
        "info_data" JSON DEFAULT NULL,
        "download_url" TEXT NOT NULL DEFAULT '',
        "download_data" JSON DEFAULT NULL,
        PRIMARY KEY("id") ON CONFLICT REPLACE
    );
    COMMIT;""")
                yield write

    def progressbar_wrapper(it):
        putstr = stdout.write
        flush  = stdout.flush
        get_haha = cycle("😃😄😁😆😅🤣😂🙂🙃😉😊😇🫠🥰😍🤩😘😗😚😙😋😛😜🤪😝🤑🤗🤭🤫🤔🤤").__next__
        try:
            total = len(it)
        except TypeError:
            total = -1
        i = 0
        start_t = time()
        try:
            if total < 0:
                putstr(f"\r\x1b[K{get_haha()} count: 0 | 0.000 s")
                flush()
                for i, e in enumerate(it, 1):
                    yield e
                    putstr(f"\r\x1b[K{get_haha()} count: {i} | {time()-start_t:.3f} s")
                    flush()
            elif total > 0:
                putstr(f"\r\x1b[K{get_haha()} count: 0 of {total} | 0.00 % | 0.000 s")
                flush()
                for i, e in enumerate(it, 1):
                    yield e
                    putstr(f"\r\x1b[K{get_haha()} count: {i} of {total} | {100*i/total:.2f} % | {time()-start_t:.3f} s")
                    flush()
        finally:
            putstr(f"\r\x1b[K😁 count: {i} | {time()-start_t:.3f} s\n")
            flush()

    def progressbar(total=None):
        putstr = stdout.write
        flush  = stdout.flush
        get_haha = cycle("😃😄😁😆😅🤣😂🙂🙃😉😊😇🫠🥰😍🤩😘😗😚😙😋😛😜🤪😝🤑🤗🤭🤫🤔🤤").__next__
        i = 0
        start_t = time()
        try:
            if total is None:
                putstr(f"\r\x1b[K{get_haha()} count: 0 | 0.000 s")
                flush()
                while True:
                    yield
                    i += 1
                    putstr(f"\r\x1b[K{get_haha()} count: {i} | {time()-start_t:.3f} s")
                    flush()
            else:
                putstr(f"\r\x1b[K{get_haha()} count: 0 of {total} | 0.00 % | 0.000 s")
                flush()
                while True:
                    yield
                    i += 1
                    putstr(f"\r\x1b[K{get_haha()} count: {i} of {total} | {100*i/total:.2f} % | {time()-start_t:.3f} s")
                    flush()
        except GeneratorExit:
            putstr(f"\r\x1b[K😁 count: {i} | {time()-start_t:.3f} s\n")
            flush()

    print("📖 Logging in ...")
    session = login(USERNAME, PASSWORD)
    p = progressbar(end-begin+1)

    def work(id_):
        try:
            info = get_info(id_, session)
            if info is None:
                print(f"\r\x1b[K\x1b[38;5;3m\x1b[1mMISSING\x1b[0m: {id_}")
            else:
                return info
        except Exception as e:
            print("\r\x1b[K\x1b[38;5;4m\x1b[4mFailed\x1b[0m: "
                 f"{id_}:\n    |_ \x1b[38;5;1m{type(e).__qualname__}\x1b[0m: {e}")

    with ctx_writer(output_file) as write, ThreadPoolExecutor(max_workers) as executor:
        for info in executor.map(work, rng):
            if info is not None:
                write(info)
            next(p)

    p.close()

