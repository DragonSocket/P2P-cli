"""Demo mode: the full engine running in-process with fake collaborators.

No root, no TAP, no network. Demonstrates the whole pipeline:
config → engine → hole punch → heartbeat → peer lifecycle → frame forwarding.
The View renders exactly the same status snapshot as against a real daemon.
"""
from __future__ import annotations

import asyncio
import time

from p2pvpn_common.models.vpn_config import PeerConfig, VPNConfig
from p2pvpn_daemon.core.engine import VPNEngine
from p2pvpn_daemon.core.peer_manager import PeerManager, PeerManagerConfig
from p2pvpn_daemon.testing.fake_transport import FakeTransport
from p2pvpn_daemon.testing.memory_interface import InMemoryL2Interface
from p2pvpn_cli.view.render import console, render_banner, render_status


def _eth_frame(src: str, dst: str, payload: bytes) -> bytes:
    """Minimal Ethernet frame: dst(6) src(6) proto(2) payload."""
    def mac(s: str) -> bytes:
        return bytes(int(x, 16) for x in s.split(":"))
    return mac(dst) + mac(src) + b"\x08\x00" + payload


async def run_demo(duration: float = 8.0) -> int:
    render_banner()

    config = VPNConfig(
        local_ip="10.0.0.1",
        listen_port=5555,
        tap_name="tap-demo",
        peers=[
            PeerConfig("203.0.113.50", 5555),   # "remote node A"
            PeerConfig("198.51.100.7", 5555),   # "remote node B"
        ],
        skip_stun=True,
        stale_timeout=6.0,
        dead_timeout=12.0,
    )

    interface = InMemoryL2Interface("tap-demo")
    peers = PeerManager(PeerManagerConfig(
        stale_timeout=config.stale_timeout,
        dead_timeout=config.dead_timeout,
        heartbeat_interval=1.0,
    ))

    engine: VPNEngine = None

    def on_datagram(data: bytes, addr: tuple[str, int]) -> None:
        engine.on_datagram(data, addr)

    transport = FakeTransport(on_datagram, echo=True)
    engine = VPNEngine(config, interface, transport, peers)

    console.print("[dim]Demo: engine assembling (fake TAP + loopback transport)…[/dim]")
    await engine.start()

    # Simulated remote traffic arriving "over the wire"
    remote_frame = _eth_frame(
        "20:30:40:50:60:70", "10:20:30:40:50:60",
        b"echo: hello from remote node A",
    )

    deadline = time.time() + duration
    tick = 0
    try:
        while time.time() < deadline:
            await asyncio.sleep(1.0)
            tick += 1
            if tick == 3:
                # Local app sends a frame → engine forwards to all peers
                interface.inject(_eth_frame(
                    "10:20:30:40:50:60", "ff:ff:ff:ff:ff:ff",
                    b"arp: who has 10.0.0.2?",
                ))
            if tick == 4:
                transport.inject_remote_frame(remote_frame)
            render_status(engine.status_snapshot())
    except KeyboardInterrupt:
        pass
    finally:
        await engine.stop()

    console.print("\n[dim]Demo finished. Frames forwarded to peers: "
                  f"{len(transport.sent)}[/dim]")
    return 0


def demo(duration: float) -> int:
    return asyncio.run(run_demo(duration))
