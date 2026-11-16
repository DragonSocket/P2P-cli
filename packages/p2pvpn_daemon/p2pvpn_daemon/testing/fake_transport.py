"""Loopback Transport for demo/tests: every sent packet is echoed back
to the engine as if it came from the peer. Optionally injects scripted
frames from a "remote node" to simulate real traffic."""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from p2pvpn_common.protocol.packet import decode, encode_data
from p2pvpn_daemon.transport.base import DatagramHandler, Transport


class FakeTransport(Transport):
    def __init__(self, on_datagram: DatagramHandler,
                 echo: bool = True,
                 remote_frames: Optional[list[bytes]] = None,
                 remote_addr: tuple[str, int] = ("203.0.113.50", 5555)):
        self._on_datagram = on_datagram
        self._echo = echo
        self._remote_frames = remote_frames or []
        self._remote_addr = remote_addr
        self._started = False
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    async def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._started = True

    def send(self, packet: bytes, addr: tuple[str, int]) -> None:
        if not self._started:
            raise RuntimeError("FakeTransport not started")
        self.sent.append((packet, addr))
        if self._echo:
            ptype, _ = decode(packet)
            # Echo only HELLO: peers answer keepalive, but echoing DATA back
            # would create an infinite L2 loop in the demo.
            if ptype == 0x02:
                self._on_datagram(packet, addr)

    def inject_remote_frame(self, frame: bytes) -> None:
        """Simulate a frame arriving from the remote node."""
        self._on_datagram(encode_data(frame), self._remote_addr)

    def drain_script(self) -> int:
        """Deliver all scripted remote frames. Returns count."""
        for frame in self._remote_frames:
            self.inject_remote_frame(frame)
        n = len(self._remote_frames)
        self._remote_frames = []
        return n

    def close(self) -> None:
        self._started = False
