#!/usr/bin/env python3
# encoding: utf-8

# TODO: 作为模块提供，允许全量更新(updatedb)和增量更新(updatedb_one)，但只允许同时最多一个写入任务
# TODO: 可以起一个服务，其它的程序，可以发送读写任务过来，数据库可以以 fuse 或 webdav 展示
# TODO: 支持多个不同登录设备并发
# TODO: 支持同一个 cookies 并发因子，默认值 1
# TODO: 使用协程进行并发，而非多线程
# TODO: 如果请求超时，则需要进行重试
# TODO: 使用 urllib3 替代 httpx，增加稳定性

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["updatedb", "updatedb_one"]
__doc__ = "遍历 115 网盘的目录信息导出到数据库"
__requirements__ = ["orjson", "python-115", "posixpatht"]

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, 
        description=__doc__, 
    )
    parser.add_argument("top_ids", metavar="dirid", nargs="*", type=int, help="115 目录 id，可以传入多个，如果不传默认为 0")
    parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -cp/--cookies-path")
    parser.add_argument("-cp", "--cookies-path", help="""\
存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一: 
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录
如果都找不到，则默认使用 '2. 用户根目录，此时则需要扫码登录'""")
    parser.add_argument("-f", "--dbfile", default="", help="sqlite 数据库文件路径，默认为在当前工作目录下的 f'115-{user_id}.db'")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

import logging

from collections import deque, ChainMap
from collections.abc import Iterator, Iterable
from errno import EBUSY, ENOENT, ENOTDIR
from sqlite3 import (
    connect, register_adapter, register_converter, Connection, Cursor, 
    Row, PARSE_COLNAMES, PARSE_DECLTYPES
)
from typing import cast

try:
    from orjson import dumps, loads
    from p115 import check_response, P115Client
    from posixpatht import escape
except ImportError:
    from sys import executable
    from subprocess import run
    run([executable, "-m", "pip", "install", "-U", *__requirements__], check=True)
    from orjson import dumps, loads
    from p115 import check_response, P115Client
    from posixpatht import escape


register_adapter(list, dumps)
register_adapter(dict, dumps)
register_converter("JSON", loads)

logger = logging.Logger("115-updatedb", level=logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    "[\x1b[1m%(asctime)s\x1b[0m] (\x1b[1;36m%(levelname)s\x1b[0m) "
    "\x1b[0m\x1b[1;35m%(name)s\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s"
))
logger.addHandler(handler)


class OSBusyError(OSError):

    def __init__(self, *args):
        super().__init__(EBUSY, *args)


def cut_iter(
    start: int, 
    stop: None | int = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int]]:
    if stop is None:
        start, stop = 0, start
    for mid in range(start + step, stop, step):
        yield start, step
        start = mid
    if start < stop:
        yield start, stop - start


def do_commit(
    con: Connection | Cursor, 
):
    conn = cast(Connection, getattr(con, "connection", con))
    conn.commit()


def execute_commit(
    con: Connection | Cursor, 
    /, 
    sql: str, 
    params = None, 
    executemany: bool = False, 
) -> Cursor:
    conn = cast(Connection, getattr(con, "connection", con))
    try:
        if executemany:
            cur = con.executemany(sql, params)
        elif params is None:
            cur = con.execute(sql)
        else:
            cur = con.execute(sql, params)
        conn.commit()
        return cur
    except BaseException:
        conn.rollback()
        raise


def json_array_head_replace(value, repl, stop=None):
    value = loads(value)
    repl  = loads(repl)
    if stop is None:
        stop = len(repl)
    value[:stop] = repl
    return dumps(value)


def initdb(con: Connection | Cursor, /) -> Cursor:
    conn = cast(Connection, getattr(con, "connection", con))
    conn.row_factory = Row
    conn.create_function("escape_name", 1, escape)
    conn.create_function("json_array_head_replace", 3, json_array_head_replace)
    return con.executescript("""\
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS "data" (
    "id" INTEGER NOT NULL PRIMARY KEY,
    "parent_id" INTEGER NOT NULL,
    "pickcode" TEXT NOT NULL DEFAULT '',
    "name" TEXT NOT NULL,
    "size" INTEGER NOT NULL DEFAULT 0,
    "sha1" TEXT NOT NULL DEFAULT '',
    "is_dir" INTEGER NOT NULL CHECK("is_dir" IN (0, 1)),
    "is_image" INTEGER NOT NULL CHECK("is_image" IN (0, 1)) DEFAULT 0,
    "mtime" INTEGER NOT NULL DEFAULT 0,
    "path" TEXT NOT NULL DEFAULT '',
    "ancestors" JSON NOT NULL DEFAULT '',
    "updated_at" DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S.%f+08:00', 'now', '+8 hours'))
);

CREATE TRIGGER IF NOT EXISTS trg_data_updated_at
AFTER UPDATE ON data 
FOR EACH ROW
BEGIN
    UPDATE data SET updated_at = strftime('%Y-%m-%dT%H:%M:%S.%f+08:00', 'now', '+8 hours') WHERE id = NEW.id;
END;

CREATE INDEX IF NOT EXISTS idx_data_parent_id ON data(parent_id);
CREATE INDEX IF NOT EXISTS idx_data_path ON data(path);

CREATE VIEW IF NOT EXISTS "id_to_relpath" AS
WITH RECURSIVE ancestors(id, relpath, relative_ancestors) AS (
    SELECT
        d1.id, 
        CASE
            WHEN d1.name IN ('.', '..') THEN '\\' || d1.name
            ELSE REPLACE(REPLACE(d1.name, '\\', '\\\\'), '/', '\\/')
        END, 
        JSON_ARRAY(JSON(CONCAT('{"id": ', d1.id,', "name": ', JSON_QUOTE(d1.name), '}')))
    FROM
        data d1 LEFT JOIN data d2 ON (d2.mtime != 0 AND d1.parent_id = d2.id)
    WHERE
        d1.mtime != 0
        AND d2.id IS NULL

    UNION ALL

    SELECT 
        data.id, 
        ancestors.relpath || '/' || CASE
            WHEN data.name IN ('.', '..') THEN '\\' || data.name
            ELSE REPLACE(REPLACE(data.name, '\\', '\\\\'), '/', '\\/')
        END, 
        JSON_INSERT(
            ancestors.relative_ancestors, 
            '$[#]', 
            JSON(CONCAT('{"id": ', data.id,', "name": ', JSON_QUOTE(data.name), '}'))
        )
    FROM 
        data JOIN ancestors ON (data.parent_id = ancestors.id)
)
SELECT * FROM ancestors;
""")


def select_subdir_ids(
    con: Connection | Cursor, 
    parent_id: int = 0, 
    /, 
) -> Cursor:
    sql = "SELECT id FROM data WHERE parent_id=? AND is_dir=1;"
    return con.execute(sql, (parent_id,))


def select_mtime_groups(
    con: Connection | Cursor, 
    parent_id: int = 0, 
    /, 
) -> Cursor:
    sql = """\
SELECT mtime, JSON_GROUP_ARRAY(id) AS "ids [JSON]"
FROM data
WHERE parent_id=? AND mtime != 0
GROUP BY mtime
ORDER BY mtime DESC;
"""
    return con.execute(sql, (parent_id,))


def update_dir_ancestors(
    con: Connection | Cursor, 
    ancestors: list[dict], 
    to_replace: list[dict] = [], 
    /, 
    commit: bool = True, 
) -> Cursor:
    if isinstance(con, Cursor):
        cur = con
        con = cur.connection
    else:
        cur = con.cursor()
    items1: dict[int, dict] = {}
    items2: dict[int, dict] = {}
    items = ChainMap(items1, items2)
    path = ""
    for i, a in enumerate(ancestors[1:], 2):
        path += "/" + escape(a["name"])
        items1[a["id"]] = {
            "id": a["id"], 
            "parent_id": a["parent_id"], 
            "name": a["name"], 
            "is_dir": 1, 
            "path": path, 
            "ancestors": ancestors[:i], 
        }
    for a in to_replace:
        if a["is_dir"]:
            items2[a["id"]] = {
                "id": a["id"], 
                "parent_id": a["parent_id"], 
                "name": a["name"], 
                "is_dir": 1, 
                "path": path + "/" + escape(a["name"]), 
                "ancestors": [*ancestors, {"id": a["id"], "parent_id": a["parent_id"], "name": a["name"]}], 
            }
    if not items:
        return cur
    sql = f"""\
SELECT id, parent_id, name, path, JSON_ARRAY_LENGTH(ancestors) AS ancestors_length
FROM data
WHERE id IN {tuple(items)}
ORDER BY LENGTH(path) DESC;
"""
    changed = []
    for row in cur.execute(sql):
        cid = row["id"]
        new = items[cid]
        if row["name"] != new["name"] or row["parent_id"] != new["parent_id"]:
            changed.append({
                "path_old": row["path"], 
                "path_old_stop": len(row["path"]) + 1, 
                "path": new["path"], 
                "ancestors_old_stop": row["ancestors_length"], 
                "ancestors": new["ancestors"], 
            })
    try:
        if changed:
            sql = """\
UPDATE data
SET
    path = :path || SUBSTR(path, :path_old_stop), 
    ancestors = json_array_head_replace(ancestors, :ancestors, :ancestors_old_stop)
WHERE
    path LIKE :path_old || '/%'
"""
            cur.executemany(sql, changed)
        sql = """\
INSERT INTO
    data(id, parent_id, name, is_dir, path, ancestors)
VALUES
    (:id, :parent_id, :name, :is_dir, :path, :ancestors)
ON CONFLICT(id) DO UPDATE SET
    parent_id = excluded.parent_id,
    name      = excluded.name,
    path      = excluded.path,
    ancestors = excluded.ancestors
WHERE
    path != excluded.path;
"""
        cur.executemany(sql, items1.values())
        if commit:
            con.commit()
        return cur
    except BaseException:
        if commit:
            con.rollback()
        raise


def insert_items(
    con: Connection | Cursor, 
    items: dict | Iterable[dict], 
    /, 
    commit: bool = True, 
) -> Cursor:
    sql = """\
INSERT INTO
    data(id, parent_id, pickcode, name, size, sha1, is_dir, is_image, mtime)
VALUES
    (:id, :parent_id, :pickcode, :name, :size, :sha1, :is_dir, :is_image, :mtime)
ON CONFLICT(id) DO UPDATE SET
    parent_id = excluded.parent_id,
    pickcode  = excluded.pickcode,
    name      = excluded.name,
    mtime     = excluded.mtime
WHERE
    mtime != excluded.mtime
"""
    if isinstance(items, dict):
        items = items,
    if commit:
        return execute_commit(con, sql, items, executemany=True)
    else:
        return con.executemany(sql, items)


def delete_items(
    con: Connection | Cursor, 
    ids: int | Iterable[int], 
    /, 
    commit: bool = True, 
) -> Cursor:
    sql = "DELETE FROM data WHERE id=?"
    if isinstance(ids, int):
        ls_ids = [(ids,)]
    else:
        ls_ids = [(id,) for id in ids]
    if commit:
        return execute_commit(con, sql, ls_ids, executemany=True)
    else:
        return con.executemany(sql, ls_ids)


def update_files_time(
    con: Connection | Cursor, 
    parent_id: int = 0, 
    /, 
    commit: bool = True, 
) -> Cursor:
    sql = """\
UPDATE data
SET updated_at = strftime('%Y-%m-%dT%H:%M:%S.%f+08:00', 'now', '+8 hours')
WHERE parent_id = ?;
"""
    if commit:
        return execute_commit(con, sql, (parent_id,))
    else:
        return con.execute(sql, (parent_id,))


def update_path(
    con: Connection | Cursor, 
    parent_id: int = 0, 
    /, 
    ancestors: list[dict] = [], 
    commit: bool = True, 
) -> Cursor:
    sql = """\
UPDATE data
SET
    ancestors = JSON_INSERT(?, '$[#]', JSON_OBJECT('id', id, 'parent_id', parent_id, 'name', name)), 
    path = ? || escape_name(name)
WHERE parent_id=?;
"""
    dirname = "/".join(a["name"] for a in ancestors) + "/"
    if commit:
        return execute_commit(con, sql, (ancestors, dirname, parent_id))
    else:
        return con.execute(sql, (ancestors, dirname, parent_id))


def cleandb(
    con: Connection | Cursor, 
    top_ids: int | Iterable[int] = 0, 
    /, 
    commit: bool = True, 
) -> Cursor:
    if isinstance(top_ids, int):
        ids = "(%s)" % top_ids
    else:
        ids = "(%s)" % (",".join(map(str, top_ids) or "NULL"))
    sql = f"""\
WITH RECURSIVE ancestors(id) AS (
    SELECT
        d1.id
    FROM
        data d1 LEFT JOIN data d2 ON (d2.mtime != 0 AND d1.parent_id = d2.id)
    WHERE
        d1.mtime != 0
        AND d2.id IS NULL
        AND d1.parent_id NOT IN {ids} 

    UNION ALL

    SELECT
        data.id
    FROM
        data JOIN ancestors ON (data.parent_id = ancestors.id)
)
DELETE FROM data WHERE id IN (SELECT id FROM ancestors);
"""
    if commit:
        return execute_commit(con, sql)
    else:
        return con.execute(sql)


def normalize_attr(info: dict, /) -> dict:
    is_dir = "fid" not in info
    if is_dir:
        attr: dict = {"id": int(info["cid"]), "parent_id": int(info["pid"])}
    else:
        attr = {"id": int(info["fid"]), "parent_id": int(info["cid"])}
    attr["pickcode"] = info["pc"]
    attr["name"] = info["n"]
    attr["size"] = info.get("s") or 0
    attr["sha1"] = info.get("sha") or ""
    attr["is_dir"] = is_dir
    attr["is_image"] = not is_dir and bool(info.get("u"))
    attr["mtime"] = int(info.get("te", 0))
    return attr


def iterdir(
    client: P115Client, 
    id: int = 0, 
    /, 
    page_size: int = 1024, 
) -> tuple[int, list[dict], Iterator[dict]]:
    if page_size <= 0:
        page_size = 1024
    payload = {
        "asc": 0, "cid": id, "custom_order": 1, "fc_mix": 1, "limit": min(16, page_size), 
        "show_dir": 1, "o": "user_utime", "offset": 0, 
    }
    fs_files = client.fs_files
    count = -1
    ancestors = [{"id": 0, "parent_id": 0, "name": ""}]

    def get_files():
        nonlocal count
        resp = check_response(fs_files(payload))
        if int(resp["path"][-1]["cid"]) != id:
            if count < 0:
                raise NotADirectoryError(ENOTDIR, f"not a dir or deleted: {id}")
            else:
                raise FileNotFoundError(ENOENT, f"no such dir: {id}")
        ancestors[1:] = (
            {"id": int(info["cid"]), "parent_id": int(info["pid"]), "name": info["name"]} 
            for info in resp["path"][1:]
        )
        if count < 0:
            count = resp["count"]
        elif count != resp["count"]:
            raise OSBusyError(f"detected count changes during iteration: {id}")
        return resp

    resp = get_files()

    def iter():
        nonlocal resp
        offset = 0
        payload["limit"] = page_size
        while True:
            yield from map(normalize_attr, resp["data"])
            offset += len(resp["data"])
            if offset >= count:
                break
            payload["offset"] = offset
            resp = get_files()

    return count, ancestors, iter()


def diff_dir(
    con: Connection | Cursor, 
    client: P115Client, 
    id: int = 0, 
    /, 
):
    n = 0
    saved: dict[int, set[int]] = {}
    for mtime, ls in select_mtime_groups(con, id):
        saved[mtime] = set(ls)
        n += len(ls)

    replace_list: list[dict] = []
    delete_list: list[int] = []
    count, ancestors, data_it = iterdir(client, id)
    if not n:
        replace_list.extend(data_it)
        return ancestors, delete_list, replace_list

    seen: set[int] = set()
    seen_add = seen.add
    it = iter(saved.items())
    his_mtime, his_ids = next(it)
    for attr in data_it:
        cur_id = attr["id"]
        if cur_id in seen:
            raise OSBusyError(f"duplicate id found: {cur_id}")
        seen_add(cur_id)
        cur_mtime = attr["mtime"]
        while his_mtime > cur_mtime:
            delete_list.extend(his_ids - seen)
            n -= len(his_ids)
            if not n:
                replace_list.append(attr)
                replace_list.extend(data_it)
                return ancestors, delete_list, replace_list
            his_mtime, his_ids = next(it)
        if his_mtime == cur_mtime:
            if cur_id in his_ids:
                n -= 1
                if count - len(seen) == n:
                    return ancestors, delete_list, replace_list
                his_ids.remove(cur_id)
        else:
            replace_list.append(attr)
    for _, his_ids in it:
        delete_list.extend(his_ids - seen)
    return ancestors, delete_list, replace_list


def updatedb_one(
    client: str | P115Client, 
    dbfile: None | str | Connection | Cursor = None, 
    id: int = 0, 
):
    if isinstance(client, str):
        client = P115Client(client, check_for_relogin=True)
    if not dbfile:
        dbfile = f"115-{client.user_id}.db"
    if isinstance(dbfile, (Connection, Cursor)):
        con = dbfile
        try:
            ancestors, to_delete, to_replace = diff_dir(con, client, id)
            logger.info("[\x1b[1;32mGOOD\x1b[0m] %s", id)
        except BaseException as e:
            logger.exception("[\x1b[1;31mFAIL\x1b[0m] %s", id)
            if isinstance(e, (FileNotFoundError, NotADirectoryError)):
                delete_items(con, id)
            raise
        else:
            update_dir_ancestors(con, ancestors, to_replace, commit=False)
            if to_delete:
                delete_items(con, to_delete, commit=False)
            if to_replace:
                insert_items(con, to_replace, commit=False)
                update_path(con, id, ancestors=ancestors, commit=False)
            update_files_time(con, id, commit=False)
            do_commit(con)
    else:
        with connect(
            dbfile, 
            detect_types=PARSE_DECLTYPES|PARSE_COLNAMES, 
            uri=dbfile.startswith("file:"), 
        ) as con:
            initdb(con)
            updatedb_one(client, con, id)


def updatedb(
    client: str | P115Client, 
    dbfile: None | str | Connection | Cursor = None, 
    top_ids: int | tuple[int, ...] = 0, 
    clean: bool = True, 
):
    if isinstance(client, str):
        client = P115Client(client, check_for_relogin=True)
    if not dbfile:
        dbfile = f"115-{client.user_id}.db"
    if isinstance(dbfile, (Connection, Cursor)):
        con = dbfile
        seen: set[int] = set()
        seen_add = seen.add
        dq: deque[int] = deque()
        push, pop = dq.append, dq.popleft
        if isinstance(top_ids, int):
            top_ids = top_ids,
        all_top_ids: set[int] = set()
        for top_id in top_ids:
            if top_id in all_top_ids:
                continue
            else:
                all_top_ids.add(top_id)
            push(top_id)
            while dq:
                id = pop()
                if id in seen:
                    print("[\x1b[1;33mSKIP\x1b[0m]", id)
                    continue
                try:
                    updatedb_one(client, con, id)
                except (FileNotFoundError, NotADirectoryError):
                    pass
                except OSBusyError:
                    logger.warning("[\x1b[1;34mREDO\x1b[0m] %s", id)
                    push(id)
                else:
                    seen_add(id)
                    dq.extend(r[0] for r in select_subdir_ids(con, id))
        if clean and all_top_ids:
            cleandb(con, all_top_ids)
    else:
        with connect(
            dbfile, 
            detect_types=PARSE_DECLTYPES|PARSE_COLNAMES, 
            uri=dbfile.startswith("file:"), 
        ) as con:
            initdb(con)
            updatedb(client, con, top_ids)
            con.execute("PRAGMA wal_checkpoint;")
            con.execute("VACUUM;")


if __name__ == "__main__":
    if args.cookies:
        cookies = args.cookies
    else:
        from pathlib import Path

        if args.cookies_path:
            cookies = Path(args.cookies_path).absolute()
        else:
            for path in (
                Path("./115-cookies.txt").absolute(), 
                Path("~/115-cookies.txt").expanduser(), 
                Path(__file__).parent / "115-cookies.txt", 
            ):
                if path.is_file():
                    cookies = path
            else:
                cookies = Path("~/115-cookies.txt").expanduser()
    client = P115Client(cookies, check_for_relogin=True)
    updatedb(client, dbfile=args.dbfile, top_ids=args.top_ids or 0)

