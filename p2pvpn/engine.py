"""Application model: coordinates discovery, membership and frame switching."""
import asyncio
import json
import logging
import time
from collections import Counter
from .contracts import Link, Transport, Discovery
from .models import Record, endpoint, name
from .peers import PeerTable
from .protocol import Codec, HELLO, DATA
from .routing import Switch

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, config, link: Link, transport: Transport, discovery: Discovery):
        self.config, self.link, self.transport, self.discovery = config, link, transport, discovery
        self.peers = PeerTable(config)
        self.switch = Switch()
        self.codec = Codec(config.key, config.swarm)
        self.targets = set(config.peers)
        self.stats = Counter()
        self.started = time.monotonic()
        self.stop_event = asyncio.Event()
        self.tasks = []
        self.published = False
        self.failure = None

    def record(self):
        return Record(self.config.name, self.config.ip, self.config.advertise, int(time.time()) + 120)

    async def start(self):
        try:
            await self.transport.open(self.receive)
            await self.discovery.start()
            self.link.open(self.forward, self.fail)
            self.tasks = [asyncio.create_task(self.heartbeat()), asyncio.create_task(self.refresh())]
        except BaseException:
            await self.close()
            raise
        log.info("Node %s started in swarm %s", self.config.name, self.config.swarm)

    def fail(self, error):
        self.failure = error
        self.stop_event.set()

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.link.close()
        self.transport.close()
        self.discovery.close()

    def hello(self, address):
        # Bounded gossip exchanges names, not trusted endpoints. DHT resolves names.
        names = sorted(self.peers.entries)[:32]
        message = json.dumps({"record": self.record().to_dict(), "members": names}).encode()
        self.transport.send(self.codec.encode(HELLO, message), address)

    async def heartbeat(self):
        while True:
            for _, address, _ in list(self.peers.entries.values()):
                self.hello(address)
            self.peers.prune()
            await asyncio.sleep(5)

    async def resolve(self, peer_name):
        name(peer_name)
        if peer_name == self.config.name:
            return self.record().to_dict()
        record = await self.discovery.resolve(peer_name)
        if record is None:
            raise LookupError(f"peer not found in DHT: {peer_name}")
        record.validate(self.peers.network)
        return record.to_dict()

    async def connect(self, peer_name):
        record = Record(**await self.resolve(peer_name))
        if peer_name == self.config.name:
            return record.to_dict()
        address = endpoint(record.endpoint)
        self.peers.update(record, address)
        self.hello(address)
        return record.to_dict()

    async def refresh(self):
        while True:
            try:
                self.published = await self.discovery.publish(self.record())
                if not self.published:
                    log.warning("DHT publication has no replicas yet")
            except (OSError, ValueError, TimeoutError) as exc:
                log.warning("DHT publication failed: %s", exc)
            limit = asyncio.Semaphore(8)

            async def refresh_peer(peer_name):
                async with limit:
                    try:
                        await self.connect(peer_name)
                    except (OSError, ValueError, LookupError, TimeoutError) as exc:
                        log.debug("Discovery %s: %s", peer_name, exc)

            await asyncio.gather(*(refresh_peer(item) for item in sorted(self.targets | set(self.peers.entries))))
            await asyncio.sleep(15)

    def receive(self, packet, address):
        try:
            kind, payload = self.codec.decode(packet)
            if kind == HELLO:
                data = json.loads(payload)
                record = Record(**data["record"])
                members = data["members"]
                if not isinstance(members, list) or len(members) > 32:
                    raise ValueError("invalid member list")
                for item in members:
                    name(item)
                was_alive = address in self.peers.live()
                self.peers.update(record, address, confirmed=True)
                for item in [record.name, *members]:
                    if item != self.config.name and len(self.targets) < 256:
                        self.targets.add(item)
                if not was_alive:
                    self.hello(address)
            elif not self.config.headless:
                if address not in self.peers.live() or not 14 <= len(payload) <= self.config.mtu + 14:
                    raise ValueError("data from unconfirmed peer or invalid frame size")
                self.switch.learn(payload, address)
                self.link.write(payload)
                self.stats["rx_frames"] += 1
                self.stats["rx_bytes"] += len(payload)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.stats["dropped"] += 1
            log.debug("Dropped UDP packet from %s: %s", address, exc)

    def forward(self, frame):
        if not 14 <= len(frame) <= self.config.mtu + 14:
            self.stats["dropped"] += 1
            return
        packet = self.codec.encode(DATA, frame)
        for address in self.switch.destinations(frame, self.peers.live()):
            self.transport.send(packet, address)
            self.stats["tx_frames"] += 1
            self.stats["tx_bytes"] += len(frame)

    def status(self):
        return {"name": self.config.name, "swarm": self.config.swarm, "ip": self.config.ip,
                "headless": self.config.headless, "uptime": round(time.monotonic() - self.started),
                "dht_published": self.published, "peers": self.peers.snapshot(), "traffic": dict(self.stats)}

    async def wait(self):
        stopped = asyncio.create_task(self.stop_event.wait())
        try:
            done, _ = await asyncio.wait([stopped, *self.tasks], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()  # Unexpected background errors must fail the service.
            if self.failure:
                raise self.failure
        finally:
            stopped.cancel()
            await asyncio.gather(stopped, return_exceptions=True)
