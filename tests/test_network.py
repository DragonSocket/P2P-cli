"""Real loopback sockets, Kademlia replication, encrypted frame delivery."""
import asyncio
from dataclasses import replace
import socket
import time
from p2pvpn.adapters import UDPTransport
from p2pvpn.discovery import DHTDiscovery
from p2pvpn.engine import Engine
from p2pvpn.models import Record
from test_core import config, Link


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def eventually(predicate):
    async with asyncio.timeout(10):
        while not predicate():
            await asyncio.sleep(.02)


async def test_three_nodes_dht_and_frame_delivery():
    ports = [free_port() for _ in range(6)]
    nodes = []
    for index, peer_name in enumerate(("alice", "bob", "carol")):
        cfg = config(name=peer_name, address=f"10.77.0.{index+1}/24",
                     listen=f"127.0.0.1:{ports[index*2]}", advertise=f"127.0.0.1:{ports[index*2]}",
                     dht_listen=f"127.0.0.1:{ports[index*2+1]}",
                     bootstrap=[] if index == 0 else [f"127.0.0.1:{ports[1]}"])
        nodes.append(Engine(cfg, Link(), UDPTransport(cfg.listen), DHTDiscovery(cfg)))
    try:
        for node in nodes:
            await node.start()
        a, b, c = nodes
        for node in nodes:
            assert await node.discovery.publish(node.record())
        # Carol knows only the seed, yet resolves Bob through the distributed table.
        assert (await c.discovery.resolve("bob")).ip == "10.77.0.2"
        await c.connect("bob")
        await eventually(lambda: b.peers.live() and c.peers.live())
        frame = b"\xff" * 6 + bytes.fromhex("0200000000030800") + b"game-payload"
        c.forward(frame)
        await eventually(lambda: b.link.frames)
        assert b.link.frames == [frame]
        # A replica remains useful after the original publisher stops its DHT.
        b.discovery.close()
        assert (await a.discovery.resolve("bob")).name == "bob"
        assert await a.discovery.resolve("missing") is None
    finally:
        for node in reversed(nodes):
            await node.close()
        await asyncio.sleep(.05)
