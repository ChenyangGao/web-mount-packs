#!/usr/bin/env python3
# coding: utf-8

"批量采集 torrentgalaxy（https://proxygalaxy.me）所发布的磁力链接"

# NOTE: 查询磁力链接，请用：
# > SELECT id, uploader, data->>'$.title' AS title, data->>'$.magnet' AS magnet FROM data

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__requirements__ = ["lxml"]
__all__ = ["search", "upload_by"]

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="torrentgalaxy：磁力链接采集工具")
    parser.add_argument("uploader", help="上传者")
    parser.add_argument("-s", "--start", type=int, default=0, help="开始索引页（从0开始，默认为0）")
    parser.add_argument("-t", "--stop", type=int, help="结束索引页（不含此页，从0开始，默认为None，即自动判断最后一页）")
    parser.add_argument("-q", "--stop-if-no-insert", action="store_true", help="如果遇到成功插入数为 0，自动终止")
    parser.add_argument("-db", "--database", default="torrentgalaxy.db", help="数据库文件路径，默认为当前工作目录下的 torrentgalaxy.db 文件")

    args = parser.parse_args()

from itertools import count
from json import dumps
from os import path as ospath
from sqlite3 import connect as sqlite_connect
from urllib.parse import urlencode
from urllib.request import urlopen

from lxml.html import parse


# Download TorrentGalaxy's last 24h torrent data dump (Updated hourly)
# > https://torrentgalaxy.mx/torrentdump
# Official TorrentGalaxy proxies & health status
# > https://proxygalaxy.me
# ORIGIN = "https://torrentgalaxy.to"
ORIGIN = "https://torrentgalaxy.mx"
# ORIGIN = "https://tgx.rs"
# ORIGIN = "https://tgx.sb"
SQL = """\
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "uploader" (
    "uploader" TEXT NOT NULL UNIQUE,
    "class" TEXT NOT NULL DEFAULT '',
    "extra" JSON DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS "data" (
    "id" INTEGER NOT NULL,
    "uploader" TEXT NOT NULL DEFAULT '',
    "data" JSON DEFAULT NULL,
    PRIMARY KEY("id") ON CONFLICT IGNORE
);
CREATE INDEX "idx_uploader" ON "data" (
    "uploader" ASC
);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Pornbits','Porn',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('NoisyBoY','Porn',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Pornlake','Porn',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('GalaXXXy','Porn',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('sbudennogo','Porn',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('WEBDL','Porn',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('GalaxyRG','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('TGxMovies','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('indexFroggy','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('yerisan710','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('B0NE','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('EDGE2020','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Dr4gon','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('TeeWee','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('jay77cujo','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Freddy1714','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('NAHOM1','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('MgB','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('V3SP4EXP0RT','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('BigJ0554','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Sp33dy94','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('AsPiDe','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Asmo','Movie',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('TGxTV','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('GalaxyTV','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Saturn5','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('rondobym','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('ppb1','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('icecracked','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Prof','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Nick007','Television',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('pmedia','Music',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Lulloz','Music',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('ZBYSZEK3k','Music',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('DarkAngie','Music',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('zakareya','Book',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('Skyeater','Book',NULL);
INSERT INTO "uploader" ("uploader","class","extra") VALUES ('haxNode','App',NULL);
COMMIT;
"""


def text_after(text, find, n=0):
    if n < 0:
        index = len(text)
        for _ in range(-n):
            index = text.rfind(find, 0, index)
            if index == -1:
                return text
    else:
        index = 0
        for _ in range(n+1):
            index = text.find(find, index)
            if index == -1:
                return text[:0]
    return text[index+len(find):]


def extract_row(row):
    a = row[-10].find('.//a[@class="txlight"]')
    next_a = a.xpath('following-sibling::a')
    if next_a:
        imdb = text_after(next_a[0].attrib["href"], "=", -1)
    else:
        imdb = None
    return {
        "id": int(a.attrib['href'].split("/", 3)[2]), 
        "title": a.attrib['title'], 
        "link": a.attrib['href'], 
        "imdb": imdb, 
        "torrent": row[-9].find('.//a[1]').attrib["href"], 
        "magnet": row[-9].find('.//a[2]').attrib["href"], 
        "uploader": text_after(row[-7].find(".//a").attrib["href"], "/", -1), 
        "size": row[-6].text_content(), 
    }


def extract_table(etree):
    table = etree.find('.//div[@class="tgxtable"]')
    return len(table)-1, map(extract_row, table[1:])


def search(params, **request_kwargss):
    # cat, genres[], order, page, search, sort
    url = f"{ORIGIN}/torrents.php"
    if params:
        url += "?" + urlencode(params)
    with urlopen(url, **request_kwargss) as resp:
        etree = parse(resp)
    return extract_table(etree)


def upload_by(uploader, page=0, **request_kwargss):
    url = f"{ORIGIN}/profile/{uploader}/torrents/{page}"
    with urlopen(url, **request_kwargss) as resp:
        etree = parse(resp)
    return extract_table(etree)


def main(
    uploader, 
    start=0, 
    stop=None, 
    database="torrentgalaxy.db", 
    stop_if_no_insert=False, 
    **request_kwargss, 
):
    def crawl(page):
        while True:
            try:
                return upload_by(uploader, page, **request_kwargss)
            except Exception as e:
                print(f"{type(e).__qualname__}: {e}")
                print(f"RETRY: {page=}")
    if stop is None:
        rng = count(start)
    else:
        rng = range(start, stop)
    need_init = not ospath.exists(database) or ospath.getsize(database) == 0
    with sqlite_connect(database) as conn:
        if need_init:
            conn.executescript(SQL)
        for page in rng:
            n, it = crawl(page)
            if n == 0:
                return
            cursor = conn.executemany(
                "INSERT INTO data (id, uploader, data) VALUES (?, ?, ?)", 
                ((record["id"], record["uploader"], dumps(record, ensure_ascii=False)) for record in it), 
            )
            insert_rows = cursor.rowcount
            if insert_rows == 0 and stop_if_no_insert:
                return
            conn.commit()
            print(f"OK: {page=!r} {insert_rows=!r}")
            if n < 40:
                return


if __name__ == "__main__":
    main(
        args.uploader, 
        timeout=10, 
        start=args.start, 
        stop=args.stop, 
        database=args.database, 
        stop_if_no_insert=args.stop_if_no_insert, 
    )

# TODO: 支持多线程，退出时自动关闭所有网络链接
# TODO: 支持把数据采集到 json 和 sqlite，都是增量采集，不是完成后一次性写入
# TODO: 一开始就确定总的页数，当采集完最后一个后，看一下是不是40个，如果是40个，才尝试继续去获取之后的

