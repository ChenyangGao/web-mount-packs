#!/usr/bin/env python3
# encoding: utf-8

# TODO: 允许传入 cookies 或 路径
# TODO: 支持多个不同登录设备并发
# TODO: 支持同一个 cookies 并发因子，默认值 1
# TODO: 使用协程进行并发，而非多线程
# TODO: 如果请求超时，则需要进行重试
# TODO: 由于一个文件夹里面的变动不可能太多，所以应该使用递增 limit 的方式去获取列表（有时候可能只变动了几个，但文件夹里面有几千个文件，前 2 次拉取应该以适量为主）
# TODO: 很多文件的更新时间是一样的，但是它们内部却有排序，如何在sqlite数据库里面，也能保持这种顺序，这样的话，就不需要专门为相同的更新时间来分组了

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 0)
__all__ = ["run"]
__doc__ = "遍历 115 网盘的目录信息导出到数据库"

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, 
        description=__doc__, 
    )
    parser.add_argument("top_ids", metavar="dirid", nargs="*", type=int, help="115 目录 id，可以传入多个，如果不传默认为 0")
    parser.add_argument("-f", "--dbfile", default="115.db", help="sqlite 数据库文件路径，默认为当前工作目录下 115.db")
    parser.add_argument("-v", "--version", action="store_true", help="输出版本号")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)

from collections import deque
from collections.abc import Iterator
from contextlib import closing
from json import dumps
from pathlib import Path
from sqlite3 import connect
from types import MappingProxyType

from p115 import check_response, P115Client


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


def select_subdir_ids(con, parent_id: int = 0, /):
    sql = '''SELECT id FROM data WHERE parent_id=? AND is_dir=1'''
    with closing(con.cursor()) as cur:
        cur.execute(sql, (parent_id,))
        return [id for id, in cur]


def select_grouped_mtime(con, parent_id: int = 0, /):
    sql = '''\
SELECT id, mtime
FROM data
WHERE parent_id=?
ORDER BY mtime DESC;'''
    d: dict[int, set[int]] = {}
    last_mtime = 0
    with closing(con.cursor()) as cur:
        cur.execute(sql, (parent_id,))
        n = 0
        for n, (id, mtime) in enumerate(cur, 1):
            if last_mtime != mtime:
                s = d[mtime] = set()
                add = s.add
            add(id)
        return n, d


def replace_items(con, items, /):
    sql = '''\
INSERT OR REPLACE INTO 
    data(id, parent_id, name, is_dir, size, pickcode, sha1, is_image, mtime) 
VALUES
    (?,?,?,?,?,?,?,?,?);'''
    try:
        con.executemany(sql, items)
        con.commit()
    except BaseException as e:
        con.rollback()
        raise


def delete_items(con, ids: int | tuple[int, ...] = 0, /):
    sql = '''DELETE FROM data WHERE id=?'''
    if isinstance(ids, int):
        ids_ = [(ids,)]
    else:
        ids_ = [(id,) for id in ids]
    try:
        con.executemany(sql, ids_)
        con.commit()
    except BaseException as e:
        con.rollback()
        raise


def update_ancestors(con, parent_id: int = 0, /, ancestors: list[dict] = []):
    sql = '''\
UPDATE
    data
SET
    ancestors = JSON_INSERT(?, '$[#]', JSON_OBJECT('id', id, 'name', name))
WHERE
    parent_id=?;'''
    json_str = dumps(ancestors, ensure_ascii=False)
    try:
        con.execute(sql, (json_str, parent_id))
        con.commit()
    except BaseException as e:
        con.rollback()
        raise


def clean(con, top_ids: int | tuple[int, ...] = 0, /):
    if isinstance(top_ids, int):
        ids = "(%s)" % top_ids
    else:
        ids = "(%s)" % (",".join(map(str, top_ids) or "NULL"))
    sql = f'''\
WITH RECURSIVE ancestors(id) AS (
    SELECT
        d1.id
    FROM
        data d1 LEFT JOIN data d2 ON d1.parent_id = d2.id
    WHERE 
        d1.parent_id NOT IN {ids} AND d2.id IS NULL

    UNION ALL

    SELECT data.id
    FROM data
    JOIN ancestors ON data.parent_id = ancestors.id
)
DELETE FROM data WHERE id in (SELECT id FROM ancestors);
'''
    try:
        con.execute(sql)
        con.commit()
    except BaseException as e:
        con.rollback()
        raise


def normalize_attr(info):
    is_dir = "fid" not in info
    if is_dir:
        attr = {"id": int(info["cid"]), "parent_id": int(info["pid"])}
    else:
        attr = {"id": int(info["fid"]), "parent_id": int(info["cid"])}    
    attr["name"] = info["n"]
    attr["is_dir"] = is_dir
    attr["size"] = info.get("s")
    attr["pickcode"] = info.get("pc")
    attr["sha1"] = info.get("sha")
    attr["is_image"] = not is_dir and bool(info.get("u"))
    attr["mtime"] = int(info.get("te", 0))
    return attr


def iterdir(client: P115Client, id: int = 0, /):
    payload = {"asc": 0, "cid": id, "custom_order": 1, "fc_mix": 1, "limit": 1, "show_dir": 1, "o": "user_utime"}
    files = check_response(get_files(client, payload))
    if int(files["path"][-1]["cid"]) != id:
        raise NotADirectoryError
    count = files["count"]
    ancestors = [{"id": 0, "name": ""}]
    ancestors.extend({"id": int(info["cid"]), "name": info["name"]} for info in files["path"][1:])
    d = {}
    def iter():
        nonlocal files
        if count:
            attr = normalize_attr(files["data"][0])
            subid = attr["id"]
            d[subid] = attr
            yield attr
            for offset, limit in cut_iter(1, count, 1_000):
                payload["offset"] = offset
                payload["limit"] = limit
                files = check_response(get_files(client, payload))
                if int(files["path"][-1]["cid"]) != id:
                    raise NotADirectoryError
                if files["count"] != count:
                    raise RuntimeError
                for attr in map(normalize_attr, files["data"]):
                    subid = attr["id"]
                    if subid in d:
                        raise RuntimeError
                    d[subid] = attr
                    yield attr
    return ancestors, count, MappingProxyType(d), iter()


def diff_dir(con, client: P115Client, id: int = 0, /):
    n, saved = select_grouped_mtime(con, id)
    ancestors, count, collected, data_it = iterdir(client, id)
    if not n:
        return ancestors, [tuple(attr.values()) for attr in data_it], []
    seen = collected.keys()
    replace_list: list[tuple] = []
    delete_list: list[int] = []
    it = iter(saved.items())
    his_mtime, his_ids = next(it)
    for attr in data_it:
        cur_mtime = attr["mtime"]
        while his_mtime > cur_mtime:
            delete_list.extend(his_ids - seen)
            n -= len(his_ids)
            if not n:
                replace_list.extend(tuple(attr.values()) for attr in data_it)
                return ancestors, replace_list, delete_list
            his_mtime, his_ids = next(it)
        if his_mtime == cur_mtime:
            cur_id = attr["id"]
            if cur_id in his_ids:
                n -= 1
                his_ids.remove(cur_id)
                if count - len(seen) == n:
                    return ancestors, replace_list, delete_list
        else:
            replace_list.append(tuple(attr.values()))
    for _, his_ids in it:
        delete_list.extend(his_ids - seen)
    return ancestors, replace_list, delete_list


def run(
    client: P115Client, 
    dbfile: str = "115.db", 
    top_ids: int | tuple[int, ...] = 0, 
):
    with connect(dbfile) as con:
        con.execute('PRAGMA journal_mode = WAL;')
        con.execute('''\
CREATE TABLE IF NOT EXISTS "data" (
    "id" INTEGER,
    "parent_id" INTEGER NOT NULL DEFAULT 0,
    "name" TEXT,
    "is_dir" INTEGER CHECK("is_dir" IN (0, 1)),
    "size" INTEGER,
    "pickcode" TEXT,
    "sha1" TEXT,
    "is_image" INTEGER CHECK("is_image" IN (0, 1)),
    "mtime" INTEGER,
    "ancestors" JSON,
    PRIMARY KEY("id")
);''')
        con.execute('''\
CREATE INDEX IF NOT EXISTS "idx_parent_id" ON "data" (
    "parent_id"
);''')
        con.execute('''\
CREATE VIEW IF NOT EXISTS "id_to_relpath" AS
WITH RECURSIVE ancestors(id, relpath) AS (
    SELECT
        d1.id, 
        JSON_ARRAY(JSON(CONCAT('{"id": ', d1.id,', "name": ', JSON_QUOTE(d1.name), '}')))
    FROM
        data d1 LEFT JOIN data d2 ON d1.parent_id = d2.id
    WHERE 
        d2.id IS NULL

    UNION ALL

    SELECT 
        data.id, 
        JSON_INSERT(
            ancestors.relpath, 
            '$[#]', 
            JSON(CONCAT('{"id": ', data.id,', "name": ', JSON_QUOTE(data.name), '}'))
        )
    FROM 
        data JOIN ancestors ON data.parent_id = ancestors.id
)
SELECT * FROM ancestors;
''')
        con.execute('''\
CREATE VIEW IF NOT EXISTS "data_with_relpath" AS
SELECT 
    *
FROM 
    data JOIN id_to_relpath USING (id);
''')
        dq: deque[int] = deque()
        if isinstance(top_ids, int):
            dq.append(top_ids)
        else:
            dq.extend(top_ids)
        while dq:
            id = dq.popleft()
            print("[\x1b[1;32mGOOD\x1b[0m]", id)
            try:
                ancestors, to_replace, to_delete = diff_dir(con, client, id)
            except NotADirectoryError:
                delete_items(con, id)
                print("[\x1b[1;31mFAIL\x1b[0m]", id)
                continue
            except RuntimeError:
                dq.appendleft(id)
                print("[\x1b[1;33mREDO\x1b[0m]", id)
                continue
            if to_replace:
                replace_items(con, to_replace)
            if to_delete:
                delete_items(con, to_delete)
            update_ancestors(con, id, ancestors=ancestors)
            dq.extend(select_subdir_ids(con, id))
        clean(con, top_ids)
        con.execute('PRAGMA wal_checkpoint;')
        con.execute('VACUUM;')


if __name__ == "__main__":
    get_files = P115Client.fs_files
    client = P115Client(Path("~/115-cookies.txt").expanduser(), check_for_relogin=True)
    run(client, dbfile=args.dbfile, top_ids=args.top_ids or 0)

