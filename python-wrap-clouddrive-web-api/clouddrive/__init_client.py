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
method_map = {}
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
        arg_anno = "None"
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
    method_map[name] = "{%s}" % ", ".join(f'"{k}": {v}' for k, v in (("argument", arg_anno), ("return", ret_anno)) if v != "None")
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
__all__ = ["Client", "CLOUDDRIVE_API_MAP"]

from functools import cached_property
from typing import Any, Iterator, Never, Optional
from urllib.parse import urlsplit, urlunsplit

from google.protobuf.empty_pb2 import Empty # type: ignore
from grpc import insecure_channel, Channel # type: ignore
from grpclib.client import Channel as AsyncChannel # type: ignore
from yarl import URL

import pathlib, sys
PROTO_DIR = str(pathlib.Path(__file__).parent / "proto")
if PROTO_DIR not in sys.path:
    sys.path.append(PROTO_DIR)

import CloudDrive_pb2 # type: ignore
import CloudDrive_pb2_grpc # type: ignore
import CloudDrive_grpc # type: ignore


CLOUDDRIVE_API_MAP = {
""" + "\n".join(f'    "{k}": {v}, ' for k, v in method_map.items()) + """
}


class Client:
    "clouddrive client that encapsulates grpc APIs"
    origin: URL
    username: str
    password: str
    download_baseurl: str
    metadata: list[tuple[str, str]]

    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
    ):
        origin = origin.rstrip("/")
        urlp = urlsplit(origin)
        scheme = urlp.scheme or "http"
        netloc = urlp.netloc or "localhost:19798"
        self.__dict__.update(
            origin = URL(urlunsplit(urlp._replace(scheme=scheme, netloc=netloc))), 
            download_baseurl = f"{scheme}://{netloc}/static/{scheme}/{netloc}/False/", 
            username = username, 
            password = password, 
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
        return f"{name}(origin={self.origin!r}, username={self.username!r}, password='******')"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    @cached_property
    def channel(self, /) -> Channel:
        return insecure_channel(self.origin.authority)

    @cached_property
    def stub(self, /) -> CloudDrive_pb2_grpc.CloudDriveFileSrvStub:
        return CloudDrive_pb2_grpc.CloudDriveFileSrvStub(self.channel)

    @cached_property
    def async_channel(self, /) -> AsyncChannel:
        origin = self.origin
        return AsyncChannel(origin.host, origin.port)

    @cached_property
    def async_stub(self, /) -> CloudDrive_grpc.CloudDriveFileSrvStub:
        return CloudDrive_grpc.CloudDriveFileSrvStub(self.async_channel)

    def close(self, /):
        ns = self.__dict__
        if "channel" in ns:
            ns["channel"].close()
        if "async_channel" in ns:
            ns["async_channel"].close()

    def set_password(self, value: str, /):
        self.__dict__["password"] = value
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

