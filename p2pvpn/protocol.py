"""Versioned AEAD envelopes; separate keys for records and traffic."""
import hashlib
import os
import struct
import time
from collections import OrderedDict
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidTag

MAGIC = b"P2P2"
HELLO, DATA = 1, 2


class Cipher:
    def __init__(self, key: str, swarm: str, purpose: str):
        derived = hashlib.sha256(bytes.fromhex(key) + b"\0" + swarm.encode() + b"\0" + purpose.encode()).digest()
        self.aead = ChaCha20Poly1305(derived)

    def seal(self, data):
        nonce = os.urandom(12)
        return MAGIC + nonce + self.aead.encrypt(nonce, data, MAGIC)

    def open(self, packet):
        if not 32 <= len(packet) <= 4096 or packet[:4] != MAGIC:
            raise ValueError("invalid envelope")
        try:
            return self.aead.decrypt(packet[4:16], packet[16:], MAGIC)
        except InvalidTag as exc:
            raise ValueError("authentication failed") from exc


class Codec:
    def __init__(self, key, swarm):
        self.cipher = Cipher(key, swarm, "traffic")
        self.seen = OrderedDict()

    def encode(self, kind, payload):
        return self.cipher.seal(struct.pack("!BQ", kind, int(time.time())) + payload)

    def decode(self, packet):
        plain = self.cipher.open(packet)
        if len(plain) < 9:
            raise ValueError("short packet")
        kind, timestamp = struct.unpack("!BQ", plain[:9])
        if kind not in (HELLO, DATA) or abs(time.time() - timestamp) > 30:
            raise ValueError("invalid kind or timestamp")
        now = time.monotonic()
        while self.seen and next(iter(self.seen.values())) < now - 65:
            self.seen.popitem(last=False)
        nonce = packet[4:16]
        if nonce in self.seen or len(self.seen) >= 65536:
            raise ValueError("replay or replay window full")
        self.seen[nonce] = now
        return kind, plain[9:]
