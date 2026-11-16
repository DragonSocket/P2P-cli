"""Typed configuration model. Replaces the untyped dict `cfg` access."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from p2pvpn_common.constants import (
    DEFAULT_STUN_SERVERS,
    PEER_DEAD_TIMEOUT,
    PEER_STALE_TIMEOUT,
    TAP_MTU,
)
from p2pvpn_common.errors import ConfigError


@dataclass(frozen=True)
class PeerConfig:
    host: str
    port: int

    @staticmethod
    def parse(s: str) -> "PeerConfig":
        """Parse 'host:port'."""
        parts = s.rsplit(":", 1)
        if len(parts) != 2:
            raise ConfigError(f"Peer must be host:port, got: {s!r}")
        try:
            return PeerConfig(host=parts[0], port=int(parts[1]))
        except ValueError as exc:
            raise ConfigError(f"Invalid peer port in {s!r}") from exc


@dataclass
class VPNConfig:
    local_ip: str = "10.0.0.1"
    listen_port: int = 5555
    tap_name: str = "tap0"
    prefix: int = 24
    mtu: int = TAP_MTU
    peers: list[PeerConfig] = field(default_factory=list)

    skip_stun: bool = False
    stun_servers: list[tuple[str, int]] = field(default_factory=lambda: list(DEFAULT_STUN_SERVERS))
    stun_timeout: float = 3.0

    stale_timeout: float = PEER_STALE_TIMEOUT
    dead_timeout: float = PEER_DEAD_TIMEOUT

    def validate(self) -> None:
        if not self.local_ip:
            raise ConfigError("local_ip is required")
        if not 1 <= self.listen_port <= 65535:
            raise ConfigError(f"listen_port must be 1..65535, got {self.listen_port}")
        if not 1 <= self.prefix <= 32:
            raise ConfigError(f"prefix must be 1..32, got {self.prefix}")
        if self.mtu <= 0:
            raise ConfigError(f"mtu must be positive, got {self.mtu}")

    @staticmethod
    def from_dict(data: dict) -> "VPNConfig":
        try:
            cfg = VPNConfig(
                local_ip=data.get("local_ip", "10.0.0.1"),
                listen_port=int(data.get("listen_port", 5555)),
                tap_name=data.get("tap_name", "tap0"),
                prefix=int(data.get("prefix", 24)),
                mtu=int(data.get("mtu", TAP_MTU)),
                peers=[
                    PeerConfig(host=p["host"], port=int(p["port"]))
                    for p in data.get("peers", [])
                ],
                skip_stun=bool(data.get("skip_stun", False)),
                stun_servers=[
                    (s["host"], int(s["port"])) for s in data["stun_servers"]
                ] if "stun_servers" in data else list(DEFAULT_STUN_SERVERS),
                stun_timeout=float(data.get("stun_timeout", 3.0)),
                stale_timeout=float(data.get("stale_timeout", PEER_STALE_TIMEOUT)),
                dead_timeout=float(data.get("dead_timeout", PEER_DEAD_TIMEOUT)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid config: {exc}") from exc
        cfg.validate()
        return cfg

    @staticmethod
    def from_json(path: Path | str) -> "VPNConfig":
        try:
            with open(path) as f:
                return VPNConfig.from_dict(json.load(f))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Config file {path!r} is not valid JSON: {exc}") from exc
        except FileNotFoundError as exc:
            raise ConfigError(f"Config file {path!r} not found") from exc

    def to_dict(self) -> dict:
        return {
            "local_ip": self.local_ip,
            "listen_port": self.listen_port,
            "tap_name": self.tap_name,
            "prefix": self.prefix,
            "mtu": self.mtu,
            "peers": [{"host": p.host, "port": p.port} for p in self.peers],
            "skip_stun": self.skip_stun,
            "stun_timeout": self.stun_timeout,
        }
