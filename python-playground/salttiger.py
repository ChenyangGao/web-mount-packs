#!/usr/bin/env python3
# coding: utf-8

__version__ = (0, 0, 1)
__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = [
    "get_archive_list", "get_archive_detail", "update_archives", "update_json_db", 
    "update_sqlite_db", "sqlite_to_json", "json_to_sqlite"
]

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(description="   salttiger.com 文章采集", formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "-d", "--db-path", default="salttiger.json", 
        help="数据库文件，只支持 .json 和 .db (sqlite) 后缀，默认值：salttiger.json", 
    )
    parser.add_argument("-l", "--list-files", action="store_true", help="（从 ed2k 或者 百度网盘 链接中）获取文件列表")
    parser.add_argument("-m", "--max-workers", default=0, type=int, help="最多并发线程数，小于或等于 0 时自动确定合适的值")
    args = parser.parse_args()

try:
    from dupan import DuPanShareList
    from lxml.etree import iselement, Comment
    from lxml.html import parse, fromstring, tostring, HtmlElement
    from wcwidth import wcwidth
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", "python-dupan<0.0.1", "lxml", "wcwidth"], check=True)
    from dupan import DuPanShareList
    from lxml.etree import iselement, Comment
    from lxml.html import parse, fromstring, tostring, HtmlElement
    from wcwidth import wcwidth

import json
import sqlite3

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http.client import IncompleteRead
from html import unescape
from itertools import cycle
from os import get_terminal_size, remove
from os.path import exists
from re import compile as re_compile
from sys import stdout
from threading import Lock
from textwrap import indent
from time import perf_counter
from typing import cast, Final, Optional
from urllib.error import URLError
from urllib.parse import unquote, urlparse, urlunparse
from urllib.request import urlopen


CRE_BACKTICKS: Final = re_compile(r"`+")
CRE_YEAR_MONTH: Final = re_compile(r'(?P<year>\d{4})年(?P<month>\d{1,2})月')
CRE_PWD: Final = re_compile(r"(?m:提取码.*?\b(?P<pwd1>[0-9a-zA-Z]{4})\b.*)")


def html_to_markdown(
    el: bytes | bytearray | str | HtmlElement, 
    /, 
) -> str:
    """html 转 markdown
    """
    if isinstance(el, (bytes, bytearray, str)):
        el = fromstring(el)
    parts: list[str] = []
    add = parts.append
    def add_part(s, indent_level=0):
        if indent_level and (not parts or parts[-1][-1:] == "\n") and "\n" in s:
            s = indent(s, " " * (4 * indent_level)).lstrip(" ")
        if s:
            add(s)
    def extract(el, indent_level=0):
        if not iselement(el) or el.tag is Comment:
            return
        match el.tag:
            case "br":
                if parts:
                    if parts[-1][-1:] == "\n":
                        pass
                    elif parts[-1]:
                        add("  \n")
                    else:
                        add("\n")
            case "h1" | "h2" | "h3" | "h4" | "h5" | "h6" as tag:
                add_part("#" * int(tag[1]), indent_level)
                add(" ")
                text = (el.text or "").strip()
                if text:
                    add(text)
                for sel in el.iterfind("*"):
                    text = html_to_markdown(sel)
                    if text:
                        add(text)
            case "a":
                add_part("[", indent_level)
                text = (el.text or "").strip()
                if text:
                    add(text.replace("]", "&rbrack;"))
                for sel in el.iterfind("*"):
                    text = html_to_markdown(sel)
                    if text:
                        add(text.replace("]", "&rbrack;"))
                add("](")
                add(el.attrib.get("href", "").replace(")", "%29"))
                add(")")
            case "img":
                add_part("![", indent_level)
                text = el.attrib.get("alt", "").strip()
                if text:
                    add(text.replace("]", "&rbrack;"))
                add("](")
                add(el.attrib.get("src", "").replace(")", "%29"))
                title = el.attrib.get("title", "").strip()
                if title:
                    add(' "')
                    add(title.replace('"', "&quot;"))
                    add('"')
                add(")")
            case "code":
                max_backtick_len = max(map(len, CRE_BACKTICKS.findall(el.text)))
                if max_backtick_len:
                    backticks = "`" * (max_backtick_len + 1)
                    add_part("%s %s %s" % el.text.replace(backticks, el.text, backticks), indent_level)
                else:
                    add_part("`%s`" % el.text, indent_level)
            case "strong" | "em" as tag:
                text = (el.text or "").strip()
                children = el.findall("*")
                if children:
                    add_part(f"<{tag}>", indent_level)
                    if text:
                        add(text)
                    for sel in children:
                        extract(sel, indent_level)
                    add(f"</{tag}>")
                elif text:
                    if tag == "em":
                        add_part("*%s*" % text.replace("*", r"\*"))
                    else:
                        add_part("**%s**" % text.replace("*", r"\*"))
            case "svg" | "audio" | "video":
                add_part(tostring(el, encoding="utf-8", with_tail=False).decode("utf-8"), indent_level)
            case "script" | "style" | "link":
                pass
            case "li":
                if not parts or parts[-1][:-1] == "\n":
                    add_part("-   ", indent_level)
                else:
                    add_part("\n-   ", indent_level)
                text = (el.text or "").strip()
                if text:
                    add(text)
                for sel in el:
                    extract(sel, indent_level + 1)
            # TODO: case "table": ...
            case _:
                text = (el.text or "").strip()
                add_part(text, indent_level)
                for sel in el:
                    extract(sel, indent_level)
        if el.tag in (
            "address", "article", "aside", "blockquote", "canvas", "dd", "div", "dl", 
            "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", 
            "h4", "h5", "h6", "header", "hr", "main", "nav", "noscript", "ol", "output", 
            "p", "pre", "section", "table", "tfoot", "ul", "video", 
        ):
            if parts:
                if parts[-1][-2:] == "\n\n":
                    pass
                elif parts[-1][-1:] == "\n":
                    add("\n")
                else:
                    add("\n\n")
        text = (el.tail or "").strip()
        if text:
            add_part(text, indent_level)
    extract(el)
    return "".join(parts).strip()


def get_archive_list() -> list[dict]:
    """采集 https://salttiger.com/archives/ 页面罗列的条目（但不采集详情页）
    """
    url = "https://salttiger.com/archives/"
    etree = parse(urlopen(url, timeout=5))
    datalist = []
    for car in etree.iterfind('.//ul[@class="car-list"]/li'):
        year, month = map(int, CRE_YEAR_MONTH.search(car[0].text).groups()) # type: ignore
        for m in car.findall("ul/li"):
            datalist.append(dict(
                title = m.find("a").text, 
                url = m.find("a").attrib["href"], 
                year = year, 
                month = month, 
                day = int(m.text.rstrip(": ")),                 
            ))
    return datalist


def get_archive_detail(url: str, /) -> dict:
    """采集 url 对应的详情页信息
    """
    etree = parse(urlopen(url, timeout=5))
    entry_content = etree.find(f'.//*[@class="entry-content"]')
    entry_meta = etree.find(f'.//*[@class="entry-meta"]')
    attribute_content = entry_content[0]
    try:
        cover_el = attribute_content[0]
        if cover_el.tag != "img":
            raise
        cover = cover_el.attrib["src"]
        download_links = extract_download_links(attribute_content)
    except:
        cover = ""
        download_links = None
    try:
        datetime = entry_meta.find('.//time[@class="entry-date"]').attrib["datetime"]
    except:
        datetime = ""
    return {
        "cover": cover, 
        "description": html_to_markdown(entry_content), 
        "datetime": datetime, 
        "tags": [
            {"tag": el.text, "href": el.attrib["href"], "rel": el.attrib["rel"]}
            for el in entry_meta.xpath(".//a[@rel and contains(concat(' ', normalize-space(@rel), ' '), ' tag ')]")
        ], 
        "download_links": download_links, 
    }


def ed2k_extract(link: str, /) -> dict:
    """从 ed2k 链接中提取文件名和文件大小等信息
    """
    parts = link.split("|", 4)
    return {
        "link": link, 
        "name": parts[2], 
        "size": int(parts[3]), 
    }


def extract_download_links(el: HtmlElement, /) -> Optional[list[str]]:
    def dupan_append_pwd(urlp, pwd):
        query = urlp.query
        pwd = "pwd=" + pwd
        if query:
            if pwd in query:
                return ""
            return "&" + pwd
        else:
            return pwd

    for br in el.iterfind(".//br"):
        text = br.tail or ""
        try:
            text += (br.getnext().text or "")
        except:
            pass
        if not text:
            continue
        text = text.lower()
        if "download" in text or "下载" in text:
            break
    else:
        return None

    ls: list[str] = []
    for sel in br.xpath("following-sibling::a[@href] | following-sibling::*/descendant-or-self::a[@href]"):
        href = unquote(unescape(sel.attrib["href"]))
        if href.startswith(("magnet:", "ed2k:")):
            ls.append(href)
        else:
            urlp = urlparse(href)
            if not urlp.scheme or urlp.scheme not in ("http", "https"):
                continue
            if urlp.netloc == "pan.baidu.com" and not (urlp.query.startswith("pwd=") or "&pwd=" in urlp.query):
                match = None
                text = sel.text_content() + (sel.tail or "")
                if text:
                    match = CRE_PWD.search(text)
                nsel: Optional[HtmlElement]
                if match is None:
                    nsel = sel.getnext()
                    if iselement(nsel) and nsel.tag == "br":
                        text = nsel.tail or ""
                        match = CRE_PWD.search(text)
                        if match is None:
                            nsel = nsel.getnext()
                            if iselement(nsel) and nsel.tag is not Comment and nsel.tag != "br":
                                nsel = cast(HtmlElement, nsel)
                                text = nsel.text_content().lstrip()
                                if text.startswith("提取码"):
                                    match = CRE_PWD.search(text)
                if match is not None:
                    pwd = dupan_append_pwd(urlp, match[cast(str, match.lastgroup)])
                    if pwd:
                        href = urlunparse(urlp._replace(query=urlp.query+pwd))
            ls.append(href)
    return ls


def to_time_str(t: int | float, /) -> str:
    s: int | float | str
    m, s = divmod(t, 60)
    if isinstance(t, float):
        s = format(s, ">09.6f")
        m = int(m)
    else:
        s = format(s, ">02d")
    h, m = divmod(m, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        return f"{d} d {h:02d}:{m:02d}:{s}"
    return f"{h:02d}:{m:02d}:{s}"


def calc_lines(s: str, /, columns: Optional[int] = None) -> int:
    """计算文字会输出的长度（请预先去除 escape sequence 并进行 'NFC' 或 'NFKC' normalize）
    """
    if columns is None or columns <= 0:
        columns = get_terminal_size().columns
    colsize = 0
    lines = 0
    for ch in s:
        if ch == "\n":
            lines += 1
            colsize = 0
        c = wcwidth(ch)
        if c:
            if c < 0:
                c = 2
            if not colsize:
                lines += 1
            colsize += c
            if colsize >= columns:
                if colsize > columns:
                    colsize = c
                    lines += 1
                else:
                    colsize = 0
    return lines


def make_progress_output(total: Optional[int] = None):
    """创建一个 println 函数，可向控制台输出消息，同时输出进度条
    """
    lock = Lock()
    write = stdout.write
    flush = stdout.flush
    count = 0
    success = 0
    get_msg_fns = [
        cycle("😃😄😁😆😅🤣😂🙂🙃😉😊😇🫠🥰😍🤩😘😗😚😙😋😛😜🤪😝🤑🤗🤭🤫🤔🤤").__next__, 
        lambda: f" {count}", 
    ]
    if total is not None and total > 0:
        get_msg_fns.append(lambda: f" of {total}")
        get_msg_fns.append(lambda: f" | 🧮 {count/total*100:.2f} %")
    get_msg_fns.append(lambda: f" | 🕙 {to_time_str(perf_counter()-start_t)}")
    get_msg_fns.append(lambda: f" | ✅ {success}")
    get_msg_fns.append(lambda: f" | ❎ {count - success}")
    last_columns = 0
    last_progress = ""
    try:
        get_terminal_size()
    except OSError:
        def println(msg: str = "", update: Optional[bool] = None):
            with lock:
                write(msg + "\n")
    else:
        def println(msg: str = "", update: Optional[bool] = None):
            nonlocal count, success, last_columns, last_progress
            with lock:
                if update is not None:
                    count += 1
                    if update:
                        success += 1
                columns = get_terminal_size().columns
                write("\r\x1b[K")
                if columns < last_columns:
                    last_lines = calc_lines(last_progress)
                    if last_lines > 1:
                        write("\x1b[A\x1b[K"*(last_lines-1))
                last_columns = columns
                write(msg + "\n")
                cw = 0
                progress = ""
                for fn in get_msg_fns:
                    s = fn()
                    columns -= len(s) + 1
                    if columns >= 0:
                        progress += s
                    if columns <= 0:
                        break
                write(progress)
                write("\r")
                flush()
                last_progress = progress
    start_t = perf_counter()
    println()
    return println


def update_archives(
    archive_list, 
    list_files: bool = False, 
    callabck: Optional[Callable] = None, 
    max_workers: Optional[int] = None, 
):
    """更新数据
    """
    total = len(archive_list)
    print = make_progress_output(total)

    def update(item):
        url = item["url"]
        if "description" not in item:
            while True:
                try:
                    item.update(get_archive_detail(url))
                    if callabck: 
                        callabck(item)
                    break
                except (URLError, TimeoutError, IncompleteRead) as e:
                    print(f"\x1b[1m\x1b[38;5;3mRETRY\x1b[0m \x1b[4m\x1b[38;5;4m{url}\x1b[0m\n    |_ \x1b[1m\x1b[38;5;1m{type(e).__qualname__}\x1b[0m: {e}")
                except BaseException as e:
                    print(f"\x1b[1m\x1b[38;5;1mNA\x1b[0m \x1b[4m\x1b[38;5;4m{url}\x1b[0m\n    |_ \x1b[1m\x1b[38;5;1m{type(e).__qualname__}\x1b[0m: {e}", update=False)
                    raise
        if list_files and "files" not in item:
            try:
                download_links = item["download_links"]
                if download_links:
                    files = []
                    for link in download_links:
                        if link.startswith("ed2k://"):
                            files.append(ed2k_extract(link))
                        elif "://pan.baidu.com/" in link:
                            try:
                                files = [item for item in DuPanShareList(link) if not item["isdir"]]
                                print(f"\x1b[1m\x1b[38;5;2mOK\x1b[0m \x1b[4m\x1b[38;5;4m{link}\x1b[0m")
                            except:
                                print(f"\x1b[1m\x1b[38;5;1mNA\x1b[0m \x1b[4m\x1b[38;5;4m{link}\x1b[0m")
                                raise
                            break
                    item["files"] = files
                else:
                    item["files"] = []
                if callabck: 
                    callabck(item)
            except BaseException as e:
                print(f"\x1b[1m\x1b[38;5;1mNA\x1b[0m \x1b[4m\x1b[38;5;4m{url}\x1b[0m\n    |_ \x1b[1m\x1b[38;5;1m{type(e).__qualname__}\x1b[0m: {e}", update=False)
                raise
        print(f"\x1b[1m\x1b[38;5;2mOK\x1b[0m \x1b[4m\x1b[38;5;4m{url}\x1b[0m", update=True)

    if max_workers == 1:
        for item in archive_list:
            try:
                update(item)
            except:
                pass
    else:
        with ThreadPoolExecutor(max_workers) as ex:
            for item in archive_list:
                ex.submit(update, item)


def update_json_db(
    path: str = "salttiger.json", 
    list_files: bool = False, 
    max_workers: Optional[int] = None, 
):
    """采集或更新数据到 json 数据库
    """
    archive_list = get_archive_list()
    try:
        archives = json.load(open(path, "r", encoding="utf-8"))
    except FileNotFoundError:
        archives = {item["url"].rsplit('/', 2)[-2]: item for item in archive_list}
    else:
        for item in archive_list:
            key = item["url"].rsplit('/', 2)[-2]
            if key not in archives:
                archives[key] = item
    update_archives(
        archives.values(), 
        list_files=list_files, 
        max_workers=max_workers, 
    )
    json.dump(archives, open(path, "w", encoding="utf-8"), ensure_ascii=False)


def update_sqlite_db(
    path: str = "salttiger.db", 
    list_files: bool = False, 
    max_workers: Optional[int] = None, 
):
    """采集或更新数据到 sqlite 数据库
    """
    sql = """\
CREATE TABLE "data" (
    "id" TEXT NOT NULL, 
    "data" JSON NOT NULL, 
    "datetime" TEXT DEFAULT '', 
    PRIMARY KEY("id") ON CONFLICT REPLACE
);"""
    changed: dict[str, dict] = {}
    def update(item):
        changed[item["url"].rsplit('/', 2)[-2]] = item
    archive_list = get_archive_list()
    with sqlite3.connect(path) as con:
        try:
            archives = {k: json.loads(v) for k, v in con.execute("SELECT id, data FROM data")}
        except:
            con.execute(sql)
            archives = {}
        for item in archive_list:
            key = item["url"].rsplit('/', 2)[-2]
            if key not in archives:
                archives[key] = item
                changed[key] = item
        update_archives(
            archives.values(), 
            callabck=update, 
            list_files=list_files, 
            max_workers=max_workers, 
        )
        if changed:
            con.executemany(
                "INSERT INTO data (id, data, datetime) VALUES (?, ?, ?)", 
                (
                    (key, json.dumps(item, ensure_ascii=False), item.get("datetime", ""))
                    for key, item in changed.items()
                )
            )
            con.commit()


def sqlite_to_json(db_path: str, json_path: str):
    """sqlite 数据库转 json 数据库
    """
    with sqlite3.connect(db_path) as con:
        archives = {k: json.loads(v) for k, v in con.execute("SELECT id, data FROM data")}
    json.dump(archives, open(json_path, "w", encoding="utf-8"), ensure_ascii=False)


def json_to_sqlite(json_path: str, db_path: str):
    """json 数据库转 sqlite 数据库
    """
    archives = json.load(open(json_path, "r", encoding="utf-8"))
    if exists(db_path):
        remove(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute("""\
CREATE TABLE "data" (
    "id" TEXT NOT NULL, 
    "data" JSON NOT NULL, 
    "datetime" TEXT DEFAULT '', 
    PRIMARY KEY("id") ON CONFLICT REPLACE
);""")
        con.executemany(
            "INSERT INTO data (id, data, datetime) VALUES (?, ?, ?)", 
            (
                (key, json.dumps(item, ensure_ascii=False), item.get("datetime", ""))
                for key, item in archives.items()
            )
        )
        con.commit()


if __name__ == "__main__":
    db_path = args.db_path
    max_workers = args.max_workers if args.max_workers > 0 else None
    if db_path.endswith(".json"):
        update_json_db(db_path, list_files=args.list_files, max_workers=max_workers)
    elif db_path.endswith(".db"):
        update_sqlite_db(db_path, list_files=args.list_files, max_workers=max_workers)

