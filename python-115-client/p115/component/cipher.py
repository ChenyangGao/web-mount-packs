#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["P115RSACipher", "P115ECDHCipher"]

from base64 import b64decode, b64encode
from binascii import crc32
from itertools import pairwise
from random import randrange
from typing import Final

from ecdsa import ECDH, NIST224p, SigningKey # type: ignore
from lz4.block import decompress as lz4_block_decompress # type: ignore
from Crypto import Random
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.PublicKey import RSA


NIST224P_BASELEN: Final = 28
RSA_KEY_SIZE: Final = 16
RSA_BLOCK_SIZE: Final = 128
CRC_SALT: Final = b"^j>WD3Kr?J2gLFjD4W2y@"
MD5_SALT: Final = b"Qclm8MGWUv59TnrR0XPg"
ECDH_REMOTE_PUBKEY: Final = bytes((
    0x57, 0xA2, 0x92, 0x57, 0xCD, 0x23, 0x20, 0xE5, 0xD6, 0xD1, 0x43, 0x32, 0x2F, 0xA4, 0xBB, 0x8A, 
    0x3C, 0xF9, 0xD3, 0xCC, 0x62, 0x3E, 0xF5, 0xED, 0xAC, 0x62, 0xB7, 0x67, 0x8A, 0x89, 0xC9, 0x1A, 
    0x83, 0xBA, 0x80, 0x0D, 0x61, 0x29, 0xF5, 0x22, 0xD0, 0x34, 0xC8, 0x95, 0xDD, 0x24, 0x65, 0x24, 
    0x3A, 0xDD, 0xC2, 0x50, 0x95, 0x3B, 0xEE, 0xBA, 
))
G_key_l: Final = bytes((
    0x78, 0x06, 0xad, 0x4c, 0x33, 0x86, 0x5d, 0x18, 0x4c, 0x01, 0x3f, 0x46, 
))
G_key_s: Final = bytes((0x29, 0x23, 0x21, 0x5e))
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
RSA_PRIVATE_KEY: Final = RSA.construct((
    0x8C81424BC166F4918756E9F7B22EFAA03479B081E61896872CB7C51C910D7EC1A4CE2871424D5C9149BD5E08A25959A19AD3C981E6512EFDAB2BB8DA3F1E315C294BD117A9FB9D8CE8E633B4962E087C629DC6CA3A149214B4091EF2B0363CB3AE6C7EE702377F055ED3CD93F6C342256A76554BBEA7F203437BBE65F2DA2741,
    0x10001, 
    0x3704DAB00D80C25E464FFB785A16D95F688D0A5823811758C16308D5A1DB55FA800D967A9B4AEDE79AA783ADFFDCDB23541C80B8D436901F172B1CCCA190B224DBE777BF18B96DD9A30AACE8780350793A4F90A645A7747EF695622EADBE23A4C6D88F22E87842B43B35486C2D1B5B1FA77DB3528B0910CA84EDB7A46AFDBED1, 
))
RSA_PUBLIC_KEY: Final = RSA.construct((
    0x8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683, 
    0x10001, 
))


class P115RSACipher:

    def __init__(self, /):
        self.rand_key: bytes = Random.new().read(RSA_KEY_SIZE)
        self.key: bytes = type(self).gen_key(self.rand_key)

    @staticmethod
    def gen_key(rand_key: bytes | bytearray, sk_len: int = 4, /) -> bytes:
        xor = __class__.xor # type: ignore
        xor_key = bytearray()
        if rand_key and sk_len > 0:
            length = sk_len * (sk_len - 1)
            index = 0
            for i in range(sk_len):
                x = (rand_key[i] + G_kts[index]) & 0xff
                xor_key.append(G_kts[length] ^ x)
                length -= sk_len
                index += sk_len
        return bytes(xor_key)

    @staticmethod
    def xor(src: bytes | bytearray, key: bytes | bytearray, /) -> bytearray:
        secret = bytearray()
        pad = len(src) % 4
        if pad:
            secret.extend(c ^ k for c, k in zip(src[:pad], key[:pad]))
            src = src[pad:]
        key_len = len(key)
        secret.extend(c ^ key[i % key_len] for i, c in enumerate(src))
        return secret

    def encode(self, text: bytes | bytearray | str, /) -> bytes:
        if isinstance(text, str):
            text = bytes(text, "utf-8")
        xor = __class__.xor # type: ignore
        tmp = xor(text, self.key)[::-1]
        xor_text = self.rand_key + xor(tmp, G_key_l)
        block_size = RSA_BLOCK_SIZE - 11
        cipher = PKCS1_v1_5.new(RSA_PUBLIC_KEY)
        cipher_text = bytearray()
        for l, r in pairwise(range(0, len(xor_text) + block_size, block_size)):
            cipher_text += cipher.encrypt(xor_text[l:r])
        return b64encode(cipher_text)

    def decode(self, cipher_text: bytes | bytearray | str, /) -> bytes:
        cipher_text = b64decode(cipher_text)
        xor = __class__.xor # type: ignore
        rsa_e, rsa_n = RSA_PUBLIC_KEY.e, RSA_PUBLIC_KEY.n
        cipher = PKCS1_v1_5.new(RSA_PUBLIC_KEY)
        text = bytearray()
        for l, r in pairwise(range(0, len(cipher_text) + RSA_BLOCK_SIZE, RSA_BLOCK_SIZE)):
            n = int.from_bytes(cipher_text[l:r])
            m = pow(n, rsa_e, rsa_n)
            b = int.to_bytes(m, (m.bit_length() + 0b111) >> 3)
            text += b[b.index(0)+1:]
        rand_key = text[0:RSA_KEY_SIZE]
        text = text[RSA_KEY_SIZE:]
        key_l = __class__.gen_key(rand_key, 12) # type: ignore
        tmp = xor(text, key_l)[::-1]
        return bytes(xor(tmp, self.key))


class P115ECDHCipher:

    def __init__(self):
        pub_key, secret = type(self).generate_pair()
        self.pub_key: bytes = pub_key
        # NOTE: use AES-128
        self.aes_key: bytes = secret[:16]
        self.aes_iv: bytes  = secret[-16:]

    @staticmethod
    def generate_pair() -> tuple[bytes, bytes]:
        sk = SigningKey.generate(NIST224p)
        pk = sk.verifying_key
        ecdh = ECDH(NIST224p)
        ecdh.load_private_key(sk)
        ecdh.load_received_public_key_bytes(ECDH_REMOTE_PUBKEY)
        public = pk.pubkey.point.to_bytes()
        x, y = public[:NIST224P_BASELEN], public[NIST224P_BASELEN:]
        pub_key = bytes((NIST224P_BASELEN + 1, 0x02 + (int.from_bytes(y) & 1))) + x
        # NOTE: Roughly equivalent to
        # n = int((ecdh.public_key.pubkey.point * int.from_bytes(sk.to_string())).x())
        # secret = int.to_bytes(n, (n.bit_length() + 0b111) >> 3)
        secret = ecdh.generate_sharedsecret_bytes()
        return pub_key, secret

    def encode(self, text: bytes | bytearray | str, /) -> bytes:
        "加密数据"
        if isinstance(text, str):
            text = bytes(text, "utf-8")
        pad_size = 16 - (len(text) & 15)
        return AES.new(self.aes_key, AES.MODE_CBC, self.aes_iv).encrypt(
            text + int.to_bytes(pad_size) * pad_size)

    def decode(
        self, 
        cipher_text: bytes | bytearray, 
        /, 
        decompress: bool = False, 
    ) -> bytes:
        "解密数据"
        data = AES.new(self.aes_key, AES.MODE_CBC, self.aes_iv).decrypt(
            cipher_text[:len(cipher_text) & -16])
        if decompress:
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
        ts = int.to_bytes(timestamp, (timestamp.bit_length() + 0b111) >> 3)
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
        h_crc32 = int.to_bytes(crc, 4)
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
            int.from_bytes(bytes(i ^ r1 for i in data[20:24]), byteorder="little"), 
        )

