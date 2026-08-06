"""murmurhash3 x86-32, seed 0 — stdlib reimplementation for the serving path.

The gate cannot depend on sklearn/numpy (AD-11: the advisory path installs
with zero ML dependency). Bit-compatibility with sklearn's HashingVectorizer
hashing is PROVEN by a skip-flagged test that runs when the ml extra exists.
"""

from __future__ import annotations

_MASK = 0xFFFFFFFF
_C1 = 0xCC9E2D51
_C2 = 0x1B873593


def _rotl32(x: int, r: int) -> int:
    return ((x << r) & _MASK) | (x >> (32 - r))


def _fmix(h: int) -> int:
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & _MASK
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _MASK
    h ^= h >> 16
    return h


def murmur3_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3 x86 32-bit — reference algorithm, little-endian blocks."""
    length = len(data)
    h = seed & _MASK
    nblocks = length // 4
    for i in range(nblocks):
        k = int.from_bytes(data[i * 4 : i * 4 + 4], "little")
        k = (k * _C1) & _MASK
        k = _rotl32(k, 15)
        k = (k * _C2) & _MASK
        h ^= k
        h = _rotl32(h, 13)
        h = (h * 5 + 0xE6546B64) & _MASK
    tail = data[nblocks * 4 :]
    k1 = 0
    if len(tail) == 3:
        k1 ^= tail[2] << 16
    if len(tail) >= 2:
        k1 ^= tail[1] << 8
    if len(tail) >= 1:
        k1 ^= tail[0]
        k1 = (k1 * _C1) & _MASK
        k1 = _rotl32(k1, 15)
        k1 = (k1 * _C2) & _MASK
        h ^= k1
    h ^= length
    return _fmix(h)
