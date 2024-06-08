#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["cycle_text", "rotate_text"]

from collections.abc import Iterable, Iterator
from itertools import accumulate, count, cycle, repeat
from time import perf_counter

from wcwidth import wcwidth, wcswidth # type: ignore


def cycle_text(
    text_it: Iterable[str], 
    /, 
    prefix: str = "", 
    interval: float = 0, 
    min_length: int = 0, 
) -> Iterator[str]:
    prefix_len = wcswidth(prefix)
    if prefix:
        ajust_len = min_length - prefix_len
        if ajust_len > 0:
            text_it = (prefix + s + " " * (ajust_len - wcswidth(s)) for s in text_it)
        else:
            text_it = (prefix + s for s in text_it)
    if interval <= 0:
        return cycle(text_it)
    else:
        def wrapper():
            t = perf_counter()
            for p in cycle(text_it):
                yield p
                while (s := perf_counter()) - t < interval:
                    yield p
                t = s
        return wrapper()


def rotate_text(
    text: str, 
    length: int = 10, 
    interval: float = 0, 
) -> Iterator[str]:
    if length < 0:
        length = 0
    wcls = list(map(wcwidth, text))
    diff = sum(wcls) - length
    if diff <= 0:
        return repeat(text + " " * -diff)
    if all(v == 1 for v in wcls):
        del wcls
        if length <= 1:
            def wrap():
                yield from text
        else:
            def wrap():
                for i in range(diff + 1):
                    yield text[i:i+length]
                for j in range(1, length):
                    yield text[i+j:] + " " * j
    else:
        wcm = tuple(dict(zip(accumulate(wcls), count(1))).items())
        del wcls
        if length <= 1:
            def wrap():
                nonlocal wcm
                i = 0
                for _, j in wcm:
                    yield text[i:j]
                    i = j
                del wcm
        else:
            def wrap():
                nonlocal wcm
                size = len(wcm)
                for n, (right, j) in enumerate(wcm):
                    if right > length:
                        if n == 0:
                            break
                        n -= 1
                        right, j = wcm[n]
                        break
                if n == 0:
                    yield text[:j]
                else:
                    yield text[:j] + " " * (length - right)
                for m, (left, i) in enumerate(wcm):
                    while (right - left) < length:
                        n += 1
                        if n == size:
                            break
                        right, j = wcm[n]
                    if n == size:
                        break
                    if right - left == length:
                        yield text[i:j]
                    elif n - m == 1:
                        yield text[i:j]
                    else:
                        n -= 1
                        right, j = wcm[n]
                        yield text[i:j] + " " * (length - diff)
                for left, i in wcm[m:-1]:
                    yield text[i:] + " " * (left - diff)
                del wcm
    return cycle_text(wrap(), interval=interval)

