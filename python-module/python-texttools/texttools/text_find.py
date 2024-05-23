#!/usr/bin/env python3
# coding: utf-8

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "Span", "text_find", "text_finditer", "text_before", "text_after", "text_between", 
]

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
    start: Optional[int] = None, 
    stop: Optional[int] = None, 
) -> Span:
    """find substring.

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
        >>> text_find("<a>0</a><a>1</a>@", "<a>", start=1)
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
        >>> text_find(b"<a>0</a><a>1</a>@", b"<a>", start=1)
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
        >>> text_find("<a>0</a><a>1</a>@", re.compile("<a>"), start=1)
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
        >>> text_find(b"<a>0</a><a>1</a>@", re.compile(b"<a>"), start=1)
        Span(start=8, stop=11)
    """
    text_len = len(text)
    if text_len == 0:
        return Span(0, 0)
    if start is None:
        start = 0
    elif start < 0:
        start += text_len
    if start < 0:
        start = 0
    elif start > text_len:
        start = text_len
    if stop is None:
        stop = text_len
    elif stop < 0:
        stop += text_len
    if stop < 0:
        stop = 0
    elif stop > text_len:
        stop = text_len
    if start >= stop:
        if index >= 0:
            return Span(start, start)
        else:
            return Span(stop, stop)
    if isinstance(pattern, (bytes, str)):
        pattern = cast(AnyStr, pattern)
        patn_len = len(pattern)
        if patn_len == 0:
            if index >= 0:
                index = min(start+index, text_len)
            else:
                index = max(start+1+index, 0)
            return Span(index, index)
        if index >= 0:
            find = text.find
            for _ in range(-1, index):
                i = find(pattern, start, stop)
                if i == -1:
                    return Span(stop, stop)
                start = i + patn_len
            return Span(start-patn_len, start)
        else:
            rfind = text.rfind
            for _ in range(-index):
                i = rfind(pattern, start, stop)
                if i < 0:
                    return Span(start, start)
                stop = i
            return Span(stop, stop+patn_len)
    elif index >= 0:
        try:
            match = next(islice(pattern.finditer(text, start, stop), index, None))
            return Span(*match.span())
        except StopIteration:
            return Span(stop, stop)
    else:
        dq = deque(pattern.finditer(text, start, stop), maxlen=-index)
        if len(dq) == -index:
            return Span(*dq[0].span())
        else:
            return Span(start, start)


def text_finditer(
    text: AnyStr, 
    pattern, 
    /, 
    start: Optional[int] = None, 
    stop: Optional[int] = None, 
) -> Iterator[Span]:
    """find and iterate over substrings.

    DOCTEST & EXAMPLES::
        >>> tuple(text_finditer("<a>0</a><a>1</a>@", "<a>"))
        (Span(start=0, stop=3), Span(start=8, stop=11))
        >>> tuple(text_finditer(b"<a>0</a><a>1</a>@", b"<a>"))
        (Span(start=0, stop=3), Span(start=8, stop=11))
        >>> tuple(text_finditer("<a>0</a><a>1</a>@", "<a>", 1))
        (Span(start=8, stop=11),)
        >>> tuple(text_finditer(b"<a>0</a><a>1</a>@", b"<a>", 1))
        (Span(start=8, stop=11),)
        >>> import re
        >>> tuple(text_finditer("<a>0</a><a>1</a>@", re.compile("<a>")))
        (Span(start=0, stop=3), Span(start=8, stop=11))
        >>> tuple(text_finditer(b"<a>0</a><a>1</a>@", re.compile(b"<a>")))
        (Span(start=0, stop=3), Span(start=8, stop=11))
    """
    text_len = len(text)
    if start is None:
        start = 0
    elif start < 0:
        start += text_len
    if start < 0:
        start = 0
    elif start > text_len:
        start = text_len
    if stop is None:
        stop = text_len
    elif stop < 0:
        stop += text_len
    if stop < 0:
        stop = 0
    elif stop > text_len:
        stop = text_len
    if isinstance(pattern, (bytes, str)):
        pattern = cast(AnyStr, pattern)
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
        while True:
            i = find(pattern, start, stop)
            if i == -1:
                return
            yield Span(i, (start := i + patn_len))
    else:
        for match in pattern.finditer(text, start, stop):
            yield Span(*match.span())


def text_before(
    text: AnyStr, 
    prefix, 
    /, 
    index: int = 0, 
    start: Optional[int] = None, 
    stop: Optional[int] = None, 
    with_match: bool = False, 
) -> AnyStr:
    """find substring with prefix.

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
    return text[:text_find(text, prefix, index, start, stop)[with_match]]


def text_after(
    text: AnyStr, 
    suffix, 
    /, 
    index: int = 0, 
    start: Optional[int] = None, 
    stop: Optional[int] = None, 
    with_match: bool = False, 
) -> AnyStr:
    """find substring with suffix.

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
    return text[text_find(text, suffix, index, start, stop)[not with_match]:]


def text_between(
    text: AnyStr, 
    prefix, 
    suffix, 
    /, 
    index: int = 0, 
    start: Optional[int] = None, 
    stop: Optional[int] = None, 
    with_match: bool = False, 
) -> AnyStr:
    """find substring with prefix and suffix.

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
    text_len = len(text)
    if text_len == 0:
        return text[:0]
    if start is None:
        start = 0
    elif start < 0:
        start += text_len
    if start < 0:
        start = 0
    elif start > text_len:
        start = text_len
    if stop is None:
        stop = text_len
    elif stop < 0:
        stop += text_len
    if stop < 0:
        stop = 0
    elif stop > text_len:
        stop = text_len
    if start >= stop:
        return text[:0]
    if index >= 0:
        stop0 = start
        for _ in range(-1, index):
            start0, start1 = text_find(text, prefix, 0, stop0, stop)
            stop1,  stop0  = text_find(text, suffix, 0, start1, stop)
            if start0 == stop0:
                break
    elif isinstance(prefix, (bytes, str)) and isinstance(suffix, (bytes, str)):
        start0 = stop
        for _ in range(-index):
            stop1,  stop0  = text_find(text, suffix, -1, start, start0)
            start0, start1 = text_find(text, prefix, -1, start, stop1)
            if start0 == stop0:
                break
    else:
        prefix_rit = reversed(tuple(text_finditer(text, prefix, start, stop)))
        suffix_rit = reversed(tuple(text_finditer(text, suffix, start, stop)))
        start0 = stop
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

