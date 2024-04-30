#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["startfile", "startfile_async"]

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(
        description="Start file(s) with its/their associated application.", 
        formatter_class=RawTextHelpFormatter, 
    )
    parser.add_argument("paths", nargs="*", metavar="path", help="path to file or directory")
    parser.add_argument("-v", "--version", action="store_true", help="print the current version")

    args = parser.parse_args()
    if args.version:
        print(".".join(map(str, __version__)))
        raise SystemExit(0)
    paths = args.paths
    if not paths:
        parser.parse_args(["-h"])

try:
    from os import startfile
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
    async def startfile_aysnc(*args, **kwds):
        return await to_thread(startfile, *args, **kwds)


if __name__ == "__main__":
    for path in paths:
        startfile(path)

