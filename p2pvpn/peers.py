"""Peer membership, liveness and collision policy independent of transport."""
import ipaddress
import time
from .models import Record


class PeerTable:
    def __init__(self, config):
        self.config = config
        self.network = ipaddress.IPv4Interface(config.address).network
        self.entries = {}

    def update(self, record: Record, address, confirmed=False):
        record.validate(self.network)
        if record.name == self.config.name or record.ip == self.config.ip:
            raise ValueError("peer name or virtual IP conflicts with local node")
        for other, (old, _, _) in self.entries.items():
            if other != record.name and old.ip == record.ip:
                raise ValueError("duplicate virtual IP")
        previous = self.entries.get(record.name)
        if previous and previous[0].ip != record.ip:
            raise ValueError("peer name changed virtual IP")
        if not previous and len(self.entries) >= 256:
            raise ValueError("swarm peer limit reached")
        seen = time.monotonic() if confirmed else (previous[2] if previous and previous[1] == address else 0)
        self.entries[record.name] = (record, address, seen)

    def live(self):
        now = time.monotonic()
        return {address for _, address, seen in self.entries.values() if seen and now - seen < 20}

    def prune(self):
        for key, (record, _, seen) in list(self.entries.items()):
            if record.expires < time.time() and (not seen or time.monotonic() - seen > 60):
                del self.entries[key]

    def snapshot(self):
        live = self.live()
        return [dict(record.to_dict(), observed=f"{addr[0]}:{addr[1]}", status="alive" if addr in live else "pending")
                for record, addr, _ in self.entries.values()]
