#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115RSACipher", "P115ECDHCipher"]

from base64 import b64decode, b64encode
from binascii import crc32
from itertools import pairwise
from random import randrange

from .const import G_key_l, CRC_SALT, RSA_PUBKEY_PAIR
from .common import Buffer, RSA_encrypt, gen_key, from_bytes, to_bytes, xor, generate_ecdh_pair


class P115RSACipher:

    def __init__(self, /):
        from Crypto import Random
        self.rand_key: bytes = Random.new().read(16)
        self.key: bytes = gen_key(self.rand_key)

    def encode(self, text: bytes | bytearray | str, /) -> bytes:
        if isinstance(text, str):
            text = bytes(text, "utf-8")
        tmp = xor(text, self.key)[::-1]
        xor_text = self.rand_key + xor(tmp, G_key_l)
        block_size = 128 - 11
        cipher_text = bytearray()
        for l, r in pairwise(range(0, len(xor_text) + block_size, block_size)):
            cipher_text += RSA_encrypt(xor_text[l:r])
        return b64encode(cipher_text)

    def decode(self, cipher_text: bytes | bytearray | str, /) -> bytes:
        cipher_text = b64decode(cipher_text)
        text = bytearray()
        for l, r in pairwise(range(0, len(cipher_text) + 128, 128)):
            n = from_bytes(cipher_text[l:r])
            m = pow(n, RSA_PUBKEY_PAIR[1], RSA_PUBKEY_PAIR[0])
            b = to_bytes(m, (m.bit_length() + 0b111) >> 3)
            text += b[b.index(0)+1:]
        rand_key = text[0:16]
        text = text[16:]
        key_l = gen_key(rand_key, 12)
        tmp = xor(text, key_l)[::-1]
        return bytes(xor(tmp, self.key))


class P115ECDHCipher:

    def __init__(self):
        pub_key, secret = generate_ecdh_pair()
        self.pub_key: bytes = pub_key
        # NOTE: use AES-128
        self.aes_key: bytes = secret[:16]
        self.aes_iv: bytes  = secret[-16:]

    def encode(self, text: bytes | bytearray | str, /) -> bytes:
        "加密数据"
        from Crypto.Cipher import AES

        if isinstance(text, str):
            text = bytes(text, "utf-8")
        pad_size = 16 - (len(text) & 15)
        return AES.new(self.aes_key, AES.MODE_CBC, self.aes_iv).encrypt(
            text + to_bytes(pad_size) * pad_size)

    def decode(
        self, 
        cipher_text: bytes | bytearray, 
        /, 
        decompress: bool = False, 
    ) -> bytes:
        "解密数据"
        from Crypto.Cipher import AES

        data = AES.new(self.aes_key, AES.MODE_CBC, self.aes_iv).decrypt(
            cipher_text[:len(cipher_text) & -16])
        if decompress:
            from lz4.block import decompress as lz4_block_decompress # type: ignore
            size = data[0] + (data[1] << 8)
            data = lz4_block_decompress(data[2:size+2], 0x2000)
        else:
            padding = data[-1]
            if all(c == padding for c in data[-padding:]):
                data = data[:-padding]
        return data

    def encode_token(self, /, timestamp: int) -> bytes:
        "接受一个时间戳（单位是秒），返回一个 token，会把 pub_key 和 timestamp 都编码在内"
        r1, r2 = randrange(256), randrange(256)
        token = bytearray()
        ts = to_bytes(timestamp, (timestamp.bit_length() + 0b111) >> 3)
        if isinstance(self, P115ECDHCipher):
            pub_key = self.pub_key
        else:
            pub_key = self
        token.extend(pub_key[i]^r1 for i in range(15))
        token.append(r1)
        token.append(0x73^r1)
        token.extend((r1,)*3)
        token.extend(r1^ts[3-i] for i in range(4))
        token.extend(pub_key[i]^r2 for i in range(15, len(pub_key)))
        token.append(r2)
        token.append(0x01^r2)
        token.extend((r2,)*3)
        crc = crc32(CRC_SALT+token) & 0xffffffff
        h_crc32 = to_bytes(crc, 4)
        token.extend(h_crc32[3-i] for i in range(4))
        return b64encode(token)

    @staticmethod
    def decode_token(data: str | bytes) -> tuple[bytes, int]:
        "解密 token 数据，返回 pub_key 和 timestamp 的元组"
        data = b64decode(data)
        r1 = data[15]
        r2 = data[39]
        return (
            bytes(c ^ r1 for c in data[:15]) + bytes(c ^ r2 for c in data[24:39]), 
            from_bytes(bytes(i ^ r1 for i in data[20:24]), byteorder="little"), 
        )

