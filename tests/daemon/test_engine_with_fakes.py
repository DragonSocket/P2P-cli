import asyncio

from p2pvpn_common.models.vpn_config import PeerConfig, VPNConfig
from p2pvpn_daemon.core.engine import VPNEngine
from p2pvpn_daemon.core.peer_manager import PeerManager, PeerManagerConfig
from p2pvpn_daemon.testing.fake_transport import FakeTransport
from p2pvpn_daemon.testing.memory_interface import InMemoryL2Interface


def build_engine() -> tuple[VPNEngine, FakeTransport, InMemoryL2Interface]:
    config = VPNConfig(
        local_ip="10.0.0.1",
        listen_port=5555,
        peers=[PeerConfig("203.0.113.50", 5555)],
        stale_timeout=6.0,
        dead_timeout=12.0,
    )
    iface = InMemoryL2Interface()
    peers = PeerManager(PeerManagerConfig(heartbeat_interval=0.1))
    engine_holder = {}

    def on_datagram(data: bytes, addr: tuple) -> None:
        engine_holder["engine"].on_datagram(data, addr)

    transport = FakeTransport(on_datagram, echo=True)
    engine = VPNEngine(config, iface, transport, peers)
    engine_holder["engine"] = engine
    return engine, transport, iface


def test_engine_forwards_local_frames_to_all_peers():
    engine, transport, iface = build_engine()

    async def run():
        await engine.start()
        iface.inject(b"local frame")
        await asyncio.sleep(0.1)
        await engine.stop()

    asyncio.run(run())
    sent = [pkt for pkt, addr in transport.sent if addr == ("203.0.113.50", 5555)]
    data_frames = [p for p in sent if p[5] == 0x01]
    assert any(f == b"P2PL2\x01local frame" for f in data_frames)


def test_remote_frame_reaches_interface():
    engine, transport, iface = build_engine()

    async def run():
        await engine.start()
        transport.inject_remote_frame(b"remote frame")
        await asyncio.sleep(0.1)
        frames = iface.frames()
        await engine.stop()
        return frames

    assert b"remote frame" in asyncio.run(run())


def test_hole_punch_echo_marks_peers_alive():
    engine, transport, iface = build_engine()

    async def run():
        await engine.start()
        await asyncio.sleep(0.5)
        snap = engine.status_snapshot()
        await engine.stop()
        return snap

    snap = asyncio.run(run())
    assert snap["peer_counts"]["alive"] == 1


def test_status_snapshot_has_required_fields():
    engine, _, _ = build_engine()

    async def run():
        await engine.start()
        snap = engine.status_snapshot()
        await engine.stop()
        return snap

    snap = asyncio.run(run())
    for field in ("running", "local_ip", "listen_port", "peers", "peer_counts"):
        assert field in snap
    assert snap["running"] is True
