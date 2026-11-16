"""Validated configuration and peer records shared across adapters."""
from dataclasses import dataclass, field, asdict
import ipaddress
import json
import re
import time


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", value):
        raise ValueError("name/swarm must contain 1–32 lowercase letters, digits, '_' or '-'")
    return value


def endpoint(value):
    host, port = value.rsplit(":", 1)
    address = ipaddress.IPv4Address(host)
    port = int(port)
    if address.is_unspecified or address.is_multicast or int(address) == 0xffffffff or not 1 <= port <= 65535:
        raise ValueError("endpoint must be a unicast IPv4 address:port")
    return str(address), port


@dataclass(frozen=True)
class Config:
    name: str
    swarm: str
    key: str = field(repr=False)
    address: str
    advertise: str
    listen: str = "0.0.0.0:5555"
    dht_listen: str = "0.0.0.0:5556"
    bootstrap: list[str] = field(default_factory=list)
    peers: list[str] = field(default_factory=list)
    interface: str = "p2p0"
    mtu: int = 1200
    socket: str = "/run/p2pvpn/control.sock"
    log_level: str = "INFO"
    log_file: str | None = None
    headless: bool = False

    def __post_init__(self):
        name(self.name)
        name(self.swarm)
        if len(bytes.fromhex(self.key)) != 32:
            raise ValueError("key must be 32 random bytes encoded as 64 hex characters")
        iface = ipaddress.IPv4Interface(self.address)
        if iface.network.prefixlen > 30 or iface.ip in (iface.network.network_address, iface.network.broadcast_address):
            raise ValueError("address must be a usable IPv4 host with prefix <= 30")
        endpoint(self.advertise)
        for value in (self.listen, self.dht_listen):
            host, port = value.rsplit(":", 1)
            ipaddress.IPv4Address(host)
            if not 1 <= int(port) <= 65535:
                raise ValueError("invalid listen port")
        if self.listen == self.dht_listen:
            raise ValueError("data and DHT require different UDP sockets")
        if not isinstance(self.bootstrap, list) or not isinstance(self.peers, list):
            raise ValueError("bootstrap and peers must be lists")
        if len(self.bootstrap) > 16 or len(self.peers) > 256:
            raise ValueError("too many bootstrap nodes or peers")
        for value in self.bootstrap:
            endpoint(value)
        for value in self.peers:
            name(value)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,15}", self.interface):
            raise ValueError("invalid interface name")
        if type(self.mtu) is not int or not 576 <= self.mtu <= 1200:
            raise ValueError("mtu must be between 576 and 1200")
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("invalid log_level")
        if type(self.headless) is not bool:
            raise ValueError("headless must be boolean")

    @property
    def ip(self):
        return str(ipaddress.IPv4Interface(self.address).ip)

    @classmethod
    def load(cls, path):
        with open(path) as stream:
            return cls(**json.load(stream))


@dataclass(frozen=True)
class Record:
    name: str
    ip: str
    endpoint: str
    expires: int

    def validate(self, network=None):
        name(self.name)
        address = ipaddress.IPv4Address(self.ip)
        endpoint(self.endpoint)
        if type(self.expires) is not int or not time.time() < self.expires <= time.time() + 180:
            raise ValueError("expired or future peer record")
        if network and (address not in network or address in (network.network_address, network.broadcast_address)):
            raise ValueError("peer IP is outside the swarm subnet")
        return self

    def to_dict(self):
        return asdict(self)
