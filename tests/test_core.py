import asyncio
from dataclasses import replace
import json
import time
import pytest
from p2pvpn.models import Config, Record
from p2pvpn.protocol import Codec, DATA, HELLO
from p2pvpn.routing import Switch
from p2pvpn.peers import PeerTable
from p2pvpn.controller import Controller
from p2pvpn.engine import Engine
from p2pvpn.ipc import IPCServer, request

KEY = "ab" * 32


def config(**kwargs):
    return Config(**(dict(name="alice", swarm="test", key=KEY, address="10.77.0.1/24", advertise="127.0.0.1:5555") | kwargs))


def test_config_rejects_unsafe_values():
    for kwargs in [dict(interface="x;reboot"), dict(address="10.77.0.0/24"), dict(key="00"),
                   dict(advertise="0.0.0.0:123"), dict(name="../x"), dict(mtu=1500)]:
        with pytest.raises(ValueError):
            config(**kwargs)


def test_authenticated_packets_and_replay():
    sender, receiver = Codec(KEY, "test"), Codec(KEY, "test")
    packet = sender.encode(DATA, b"abc")
    assert receiver.decode(packet) == (DATA, b"abc")
    with pytest.raises(ValueError):
        receiver.decode(packet)
    with pytest.raises(ValueError):
        Codec(KEY, "other").decode(packet)
    with pytest.raises(ValueError):
        receiver.decode(packet[:-1] + bytes([packet[-1] ^ 1]))


def test_switch_unicast_broadcast_and_dead_destination():
    switch = Switch()
    a, b = ("127.0.0.1", 1), ("127.0.0.1", 2)
    source = bytes.fromhex("020000000001")
    switch.learn(b"\xff" * 6 + source + b"\x08\x00", a)
    assert switch.destinations(source + b"x" * 8, {a, b}) == [a]
    assert set(switch.destinations(b"\xff" * 6 + b"x" * 8, {a, b})) == {a, b}
    assert switch.destinations(source + b"x" * 8, {b}) == [b]


def test_ip_collision_and_expiry():
    peers = PeerTable(config())
    record = Record("bob", "10.77.0.2", "127.0.0.1:5557", int(time.time()) + 120)
    peers.update(record, ("127.0.0.1", 5557), True)
    assert peers.live()
    with pytest.raises(ValueError):
        peers.update(replace(record, name="eve"), ("127.0.0.1", 5558))
    with pytest.raises(ValueError):
        replace(record, expires=1).validate()


class Link:
    def __init__(self): self.frames = []
    def open(self, receive, failed): self.receive = receive
    def write(self, frame): self.frames.append(frame)
    def close(self): pass


class Transport:
    def __init__(self): self.sent = []
    async def open(self, receive): self.receive = receive
    def send(self, data, address): self.sent.append((data, address))
    def close(self): pass


class Discovery:
    async def start(self): pass
    async def publish(self, record): return True
    async def resolve(self, name): return None
    def close(self): pass


def test_engine_requires_membership_and_survives_malformed_packets():
    link, transport = Link(), Transport()
    engine = Engine(config(), link, transport, Discovery())
    remote = Codec(KEY, "test")
    addr = ("127.0.0.1", 5557)
    frame = b"\xff" * 6 + bytes.fromhex("0200000000020800") + b"payload"
    engine.receive(remote.encode(DATA, frame), addr)
    assert not link.frames
    record = Record("bob", "10.77.0.2", "127.0.0.1:5557", int(time.time()) + 120)
    engine.receive(remote.encode(HELLO, json.dumps(dict(record=record.to_dict(), members=[])).encode()), addr)
    engine.receive(remote.encode(DATA, frame), addr)
    assert link.frames == [frame]
    for packet in (b"", b"bad", remote.encode(HELLO, b"[]"), remote.encode(HELLO, b"null")):
        engine.receive(packet, addr)
    assert engine.stats["dropped"] == 5


async def test_ipc_lock_error_and_stop(tmp_path):
    engine = Engine(config(), Link(), Transport(), Discovery())
    path = str(tmp_path / "control.sock")
    server = IPCServer(path, Controller(engine))
    await server.start()
    second = IPCServer(path, Controller(engine))
    try:
        with pytest.raises(ValueError):
            await second.start()
        assert (await request(path, "status"))["name"] == "alice"
        with pytest.raises(ValueError):
            await request(path, "unknown")
        assert (await request(path, "stop"))["stopping"]
        assert engine.stop_event.is_set()
    finally:
        await server.close()


async def test_link_failure_stops_engine():
    engine = Engine(config(), Link(), Transport(), Discovery())
    await engine.start()
    try:
        engine.fail(OSError("device disappeared"))
        with pytest.raises(OSError, match="device disappeared"):
            await engine.wait()
    finally:
        await engine.close()


def test_tap_configuration_failure_closes_descriptor(monkeypatch):
    from p2pvpn import adapters
    closed = []
    monkeypatch.setattr(adapters.socket, "if_nameindex", lambda: [])
    monkeypatch.setattr(adapters.os, "open", lambda *args: 42)
    monkeypatch.setattr(adapters.os, "close", closed.append)
    monkeypatch.setattr(adapters.fcntl, "ioctl", lambda *args: None)

    class BrokenConfigurator:
        def configure(self, *args):
            raise OSError("ip failed")

    tap = adapters.LinuxTap(config(), BrokenConfigurator())
    with pytest.raises(OSError, match="ip failed"):
        tap.open(lambda frame: None, lambda error: None)
    assert closed == [42] and tap.fd is None


def test_init_private_file_and_no_overwrite(tmp_path):
    from p2pvpn.cli import main
    path = tmp_path / "node.json"
    args = ["init", "--config", str(path), "--name", "alice", "--address", "10.77.0.1/24", "--advertise", "127.0.0.1:5555"]
    assert main(args) == 0
    original = path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    assert main(args) == 1
    assert path.read_bytes() == original
