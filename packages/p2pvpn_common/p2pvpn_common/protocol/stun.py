"""Minimal STUN client (RFC 5389). No external dependencies.

Ported from root stun_client.py into the common package.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
import struct
from dataclasses import dataclass
from typing import Optional

from p2pvpn_common.constants import (
    DEFAULT_STUN_SERVERS,
    STUN_ATTR_MAPPED_ADDRESS,
    STUN_ATTR_XOR_MAPPED_ADDRESS,
    STUN_BINDING_ERROR,
    STUN_BINDING_REQUEST,
    STUN_BINDING_RESPONSE,
    STUN_HEADER_SIZE,
    STUN_MAGIC_COOKIE,
)

log = logging.getLogger("p2pvpn.stun")


@dataclass(frozen=True)
class STUNResult:
    public_ip: str
    public_port: int
    server_used: str

    def __str__(self) -> str:
        return f"{self.public_ip}:{self.public_port}  (via {self.server_used})"


def _build_binding_request() -> tuple[bytes, bytes]:
    """Return (packet, transaction_id)."""
    txn_id = os.urandom(12)
    header = struct.pack(">HHI", STUN_BINDING_REQUEST, 0, STUN_MAGIC_COOKIE) + txn_id
    return header, txn_id


def _parse_mapped(val: bytes) -> Optional[tuple[str, int]]:
    family = val[1]
    port = struct.unpack(">H", val[2:4])[0]
    if family == 0x01:  # IPv4
        return str(ipaddress.IPv4Address(val[4:8])), port
    return None


def _parse_xor_mapped(val: bytes) -> Optional[tuple[str, int]]:
    family = val[1]
    xport = struct.unpack(">H", val[2:4])[0] ^ (STUN_MAGIC_COOKIE >> 16)
    if family == 0x01:  # IPv4
        xip = struct.unpack(">I", val[4:8])[0] ^ STUN_MAGIC_COOKIE
        return str(ipaddress.IPv4Address(xip)), xport
    if family == 0x02:
        log.debug("IPv6 XOR-MAPPED-ADDRESS — not yet handled")
        return None
    return None


def _parse_response(data: bytes, txn_id: bytes) -> Optional[tuple[str, int]]:
    if len(data) < STUN_HEADER_SIZE:
        log.debug("STUN response too short: %d bytes", len(data))
        return None

    msg_type, _, magic = struct.unpack(">HHI", data[:8])
    resp_txn = data[8:STUN_HEADER_SIZE]

    if msg_type == STUN_BINDING_ERROR:
        log.debug("STUN server returned error response")
        return None
    if msg_type != STUN_BINDING_RESPONSE:
        log.debug("Unexpected STUN message type: 0x%04x", msg_type)
        return None
    if magic != STUN_MAGIC_COOKIE:
        log.debug("STUN magic cookie mismatch")
        return None
    if resp_txn != txn_id:
        log.debug("STUN transaction ID mismatch")
        return None

    offset = STUN_HEADER_SIZE
    xor_result: Optional[tuple[str, int]] = None
    mapped_result: Optional[tuple[str, int]] = None

    while offset + 4 <= len(data):
        attr_type, attr_len = struct.unpack(">HH", data[offset:offset + 4])
        attr_val = data[offset + 4: offset + 4 + attr_len]
        offset += 4 + attr_len
        if attr_len % 4:
            offset += 4 - (attr_len % 4)

        if attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS and len(attr_val) >= 8:
            xor_result = _parse_xor_mapped(attr_val)
        elif attr_type == STUN_ATTR_MAPPED_ADDRESS and len(attr_val) >= 8:
            mapped_result = _parse_mapped(attr_val)

    # XOR-MAPPED-ADDRESS preferred (RFC 5389)
    return xor_result or mapped_result


class _STUNProtocol(asyncio.DatagramProtocol):
    def __init__(self, txn_id: bytes, future: asyncio.Future):
        self._txn_id = txn_id
        self._fut = future

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if self._fut.done():
            return
        result = _parse_response(data, self._txn_id)
        if result:
            self._fut.set_result(result)
        else:
            self._fut.set_exception(ValueError("Invalid STUN response"))

    def error_received(self, exc: Exception) -> None:
        if not self._fut.done():
            self._fut.set_exception(exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if not self._fut.done():
            self._fut.set_exception(ConnectionError("STUN connection lost"))


def _make_reusable_socket(local_port: int) -> socket.socket:
    """SO_REUSEADDR is required so the VPN socket can rebind the same port
    on Windows after the STUN transport closes asynchronously."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
    sock.setblocking(False)
    sock.bind(("0.0.0.0", local_port))
    return sock


async def discover_async(
    servers: Optional[list[tuple[str, int]]] = None,
    timeout: float = 3.0,
    local_port: int = 0,
) -> STUNResult:
    """Discover public IP:port via STUN. Raises RuntimeError if all servers fail.

    CRITICAL: bind the STUN socket to the same port the VPN will listen on.
    NAT creates a distinct mapping per (src_port, dst) — using port 0 here
    would report a wrong external port.
    """
    if not servers:
        servers = list(DEFAULT_STUN_SERVERS)

    loop = asyncio.get_running_loop()
    last_error: Exception = RuntimeError("No STUN servers configured")

    for host, port in servers:
        label = f"{host}:{port}"
        try:
            log.debug("Trying STUN server %s …", label)

            infos = await loop.getaddrinfo(
                host, port, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP
            )
            if not infos:
                raise OSError(f"DNS lookup failed for {host}")
            server_addr = (infos[0][4][0], port)

            request, txn_id = _build_binding_request()
            fut: asyncio.Future = loop.create_future()

            # NOTE: do NOT sock.connect(server_addr) — on Windows ProactorEventLoop
            # a connected socket breaks transport.sendto(data, addr).
            sock = _make_reusable_socket(local_port)
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _STUNProtocol(txn_id, fut), sock=sock
            )
            try:
                transport.sendto(request, server_addr)
                ip, pub_port = await asyncio.wait_for(fut, timeout=timeout)
                log.info("STUN success via %s → %s:%d", label, ip, pub_port)
                return STUNResult(public_ip=ip, public_port=pub_port, server_used=label)
            finally:
                transport.close()

        except asyncio.TimeoutError:
            log.debug("STUN timeout on %s", label)
            last_error = TimeoutError(f"STUN server {label} timed out")
        except Exception as exc:
            log.debug("STUN error on %s: %s", label, exc)
            last_error = exc

    raise RuntimeError(f"All STUN servers failed. Last error: {last_error}")


def discover(
    servers: Optional[list[tuple[str, int]]] = None,
    timeout: float = 3.0,
    local_port: int = 0,
) -> STUNResult:
    """Synchronous convenience wrapper."""
    return asyncio.run(discover_async(servers, timeout, local_port))
