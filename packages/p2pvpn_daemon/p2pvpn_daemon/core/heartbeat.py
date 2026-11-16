"""Keepalive strategy: periodic HELLO to every peer (SRP: one class, one job)."""
from __future__ import annotations

import asyncio

from p2pvpn_common.protocol.packet import encode_hello
from p2pvpn_daemon.core.peer_manager import PeerManager
from p2pvpn_daemon.transport.base import Transport


class Heartbeat:
    def __init__(self, peer_manager: PeerManager, transport: Transport,
                 interval: float):
        self._peers = peer_manager
        self._transport = transport
        self._interval = interval

    async def run(self) -> None:
        hello = encode_hello()
        while True:
            await asyncio.sleep(self._interval)
            for peer in list(self._peers.all()):
                self._transport.send(hello, peer.addr)
