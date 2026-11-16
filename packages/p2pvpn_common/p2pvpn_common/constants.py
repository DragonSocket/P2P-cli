"""Leaf module: protocol and node constants.

This module MUST NOT import anything from the project (dependency-tree leaf),
which guarantees the absence of circular imports.
"""
import os

# ── Wire protocol ────────────────────────────────────────────────
MAGIC: bytes = b"P2PL2"
MAGIC_LEN: int = len(MAGIC)
TYPE_DATA: int = 0x01
TYPE_HELLO: int = 0x02

# ── Ethernet ─────────────────────────────────────────────────────
ETH_PROTO_ARP: int = 0x0806
MAX_FRAME: int = 2048          # Ethernet(1518) + VLAN + запас

# ── MTU budget ───────────────────────────────────────────────────
# Physical MTU 1500 − IP(20) − UDP(8) − MAGIC+TYPE(6) − ISP margin(46)
TAP_MTU: int = 1420

# ── Peer lifecycle ───────────────────────────────────────────────
HEARTBEAT_INTERVAL: float = 5.0
PEER_STALE_TIMEOUT: float = 15.0   # после этого peer считается "stale"
PEER_DEAD_TIMEOUT: float = 30.0    # после этого peer удаляется из таблицы

# ── Hole punching ────────────────────────────────────────────────
PUNCH_COUNT: int = 10
PUNCH_INTERVAL: float = 0.3

# ── STUN (RFC 5389) ──────────────────────────────────────────────
STUN_MAGIC_COOKIE: int = 0x2112A442
STUN_BINDING_REQUEST: int = 0x0001
STUN_BINDING_RESPONSE: int = 0x0101
STUN_BINDING_ERROR: int = 0x0111
STUN_ATTR_MAPPED_ADDRESS: int = 0x0001
STUN_ATTR_XOR_MAPPED_ADDRESS: int = 0x0020
STUN_HEADER_SIZE: int = 20

DEFAULT_STUN_SERVERS: tuple[tuple[str, int], ...] = (
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun.stunprotocol.org", 3478),
    ("stun.nextcloud.com", 3478),
    ("stun.voip.blackberry.com", 3478),
)

# ── IPC (daemon ↔ CLI) ───────────────────────────────────────────
# Overridable via env for tests and for running several instances side by side.
IPC_SOCKET_PATH: str = os.environ.get("P2PVPN_IPC_PATH", "/tmp/p2pvpn.sock")  # Linux
IPC_TCP_PORT: int = int(os.environ.get("P2PVPN_IPC_PORT", "5678"))            # Windows
