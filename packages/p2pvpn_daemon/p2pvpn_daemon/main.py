"""p2pvpn-daemon — entry point.

Assembles the model layer (engine + collaborators), exposes it through IPC.
Run:  python -m p2pvpn_daemon.main --config node_a.json
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from p2pvpn_common.errors import ConfigError, P2PVPNError
from p2pvpn_common.models.vpn_config import VPNConfig
from p2pvpn_common.protocol.stun import discover_async
from p2pvpn_common.utils.system import is_admin
from p2pvpn_daemon.core.engine import VPNEngine
from p2pvpn_daemon.core.peer_manager import PeerManager, PeerManagerConfig
from p2pvpn_daemon.interface.factory import create_l2_interface
from p2pvpn_daemon.ipc.controller import IPCController
from p2pvpn_daemon.ipc.server import create_ipc_server
from p2pvpn_daemon.testing.fake_transport import FakeTransport
from p2pvpn_daemon.testing.memory_interface import InMemoryL2Interface
from p2pvpn_daemon.transport.udp.udp_transport import UDPTransport

log = logging.getLogger("p2pvpn.daemon")


def build_engine(config: VPNConfig, fake: bool = False) -> VPNEngine:
    """Composition root: wire real implementations together.

    ``fake=True`` swaps TAP/UDP for in-memory fakes — same IPC, same engine,
    no root and no network. Used by the CLI demo and by smoke tests.
    """
    if not fake and not is_admin():
        raise P2PVPNError(
            "Daemon requires root (Linux) or Administrator (Windows) "
            "to create a TAP interface. Use the CLI demo mode to try "
            "without privileges: p2pvpn-cli demo"
        )

    if fake:
        config.skip_stun = True

    peers = PeerManager(PeerManagerConfig(
        stale_timeout=config.stale_timeout,
        dead_timeout=config.dead_timeout,
    ))

    def _make_transport(on_datagram):
        if fake:
            return FakeTransport(on_datagram, echo=True)
        return UDPTransport(config.listen_port, on_datagram)

    def _make_interface():
        if fake:
            return InMemoryL2Interface()
        return create_l2_interface(config)

    if fake:
        interface = _make_interface()
        engine_holder: list[VPNEngine] = []

        def on_datagram(data: bytes, addr: tuple[str, int]) -> None:
            engine_holder[0].on_datagram(data, addr)

        engine = VPNEngine(config, interface, _make_transport(on_datagram), peers)
        engine_holder.append(engine)
        return engine

    interface = _make_interface()

    async def _assemble() -> VPNEngine:
        stun = None
        try:
            stun = await discover_async(
                config.stun_servers, config.stun_timeout, config.listen_port
            )
        except RuntimeError as exc:
            log.warning("STUN discovery failed: %s", exc)
            log.warning("Peers will still connect if they know our address.")

        engine: VPNEngine = None  # noqa: F811 — assigned right after transport

        def on_datagram(data: bytes, addr: tuple[str, int]) -> None:
            engine.on_datagram(data, addr)

        transport = UDPTransport(config.listen_port, on_datagram)
        engine = VPNEngine(config, interface, transport, peers, stun)
        return engine

    return asyncio.run(_assemble())


async def run_daemon(engine: VPNEngine) -> None:
    """Run engine + IPC server until SIGINT/SIGTERM."""
    controller = IPCController(engine)
    server = create_ipc_server(controller)
    srv = await server.serve()

    stop_event = asyncio.Event()

    def _signal_handler(sig: int) -> None:
        log.info("Received signal %s, shutting down…", sig)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler, sig)
        except NotImplementedError:
            pass  # Windows

    await engine.start()
    await stop_event.wait()
    await engine.stop()
    srv.close()
    await srv.wait_closed()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="p2pvpn-daemon",
        description="P2P L2 VPN daemon (SOLID/MVC model layer)",
    )
    parser.add_argument("--config", required=True, help="Path to node config JSON")
    parser.add_argument("--skip-stun", action="store_true", help="Skip STUN discovery")
    parser.add_argument("--fake", action="store_true",
                        help="Use in-memory TAP/transport (no root, no network)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    try:
        config = VPNConfig.from_json(args.config)
    except ConfigError as exc:
        log.error("Config error: %s", exc)
        return 2

    if args.skip_stun:
        config.skip_stun = True

    try:
        engine = build_engine(config, fake=args.fake)
    except P2PVPNError as exc:
        log.error("%s", exc)
        return 1

    try:
        asyncio.run(run_daemon(engine))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
