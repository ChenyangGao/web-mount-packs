#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "Buffer", "RSA_encrypt", "from_bytes", "to_bytes", 
    "bytes_xor", "bytes_xor_reverse", "xor", "gen_key", 
]

from functools import partial
from typing import Final

from iterutils import acc_step

from .const import G_kts, ECDH_REMOTE_PUBKEY, RSA_PUBKEY_PAIR

try:
    from collections.abc import Buffer # type: ignore
except ImportError:
    from abc import ABC, abstractmethod
    from array import array

    def _check_methods(C, *methods):
        mro = C.__mro__
        for method in methods:
            for B in mro:
                if method in B.__dict__:
                    if B.__dict__[method] is None:
                        return NotImplemented
                    break
            else:
                return NotImplemented
        return True

    class Buffer(ABC): # type: ignore
        __slots__ = ()

        @abstractmethod
        def __buffer__(self, flags: int, /) -> memoryview:
            raise NotImplementedError

        @classmethod
        def __subclasshook__(cls, C):
            if cls is Buffer:
                return _check_methods(C, "__buffer__")
            return NotImplemented

    Buffer.register(bytes)
    Buffer.register(bytearray)
    Buffer.register(memoryview)
    Buffer.register(array)


to_bytes = partial(int.to_bytes, byteorder="big", signed=False)
from_bytes = partial(int.from_bytes, byteorder="big", signed=False)

_pkcs_encrypt = None

def RSA_encrypt(message, /):
    global _pkcs_encrypt
    if _pkcs_encrypt is None:
        from Crypto.Cipher import PKCS1_v1_5
        from Crypto.PublicKey import RSA
        _pkcs_encrypt = PKCS1_v1_5.new(RSA.construct(RSA_PUBKEY_PAIR)).encrypt
    return _pkcs_encrypt(message)


def bytes_xor(v1: Buffer, v2: Buffer, /, size: int = 0) -> Buffer:
    if size:
        v1 = v1[:size]
        v2 = v2[:size]
    else:
        size = len(v1)
    return to_bytes(from_bytes(v1) ^ from_bytes(v2), size)


def bytes_xor_reverse(v1: Buffer, v2: Buffer, /, size: int = 0) -> Buffer:
    if size:
        v1 = v1[:size]
        v2 = v2[:size]
    else:
        size = len(v1)
    return to_bytes(from_bytes(v1) ^ from_bytes(v2), size, "little")


def xor(src: Buffer, key: Buffer, /) -> bytearray:
    src = memoryview(src)
    key = memoryview(key)
    secret = bytearray()
    if i := len(src) & 0b11:
        secret += bytes_xor(src, key, i)
    for i, j, s in acc_step(i, len(src), len(key)):
        secret += bytes_xor(src[i:j], key[:s])
    return secret


def gen_key(
    rand_key: Buffer, 
    sk_len: int = 4, 
    /, 
) -> bytearray:
    xor_key = bytearray()
    if rand_key and sk_len > 0:
        length = sk_len * (sk_len - 1)
        index = 0
        for i in range(sk_len):
            x = (rand_key[i] + G_kts[index]) & 0xff
            xor_key.append(G_kts[length] ^ x)
            length -= sk_len
            index += sk_len
    return xor_key


def generate_ecdh_pair() -> tuple[bytes, bytes]:
    from ecdsa import ECDH, NIST224p, SigningKey # type: ignore

    sk = SigningKey.generate(NIST224p)
    pk = sk.verifying_key
    ecdh = ECDH(NIST224p)
    ecdh.load_private_key(sk)
    ecdh.load_received_public_key_bytes(ECDH_REMOTE_PUBKEY)
    public = pk.pubkey.point.to_bytes()
    x, y = public[:28], public[28:]
    pub_key = bytes((28 + 1, 0x02 + (from_bytes(y) & 1))) + x
    # NOTE: Roughly equivalent to
    # n = int((ecdh.public_key.pubkey.point * from_bytes(sk.to_string())).x())
    # secret = to_bytes(n, (n.bit_length() + 0b111) >> 3)
    secret = ecdh.generate_sharedsecret_bytes()
    return pub_key, secret

