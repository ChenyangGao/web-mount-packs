#!/usr/bin/env python3
# coding: utf-8

__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 1)
__all__ = ["clear_lines", "clear_last_lines", "print_iter"]

from inspect import isgeneratorfunction
from sys import stdout
from typing import (
    cast, Callable, Generator, Iterable, Optional, TypeVar, Union
)


T = TypeVar("T")


def clear_lines(offset: int = 0, /):
    write = stdout.write
    if offset > 0:
        write(f"\x1b[{offset}B")
    elif offset < 0:
        offset = -offset
    write("\r\x1b[K")
    if offset:
        write("\x1b[1A\x1b[K" * offset)


def clear_last_lines(offset: int = 0, /):
    clear_lines(-offset)


def print_iter(
    it: Iterable[T], /, 
    genstr: Union[
        Callable[[T], Optional[str]], 
        Callable[[Iterable[T]], Generator[str, T, Optional[str]]], 
    ] = lambda s: str(s), 
    clear_n_lines: Union[None, int, Callable[[str], int]] = lambda s: s.count("\n") + 1, 
) -> Generator[T, None, None]:
    write, flush = stdout.write, stdout.flush
    n_lines: Optional[int] = 0
    will_calc: bool = callable(clear_n_lines)
    isgen: bool = isgeneratorfunction(genstr)
    output: Optional[str]
    if isgen:
        genstr = cast(
            Callable[[Iterable[T]], Generator[str, T, Optional[str]]], 
            genstr, 
        )
        gen = genstr(it)
        output = next(gen)
        if output is not None:
            n_lines and n_lines > 0 and clear_last_lines(n_lines-1)
            write(output)
            flush()
            n_lines = clear_n_lines(output) if will_calc else clear_n_lines # type: ignore
        genstr = gen.send
    genstr = cast(Callable[[T], Optional[str]], genstr)
    try:
        for i in it:
            yield i
            output = genstr(i)
            if output is not None:
                n_lines and n_lines > 0 and clear_last_lines(n_lines-1)
                write(output)
                flush()
                n_lines = clear_n_lines(output) if will_calc else clear_n_lines # type: ignore
    except GeneratorExit:
        if isgen:
            try:
                gen.throw(StopIteration)
            except StopIteration as e:
                if e.args and e.args[0] is not None:
                    n_lines and n_lines > 0 and clear_last_lines(n_lines-1)
                    write(e.args[0])
                    flush()
            except BaseException:
                pass
    else:
        if isgen:
            try:
                gen.throw(GeneratorExit)
            except StopIteration as e:
                if e.args and e.args[0] is not None:
                    n_lines and n_lines > 0 and clear_last_lines(n_lines-1)
                    write(e.args[0])
                    flush()


if __name__ == "__main__":
    from time import perf_counter
    from typing import Any

    _: Any
    g: Any

    def gen_count_time(it, /):
        try:
            total = len(it)
        except TypeError:
            total = '?'
        start_t = perf_counter()
        n = 1
        _ = yield
        try:
            while True:
                _ = yield f"PROCESSED: {n}/{total}\nCOST: {perf_counter() - start_t:.6f} s\n"
                n += 1
        except StopIteration:
            return f"[FAILED] PROCESSED PARTIAL\n    TOTAL: {n}\n    COST: {perf_counter() - start_t:.6f} s\n"
        except GeneratorExit:
            return f"[SUCCESS] PROCESSED ALL\n    TOTAL: {n}\n    COST: {perf_counter() - start_t:.6f} s\n"

    def gen_batch_count_time(it, /):
        try:
            total = len(it)
        except TypeError:
            total = '?'
        start_t = perf_counter()
        n = 0
        t = 0
        i = yield
        try:
            while True:
                n += 1
                t += len(i)
                i = yield f"BATCH: {n}/{total}\nPROCESSED: {t}\nCOST: {perf_counter() - start_t:.6f} s\n"
        except StopIteration:
            return f"[FAILED] PROCESSED PARTIAL\n    BATCHS: {n}\n    TOTAL: {t}\n    COST: {perf_counter() - start_t:.6f} s\n"
        except GeneratorExit:
            return f"[SUCCESS] PROCESSED ALL\n    BATCHS: {n}\n    TOTAL: {t}\n    COST: {perf_counter() - start_t:.6f} s\n"

    from time import sleep

    print("😄 process 10 elements")
    for _ in print_iter(range(10), gen_count_time):
        sleep(.1)

    print("😂 process 10 elements, failed after the 5th")
    g = print_iter(range(10), gen_count_time)
    for i, _ in enumerate(g):
        sleep(.1)
        if i == 5:
            g.close()

    print("🤭 process 10 batches, the latter "
          "batch has 1 more element than the previous one")
    for _ in print_iter([range(i) for i in range(10)], gen_batch_count_time):
        sleep(.1)

    print("😢 process 10 batches, failed after the 5th")
    g = print_iter([range(i) for i in range(10)], gen_batch_count_time)
    for i, _ in enumerate(g):
        sleep(.1)
        if i == 5:
            g.close()

