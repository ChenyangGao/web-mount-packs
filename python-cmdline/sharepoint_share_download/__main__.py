#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description="""\
    🔧 从 SharePoint 的分享，提取下载链接或下载文件

Source Code:  https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/sharepoint_share_download
MIT Licensed: https://github.com/ChenyangGao/web-mount-packs/tree/main/python-cmdline/sharepoint_share_download/LICENSE
""", epilog=r"""------------------------------

🔨 使用示例：

假设分享链接如下：

.. code: shell

    url='https://yuesezhengmei-my.sharepoint.com/:f:/g/personal/drive1_box_catimage_work/EiLyE4C4BcJIsJnzqpSUxvcBri66YZAYgBoGsS4ynQ5iug'

0. 输出下载链接或属性字典

可以用以下命令输出下载链接，奇数行是 Cookie，偶数行是 链接，因为下载需要携带 Cookie

.. code: shell

    python sharepoint_share_download "$url"

如果需要过滤掉奇数行，可以这样写

.. code: shell

    python sharepoint_share_download "$url" | sed -n 'n;p'

可以通过 -p/--print-attr 参数输出属性字典

.. code: shell

    python sharepoint_share_download "$url"

1. 使用自带的下载器下载：

可以通过 -d/--download-dir 参数指定下载目录，下载到当前目录可指定为 ""

.. code: shell

    python sharepoint_share_download "$url" -d ""

2. 使用 wget 批量下载：

可以用以下命令进行批量下载（可以用 xargs -P num 指定 num 进程并行），需要携带 Cookie，Mac 中使用 gxargs 代替 xargs：

.. code: shell

    /usr/bin/env python3 sharepoint_share_download "$url" | awk '{ if (NR%2==1) {first=substr($0, 3)} else {print "wget --content-disposition \x27" $0 "\x27 --header \x27" first "\x27" } }' | xargs -d '\n' -n 1 -P 4 sh -c

或者使用这个封装函数

.. code: shell

    wget_download() {
        local url=$1
        local procs=$(($2))
        if [ $procs -le 0 ]; then
            procs=1
        fi
        /usr/bin/env python3 sharepoint_share_download "$url" | awk '{ if (NR%2==1) {first=substr($0, 3)} else {print "wget --content-disposition \x27" $0 "\x27 --header \x27" first "\x27" } }' | gxargs -d '\n' -n 1 -P "${procs}" sh -c
    }
    wget_download "$url" 4
""", formatter_class=RawTextHelpFormatter)
parser.add_argument("url", nargs="?", help="""\
分享链接（链接中不要有空格）
用空格隔开，一行一个
如果不传，则从 stdin 读取""")
parser.add_argument("-d", "--download-dir", help="下载文件夹，如果指定此参数，会下载文件且断点续传")
parser.add_argument("-p", "--print-attr", action="store_true", help="输出属性字典，而不是下载链接")
parser.add_argument("-c", "--predicate-code", help="断言，当断言的结果为 True 时，链接会被输出，未指定此参数则自动为 True")
parser.add_argument(
    "-t", "--predicate-type", choices=("expr", "re", "lambda", "stmt", "code", "path"), default="expr", 
    help="""断言类型
    - expr    （默认值）表达式，会注入一个名为 attr 的文件信息的 dict
    - re      正则表达式，如果文件的名字匹配此模式，则断言为 True
    - lambda  lambda 函数，接受一个文件信息的 dict 作为参数
    - stmt    语句，当且仅当不抛出异常，则视为 True，会注入一个名为 attr 的文件信息的 dict
    - code    代码，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个文件信息的 dict 作为参数
    - path    代码的路径，运行后需要在它的全局命名空间中生成一个 check 或 predicate 函数用于断言，接受一个文件信息的 dict 作为参数

attr 字典的格式如下（包含这些 key）

.. code: python

    {
        "ID": "733",
        "PermMask": "0x3008031021",
        "FSObjType": "0",
        "HTML_x0020_File_x0020_Type": "",
        "UniqueId": "{D51B319E-76E4-4BD2-8C6D-3F7B9DFD89FA}",
        "ProgId": "",
        "NoExecute": "1",
        "ContentTypeId": "0x010100C4D0B96D7657D64EB586987AAF971D1E",
        "FileRef": "/personal/drive1_box_catimage_work/Documents/\u52a8\u6f2b/RDG \u6fd2\u5371\u7269\u79cd\u5c11\u5973/CDs.zip",
        "FileRef.urlencode": "%%2Fpersonal%%2Fdrive1%%5Fbox%%5Fcatimage%%5Fwork%%2FDocuments%%2F%%E5%%8A%%A8%%E6%%BC%%AB%%2FRDG%%20%%E6%%BF%%92%%E5%%8D%%B1%%E7%%89%%A9%%E7%%A7%%8D%%E5%%B0%%91%%E5%%A5%%B3%%2FCDs%%2Ezip",
        "FileRef.urlencodeasurl": "/personal/drive1_box_catimage_work/Documents/\u52a8\u6f2b/RDG%%20\u6fd2\u5371\u7269\u79cd\u5c11\u5973/CDs.zip",
        "FileRef.urlencoding": "/personal/drive1_box_catimage_work/Documents/\u52a8\u6f2b/RDG%%20\u6fd2\u5371\u7269\u79cd\u5c11\u5973/CDs.zip",
        "FileRef.scriptencodeasurl": "\\u002fpersonal\\u002fdrive1_box_catimage_work\\u002fDocuments\\u002f\\u52A8\\u6F2B\\u002fRDG \\u6FD2\\u5371\\u7269\\u79CD\\u5C11\\u5973\\u002fCDs.zip",
        "SMTotalSize": "1441438695",
        "File_x0020_Size": "1441437917",
        "MediaServiceFastMetadata": "",
        "_CommentFlags": "",
        "File_x0020_Type": "zip",
        "HTML_x0020_File_x0020_Type.File_x0020_Type.mapall": "iczip.gif| ||",
        "HTML_x0020_File_x0020_Type.File_x0020_Type.mapcon": "",
        "HTML_x0020_File_x0020_Type.File_x0020_Type.mapico": "iczip.gif",
        "serverurl.progid": "",
        "ServerRedirectedEmbedUrl": "",
        "File_x0020_Type.progid": "",
        "File_x0020_Type.url": "FALSE",
        "FileLeafRef": "CDs.zip",
        "FileLeafRef.Name": "CDs",
        "FileLeafRef.Suffix": "zip",
        "CheckoutUser": "",
        "CheckoutUser.id": "",
        "CheckoutUser.title": "",
        "CheckoutUser.span": "<div class=\"ms-peopleux-vanillauser\"> </div>",
        "CheckoutUser.email": "",
        "CheckoutUser.sip": "",
        "CheckoutUser.jobTitle": "",
        "CheckoutUser.department": "",
        "CheckoutUser.picture": "",
        "CheckedOutUserId": "",
        "IsCheckedoutToLocal": "0",
        "_ComplianceFlags": "",
        "_ShortcutUrl": "",
        "_ShortcutUrl.desc": "",
        "_ShortcutSiteId": "",
        "_ShortcutWebId": "",
        "_ShortcutUniqueId": "",
        "Created_x0020_Date": "0;#2024-03-19 01:40:32",
        "Created_x0020_Date.": "2024-03-19T08:40:32Z",
        "Created_x0020_Date.ifnew": "",
        "Modified": "9/15/2022 9:36 PM",
        "Modified.": "2022-09-16T04:36:45Z",
        "PrincipalCount": "6",
        "Editor": [
            {
                "id": "3",
                "title": "Cat Drive1",
                "email": "Drive1@box.catimage.work",
                "sip": "drive1@box.catimage.work",
                "picture": "/User%%20Photos/Profile%%20Pictures/7ebfda24-9e74-4b8d-a874-908065178c3c_MThumb.jpg"
            }
        ],
        "Editor.id": "3",
        "Editor.title": "Cat Drive1",
        "Editor.span": "<span class=\"ms-noWrap\"><span class='ms-imnSpan'><a href='#' onclick='IMNImageOnClick(event);return false;' class='ms-imnlink ms-spimn-presenceLink' ><span class='ms-spimn-presenceWrapper ms-imnImg ms-spimn-imgSize-10x10'><img name='imnmark' class='ms-spimn-img ms-spimn-presence-disconnected-10x10x32' title='' ShowOfflinePawn='1' src='/_layouts/15/images/spimn.png?rev=47'  alt='No presence information' sip='drive1@box.catimage.work' id='imn_235,type=sip'/></span></a></span><span class=\"ms-noWrap ms-imnSpan\"><a href='#' onclick='IMNImageOnClick(event);return false;' class='ms-imnlink' tabIndex='-1'><img name='imnmark' class='ms-hide' title='' ShowOfflinePawn='1' src='/_layouts/15/images/blank.gif?rev=47'  alt='' sip='drive1@box.catimage.work' id='imn_236,type=sip'/></a><a class=\"ms-subtleLink\" onclick=\"GoToLinkOrDialogNewWindow(this);return false;\" href=\"/personal/drive1_box_catimage_work/_layouts/15/userdisp.aspx?ID=3\">Cat Drive1</a></span></span>",
        "Editor.email": "Drive1@box.catimage.work",
        "Editor.sip": "drive1@box.catimage.work",
        "Editor.jobTitle": "",
        "Editor.department": "",
        "Editor.picture": "/User%%20Photos/Profile%%20Pictures/7ebfda24-9e74-4b8d-a874-908065178c3c_MThumb.jpg",
        "MetaInfo": [
            {
                "lookupId": 733,
                "lookupValue": "vti_parserversion:SR|16.0.0.24706\r\nvti_decryptskipreason:IW|6\r\nvti_TimeOfLastCobaltVersionCreation:TW|19 Mar 2024 08:43:08 -0000\r\nvti_previewinvalidtime:TW|19 Mar 2024 08:40:32 -0000\r\nvti_author:SR|i:0#.f|membership|drive1@box.catimage.work\r\nvti_sprocsschemaversion:SR|16.0.1078.0\r\nvti_dbschemaversion:SR|16.0.397.0\r\nvti_timelastwnssent:TR|19 Mar 2024 08:43:09 -0000\r\nvti_writevalidationtoken:SW|uWO8+EQwIQTHRw3+mEhQtdMPmC8=\r\nvti_modifiedby:SR|i:0#.f|membership|drive1@box.catimage.work\r\nvti_supportsZipIt:BW|false\r\nvti_foldersubfolderitemcount:IW|0\r\nvti_lastbitssessionid:SW|f7cb92ab-9e87-4f93-94c1-38f4128c0742\r\nContentTypeId:SW|0x010100C4D0B96D7657D64EB586987AAF971D1E\r\nvti_iplabelpromotionversion:IW|0\r\nvti_areHybridOrphanHashedBlobsCleaned:BW|false\r\nvti_streamSyncTokenSequenceNumber:IW|6330\r\nvti_folderitemcount:IW|0\r\nvti_lastbitscommit:SW|2",
                "isSecretFieldValue": false
            },
            {
                "lookupId": 1441437917,
                "lookupValue": "0\r\n",
                "isSecretFieldValue": false
            }
        ],
        "MetaInfo.": "733;#vti_parserversion:SR|16.0.0.24706\r\nvti_decryptskipreason:IW|6\r\nvti_TimeOfLastCobaltVersionCreation:TW|19 Mar 2024 08:43:08 -0000\r\nvti_previewinvalidtime:TW|19 Mar 2024 08:40:32 -0000\r\nvti_author:SR|i:0#.f|membership|drive1@box.catimage.work\r\nvti_sprocsschemaversion:SR|16.0.1078.0\r\nvti_dbschemaversion:SR|16.0.397.0\r\nvti_timelastwnssent:TR|19 Mar 2024 08:43:09 -0000\r\nvti_writevalidationtoken:SW|uWO8+EQwIQTHRw3+mEhQtdMPmC8=\r\nvti_modifiedby:SR|i:0#.f|membership|drive1@box.catimage.work\r\nvti_supportsZipIt:BW|false\r\nvti_foldersubfolderitemcount:IW|0\r\nvti_lastbitssessionid:SW|f7cb92ab-9e87-4f93-94c1-38f4128c0742\r\nContentTypeId:SW|0x010100C4D0B96D7657D64EB586987AAF971D1E\r\nvti_iplabelpromotionversion:IW|0\r\nvti_areHybridOrphanHashedBlobsCleaned:BW|false\r\nvti_streamSyncTokenSequenceNumber:IW|6330\r\nvti_folderitemcount:IW|0\r\nvti_lastbitscommit:SW|2;#8013f222-05b8-48c2-b099-f3aa9494c6f7;#~tmpC0_CDs.zip;#f7cb92ab-9e87-4f93-94c1-38f4128c0742;#\"{D51B319E-76E4-4BD2-8C6D-3F7B9DFD89FA},2\";#\"{D51B319E-76E4-4BD2-8C6D-3F7B9DFD89FA},3\";#0x02B963BCF844302104C7470DFE984850B5D30F982F;#1441437917;#0\r\n",
        "owshiddenversion": "4",
        "FileSizeDisplay": "1441437917",
        "ItemChildCount": "0",
        "FolderChildCount": "0",
        "A2ODMountCount": "",
        "_StubFile": "0",
        "_ExpirationDate": "",
        "_ExpirationDate.": "",
        "_activity": "",
        "ContentVersion": "2",
        "DocConcurrencyNumber": "5",
        "_VirusStatus": "",
        "Restricted": "",
        "PolicyDisabledUICapabilities": "0",
        "AccessPolicy": "0",
        "ecb.dispex": "return DispEx(this,event,'TRUE','FALSE','FALSE','','1','','','','','285','0','0','0x3008031021','','')",
        "RemoteItem": "",
        "Interactivity": "",
        "Edits": "",
        "name": "CDs.zip",
        "path": "/personal/drive1_box_catimage_work/Documents/\u52a8\u6f2b/RDG \u6fd2\u5371\u7269\u79cd\u5c11\u5973/CDs.zip",
        "relpath": "CDs.zip",
        "isdir": false,
        "download_url": [
            "https://yuesezhengmei-my.sharepoint.com/personal/drive1_box_catimage_work/_layouts/15/download.aspx?SourceUrl=/personal/drive1_box_catimage_work/Documents/%%E5%%8A%%A8%%E6%%BC%%AB/RDG%%20%%E6%%BF%%92%%E5%%8D%%B1%%E7%%89%%A9%%E7%%A7%%8D%%E5%%B0%%91%%E5%%A5%%B3/CDs.zip"
        ],
        "headers": {
            "Cookie": "FedAuth=77u/PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0idXRmLTgiPz48U1A+VjEzLDBoLmZ8bWVtYmVyc2hpcHx1cm4lM2FzcG8lM2Fhbm9uI2ZiYzMwN2E5OTIwOTFmYmJkNTA1OWRiYmNhMjllNmI1MzlhYmQxYjU4ZDAwNzVhNDU3NjA4NzE0MzQzZDI1NTAsMCMuZnxtZW1iZXJzaGlwfHVybiUzYXNwbyUzYWFub24jZmJjMzA3YTk5MjA5MWZiYmQ1MDU5ZGJiY2EyOWU2YjUzOWFiZDFiNThkMDA3NWE0NTc2MDg3MTQzNDNkMjU1MCwxMzM2MzYxOTA0NzAwMDAwMDAsMCwxMzM2MzcwNTE0Nzc5MjQ4NTYsMC4wLjAuMCwyNTgsMjUwZDIyODktNTZjOC00MGYzLTljYmItOTNkMzc5OGM3NzViLCwsNjA3MzM1YTEtMzA1MC0zMDAwLTU5M2ItM2Y1MWJiNGNlMzBjLDYwNzMzNWExLTMwNTAtMzAwMC01OTNiLTNmNTFiYjRjZTMwYyxzRmVBV1ZLOE5FcWNLZXdRdUV0WERBLDAsMCwwLCwsLDI2NTA0Njc3NDM5OTk5OTk5OTksMCwsLCwsLCwwLCwxOTU5OTUsRGFEQWZqUVFtcHlPWHgyUnJLX1c1bHZvTFo0LGlZMTcxVWcxQkI5TGpXeXBneVFjcjErRHVFVGY5TDVpOWVKWUNiNWtUUkYvT1o4U21Sa1pjTjVHREZGTVBvREw5REJRZ2YxVzdFcUpRYkc4MDZMZmU4dDFoWWNCczZYZ01HVWNITVo3aFAvS1UvcG5IdFRKZHpqdW53ZWZyenJPYVRUNkRZTW5aV2ErRGZzdEdGY200OUhDclNFZGlrbEtCekJwTjRxamxxaFB2T1ViZHRZb0tua1docDBMZTFkSFBGNGRtMlZHN1AxMkdpSDVQU3N4eDN5enZBWjlKK0xDTFlDd3oyd1RVZ3lzTENMT0EyOEFGMCtZMEI2cmNQZW9acVRWWUxuQUs5b1Z2Yk5ETHNXVEQ4bEpZRDBKN1RIdnNzMGYzSkQ4Y1BVUTBiQUI1bmFpd25MRXNibXREYS9yN2MvSTluZUl3cWpnNUJiYWtibEJaUT09PC9TUD4=; path=/; SameSite=None; secure; HttpOnly"
        }
    }

可以通过 -i/--init-code 或 -ip/--init-code-path 提前为断言函数的全局命名空间注入一些变量，默认会注入 re （正则表达式模块）
""")
parser.add_argument("-i", "--init-code", help="执行这段代码一次，以初始化断言函数的全局命名空间")
parser.add_argument("-ip", "--init-code-path", help="执行此路径的代码一次，以初始化断言函数的全局命名空间")
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
parser.add_argument("-li", "--license", action="store_true", help="输出 license")
args = parser.parse_args()

if args.version:
    from pkgutil import get_data
    print(get_data("__main__", "VERSION").decode("ascii")) # type: ignore
    raise SystemExit(0)
if args.license:
    from pkgutil import get_data
    print(get_data("__main__", "LICENSE").decode("ascii")) # type: ignore
    raise SystemExit(0)

from sys import stderr, stdin
from __init__ import iterdir # type: ignore

url = args.url
download_dir = args.download_dir
print_attr = args.print_attr
predicate_code = args.predicate_code
predicate_type = args.predicate_type
init_code = args.init_code
init_code_path = args.init_code_path

if url:
    urls = url.splitlines()
else:
    from sys import stdin
    urls = (l.removesuffix("\n") for l in stdin)

if predicate_code:
    ns = {"re": __import__("re")}
    if predicate_type != "re":
        if init_code:
            from textwrap import dedent
            exec(dedent(init_code), ns)
        if init_code_path:
            from runpy import run_path
            ns = run_path(init_code_path, ns)
    from util.predicate import make_predicate # type: ignore
    predicate = make_predicate(predicate_code, ns, type=predicate_type)
else:
    predicate = None

try:
    if download_dir is None:
        for url in urls:
            if not url:
                continue
            try:
                for attr in iterdir(url, predicate=predicate, max_depth=-1):
                    if attr["isdir"]:
                        continue
                    if print_attr:
                        print(attr, flush=True)
                    else:
                        print("#", f"Cookie: {attr['headers']['Cookie']}")
                        print(attr["download_url"], flush=True)
            except BaseException as e:
                print(f"\r😮‍💨 \x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n  |_ \x1b[5m🙅\x1b[0m \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
                if isinstance(e, (BrokenPipeError, EOFError, KeyboardInterrupt)):
                    raise
    else:
        from collections import deque
        from os import get_terminal_size
        from os.path import join as joinpath
        from time import perf_counter

        try:
            from download import download
            from urllib3_request import request
        except ImportError:
            from sys import executable
            from subprocess import run
            run([executable, "-m", "pip", "install", "-U", "python-download", "urllib3_request"], check=True)
            from download import download
            from urllib3_request import request

        def progress(total=None):
            dq: deque[tuple[int, float]] = deque(maxlen=64)
            read_num = 0
            dq.append((read_num, perf_counter()))
            while True:
                read_num += yield
                cur_t = perf_counter()
                speed = (read_num - dq[0][0]) / 1024 / 1024 / (cur_t - dq[0][1])
                if total:
                    percentage = read_num / total * 100
                    print(f"\r\x1b[K{read_num} / {total} | {speed:.2f} MB/s | {percentage:.2f} %", end="", flush=True)
                else:
                    print(f"\r\x1b[K{read_num} | {speed:.2f} MB/s", end="", flush=True)
                dq.append((read_num, cur_t))

        for url in urls:
            if not url:
                continue
            print("-"*get_terminal_size().columns)
            print(f"🚀 \x1b[1;5mPROCESSING\x1b[0m \x1b[4;34m{url!r}\x1b[0m")
            try:
                for attr in iterdir(url, predicate=predicate, max_depth=-1):
                    if attr["isdir"]:
                        continue
                    if print_attr:
                        print(attr)
                    down_url = attr["download_url"]
                    headers = attr["headers"]
                    try:
                        file = download(
                            down_url, 
                            joinpath(download_dir, attr["relpath"]), 
                            resume=True, 
                            headers=headers, 
                            make_reporthook=progress, 
                            urlopen=request, 
                        )
                        print(f"\r😄 \x1b[K\x1b[1;32mDOWNLOADED\x1b[0m \x1b[4;34m{down_url!r}\x1b[0m\n |_ \x1b[5m⏬\x1b[0m \x1b[4;34m{file!r}\x1b[0m")
                    except BaseException as e:
                        print(f"\r😮‍💨 \x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{down_url!r}\x1b[0m\n  |_ \x1b[5m🙅\x1b[0m \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
                        if isinstance(e, (BrokenPipeError, EOFError, KeyboardInterrupt)):
                            raise
            except BaseException as e:
                print(f"\r😮‍💨 \x1b[K\x1b[1;31mERROR\x1b[0m \x1b[4;34m{url!r}\x1b[0m\n  |_ \x1b[5m🙅\x1b[0m \x1b[1;31m{type(e).__qualname__}\x1b[0m: {e}")
                if isinstance(e, (BrokenPipeError, EOFError, KeyboardInterrupt)):
                    raise
except (BrokenPipeError, EOFError):
    stderr.close()

