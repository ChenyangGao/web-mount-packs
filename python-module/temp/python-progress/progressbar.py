import sys
from os import get_terminal_size
from typing import Generator, Iterable, Optional, Sized, TypeVar

T = TypeVar('T')


__all__ = ['progressbar', 'printwithbar']


PROGRESSBAR: str = ''


def progressbar(
    iterable: Iterable[T], 
    total: Optional[int] = None, 
    max_columns: int = 0, 
    a_fillchar: str = '█', 
    b_fillchar: str = '░', 
) -> Generator[T, None, None]:
    global PROGRESSBAR
    allocated_columns = 10
    if total is None:
        if isinstance(iterable, Sized):
            total = len(iterable)
        else:
            raise ValueError(
                f"unable to get size of {iterable!r}"
                " , please specify 'total'"
            )
    for i, e in enumerate(iterable):
        term_columns = get_terminal_size()[0]
        columns = (min(max_columns, term_columns) if max_columns else term_columns) - allocated_columns
        percent = i * 100 // total
        width = columns * i // total
        a_chars = a_fillchar * width
        b_chars = b_fillchar * (columns - width)
        PROGRESSBAR = f"[{percent:>3d}%]: |{a_chars}{b_chars}|"
        print('\r', PROGRESSBAR, sep='', end='', flush=True)
        yield e
    term_columns = get_terminal_size()[0]
    columns = (min(max_columns, term_columns) if max_columns else term_columns) - allocated_columns
    PROGRESSBAR = "[100%%]: |%s|" % (a_fillchar * columns)
    print('\r', PROGRESSBAR, sep='', flush=True)


def printwithbar(
    *values, 
    sep: str = ' ', 
    end: str = '\n'
) -> None:
    print('\r', ' '.ljust(get_terminal_size()[0]), '\r', 
        sep.join(map(str, values)), end, PROGRESSBAR, 
        sep='', end='', flush=True)


if __name__ == '__main__':
    from time import sleep

    for i in progressbar(range(100)): 
        printwithbar(i) 
        sleep(.02)

