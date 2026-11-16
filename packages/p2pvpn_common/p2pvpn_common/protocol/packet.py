"""L2 wire codec: [ MAGIC (5) | TYPE (1) | PAYLOAD ].

TYPE 0x01 — DATA  : raw Ethernet frame
TYPE 0x02 — HELLO : keepalive / hole-punch announcement (no payload)
"""
from __future__ import annotations

from p2pvpn_common.constants import MAGIC, MAGIC_LEN, TYPE_DATA, TYPE_HELLO


def encode_data(frame: bytes) -> bytes:
    return MAGIC + bytes([TYPE_DATA]) + frame


def encode_hello() -> bytes:
    return MAGIC + bytes([TYPE_HELLO])


def decode(packet: bytes) -> tuple[int | None, bytes]:
    """Return (type, payload) or (None, b'') if the packet is invalid."""
    if len(packet) < MAGIC_LEN + 1 or packet[:MAGIC_LEN] != MAGIC:
        return None, b""
    return packet[MAGIC_LEN], packet[MAGIC_LEN + 1:]
