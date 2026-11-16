"""Peer registry with injectable lifecycle thresholds (DIP).

Status model:
  pending — never responded yet (from config)
  alive   — responded within stale_timeout
  stale   — silent > stale_timeout but < dead_timeout (still sent to)
  dead    — silent >= dead_timeout (pruned from the table)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from p2pvpn_common.constants import HEARTBEAT_INTERVAL, PEER_DEAD_TIMEOUT, PEER_STALE_TIMEOUT
from p2pvpn_common.models.peer import Peer

log = logging.getLogger("p2pvpn.peers")


@dataclass(frozen=True)
class PeerManagerConfig:
    stale_timeout: float = PEER_STALE_TIMEOUT
    dead_timeout: float = PEER_DEAD_TIMEOUT
    heartbeat_interval: float = HEARTBEAT_INTERVAL


class PeerManager:
    def __init__(self, config: PeerManagerConfig = PeerManagerConfig()):
        self._config = config
        self._peers: dict[tuple[str, int], Peer] = {}

    @property
    def config(self) -> PeerManagerConfig:
        return self._config

    def add(self, host: str, port: int, now: Optional[float] = None) -> Peer:
        key = (host, port)
        peer = self._peers.get(key)
        if peer is None:
            peer = Peer(host=host, port=port)
            self._peers[key] = peer
            log.info("Registered peer: %s:%d", host, port)
        return peer

    def remove(self, host: str, port: int) -> Optional[Peer]:
        return self._peers.pop((host, port), None)

    def get(self, host: str, port: int) -> Optional[Peer]:
        return self._peers.get((host, port))

    def touch(self, host: str, port: int, now: Optional[float] = None) -> Peer:
        peer = self.add(host, port, now)
        peer.touch(now)
        return peer

    def status(self, peer: Peer, now: Optional[float] = None) -> str:
        if not peer.confirmed:
            return "pending"
        age = peer.age(now)
        if age < self._config.stale_timeout:
            return "alive"
        if age < self._config.dead_timeout:
            return "stale"
        return "dead"

    def all(self) -> Iterable[Peer]:
        return list(self._peers.values())

    def sendable(self, now: Optional[float] = None) -> list[Peer]:
        """Peers we still forward frames to: pending + alive + stale."""
        now = now if now is not None else time.time()
        return [p for p in self._peers.values() if self.status(p, now) != "dead"]

    def prune_dead(self, now: Optional[float] = None) -> list[Peer]:
        now = now if now is not None else time.time()
        dead = [key for key, p in self._peers.items() if self.status(p, now) == "dead"]
        removed = []
        for key in dead:
            removed.append(self._peers.pop(key))
            log.info("Peer timed out, removing: %s", removed[-1])
        return removed

    def snapshot(self, now: Optional[float] = None) -> list[dict]:
        now = now if now is not None else time.time()
        return [
            {
                "host": p.host,
                "port": p.port,
                "status": self.status(p, now),
                "last_seen": p.last_seen,
                "last_seen_ago": round(p.age(now), 1) if p.confirmed else None,
                "age": round(p.age(now), 1) if p.confirmed else None,
                "mac": p.mac_str,
            }
            for p in self._peers.values()
        ]

    def counts(self, now: Optional[float] = None) -> dict[str, int]:
        statuses = [self.status(p, now) for p in self._peers.values()]
        return {
            "alive": statuses.count("alive"),
            "pending": statuses.count("pending"),
            "stale": statuses.count("stale"),
            "dead": statuses.count("dead"),
            "total": len(statuses),
        }
