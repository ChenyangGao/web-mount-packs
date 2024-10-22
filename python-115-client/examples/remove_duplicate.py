#!/usr/bin/env python3
# encoding: utf-8

__doc__ = "115文件去重复"

from argparse import ArgumentParser
from p115 import P115Client, AVAILABLE_APPS
from p115.tool import traverse_files, iter_dupfiles, dict_dupfiles, ensure_attr_path
from os.path import expanduser, dirname, realpath, join as joinpath
import sys, time

def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("-a", "--app", default="alipaymini", choices=AVAILABLE_APPS,
                        help="必要时，选择一个 app 进行扫码登录，默认值 'alipaymini'，注意：这会把已经登录的相同 app 踢下线")
    parser.add_argument("-co", "--cookies", default="",
                        help="115 登录 cookies，优先级高于 -cp/--cookies-path")
    parser.add_argument("-cp", "--cookies-path", default="",
                        help="""存储 115 登录 cookies 的文本文件的路径，如果缺失，
                        则从 115-cookies.txt 文件中获取，此文件可在如下目录之一:
                        1. 当前工作目录
                        2. 用户根目录
                        3. 此脚本所在目录""")

    parser.add_argument('-d', '--dir', type=str,
                            help='要处理的文件夹路径或cid值, 不指定默认全网盘搜索')
    parser.add_argument('-l', '--lib', type=str, help='指定的库文件夹或cid值')

    parser.add_argument('-t', '--type', type=int, default=99,
                        choices=[1, 2, 3, 4, 5, 6, 7, 99],
                        help="""指定删除类型: 1: 文档, 2:
                        图片, 3: 音频, 4: 视频, 5: 压缩包, 6:
                        应用, 7: 书籍, 99: 仅文件""")
    parser.add_argument('-k', '--keep', type=str, default="longest",
                        choices=["first", "latest", "longest"],
                        help='保留哪个重复文件，默认保留文件名最长的文件')
    parser.add_argument('-p', '--print', action='store_true', default = False,
                        help='打印出删除的文件')

    args = parser.parse_args()

    # TODO: add "/" for dir/lib if not have
    if args.lib and (args.dir.find(args.lib) == 0 or args.lib.find(args.dir) == 0):
        print("lib dir should be different with dir")
        sys.exit(1)

    return args

def get_cookie(args):
    cookies = args.cookies
    cookies_path = args.cookies_path

    if cookies:
        return cookies

    if cookies_path:
        try:
            cookies = open(cookies_path).read()
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        seen = set()
        for dir_ in (".", expanduser("~"), dirname(__file__)):
            dir_ = realpath(dir_)
            if dir_ in seen:
                continue
            seen.add(dir_)
            try:
                path = joinpath(dir_, "115-cookies.txt")
                cookies = open(path).read()
                # update the cookies_path
                if cookies:
                    args.cookies_path = path
                    break
            except FileNotFoundError:
                pass

    return cookies

def remove_in_chunk(client, dup_ids, dup_files, chunk_size):
    for i in range(0, len(dup_ids), chunk_size):
        success = False
        while not success:
            try:
                client.fs_delete(dup_ids[i: i + chunk_size])
                for f in dup_files[i: i + chunk_size]:
                    print("Delete ", f)
                success = True
            except Exception as e:
                print("Failed to remove files:", e)
                print("Retrying in 5 seconds...")
                time.sleep(5)

def get_keep(args):
    if args.keep == "first":
        keep = True
    elif args.keep == "latest":
        keep = False
    else:
        keep = lambda attr: -len(attr["name"])
    return keep

def find_dup_in_target(args, client, target_cid):
    dup_files = []
    dup_ids = []
    if args.print:
        dups = dict_dupfiles(client = client, cid = target_cid, type = args.type,
                            keep_first = get_keep(args), with_path = args.print)
        for dup in dups.values():
            dup_ids.extend([attr["id"] for attr in dup])
            dup_files.extend([attr["path"] for attr in dup])
    else:
        dups = iter_dupfiles(client = client, cid = target_cid, type = args.type,
                            keep_first = get_keep(args))
        dup_ids.extend([attr['id']for key, attr in dups])

    print("Total dups: ", len(dup_ids))
    chunk_size = 1000
    remove_in_chunk(client, dup_ids, dup_files, chunk_size)

def find_dup_based_on_lib(args, client, libdir_cid, target_cid):
    key = lambda attr: (attr["sha1"], attr["size"])
    lib_files = set(map(key, traverse_files(client, libdir_cid)))
    dups = [attr for attr in traverse_files(client, target_cid) if key(attr) in lib_files]

    dup_files = []
    dup_ids = []
    if args.print:
        attrs = ensure_attr_path(client, dups)
        dup_ids.extend([attr["id"] for attr in attrs])
        dup_files.extend([attr["path"] for attr in attrs])
    else:
        dup_ids.extend([attr["id"] for attr in dups])

    print("Total dups: ", len(dup_ids))
    chunk_size = 1000
    remove_in_chunk(client, dup_ids, dup_files, chunk_size)

def main():
    args = parse_args()
    cookies = get_cookie(args)
    client = P115Client(cookies, app=args.app, check_for_relogin=True)
    if args.cookies_path and cookies != client.cookies_str:
        open(args.cookies_path, "w").write(client.cookies_str)

    fs = client.fs
    target_cid = 0
    libdir_cid = 0
    # get target_cid
    if args.dir:
        try:
            target_cid = int(args.dir)
        except ValueError:
            target_cid = fs.attr(args.dir)['id']
    # get libdir_cid
    if args.lib:
        try:
            libdir_cid = int(args.lib)
        except ValueError:
            libdir_cid = fs.attr(args.lib)['id']

    # remove dups in single dir
    if libdir_cid == 0:
        find_dup_in_target(args, client, target_cid)
    # remove dups based on lib dir
    else:
        find_dup_based_on_lib(args, client, libdir_cid, target_cid)

    # Can only call it once a day
    # client.tool_clear_empty_folder()

if __name__ == "__main__":
    main()
