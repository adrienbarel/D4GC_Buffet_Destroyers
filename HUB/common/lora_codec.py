"""Tiny binary relay messages (PROJECT_SPEC 9). Big-endian, max 51 bytes (LoRaWAN EU868 DR0)."""
from __future__ import annotations

import hashlib
import struct

MAX_PAYLOAD = 51
WHO_HAS = 0x01
I_HAVE = 0x02
BEACON = 0x03

_WHO_HAS = struct.Struct(">BHHB8sB")   # type src msg_id ttl doc_hash want         = 15 B
_I_HAVE = struct.Struct(">BHHBH")      # type src reply_to flags size_kb             = 8 B
_BEACON = struct.Struct(">BHHBI")      # type src seq flags index_version            = 10 B


def doc_hash(doc_id: str) -> bytes:
    """First 8 bytes of SHA-256(doc_id): enough to identify a document, tiny on air."""
    return hashlib.sha256(doc_id.encode("utf-8")).digest()[:8]


def _check(payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload {len(payload)} B exceeds {MAX_PAYLOAD} B")
    return payload


def pack_who_has(src: int, msg_id: int, ttl: int, doc_id: str, want_original: bool = True) -> bytes:
    return _check(_WHO_HAS.pack(WHO_HAS, src, msg_id, ttl, doc_hash(doc_id), int(want_original)))


def pack_i_have(src: int, reply_to: int, has_text: bool, has_original: bool, internet: bool, size_kb: int) -> bytes:
    flags = int(has_text) | int(has_original) << 1 | int(internet) << 2
    return _check(_I_HAVE.pack(I_HAVE, src, reply_to, flags, min(size_kb, 65535)))


def pack_beacon(src: int, seq: int, internet: bool, accepts_courier: bool, index_version: int) -> bytes:
    flags = int(internet) | int(accepts_courier) << 1
    return _check(_BEACON.pack(BEACON, src, seq, flags, index_version))
