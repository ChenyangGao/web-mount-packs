#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["SQLiteHandler", "setup_logger"]

import logging

from datetime import datetime
from os import fsdecode, PathLike
from sqlite3 import connect, register_converter, Connection, Cursor, PARSE_DECLTYPES
from tempfile import mktemp
from typing import Final, IO
from uuid import uuid4


FIELDS: Final = ("id", "time", "level", "message")
register_converter("DATETIME", lambda dt: datetime.fromisoformat(str(dt, "utf-8")))


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


class SQLiteHandler(logging.Handler):

    def __init__(
        self, 
        /, 
        level=logging.NOTSET, 
        dbfile: bytes | str | PathLike = "", 
    ):
        super().__init__(level)
        if dbfile:
            self._tempfile = ""
        else:
            dbfile = self._tempfile = mktemp(prefix=f"{uuid4()}-", suffix=".db")
        self.dbfile = dbfile
        self.con = connect(dbfile, check_same_thread=False, autocommit=True)
        self.con.executescript("""\
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+08:00', 'now', '+8 hours')),
    level TEXT NOT NULL DEFAULT 'NOTSET',
    message TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_logs_time ON logs(time);""")

    def close(self, /):
        from contextlib import suppress
        with suppress(AttributeError, OSError):
            self.con.close()
            if dbfile := self._tempfile:
                from os import remove
                remove(dbfile)
                remove(dbfile+"-shm")
                remove(dbfile+"-wal")
        super().close()

    def emit(self, record: logging.LogRecord, /):
        self.con.execute("INSERT INTO logs (time, level, message) VALUES (?, ?, ?)", (
            datetime.fromtimestamp(record.created).isoformat(), 
            record.levelname, 
            self.format(record), 
        ))

    def fetch(self, n: int = 20, /, con: None | Connection | Cursor = None) -> list[dict]:
        """Get the latest n logs.
        """
        if con is None:
            con = self.con
        return [
            dict(zip(FIELDS, record)) for record in 
            con.execute("""\
WITH last_n AS (
    SELECT id, time, level, message FROM logs ORDER BY id DESC LIMIT ?
)
SELECT * FROM last_n ORDER BY id
            """, (n,))
        ]

    def pull(self, n: int = 20, /):
        """Continuously pulling logs.
        """
        sql = "SELECT id, time, level, message FROM logs WHERE id > ?;"
        last_id = 0
        with connect(self.dbfile, check_same_thread=False, detect_types=PARSE_DECLTYPES) as con:
            cursor = con.cursor()
            logs = self.fetch(n, cursor)
            while True:
                yield logs
                if logs:
                    last_id = logs[-1]["id"]
                logs = [dict(zip(FIELDS, record)) for record in cursor.execute(sql, (last_id,))]


def setup_logger(
    dbfile: bytes | str | PathLike = "", 
    level: int = logging.NOTSET, 
    formatter: bool | str | logging.Formatter = False, 
    logger: str | logging.Logger = logging.root, 
    stream: bool | IO[str] = False, 
    filename: bytes | str | PathLike = "", 
) -> tuple[logging.Logger, SQLiteHandler]:
    """Initialize a logger object and store the data into the SQLite database.

    :param dbfile: SQLite db file path, if it's an empty string, use temporary file.
    :param level: Logger level.
    :param formatter: Output formatter object for logs. If True, it will be determined automatically.
    :param logger: Logger object or name of the logger object.
    :param stream: Write logs into a stream.
    :param filename: Write logs into a file.

    :return: A logger object.

    .. note::
        If you want to fetch the last 20 records, you can use

        .. code: python

            logger, handler = setup_logger()
            handler.fetch(20)

        If you want to continuously pull logs, you can use

        .. code: python

            logger, handler = setup_logger()
            for logs in handler.pull():
                ...
    """
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    handler = SQLiteHandler(dbfile=dbfile)
    if formatter:
        if formatter is True:
            formatter = ColoredLevelNameFormatter(
                "[\x1b[1m%(asctime)s\x1b[0m] (%(levelname)s) \x1b[1;3;36m%(funcName)s\x1b[0m"
                " @ \x1b[1;34m%(name)s\x1b[0m \x1b[5;31m➜\x1b[0m %(message)s"
            )
        elif isinstance(formatter, str):
            formatter = logging.Formatter(formatter)
        handler.setFormatter(formatter)
    if level:
        logger.setLevel(level)
    logger.addHandler(handler)
    setattr(logger, "fetch", handler.fetch)
    setattr(logger, "pull", handler.pull)
    if stream:
        shandler = logging.StreamHandler(None if stream is True else stream)
        if formatter:
            shandler.setFormatter(formatter)
        logger.addHandler(shandler)
    filename = fsdecode(filename)
    if filename:
        fhandler = logging.FileHandler(filename)
        if formatter:
            fhandler.setFormatter(formatter)
        logger.addHandler(fhandler)
    return logger, handler

