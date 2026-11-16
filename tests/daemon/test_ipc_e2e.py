import asyncio
import json

from p2pvpn_common.models.vpn_config import VPNConfig
from p2pvpn_common.protocol.ipc import IPCCommand, IPCRequest
from p2pvpn_daemon.core.engine import VPNEngine
from p2pvpn_daemon.core.peer_manager import PeerManager
from p2pvpn_daemon.ipc.controller import IPCController
from p2pvpn_daemon.ipc.server import UnixIPCServer
from p2pvpn_daemon.testing.fake_transport import FakeTransport
from p2pvpn_daemon.testing.memory_interface import InMemoryL2Interface

TEST_SOCKET = "/tmp/p2pvpn-test.sock"


def make_engine() -> VPNEngine:
    config = VPNConfig(local_ip="10.0.0.1", peers=[])
    iface = InMemoryL2Interface()
    peers = PeerManager()
    holder = {}

    def on_datagram(data: bytes, addr: tuple) -> None:
        holder["engine"].on_datagram(data, addr)

    transport = FakeTransport(on_datagram, echo=False)
    engine = VPNEngine(config, iface, transport, peers)
    holder["engine"] = engine
    return engine


async def _ask_async(path: str, payload: str) -> str:
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        writer.write((payload + "\n").encode())
        await writer.drain()
        return (await asyncio.wait_for(reader.readline(), 5)).decode()
    finally:
        writer.close()
        await writer.wait_closed()


def test_ipc_end_to_end():
    engine = make_engine()

    async def run():
        await engine.start()
        server = UnixIPCServer(IPCController(engine), path=TEST_SOCKET)
        srv = await server.serve()
        raw = await _ask_async(TEST_SOCKET,
                               IPCRequest(IPCCommand.ADD_PEER, {"peer": "9.9.9.9:5555"}).to_json())
        srv.close()
        await srv.wait_closed()
        await engine.stop()
        return raw

    resp = json.loads(asyncio.run(run()))
    assert resp["status"] == "success"
    assert resp["data"]["added"] == "9.9.9.9:5555"
    assert any(p["host"] == "9.9.9.9" for p in engine.status_snapshot()["peers"])


def test_ipc_bad_peer_returns_error():
    engine = make_engine()

    async def run():
        server = UnixIPCServer(IPCController(engine), path=TEST_SOCKET)
        srv = await server.serve()
        raw = await _ask_async(TEST_SOCKET, '{"command": "ADD_PEER", "params": {"peer": "broken"}}')
        srv.close()
        await srv.wait_closed()
        return raw

    resp = json.loads(asyncio.run(run()))
    assert resp["status"] == "error"
