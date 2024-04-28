__author__  = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 1)
__all__ = ['logthis', 'logreturn', 'logerror']

import logging

from inspect import iscoroutinefunction
from typing import cast, Callable, Optional, Union

from .decorator import optional_decorate


logging.basicConfig(
    level=logging.INFO, 
    format="[\x1b[1m%(asctime)-15s\x1b[0m] \x1b[36;1m%(name)s\x1b[0m"
           "(\x1b[31;1m%(levelname)s\x1b[0m) ➜ %(message)s"
)


@optional_decorate
def logthis(
    f: Optional[Callable] = None, 
    /, 
    logger = logging, 
    suppress: bool = False, 
    msg_before: Union[None, str, Callable[..., str]] = None, 
    msg_after: Union[None, str, Callable[..., str]] = None, 
    msg_error: Union[None, str, Callable[..., str]] = None, 
    msg_finally: Union[None, str, Callable[..., str]] = None, 
    async_: Optional[bool] = None, 
) -> Callable:
    f = cast(Callable, f)
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    if async_ or (async_ is None and iscoroutinefunction(f)):
        async def wrapper(*args, **kwds):
            if msg_before is not None:
                logger.info(msg_before(f, args, kwds) 
                            if callable(msg_before) else msg_before)
            try:
                r = await f(*args, **kwds)
                if msg_after is not None:
                    logger.info(msg_after(f, args, kwds, r) 
                                if callable(msg_after) else msg_after)
                return r
            except BaseException as exc:
                r = exc
                if msg_error is not None:
                    logger.error(msg_error(f, args, kwds, r) 
                                if callable(msg_error) else msg_error)
                if not suppress:
                    raise
            finally:
                if msg_finally is not None:
                    logger.info(msg_finally(f, args, kwds, r) 
                                if callable(msg_finally) else msg_finally)
    else:
        def wrapper(*args, **kwds):
            if msg_before is not None:
                logger.info(msg_before(f, args, kwds) 
                            if callable(msg_before) else msg_before)
            try:
                r = f(*args, **kwds)
                if msg_after is not None:
                    logger.info(msg_after(f, args, kwds, r) 
                                if callable(msg_after) else msg_after)
                return r
            except BaseException as exc:
                r = exc
                if msg_error is not None:
                    logger.error(msg_error(f, args, kwds, r) 
                                if callable(msg_error) else msg_error)
                if not suppress:
                    raise
            finally:
                if msg_finally is not None:
                    logger.info(msg_finally(f, args, kwds, r) 
                                if callable(msg_finally) else msg_finally)
    return wrapper


@optional_decorate
def logreturn(
    f: Optional[Callable] = None, 
    /, 
    print: Callable = logging.info, 
    message: Union[None, str, Callable] = None, 
    async_: Optional[bool] = None, 
) -> Callable:
    f = cast(Callable, f)
    if async_ or (async_ is None and iscoroutinefunction(f)):
        async def wrapper(*args, **kwds):
            r = await f(*args, **kwds)
            if message is None:
                print(r)
            elif callable(message):
                print(message(f, args, kwds, r))
            else:
                print(message)
            return r
    else:
        def wrapper(*args, **kwds):
            r = f(*args, **kwds)
            if message is None:
                print(r)
            elif callable(message):
                print(message(f, args, kwds, r))
            else:
                print(message)
            return r
    return wrapper


@optional_decorate
def logerror(
    f: Optional[Callable] = None, 
    /, 
    print: Callable = logging.error, 
    message: Union[None, str, Callable] = None, 
    suppress: bool = False, 
    async_: Optional[bool] = None, 
) -> Callable:
    f = cast(Callable, f)
    if async_ or (async_ is None and iscoroutinefunction(f)):
        async def wrapper(*args, **kwds):
            try:
                return await f(*args, **kwds)
            except BaseException as r:
                if message is None:
                    print(r)
                elif callable(message):
                    print(message(f, args, kwds, r))
                else:
                    print(message)
                if not suppress:
                    raise
    else:
        def wrapper(*args, **kwds):
            try:
                return f(*args, **kwds)
            except BaseException as r:
                if message is None:
                    print(r)
                elif callable(message):
                    print(message(f, args, kwds, r))
                else:
                    print(message)
                if not suppress:
                    raise
    return wrapper

