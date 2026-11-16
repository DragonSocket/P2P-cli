"""UDP hole punching without a relay server (SRP: separate strategy class).

Both endpoints simultaneously send HELLO to each other's public address.
The first outbound packet opens a NAT "hole": the router remembers the
(src, dst) mapping and starts letting replies through.

Works for Full Cone, Address-Restricted, Port-Restricted NAT.
Symmetric NAT — not guaranteed (rare for home ISPs).
"""
from __future__ import annotations

import asyncio
import logging

from p2pvpn_common.protocol.packet import encode_hello
from p2pvpn_daemon.core.peer_manager import PeerManager
from p2pvpn_daemon.transport.base import Transport

log = logging.getLogger("p2pvpn.punch")


class HolePuncher:
    def __init__(self, peer_manager: PeerManager, transport: Transport,
                 count: int, interval: float):
        self._peers = peer_manager
        self._transport = transport
        self._count = count
        self._interval = interval

    async def run(self) -> None:
        if not list(self._peers.all()):
            return

        hello = encode_hello()
        log.info("Starting hole punch for %d peer(s)…", len(list(self._peers.all())))
        for i in range(self._count):
            for peer in list(self._peers.all()):
                self._transport.send(hello, peer.addr)
                log.debug("Punch #%d → %s", i + 1, peer.addr)
            await asyncio.sleep(self._interval)

        confirmed = [p for p in self._peers.all() if p.confirmed]
        if confirmed:
            log.info("Hole punch OK: %d/%d peers responded",
                     len(confirmed), len(list(self._peers.all())))
        else:
            log.warning(
                "Hole punch: no peers responded after %d attempts. "
                "Check address, firewall, and NAT type.", self._count
            )
