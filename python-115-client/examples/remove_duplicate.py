#!/usr/bin/env python3
# encoding: utf-8

__doc__ = "115文件去重复"

from argparse import ArgumentParser
from os.path import expanduser, dirname, realpath, join as joinpath
from p115 import check_response, P115Client, P115Path, AVAILABLE_APPS
import sys

Videos = ('.mp4', '.mkv', '.ts', '.iso', '.rmvb', '.avi', '.mov', '.mpeg',
          '.mpg', '.wmv', '.3gp', '.asf','.m4v', '.flv', '.m2ts', '.strm',
          '.tp', '.f4v')

def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('-d', '--dir', type=str, required=True, help='要处理的文件夹')
    parser.add_argument("-a", "--app", default="qandroid", choices=AVAILABLE_APPS, help="必要时，选择一个 app 进行扫码登录，默认值 'qandroid'，注意：这会把已经登录的相同 app 踢下线")
    parser.add_argument("-c", "--cookies", default="", help="115 登录 cookies，优先级高于 -cp/--cookies-path")
    parser.add_argument("-cp", "--cookies-path", default="", help="""\
存储 115 登录 cookies 的文本文件的路径，如果缺失，则从 115-cookies.txt 文件中获取，此文件可在如下目录之一:
    1. 当前工作目录
    2. 用户根目录
    3. 此脚本所在目录""")
    parser.add_argument('-l', '--lib', type=str, help='指定的库文件夹')
    parser.add_argument('-A', '--all', type=bool, help='全局搜索重复文件')

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

def remove_repeate_file(args, client, fid, origin_file):
    lib = args.lib
    folder = args.dir
    all_dir = args.all
    file_list = []

    try:
        resp = client.fs_repeat_sha1(fid)
    except Exception as e:
        return

    files = check_response(resp)["data"]
    if len(files) == 0:
        return
    for file in files:
        try:
            info = client.fs_statistic(file['fid'])
        except Exception as e:
            continue
        path = '/' + '/'.join([p['file_name'] for p in info['paths'] if p['file_name'] != '根目录'])
        if len(path) == 1:
            full_name = path + info['file_name']
        else:
            full_name = path + '/' + info['file_name']
        # 有lib的模式下，发现lib内有重复直接删除源文件
        if lib:
            if path.find(lib) == 0:
                client.fs.remove(origin_file)
                print("Info: find %s, remove %s" % (full_name, origin_file))
                return
        else:
            # 非全局模式下，只检查当前目录下重复文件
            if not all_dir and path.find(folder) != 0:
                continue
            file_list.append(full_name)

    if len(file_list) <= 1:
        return

    for i in range(len(file_list)):
        print("%d: %s" % (i, file_list[i]))
    user_input = int(input("请选择要保留的文件序号: ").strip().lower())
    if user_input in range(len(file_list)):
        file_list.pop(user_input)

    fs = client.fs
    for i in range(len(file_list)):
        fs.remove(file_list[i])
        print("remove file: ", file_list[i])

def main():
    args = parse_args()
    cookies = get_cookie(args)
    client = P115Client(cookies, app=args.app)
    if args.cookies_path and cookies != client.cookies:
        open(args.cookies_path, "w").write(client.cookies)

    fs = client.fs
    attr = fs.attr(args.dir)

    if attr['is_directory']:
        fs.chdir(args.dir)
        for file in fs.iter(max_depth=-1):
            #if file.get('is_directory'):
            #    print("Debug: enter: ", file.get('path'))
            #    continue
            if file.name.endswith(Videos):
                #print("Debug: Start checking: ", file.get('path'))
                remove_repeate_file(args, client, file.get('id'), file.get('path'))
    else:
        remove_repeate_file(args, client, attr['id'], args.dir)

if __name__ == "__main__":
    main()
