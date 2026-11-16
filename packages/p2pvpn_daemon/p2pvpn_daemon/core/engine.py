"""VPNEngine — orchestrator of components (assembler role, not a god class).

Collaborators are injected via constructors (DIP):
    VPNEngine(config, interface, transport, peer_manager)
The engine never knows whether the interface is a real TAP or an in-memory
fake, nor whether the transport is UDP or a loopback — which makes the whole
system testable and demoable without root.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from p2pvpn_common.constants import HEARTBEAT_INTERVAL, PUNCH_COUNT, PUNCH_INTERVAL
from p2pvpn_common.models.vpn_config import VPNConfig
from p2pvpn_common.protocol.packet import decode, encode_data
from p2pvpn_common.protocol.stun import STUNResult
from p2pvpn_daemon.core.heartbeat import Heartbeat
from p2pvpn_daemon.core.hole_punch import HolePuncher
from p2pvpn_daemon.core.peer_manager import PeerManager
from p2pvpn_daemon.interface.base import L2Interface
from p2pvpn_daemon.transport.base import Transport

log = logging.getLogger("p2pvpn.engine")


class VPNEngine:
    def __init__(
        self,
        config: VPNConfig,
        interface: L2Interface,
        transport: Transport,
        peer_manager: PeerManager,
        stun_result: Optional[STUNResult] = None,
    ):
        self._config = config
        self._interface = interface
        self._transport = transport
        self._peers = peer_manager
        self._stun = stun_result

        self._started_at: float = 0.0
        self._frames_forwarded: int = 0
        self._frames_received: int = 0
        self._running: bool = False
        self._tasks: list[asyncio.Task] = []

    # ── Wire-level event handlers ────────────────────────────────

    def on_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        ptype, payload = decode(data)
        if ptype is None:
            log.debug("Ignoring non-VPN packet from %s (%d bytes)", addr, len(data))
            return

        self._peers.touch(addr[0], addr[1])

        if ptype == 0x01 and payload:
            self._frames_received += 1
            self._interface.write(payload)

    def _on_frame(self, frame: bytes) -> None:
        packet = encode_data(frame)
        for peer in self._peers.sendable():
            try:
                self._transport.send(packet, peer.addr)
                self._frames_forwarded += 1
            except Exception as exc:
                log.warning("Send to %s failed: %s", peer.addr, exc)

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        loop = asyncio.get_running_loop()

        self._interface.setup()
        self._interface.start_reading(loop, self._on_frame)
        await self._transport.start(loop)

        for p in self._config.peers:
            self._peers.add(p.host, p.port)

        self._running = True
        self._started_at = time.time()

        pm_config = self._peers.config  # thresholds live in PeerManagerConfig
        punch = HolePuncher(self._peers, self._transport, PUNCH_COUNT, PUNCH_INTERVAL)
        beat = Heartbeat(self._peers, self._transport, pm_config.heartbeat_interval)
        self._tasks.append(loop.create_task(punch.run()))
        self._tasks.append(loop.create_task(beat.run()))
        self._tasks.append(loop.create_task(self._prune_loop(pm_config.dead_timeout)))

        log.info("Engine started. Local %s, listening on port %d",
                 self._config.local_ip, self._config.listen_port)
        if self._stun:
            log.info("This node is reachable at %s", self._stun)

    async def _prune_loop(self, dead_timeout: float) -> None:
        while self._running:
            await asyncio.sleep(min(dead_timeout / 2, 5.0))
            self._peers.prune_dead()

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._interface.teardown()
        self._transport.close()
        log.info("Engine stopped. Forwarded %d frames, received %d",
                 self._frames_forwarded, self._frames_received)

    # ── Peer management (IPC-facing) ─────────────────────────────

    def add_peer(self, host: str, port: int) -> None:
        self._peers.add(host, port)

    def remove_peer(self, host: str, port: int) -> bool:
        return self._peers.remove(host, port) is not None

    # ── IPC-facing state ─────────────────────────────────────────

    def status_snapshot(self) -> dict:
        return {
            "running": self._running,
            "local_ip": self._config.local_ip,
            "listen_port": self._config.listen_port,
            "tap_name": self._config.tap_name,
            "mtu": self._config.mtu,
            "uptime": round(time.time() - self._started_at, 1) if self._started_at else 0,
            "frames_forwarded": self._frames_forwarded,
            "frames_received": self._frames_received,
            "public": str(self._stun) if self._stun else None,
            "peers": self._peers.snapshot(),
            "peer_counts": self._peers.counts(),
        }
