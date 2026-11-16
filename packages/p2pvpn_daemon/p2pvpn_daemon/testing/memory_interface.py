"""In-memory L2Interface for demo/tests: no root, no TAP, no OS side effects.

Frames written to the interface are kept in a ring buffer and can be
inspected via `frames()`, which is exactly what the demo needs to show
"traffic flowing through the virtual network card".
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Callable

from p2pvpn_daemon.interface.base import L2Interface


class InMemoryL2Interface(L2Interface):
    def __init__(self, name: str = "tap-demo", max_frames: int = 200):
        self.name = name
        self._frames: deque[bytes] = deque(maxlen=max_frames)
        self._on_frame: Callable[[bytes], None] | None = None
        self._setup_done = False

    def setup(self) -> None:
        self._setup_done = True

    def write(self, frame: bytes) -> None:
        self._frames.append(frame)

    def start_reading(self, loop: asyncio.AbstractEventLoop,
                      on_frame: Callable[[bytes], None]) -> None:
        self._on_frame = on_frame

    def inject(self, frame: bytes) -> None:
        """Simulate a local application sending a frame onto the interface."""
        if self._on_frame is not None:
            self._on_frame(frame)

    def frames(self) -> list[bytes]:
        return list(self._frames)

    def teardown(self) -> None:
        self._setup_done = False
        self._frames.clear()
        self._on_frame = None
