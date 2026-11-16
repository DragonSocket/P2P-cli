"""Peer domain model: pure state, no lifecycle policy.

Peer knows *what* happened (last_seen, mac); PeerManager decides *whether*
the peer is alive/stale/dead. This keeps the model interface-small and the
thresholds injectable (DIP).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Peer:
    host: str
    port: int
    # 0.0 = "никогда не отвечал" (пир из конфига, непроверенный)
    last_seen: float = 0.0
    mac: Optional[bytes] = None

    @property
    def addr(self) -> tuple[str, int]:
        return (self.host, self.port)

    @property
    def confirmed(self) -> bool:
        """True если пир хотя бы раз прислал пакет."""
        return self.last_seen > 0.0

    def touch(self, now: Optional[float] = None) -> None:
        self.last_seen = now if now is not None else time.time()

    def age(self, now: Optional[float] = None) -> float:
        return (now if now is not None else time.time()) - self.last_seen

    @property
    def mac_str(self) -> str:
        return ":".join(f"{b:02x}" for b in self.mac) if self.mac else "unknown"

    def __str__(self) -> str:
        return f"{self.host}:{self.port} mac={self.mac_str}"
