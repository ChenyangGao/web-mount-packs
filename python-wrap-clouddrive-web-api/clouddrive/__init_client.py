#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

#:------------------------------:#

from pathlib import Path

PROJECT_DIR = Path(__file__).parent
PROTO_DIR = PROJECT_DIR / "proto"
PROTO_FILE = PROTO_DIR / "CloudDrive.proto"
PROTO_PYFILE = PROTO_DIR / "CloudDrive_pb2.py"

need_make_pyproto = False

proto_mtime = PROTO_FILE.stat().st_mtime
try:
    pyproto_mtime = PROTO_PYFILE.stat().st_mtime
except FileNotFoundError:
    need_make_pyproto = True
else:
    if proto_mtime >= pyproto_mtime:
        need_make_pyproto = True

#:------------------------------:#

if need_make_pyproto:
    from subprocess import run
    from sys import executable

    run([executable, "-m", "grpc_tools.protoc", "-I", PROTO_DIR, "--python_out", PROTO_DIR, 
        "--grpc_python_out", PROTO_DIR, "--grpclib_python_out", PROTO_DIR, PROTO_FILE], check=True)

#:------------------------------:#

CLIENT_PYFILE = PROJECT_DIR / "client.py"

try:
    pyclient_mtime = CLIENT_PYFILE.stat().st_mtime
except FileNotFoundError:
    pass
else:
    if proto_mtime < pyclient_mtime:
        raise SystemExit(0)

#:------------------------------:#

from collections import deque
from re import compile as re_compile, MULTILINE
from textwrap import dedent, indent

CRE_message_finditer = re_compile("(?P<comment>(?:^//.*\n)*)^(?P<type>message|enum) (?P<name>\w+)", MULTILINE).finditer

CRE_rpc_finditer = re_compile("(?P<comment>(?:^[ \t]*//.*\n)*)^[ \t]*rpc[ \t](?P<method>\w+)\((?:(?P<argspec>\w+)[ \t]+)?(?P<argtype>[^)]+)\)[^(]+\((?:(?P<retspec>\w+)[ \t]+)?(?P<rettype>[^)]+)\)[^}]+\}", MULTILINE).finditer
CRE_field_finditer = re_compile(r'^[ \t]*(?:(?P<spec>\w+)\s+)?(?P<type>[^=;]+)\s+(?P<name>\w+)(?:\s*=\s*(?P<value>\d+))?\s*;', MULTILINE).finditer
CRE_decorative_line_sub = re_compile("^[ \t]*//.*\n|^[ \t]*\n", MULTILINE).sub
CRE_comment_prefix_sub = re_compile("^ *// *", MULTILINE).sub

proto_code = open(PROTO_FILE, encoding="utf-8").read()


def extract_messages(proto_code):
    it = CRE_message_finditer(proto_code)
    try:
        m = next(it)
    except StopIteration:
        return
    for n in it:
        yield m["name"], {**m.groupdict(), "define": proto_code[m.start():n.start()].rstrip()}
        m = n
    yield m["name"], {**m.groupdict(), "define": proto_code[m.start():].rstrip()}


messages = dict(extract_messages(proto_code))
rpcs = {m["method"]: {**m.groupdict(), "define": dedent(m[0])} for m in CRE_rpc_finditer(proto_code)}

for name, meta in messages.items():
    s = meta["refers"] = set()
    typedef = meta["define"]
    if meta["type"] != "message":
        continue
    typedef = typedef[typedef.index("{")+1:]
    typedef = CRE_decorative_line_sub("", typedef)
    for m in CRE_field_finditer(typedef):
        if m["spec"] == "enum":
            continue
        reftype = m["type"].strip()
        if not reftype:
            continue
        if reftype != name and reftype in messages:
            s.add(reftype)

for name, meta in messages.items():
    if meta["type"] != "message":
        continue
    refs: set[str] = meta["refers"] # type: ignore
    if not refs:
        continue
    dq = deque(refs)
    while dq:
        ref = dq.popleft()
        dq.extend(messages[ref]["refers"]-refs) # type: ignore

method_defs = []
for name, meta in rpcs.items():
    refs = set()
    argspec = meta["argspec"]
    argtype = meta["argtype"]
    retspec = meta["retspec"]
    rettype = meta["rettype"]
    if rettype == "google.protobuf.Empty":
        ret_anno = "None"
    else:
        if rettype not in messages:
            raise NotImplementedError(meta)
        if not retspec:
            ret_anno = f"CloudDrive_pb2.{rettype}"
        elif retspec == "repeated":
            ret_anno = f"list[CloudDrive_pb2.{rettype}]"
        elif retspec == "stream":
            ret_anno = f"Iterator[CloudDrive_pb2.{rettype}]"
        else:
            raise NotImplementedError(meta)
        refs.add(rettype)
        refs.update(messages[rettype]["refers"])
    if argtype == "google.protobuf.Empty":
        method_header = f"def {name}(self, /, async_: bool = False) -> {ret_anno}:"
        method_body = f"return (self.async_stub if async_ else self.stub).{name}(Empty(), metadata=self.metadata)"
    else:
        if argtype not in messages:
            raise NotImplementedError(meta)
        if not argspec:
            arg_anno = f"CloudDrive_pb2.{argtype}"
        elif argspec == "repeated":
            arg_anno = f"list[CloudDrive_pb2.{argtype}]"
        elif argspec == "stream":
            arg_anno = f"Iterator[CloudDrive_pb2.{argtype}]"
        else:
            raise NotImplementedError(meta)
        refs.add(argtype)
        refs.update(messages[argtype]["refers"])
        method_header = f"def {name}(self, arg: {arg_anno}, /, async_: bool = False) -> {ret_anno}:"
        method_body = f"return (self.async_stub if async_ else self.stub).{name}(arg, metadata=self.metadata)"
    method_doc_parts = [
        CRE_comment_prefix_sub("", meta["comment"]), 
        " protobuf rpc definition ".center(64, "-"), 
        "", 
        meta["define"], 
    ]
    if refs:
        method_doc_parts.extend((
            "", 
            " protobuf type definition ".center(64, "-"), 
            "", 
            *(messages[ref]["define"] for ref in sorted(refs)), 
        ))
    method_doc = "\n".join(method_doc_parts).replace('"', '\\"')
    method_def = "\n".join((
        method_header, 
        '    """', 
        indent(method_doc, " "*4), 
        '    """', 
        indent(method_body, " "*4), 
    ))
    method_defs.append(method_def)

file = CLIENT_PYFILE.open("w", encoding="utf-8")
file.write("""\
#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["Client"]

from asyncio import run
from inspect import isawaitable
from typing import Any, Iterator, Never

from google.protobuf.empty_pb2 import Empty # type: ignore
from grpc import insecure_channel # type: ignore
from grpclib.client import Channel # type: ignore
from yarl import URL

import pathlib, sys
PROTO_DIR = str(pathlib.Path(__file__).parent / "proto")
if PROTO_DIR not in sys.path:
    sys.path.append(PROTO_DIR)

import CloudDrive_pb2 # type: ignore
import CloudDrive_pb2_grpc # type: ignore
import CloudDrive_grpc # type: ignore


class Client:
    "clouddrive client that encapsulates grpc APIs"
    origin: str
    username: str
    password: str
    channel: Any
    async_channel: Any
    stub: CloudDrive_pb2_grpc.CloudDriveFileSrvStub
    async_stub: CloudDrive_grpc.CloudDriveFileSrvStub
    download_baseurl: str
    metadata: list[tuple[str, str]]

    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
        channel = None, 
        async_channel = None, 
    ):
        origin = origin.rstrip("/")
        urlp = URL(origin)
        if channel is None:
            channel = insecure_channel(urlp.authority)
        if async_channel is None:
            async_channel = Channel(urlp.host, urlp.port)
        self.__dict__.update(
            origin = origin, 
            download_baseurl = f"{origin}/static/http/{urlp.authority}/False/", 
            username = username, 
            password = password, 
            channel = channel, 
            async_channel = async_channel, 
            stub = CloudDrive_pb2_grpc.CloudDriveFileSrvStub(channel), 
            async_stub = CloudDrive_grpc.CloudDriveFileSrvStub(async_channel), 
            metadata = [], 
        )
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.origin == other.origin and self.username == other.username

    def __hash__(self, /) -> int:
        return hash((self.origin, self.username))

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self.origin!r}, username={self.username!r}, password='******', channel={self.channel!r}, async_channel={self.async_channel})"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    def close(self, /):
        try:
            self.channel.close()
        except:
            pass
        try:
            clo = self.async_channel.close()
            if isawaitable(clo):
                run(clo)
        except:
            pass

    def set_password(self, value: str, /):
        ns.__dict__["password"] = value
        self.login()

    def login(
        self, 
        /, 
        username: str = "", 
        password: str = "", 
    ):
        if not username:
            username = self.username
        if not password:
            password = self.password
        response = self.stub.GetToken(CloudDrive_pb2.GetTokenRequest(userName=username, password=password))
        self.metadata[:] = [("authorization", "Bearer " + response.token),]

""")

for method_def in method_defs:
    file.write(indent(method_def, " "*4))
    file.write("\n\n")

