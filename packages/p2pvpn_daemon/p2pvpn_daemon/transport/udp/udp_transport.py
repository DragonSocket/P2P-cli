"""Asyncio UDP transport implementation of the Transport interface."""
from __future__ import annotations

import logging
import socket

import asyncio

from p2pvpn_common.errors import TransportError
from p2pvpn_daemon.transport.base import DatagramHandler, Transport

log = logging.getLogger("p2pvpn.transport.udp")


def make_udp_socket(port: int) -> socket.socket:
    """UDP socket ready to bind on 0.0.0.0:port.

    SO_REUSEADDR is mandatory: without it bind() fails with WSAEADDRINUSE
    on Windows if the STUN socket is not fully closed yet. SO_REUSEPORT
    (Linux/BSD) allows several sockets to share the port.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
    sock.setblocking(False)
    sock.bind(("0.0.0.0", port))
    return sock


class _AsyncDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, handler: DatagramHandler):
        self._handler = handler

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._handler(data, addr)

    def error_received(self, exc: Exception) -> None:
        log.warning("UDP error: %s", exc)


class UDPTransport(Transport):
    def __init__(self, port: int, on_datagram: DatagramHandler):
        self._port = port
        self._on_datagram = on_datagram
        self._transport = None

    async def start(self, loop) -> None:
        try:
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _AsyncDatagramProtocol(self._on_datagram),
                sock=make_udp_socket(self._port),
            )
        except OSError as exc:
            raise TransportError(f"Cannot bind UDP transport on port {self._port}: {exc}") from exc
        log.info("UDP socket ready on port %d", self._port)

    def send(self, packet: bytes, addr: tuple[str, int]) -> None:
        if self._transport is None:
            raise TransportError("UDP transport is not started")
        self._transport.sendto(packet, addr)

    def close(self) -> None:
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None
