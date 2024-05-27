#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 2)
__all__ = ["startfile", "startfile_async"]

try:
    from os import startfile # type: ignore
except ImportError:
    from asyncio import create_subprocess_exec, create_subprocess_shell
    from platform import system
    from subprocess import run

    async def run_command(command):
        if isinstance(command, str):
            process = await create_subprocess_shell(command)
        else:
            process = await create_subprocess_exec(*command)
        await process.communicate()

    match system():
        case "Linux":
            def startfile(path, /, *args):
                run(["xdg-open", path, *args])
            async def startfile_async(path, /, *args):
                await run_command(["xdg-open", path, *args])
        case "Darwin":
            def startfile(path, /, *args):
                run(["open", path, *args])
            async def startfile_async(path, /, *args):
                await run_command(["open", path, *args])
        case "Windows":
            def startfile(path, /, *args):
                run(["start", path, *args])
            async def startfile_async(path, /, *args):
                await run_command(["start", path, *args])
        case _:
            raise RuntimeError("can't get startfile")
else:
    from asyncio import to_thread
    from functools import wraps

    @wraps(startfile)
    async def startfile_async(*args, **kwds):
        return await to_thread(startfile, *args, **kwds)

