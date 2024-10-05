#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "rsa_encode", "rsa_decode", "ecdh_aes_encode", "ecdh_aes_decode", 
    "ecdh_encode_token", "make_upload_payload", 
]

from base64 import b64decode, b64encode
from binascii import b2a_hex, crc32
from hashlib import md5, sha1
from time import time
from urllib.parse import urlencode

from iterutils import acc_step

from .const import AES_KEY, AES_IV, MD5_SALT, RSA_PUBKEY_PAIR
from .common import Buffer, RSA_encrypt, gen_key, from_bytes, to_bytes, xor


def rsa_encode(data: Buffer, /) -> bytes:
    "把数据用 RSA 公钥加密"
    xor_text: Buffer = bytearray(16)
    tmp = memoryview(xor(data, b"\x8d\xa5\xa5\x8d"))[::-1]
    xor_text += xor(tmp, b"x\x06\xadL3\x86]\x18L\x01?F")
    cipher_data = bytearray()
    xor_text = memoryview(xor_text)
    for l, r, _ in acc_step(0, len(xor_text), 117):
        cipher_data += RSA_encrypt(xor_text[l:r])
    return b64encode(cipher_data)


def rsa_decode(cipher_data: Buffer, /) -> bytearray:
    "把数据用 RSA 公钥解密"
    cipher_data = memoryview(b64decode(cipher_data))
    data = bytearray()
    for l, r, _ in acc_step(0, len(cipher_data), 128):
        p = pow(from_bytes(cipher_data[l:r]), RSA_PUBKEY_PAIR[1], RSA_PUBKEY_PAIR[0])
        b = to_bytes(p, (p.bit_length() + 0b111) >> 3)
        data += memoryview(b)[b.index(0)+1:]
    m = memoryview(data)
    key_l = gen_key(m[:16], 12)
    tmp = memoryview(xor(m[16:], key_l))[::-1]
    return xor(tmp, b"\x8d\xa5\xa5\x8d")


def ecdh_aes_encode(data: Buffer, /) -> bytes:
    "用 AES 加密数据，密钥由 ECDH 生成"
    from Crypto.Cipher import AES

    pad_size = -len(data) & 15
    return AES.new(AES_KEY, 2, AES_IV).encrypt(
        data + to_bytes(pad_size) * pad_size)


def ecdh_aes_decode(cipher_data: Buffer, /, decompress: bool = False) -> Buffer:
    "用 AES 解密数据，密钥由 ECDH 生成"
    from Crypto.Cipher import AES

    data = AES.new(AES_KEY, 2, AES_IV).decrypt(
        memoryview(cipher_data)[:len(cipher_data) & -16])
    data = memoryview(data)
    if decompress:
        from lz4.block import decompress as lz4_block_decompress # type: ignore
        size = data[0] + (data[1] << 8)
        data = lz4_block_decompress(data[2:size+2], 0x2000)
    else:
        padding = data[-1]
        if data[-padding:] == bytes(data[-1:]) * padding:
            data = data[:-padding]
    return data


def ecdh_encode_token(timestamp: int, /) -> bytes:
    "用时间戳生成 token，并包含由 ECDH 生成的公钥"
    token = bytearray()
    token += b"\x1d\x03\x0e\x80\xa1x\xdc\xee\xce\xcd\xa3w\xde\x12\x8d\x00s\x00\x00\x00"
    token += to_bytes(timestamp, 4, "little")
    token += b"\x8e\xd9\xdd\xcfU\xaea\xedF\xea\x12\x1a\x1c\xfc\x81\x00\x01\x00\x00\x00"
    token += to_bytes(crc32(b"^j>WD3Kr?J2gLFjD4W2y@" + token), 4, "little")
    return b64encode(token)

def make_upload_payload(payload: dict, /) -> dict:
    """为上传构建 HTTP 请求参数
    """
    t = payload["t"] = int(time())
    sig_sha1 = sha1(bytes(str(payload["userkey"]), "ascii"))
    sig_sha1.update(b2a_hex(sha1(bytes("{userid}{fileid}{target}0".format_map(payload), "ascii")).digest()))
    sig_sha1.update(b"000000")
    payload["sig"] = sig_sha1.hexdigest().upper()
    token_md5 = md5(MD5_SALT)
    token_md5.update(bytes("{fileid}{filesize}{sign_key}{sign_val}{userid}{t}".format_map(payload), "ascii"))
    token_md5.update(b2a_hex(md5(bytes(payload["userid"], "ascii")).digest()))
    token_md5.update(bytes(str(payload["appversion"]), "ascii"))
    payload["token"] = token_md5.hexdigest()
    return {
        "params": {"k_ec": ecdh_encode_token(t).decode("ascii")}, 
        "data": ecdh_aes_encode(urlencode(sorted(payload.items())).encode("latin-1")), 
    }

