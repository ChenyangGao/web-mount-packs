#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["acc_step", "cut_iter"]


from typing import Iterator, Optional


def acc_step(end: int, step: int = 1) -> Iterator[tuple[int, int, int]]:
    i = 0
    for j in range(step, end + 1, step):
        yield i, j, step
        i = j
    if (rest := end - i):
        yield i, end, rest


def cut_iter(
    start: int, 
    stop: Optional[int] = None, 
    step: int = 1, 
) -> Iterator[tuple[int, int]]:
    if stop is None:
        start, stop = 0, start
    i = start
    for j in range(start+step, stop, step):
        yield i, j
        i = j    
    yield i, stop

