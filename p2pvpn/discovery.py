"""Kademlia adapter: expiring encrypted per-name records, no central registry."""
import asyncio
import hashlib
import json
from kademlia.network import Server
from kademlia.storage import ForgetfulStorage
from kademlia.protocol import KademliaProtocol
from kademlia.utils import digest
import logging
from .models import Record, endpoint, name
from .protocol import Cipher, Codec, DATA


class BoundedStorage(ForgetfulStorage):
    def __setitem__(self, key, value):
        if not isinstance(value, bytes) or len(value) > 2048:
            return
        super().__setitem__(key, value)
        while len(self.data) > 4096:
            self.data.popitem(last=False)


class EncryptedTransport:
    def __init__(self, transport, codec):
        self.transport, self.codec = transport, codec

    def sendto(self, data, address):
        self.transport.sendto(self.codec.encode(DATA, data), address)


class PrivateProtocol(KademliaProtocol):
    def __init__(self, *args, codec):
        super().__init__(*args)
        self.codec = codec

    def connection_made(self, transport):
        super().connection_made(EncryptedTransport(transport, self.codec))

    def datagram_received(self, data, address):
        try:
            kind, payload = self.codec.decode(data)
            if kind == DATA:
                super().datagram_received(payload, address)
        except (ValueError, TypeError):
            logging.getLogger(__name__).debug("Rejected DHT datagram from %s", address)


class DHTDiscovery:
    def __init__(self, config):
        self.config = config
        self.server = Server(ksize=8, alpha=3, storage=BoundedStorage(ttl=120))
        codec = Codec(config.key, config.swarm + "/dht")
        self.server.protocol_class = lambda *args: PrivateProtocol(*args, codec=codec)
        self.cipher = Cipher(config.key, config.swarm, "discovery")

    def key(self, peer_name):
        name(peer_name)
        return hashlib.sha256(f"p2pvpn/v2/{self.config.swarm}/{peer_name}".encode()).hexdigest()

    async def start(self):
        host, port = self.config.dht_listen.rsplit(":", 1)
        await self.server.listen(int(port), interface=host)
        try:
            await self.bootstrap()
        except (OSError, TimeoutError):
            logging.getLogger(__name__).warning("DHT bootstrap unavailable; will retry")

    async def bootstrap(self):
        if self.config.bootstrap:
            async with asyncio.timeout(12):
                await self.server.bootstrap([endpoint(item) for item in self.config.bootstrap])

    async def publish(self, record):
        if not self.server.bootstrappable_neighbors():
            await self.bootstrap()
        value = self.cipher.seal(json.dumps(record.to_dict()).encode())
        # A seed must keep its own record even before a second node joins.
        self.server.storage[digest(self.key(record.name))] = value
        async with asyncio.timeout(12):
            return await self.server.set(self.key(record.name), value)

    async def resolve(self, peer_name):
        key = self.key(peer_name)
        cached = self.server.storage.get(digest(key))
        if cached is not None:
            try:
                Record(**json.loads(self.cipher.open(cached))).validate()
            except (ValueError, TypeError):
                self.server.storage.data.pop(digest(key), None)
        async with asyncio.timeout(12):
            value = await self.server.get(key)
        if value is None:
            return None
        record = Record(**json.loads(self.cipher.open(value)))
        record.validate()
        if record.name != peer_name:
            raise ValueError("DHT record name mismatch")
        return record

    def close(self):
        self.server.stop()
