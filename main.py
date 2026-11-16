#!/usr/bin/env python3
"""DEPRECATED shim — use the new CLI/daemon instead:

    p2pvpn-cli connect --config node_a.json          (starts daemon + status)
    p2pvpn-cli status / add-peer / stop / demo

This shim keeps the old CLI flags working by mapping them onto
VPNConfig and running the daemon in-process (no IPC).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import warnings

warnings.warn(
    "main.py is deprecated; use `p2pvpn-cli` (see README or ARCHITECTURE.md)",
    DeprecationWarning,
    stacklevel=2,
)

from p2pvpn_common.errors import ConfigError, P2PVPNError
from p2pvpn_common.models.vpn_config import PeerConfig, VPNConfig
from p2pvpn_daemon.main import build_engine, run_daemon


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vpn.main")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P2P L2 VPN (legacy entry)")
    parser.add_argument("--ip", default="10.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--peer", action="append", default=[])
    parser.add_argument("--config")
    parser.add_argument("--tap", default="tap0")
    parser.add_argument("--no-stun", action="store_true")
    parser.add_argument("--fake", action="store_true",
                        help="in-memory TAP/transport (demo without root)")
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> VPNConfig:
    if args.config:
        config = VPNConfig.from_json(args.config)
        for peer in args.peer:
            config.peers.append(PeerConfig.parse(peer))
    else:
        config = VPNConfig(
            local_ip=args.ip,
            listen_port=args.port,
            tap_name=args.tap,
            peers=[PeerConfig.parse(p) for p in args.peer],
        )
        config.validate()
    config.skip_stun = args.no_stun
    return config


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        config = build_config(args)
        engine = build_engine(config, fake=args.fake)
        asyncio.run(run_daemon(engine))
        return 0
    except (ConfigError, P2PVPNError) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
