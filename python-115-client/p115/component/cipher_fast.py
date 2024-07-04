#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["rsa_encode", "rsa_decode", "ecdh_aes_encode", "ecdh_aes_decode", "ecdh_encode_token"]

from base64 import b64decode, b64encode
from binascii import crc32
from typing import Final

from filewrap import Buffer
from iterutils import acc_step
from lz4.block import decompress as lz4_block_decompress # type: ignore
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.PublicKey import RSA


MD5_SALT: Final = b"Qclm8MGWUv59TnrR0XPg"
G_kts: Final = bytes((
    0xf0, 0xe5, 0x69, 0xae, 0xbf, 0xdc, 0xbf, 0x8a, 0x1a, 0x45, 0xe8, 0xbe, 0x7d, 0xa6, 0x73, 0xb8, 
    0xde, 0x8f, 0xe7, 0xc4, 0x45, 0xda, 0x86, 0xc4, 0x9b, 0x64, 0x8b, 0x14, 0x6a, 0xb4, 0xf1, 0xaa, 
    0x38, 0x01, 0x35, 0x9e, 0x26, 0x69, 0x2c, 0x86, 0x00, 0x6b, 0x4f, 0xa5, 0x36, 0x34, 0x62, 0xa6, 
    0x2a, 0x96, 0x68, 0x18, 0xf2, 0x4a, 0xfd, 0xbd, 0x6b, 0x97, 0x8f, 0x4d, 0x8f, 0x89, 0x13, 0xb7, 
    0x6c, 0x8e, 0x93, 0xed, 0x0e, 0x0d, 0x48, 0x3e, 0xd7, 0x2f, 0x88, 0xd8, 0xfe, 0xfe, 0x7e, 0x86, 
    0x50, 0x95, 0x4f, 0xd1, 0xeb, 0x83, 0x26, 0x34, 0xdb, 0x66, 0x7b, 0x9c, 0x7e, 0x9d, 0x7a, 0x81, 
    0x32, 0xea, 0xb6, 0x33, 0xde, 0x3a, 0xa9, 0x59, 0x34, 0x66, 0x3b, 0xaa, 0xba, 0x81, 0x60, 0x48, 
    0xb9, 0xd5, 0x81, 0x9c, 0xf8, 0x6c, 0x84, 0x77, 0xff, 0x54, 0x78, 0x26, 0x5f, 0xbe, 0xe8, 0x1e, 
    0x36, 0x9f, 0x34, 0x80, 0x5c, 0x45, 0x2c, 0x9b, 0x76, 0xd5, 0x1b, 0x8f, 0xcc, 0xc3, 0xb8, 0xf5, 
))
RSA_encrypt: Final = PKCS1_v1_5.new(RSA.construct((
    0x8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683, 
    0x10001, 
))).encrypt
AES_KEY: bytes = b"\xfb\x1a\x19\xd6R\xf5\xaa\xf7\xbce\x1d\x0fi\xbfB/"
AES_IV: bytes  = b"i\xbfB/I\x96\x05P\xa0\xadD\xec4F\xcbL"

to_bytes = int.to_bytes
from_bytes = int.from_bytes


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


def rsa_encode(data: Buffer, /) -> bytes:
    xor_text: Buffer = bytearray(16)
    tmp = memoryview(xor(data, b"\x8d\xa5\xa5\x8d"))[::-1]
    xor_text += xor(tmp, b"x\x06\xadL3\x86]\x18L\x01?F")
    cipher_data = bytearray()
    xor_text = memoryview(xor_text)
    for l, r, _ in acc_step(0, len(xor_text), 117):
        cipher_data += RSA_encrypt(xor_text[l:r])
    return b64encode(cipher_data)


def rsa_decode(cipher_data: Buffer, /) -> bytearray:
    rsa_e = 65537
    rsa_n = 94467199538421168685115018334776065898663751652520808966691769684389754194866868839785962914624862265689699980316658987338198288176273874160782292722912223482699621202960645813656296092078123617049558650961406540632832570073725203873545017737008711614000139573916153236215559489283800593547775766023112169091
    cipher_data = memoryview(b64decode(cipher_data))
    data = bytearray()
    for l, r, _ in acc_step(0, len(cipher_data), 128):
        p = pow(from_bytes(cipher_data[l:r]), rsa_e, rsa_n)
        b = to_bytes(p, (p.bit_length() + 0b111) >> 3)
        data += memoryview(b)[b.index(0)+1:]
    m = memoryview(data)
    key_l = gen_key(m[:16], 12)
    tmp = memoryview(xor(m[16:], key_l))[::-1]
    return xor(tmp, b"\x8d\xa5\xa5\x8d")


def ecdh_aes_encode(data: Buffer, /) -> bytes:
    "加密数据"
    pad_size = -len(data) & 15
    return AES.new(AES_KEY, 2, AES_IV).encrypt(
        data + to_bytes(pad_size) * pad_size)


def ecdh_aes_decode(cipher_data: Buffer, /, decompress: bool = False) -> Buffer:
    "解密数据"
    data = AES.new(AES_KEY, 2, AES_IV).decrypt(
        memoryview(cipher_data)[:len(cipher_data) & -16])
    data = memoryview(data)
    if decompress:
        size = data[0] + (data[1] << 8)
        data = lz4_block_decompress(data[2:size+2], 0x2000)
    else:
        padding = data[-1]
        if data[-padding:] == bytes(data[-1:]) * padding:
            data = data[:-padding]
    return data


def ecdh_encode_token(timestamp: int, /) -> bytes:
    "用时间戳生成 token"
    token = bytearray()
    token += b"\x1d\x03\x0e\x80\xa1x\xdc\xee\xce\xcd\xa3w\xde\x12\x8d\x00s\x00\x00\x00"
    token += to_bytes(timestamp, 4, "little")
    token += b"\x8e\xd9\xdd\xcfU\xaea\xedF\xea\x12\x1a\x1c\xfc\x81\x00\x01\x00\x00\x00"
    token += to_bytes(crc32(b"^j>WD3Kr?J2gLFjD4W2y@" + token), 4, "little")
    return b64encode(token)

