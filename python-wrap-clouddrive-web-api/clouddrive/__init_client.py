#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"

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

    run([executable, "-m", "grpc_tools.protoc", "-I", PROTO_DIR, "--python_out", PROTO_DIR, "--grpc_python_out", PROTO_DIR, PROTO_FILE], check=True)

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

CRE_message_finditer = re_compile("(?P<comment>(?:^[ \t]*//.*\n)*)^[ \t]*(?P<type>message|enum)[ \t](?P<clsname>\w*)\s*\{[^{}]*(?:\{[^{}]*\})*[^{}]*\}", MULTILINE).finditer
CRE_rpc_finditer = re_compile("(?P<comment>(?:^[ \t]*//.*\n)*)^[ \t]*rpc[ \t](?P<method>\w+)\((?:(?P<argspec>\w+)[ \t]+)?(?P<argtype>[^)]+)\)[^(]+\((?:(?P<retspec>\w+)[ \t]+)?(?P<rettype>[^)]+)\)[^}]+\}", MULTILINE).finditer
CRE_field_finditer = re_compile(r'^[ \t]*(?:(?P<spec>\w+)\s+)?(?P<type>[^=;]+)\s+(?P<name>\w+)(?:\s*=\s*(?P<value>\d+))?\s*;', MULTILINE).finditer
CRE_decorative_line_sub = re_compile("^[ \t]*//.*\n|^[ \t]*\n", MULTILINE).sub
CRE_comment_prefix_sub = re_compile("^ *// *", MULTILINE).sub

proto_code = open(PROTO_FILE, encoding="utf-8").read()

messages = {m['clsname']: {**m.groupdict(), "def": dedent(m[0])} for m in CRE_message_finditer(proto_code)}
rpcs = {m['method']: {**m.groupdict(), "def": dedent(m[0])} for m in CRE_rpc_finditer(proto_code)}

for name, meta in messages.items():
    s = meta["refs"] = set()
    typedef = meta["def"]
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
    refs: set[str] = meta["refs"] # type: ignore
    if not refs:
        continue
    dq = deque(refs)
    while dq:
        ref = dq.popleft()
        dq.extend(messages[ref]["refs"]-refs) # type: ignore

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
        refs.update(messages[rettype]["refs"])
    if argtype == "google.protobuf.Empty":
        method_header = f"def {name}(self, /) -> {ret_anno}:"
        method_body = f"return self._stub.{name}(Empty(), metadata=self.metadata)"
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
        refs.update(messages[argtype]["refs"])
        method_header = f"def {name}(self, arg: {arg_anno}, /) -> {ret_anno}:"
        method_body = f"return self._stub.{name}(arg, metadata=self.metadata)"
    method_doc_parts = [
        CRE_comment_prefix_sub("", meta["comment"]), 
        "-" * 64, 
        "\nrpc definition::\n", 
        meta["def"], 
    ]
    if refs:
        method_doc_parts.extend((
            "", 
            "-" * 64, 
            "\ntype definition::\n", 
            *(messages[ref]["def"] for ref in sorted(refs))
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

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["Client"]

from urllib.parse import urlsplit
from typing import Iterator

from google.protobuf.empty_pb2 import Empty # type: ignore
from grpc import insecure_channel # type: ignore

import pathlib, sys
PROTO_DIR = str(pathlib.Path(__file__).parent / "proto")
if PROTO_DIR not in sys.path:
    sys.path.append(PROTO_DIR)

import CloudDrive_pb2 # type: ignore
import CloudDrive_pb2_grpc # type: ignore


class Client:
    "clouddrive client that encapsulates grpc APIs"
    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
        channel = None, 
    ):
        urlp = urlsplit(origin)
        self._origin = f"{urlp.scheme}://{urlp.netloc}"
        self.download_baseurl = f"{urlp.scheme}://{urlp.netloc}/static/{urlp.scheme}/{urlp.netloc}/False/"
        self._username = username
        self._password = password
        self.metadata: list[tuple[str, str]] = []
        if channel is None:
            channel = insecure_channel(urlp.netloc)
        self.channel = channel
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.origin == other.origin

    def __hash__(self, /) -> int:
        return hash(self.origin)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self._origin!r}, username={self._username!r}, password='******', channel={self._channel!r})"

    def close(self, /):
        try:
            self._channel.close()
        except:
            pass

    @property
    def channel(self, /):
        return self._channel

    @channel.setter
    def channel(self, channel, /):
        if callable(channel):
            channel = channel(self.origin)
        self._channel = channel
        self._stub = CloudDrive_pb2_grpc.CloudDriveFileSrvStub(channel)

    @property
    def origin(self, /) -> str:
        return self._origin

    @property
    def username(self, /) -> str:
        return self._username

    @property
    def password(self, /) -> str:
        return self._password

    @password.setter
    def password(self, value: str, /):
        self._password = value
        self.login()

    @property
    def stub(self, /):
        return self._stub

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
        response = self._stub.GetToken(CloudDrive_pb2.GetTokenRequest(userName=username, password=password))
        self.metadata = [("authorization", "Bearer " + response.token),]

""")

for method_def in method_defs:
    file.write(indent(method_def, " "*4))
    file.write("\n\n")

#:------------------------------:#

# TODO: 不知道能不能通过 grpc_tools 直接做词法分析，这样可以少写很多代码，而且更加可靠
