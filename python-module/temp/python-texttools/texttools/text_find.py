#!/usr/bin/env python3
# coding: utf-8

# TODO 为 text_before、text_after、text_between 各增加一个 _iter 版本，且支持参数 reverse=True
# TODO 为 text_finditer 增加参数 reverse=True

__author__  = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 0)
__all__ = ["Span", "text_find", "text_finditer", "text_before", "text_after", "text_between"]

from itertools import islice
from collections import deque
from typing import cast, AnyStr, Iterator, NamedTuple, Optional


class Span(NamedTuple):
    start: int
    stop: int


def text_find(
    text: AnyStr, 
    pattern, 
    /, 
    index: int = 0, 
    begin: Optional[int] = None, 
) -> Span:
    """

    DOCTEST & EXAMPLES::
        >>> text_find("<a>0</a><a>1</a>@", "<a>")
        Span(start=0, stop=3)
        >>> text_find("<a>0</a><a>1</a>@", "<a>", 1)
        Span(start=8, stop=11)
        >>> text_find("<a>0</a><a>1</a>@", "<a>", 2)
        Span(start=17, stop=17)
        >>> text_find("<a>0</a><a>1</a>@", "<a>", -1)
        Span(start=8, stop=11)
        >>> text_find("<a>0</a><a>1</a>@", "<a>", -2)
        Span(start=0, stop=3)
        >>> text_find("<a>0</a><a>1</a>@", "<a>", -3)
        Span(start=0, stop=0)
        >>> text_find("<a>0</a><a>1</a>@", "<a>", begin=1)
        Span(start=8, stop=11)
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>")
        Span(start=0, stop=3)
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>", 1)
        Span(start=8, stop=11)
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>", 2)
        Span(start=17, stop=17)
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>", -1)
        Span(start=8, stop=11)
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>", -2)
        Span(start=0, stop=3)
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>", -3)
        Span(start=0, stop=0)
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>", begin=1)
        Span(start=8, stop=11)
        >>> import re
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"))
        Span(start=0, stop=3)
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"), 1)
        Span(start=8, stop=11)
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"), 2)
        Span(start=17, stop=17)
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"), -1)
        Span(start=8, stop=11)
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"), -2)
        Span(start=0, stop=3)
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"), -3)
        Span(start=0, stop=0)
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"), begin=1)
        Span(start=8, stop=11)
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"))
        Span(start=0, stop=3)
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), 1)
        Span(start=8, stop=11)
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), 2)
        Span(start=17, stop=17)
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), -1)
        Span(start=8, stop=11)
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), -2)
        Span(start=0, stop=3)
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), -3)
        Span(start=0, stop=0)
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), begin=1)
        Span(start=8, stop=11)
    """
    text_len = len(text)
    if begin is None:
        begin = 0 if index >= 0 else text_len
    elif begin < 0:
        begin += text_len
    if begin < 0:
        begin = 0
    elif begin > text_len:
        begin = text_len
    if text_len == 0:
        return Span(0, 0)
    elif index < 0 and begin == 0 or index >= 0 and begin == text_len:
        return Span(begin, begin)
    if isinstance(pattern, (bytes, str)):
        pattern = cast(AnyStr, pattern)
        patn_len = len(pattern)
        if patn_len == 0:
            if index >= 0:
                index = min(begin+index, text_len)
            else:
                index = max(begin+1+index, 0)
            return Span(index, index)
        if index >= 0:
            find = text.find
            start = begin
            for _ in range(-1, index):
                i = find(pattern, start)
                if i == -1:
                    return Span(text_len, text_len)
                start = i + patn_len
            return Span(start-patn_len, start)
        else:
            rfind = text.rfind
            stop = begin
            for _ in range(-index):
                i = rfind(pattern, 0, stop)
                if i < 0:
                    return Span(0, 0)
                stop = i
            return Span(stop, stop+patn_len)
    elif index >= 0:
        try:
            start, stop = next(islice(pattern.finditer(text[begin:]), index, None)).span()
            return Span(start + begin, stop + begin)
        except StopIteration:
            return Span(text_len, text_len)
    else:
        dq = deque(pattern.finditer(text[:begin]), maxlen=-index)
        if len(dq) == -index:
            return Span(*dq[0].span())
        else:
            return Span(0, 0)


def text_finditer(
    text: AnyStr, 
    pattern, 
    /, 
) -> Iterator[Span]:
    """

    DOCTEST & EXAMPLES::
        >>> tuple(text_finditer("<a>0</a><a>1</a>@", "<a>"))
        (Span(start=0, stop=3), Span(start=8, stop=11))
        >>> tuple(text_finditer(b"<a>0</a><a>1</a>@", b"<a>"))
        (Span(start=0, stop=3), Span(start=8, stop=11))
        >>> import re
        >>> tuple(text_finditer("<a>0</a><a>1</a>@", re.compile("<a>")))
        (Span(start=0, stop=3), Span(start=8, stop=11))
        >>> tuple(text_finditer(b"<a>0</a><a>1</a>@", re.compile(b"<a>")))
        (Span(start=0, stop=3), Span(start=8, stop=11))
    """
    if isinstance(pattern, (bytes, str)):
        pattern = cast(AnyStr, pattern)
        text_len = len(text)
        patn_len = len(pattern)
        if text_len == 0:
            if patn_len == 0:
                yield Span(0, 0)
            return
        if patn_len == 0:
            for i in range(text_len+1):
                yield Span(i, i)
            return
        find = text.find
        start = 0
        while True:
            i = find(pattern, start)
            if i == -1:
                return
            yield Span(i, (start := i + patn_len))
    else:
        for match in pattern.finditer(text):
            yield Span(*match.span())


def text_before(
    text: AnyStr, 
    prefix, 
    /, 
    index: int = 0, 
    with_match: bool = False, 
) -> AnyStr:
    """

    DOCTEST & EXAMPLES::
        >>> text_before("<a>0</a><a>1</a>@", "<a>")
        ''
        >>> text_before("<a>0</a><a>1</a>@", "<a>", 1)
        '<a>0</a>'
        >>> text_before("<a>0</a><a>1</a>@", "<a>", 2)
        '<a>0</a><a>1</a>@'
        >>> text_before("<a>0</a><a>1</a>@", "<a>", -1)
        '<a>0</a>'
        >>> text_before("<a>0</a><a>1</a>@", "<a>", -2)
        ''
        >>> text_before(b"<a>0</a><a>1</a>@", b"<a>")
        b''
        >>> text_before(b"<a>0</a><a>1</a>@", b"<a>", 1)
        b'<a>0</a>'
        >>> text_before(b"<a>0</a><a>1</a>@", b"<a>", 2)
        b'<a>0</a><a>1</a>@'
        >>> text_before(b"<a>0</a><a>1</a>@", b"<a>", -1)
        b'<a>0</a>'
        >>> text_before(b"<a>0</a><a>1</a>@", b"<a>", -2)
        b''
        >>> import re
        >>> text_before("<a>0</a><a>1</a>@", re.compile("<a>"))
        ''
        >>> text_before("<a>0</a><a>1</a>@", re.compile("<a>"), 1)
        '<a>0</a>'
        >>> text_before("<a>0</a><a>1</a>@", re.compile("<a>"), 2)
        '<a>0</a><a>1</a>@'
        >>> text_before("<a>0</a><a>1</a>@", re.compile("<a>"), -1)
        '<a>0</a>'
        >>> text_before("<a>0</a><a>1</a>@", re.compile("<a>"), -2)
        ''
        >>> text_before(b"<a>0</a><a>1</a>@", re.compile(b"<a>"))
        b''
        >>> text_before(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), 1)
        b'<a>0</a>'
        >>> text_before(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), 2)
        b'<a>0</a><a>1</a>@'
        >>> text_before(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), -1)
        b'<a>0</a>'
        >>> text_before(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), -2)
        b''
        >>> text_before("<a>0</a><a>1</a>@", "<a>", with_match=True)
        '<a>'
        >>> text_before("<a>0</a><a>1</a>@", "<a>", 1, with_match=True)
        '<a>0</a><a>'
        >>> text_before("<a>0</a><a>1</a>@", "<a>", 2, with_match=True)
        '<a>0</a><a>1</a>@'
        >>> text_before("<a>0</a><a>1</a>@", "<a>", -1, with_match=True)
        '<a>0</a><a>'
        >>> text_before("<a>0</a><a>1</a>@", "<a>", -2, with_match=True)
        '<a>'
    """
    return text[:text_find(text, prefix, index)[with_match]]


def text_after(
    text: AnyStr, 
    suffix, 
    /, 
    index: int = 0, 
    with_match: bool = False, 
) -> AnyStr:
    """

    DOCTEST & EXAMPLES::
        >>> text_after("<a>0</a><a>1</a>@", "<a>")
        '0</a><a>1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", "<a>", 1)
        '1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", "<a>", 2)
        ''
        >>> text_after("<a>0</a><a>1</a>@", "<a>", -1)
        '1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", "<a>", -2)
        '0</a><a>1</a>@'
        >>> text_after(b"<a>0</a><a>1</a>@", b"<a>")
        b'0</a><a>1</a>@'
        >>> text_after(b"<a>0</a><a>1</a>@", b"<a>", 1)
        b'1</a>@'
        >>> text_after(b"<a>0</a><a>1</a>@", b"<a>", 2)
        b''
        >>> text_after(b"<a>0</a><a>1</a>@", b"<a>", -1)
        b'1</a>@'
        >>> text_after(b"<a>0</a><a>1</a>@", b"<a>", -2)
        b'0</a><a>1</a>@'
        >>> import re
        >>> text_after("<a>0</a><a>1</a>@", re.compile("<a>"))
        '0</a><a>1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", re.compile("<a>"), 1)
        '1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", re.compile("<a>"), 2)
        ''
        >>> text_after("<a>0</a><a>1</a>@", re.compile("<a>"), -1)
        '1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", re.compile("<a>"), -2)
        '0</a><a>1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", "<a>", with_match=True)
        '<a>0</a><a>1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", "<a>", 1, with_match=True)
        '<a>1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", "<a>", 2, with_match=True)
        ''
        >>> text_after("<a>0</a><a>1</a>@", "<a>", -1, with_match=True)
        '<a>1</a>@'
        >>> text_after("<a>0</a><a>1</a>@", "<a>", -2, with_match=True)
        '<a>0</a><a>1</a>@'
    """
    return text[text_find(text, suffix, index)[not with_match]:]


def text_between(
    text: AnyStr, 
    prefix, 
    suffix, 
    /, 
    index: int = 0, 
    with_match: bool = False, 
) -> AnyStr:
    """

    DOCTEST & EXAMPLES::
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>")
        '0'
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", 1)
        '1'
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", 2)
        ''
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", -1)
        '1'
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", -2)
        '0'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", b"</a>")
        b'0'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", b"</a>", 1)
        b'1'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", b"</a>", 2)
        b''
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", b"</a>", -1)
        b'1'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", b"</a>", -2)
        b'0'
        >>> import re
        >>> text_between("<a>0</a><a>1</a>@", re.compile("<a>"), "</a>")
        '0'
        >>> text_between("<a>0</a><a>1</a>@", re.compile("<a>"), "</a>", 1)
        '1'
        >>> text_between("<a>0</a><a>1</a>@", re.compile("<a>"), "</a>", 2)
        ''
        >>> text_between("<a>0</a><a>1</a>@", re.compile("<a>"), "</a>", -1)
        '1'
        >>> text_between("<a>0</a><a>1</a>@", re.compile("<a>"), "</a>", -2)
        '0'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", re.compile(b"</a>"))
        b'0'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", re.compile(b"</a>"), 1)
        b'1'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", re.compile(b"</a>"), 2)
        b''
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", re.compile(b"</a>"), -1)
        b'1'
        >>> text_between(b"<a>0</a><a>1</a>@", b"<a>", re.compile(b"</a>"), -2)
        b'0'
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", with_match=True)
        '<a>0</a>'
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", 1, with_match=True)
        '<a>1</a>'
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", 2, with_match=True)
        ''
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", -1, with_match=True)
        '<a>1</a>'
        >>> text_between("<a>0</a><a>1</a>@", "<a>", "</a>", -2, with_match=True)
        '<a>0</a>'
    """
    if index >= 0:
        stop0 = 0
        for _ in range(-1, index):
            start0, start1 = text_find(text, prefix, begin=stop0)
            stop1,  stop0  = text_find(text, suffix, begin=start1)
            if start0 == stop0:
                break
    elif isinstance(prefix, (bytes, str)) and isinstance(suffix, (bytes, str)):
        start0 = len(text)
        for _ in range(-index):
            stop1,  stop0  = text_find(text, suffix, -1, begin=start0)
            start0, start1 = text_find(text, prefix, -1, begin=stop1)
            if start0 == stop0:
                break
    else:
        prefix_rit = reversed(tuple(text_finditer(text, prefix)))
        suffix_rit = reversed(tuple(text_finditer(text, suffix)))
        start0 = len(text)
        try:
            for _ in range(-index):
                while True:
                    stop1, stop0 = next(suffix_rit)
                    if stop0 <= start0:
                        break
                while True:
                    start0, start1 = next(prefix_rit)
                    if start1 <= stop1:
                        break
        except StopIteration:
            return text[:0]
    if with_match:
        return text[start0:stop0]
    else:
        return text[start1:stop1]


if __name__ == "__main__":
    import doctest
    print(doctest.testmod())

