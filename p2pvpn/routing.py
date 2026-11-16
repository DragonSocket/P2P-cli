"""Bounded learning Ethernet switch. Received frames never get flooded again."""
import time


class Switch:
    def __init__(self):
        self.table = {}

    def learn(self, frame, address):
        if len(frame) < 14:
            raise ValueError("short Ethernet frame")
        source = frame[6:12]
        if source[0] & 1 or source == b"\0" * 6:
            raise ValueError("invalid source MAC")
        if len(self.table) >= 4096:
            self.table.pop(next(iter(self.table)))
        self.table[source] = (address, time.monotonic())

    def destinations(self, frame, live):
        if len(frame) < 14:
            return []
        destination = frame[:6]
        entry = self.table.get(destination)
        if not destination[0] & 1 and entry:
            address, seen = entry
            if address in live and time.monotonic() - seen < 60:
                return [address]
        return list(live)
