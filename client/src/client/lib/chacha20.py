"""
Copied from: https://github.com/pts/chacha20
"""
import functools

from typing import Optional

import struct


def yield_chacha20_xor_stream(key, iv, position=0):
    """Generate the xor stream with the ChaCha20 cipher."""
    if not isinstance(position, int):
        raise TypeError
    if position & ~0xffffffff:
        raise ValueError('Position is not uint32.')
    if not isinstance(key, bytes):
        raise TypeError
    if not isinstance(iv, bytes):
        raise TypeError
    if len(key) != 32:
        raise ValueError
    if len(iv) != 8:
        raise ValueError

    def rotate(v, c):
        return ((v << c) & 0xffffffff) | v >> (32 - c)

    def quarter_round(x, a, b, c, d):
        x[a] = (x[a] + x[b]) & 0xffffffff
        x[d] = rotate(x[d] ^ x[a], 16)
        x[c] = (x[c] + x[d]) & 0xffffffff
        x[b] = rotate(x[b] ^ x[c], 12)
        x[a] = (x[a] + x[b]) & 0xffffffff
        x[d] = rotate(x[d] ^ x[a], 8)
        x[c] = (x[c] + x[d]) & 0xffffffff
        x[b] = rotate(x[b] ^ x[c], 7)

    ctx = [0] * 16
    ctx[:4] = (1634760805, 857760878, 2036477234, 1797285236)
    ctx[4: 12] = struct.unpack('<8L', key)
    ctx[12] = ctx[13] = position
    ctx[14: 16] = struct.unpack('<LL', iv)
    while 1:
        x = list(ctx)
        for i in range(10):
            quarter_round(x, 0, 4, 8, 12)
            quarter_round(x, 1, 5, 9, 13)
            quarter_round(x, 2, 6, 10, 14)
            quarter_round(x, 3, 7, 11, 15)
            quarter_round(x, 0, 5, 10, 15)
            quarter_round(x, 1, 6, 11, 12)
            quarter_round(x, 2, 7, 8, 13)
            quarter_round(x, 3, 4, 9, 14)
        for c in struct.pack('<16L', *(
                (x[i] + ctx[i]) & 0xffffffff for i in range(16))):
            yield c
        ctx[12] = (ctx[12] + 1) & 0xffffffff
        if ctx[12] == 0:
            ctx[13] = (ctx[13] + 1) & 0xffffffff


def chacha20_encrypt_pure(data, key, iv=None, position=0):
    """Encrypt (or decrypt) with the ChaCha20 cipher."""
    if not isinstance(data, bytes):
        raise TypeError
    if iv is None:
        iv = b'\0' * 8
    if isinstance(key, bytes):
        if not key:
            raise ValueError('Key is empty.')
        if len(key) < 32:
            key = (key * (32 // len(key) + 1))[:32]
        if len(key) > 32:
            raise ValueError('Key too long.')

    return bytes(a ^ b for a, b in zip(data, yield_chacha20_xor_stream(key, iv, position)))


@functools.lru_cache()
def get_encryptor(key: bytes, iv: bytes):
    from Crypto.Cipher import ChaCha20
    if len(key) < 32:
        key = (key * (32 // len(key) + 1))[:32]
    return ChaCha20.new(key=key, nonce=iv)


def chacha20_encrypt(data: bytes, key: bytes, iv: bytes = b'\0' * 8):
    cipher = get_encryptor(key, iv)
    cipher.seek(0)
    return cipher.decrypt(data)
