#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["format_mode", "format_size", "format_time", "format_timestamp"]

import stat

from datetime import datetime, timezone
from email.utils import format_datetime
from stat import S_IFMT, S_IMODE
from typing import Final, Literal


FILE_TYPE: Final[dict[int, str]] = {
    stat.S_IFBLK: "b", 
    stat.S_IFCHR: "c", 
    stat.S_IFDIR: "d", 
    stat.S_IFLNK: "l", 
    stat.S_IFIFO: "p", 
    stat.S_IFSOCK: "s", 
    stat.S_IFREG: "-", 
}


def format_mode(
    mode: int, 
    /, 
    with_type: bool = True, 
) -> str:
    """Formats the file mode (permissions) into a human-readable string.

    :param mode: The file mode (permissions) in integer format, typically obtained from os.stat().
    :param with_type: A flag indicating whether to include the file type prefix
                      (e.g., "d" for directory, "-" for regular file, "l" for symlink).

    :return: A formatted string representing the file's permissions.
    """
    if with_type:
        prefix = FILE_TYPE.get(S_IFMT(mode), "-")
    else:
        prefix = ""
    m = f"{S_IMODE(mode):09b}"
    return prefix + "".join(
        c if b == "1" else "-"
        for b, c in zip(m, "rwx" * 3)
    )


def format_size(
    n: int, 
    /, 
    unit: None | Literal["", "K", "M", "G", "T", "P", "E", "Z", "Y", "B", "GP", "S", "H", "A"] = None, 
    precision: int = 2, 
) -> str:
    """Converts a given number of bytes (n) into a human-readable string with appropriate units 
    (e.g., KB, MB, GB), and specified precision.

    .. note::
        1. ""    = B (Byte)        = 8 bit
        2. "K"   = KB (Kilobyte)   = 1,024 B
        3. "M"   = MB (Megabyte)   = 1,024 KB  = 1,048,576 B
        4. "G"   = GB (Gigabyte)   = 1,024 MB  = 1,073,741,824 B
        5. "T"   = TB (Terabyte)   = 1,024 GB  = 1,099,511,627,776 B
        6. "P"   = PB (Petabyte)   = 1,024 TB  = 1,125,899,906,842,624 B
        7. "E"   = EB (Exabyte)    = 1,024 PB  = 1,152,921,504,606,846,976 B
        8. "Z"   = ZB (Zettabyte)  = 1,024 EB  = 1,180,591,620,717,411,303,424 B
        9. "Y"   = YB (Yottabyte)  = 1,024 ZB  = 1,208,925,819,614,629,174,706,176 B
        10. "B"  = BB (Brontobyte) = 1,024 YB  = 1,238,800,418,099,975,609,206,999,744 B
        11. "GP" = GPB (Geopbyte)  = 1,024 BB  = 1,267,512,729,036,354,482,741,757,212,160 B
        12. "S"  = SB (Sandrobyte) = 1,024 GPB = 1,295,446,145,648,250,123,456,435,798,128 B
        13. "H"  = HB (HellaByte)  = 1,024 SB  = 1,323,680,213,591,889,151,512,532,579,801,600 B
        14. "A"  = AB (Alphabyte)  = 1,024 HB  = 1,352,215,508,049,890,905,587,086,961,027,788,800 B

    :param n: The size in bytes to be formatted.
    :param unit: The unit to scale to (e.g., "K", "M", "G", etc.). If not provided, the function auto-scales the size to the appropriate unit based on the value of n.
    :param precision: The number of decimal places to include in the formatted result. Default is 2.

    :return: A string representing the size with the appropriate unit, rounded to the specified precision.
    """
    if n < 1024 and not unit:
        return f"{n} B"
    b = 1
    b2 = 1024
    for u in ["K", "M", "G", "T", "P", "E", "Z", "Y", "B", "GP", "S", "H", "A"]:
        b, b2 = b2, b2 << 10
        if u == unit if unit else n < b2:
            break
    return f"%.{precision}f {u}B" % (n / b)


def format_time(t: int | float, /) -> str:
    """Formats a given time value (t) in seconds into a human-readable time format, supporting various time formats: minutes, hours, and days.

    :param t: The time in seconds to be formatted.

    :return: A string representing the time in a readable format. The format depends on the value of t.

        - Less than 60 seconds: `MM:SS` OR `MM:SS.mmmmmm` (if the input has fractional seconds).
        - Less than 60 minutes: `MM:SS` OR `MM:SS.mmmmmm`.
        - Less than 24 hours: `HH:MM:SS` OR `HH:MM:SS.mmmmmm`.
        - More than 24 hours: `DdHH:MM:SS` OR `DdHH:MM:SS.mmmmmm`.
    """
    m, s = divmod(t, 60)
    if isinstance(s, float):
        ss = f"{s:09.06f}"
    else:
        ss = f"{s:02d}"
    m = int(m)
    if m < 60:
        return f"{m:02d}:{ss}"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h:02d}:{m:02d}:{ss}"
    d, h = divmod(h, 24)
    return f"{d}d{h:02d}:{m:02d}:{ss}"


def format_timestamp(ts: int | float, /, format: str = "") -> str:
    """Formats a Unix timestamp (ts) into a string representation of the corresponding date and time, based on the specified format. The function supports multiple output formats, including default, ASCII, ISO 8601, GMT, and custom formatting.

    :param ts: The Unix timestamp (in seconds) to be formatted.
    :param format: The format in which the timestamp should be represented.

        - "": Default format (`datetime.datetime.__str__()`).
        - "asc": ASCII representation of the time (`datetime.datetime.ctime()`).
        - "iso": ISO 8601 format (`datetime.datetime.isoformat()`).
        - "gmt": GMT format (using `email.utils.format_datetime()` with UTC timezone).
        - Custom format: Any string format accepted by `strftime()` for a custom date-time representation.

    :return: A string representing the formatted timestamp according to the specified format.
    """
    match format:
        case "":
            return str(datetime.fromtimestamp(ts))
        case "asc":
            return datetime.fromtimestamp(ts).ctime()
        case "iso":
            return datetime.fromtimestamp(ts).isoformat()
        case "gmt":
            return format_datetime(datetime.fromtimestamp(ts, timezone.utc), usegmt=True)
        case _:
            return datetime.fromtimestamp(ts).strftime(format)

