"""L2 interface abstraction (DIP). Engine does not know TAP internals."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

import asyncio


class L2Interface(ABC):
    """A virtual Ethernet interface: lifecycle + tx/rx."""

    @abstractmethod
    def setup(self) -> None:
        """Create and configure the interface."""

    @abstractmethod
    def write(self, frame: bytes) -> None:
        """Write one Ethernet frame into the interface."""

    @abstractmethod
    def start_reading(self, loop: asyncio.AbstractEventLoop,
                       on_frame: Callable[[bytes], None]) -> None:
        """Register a reader that delivers incoming frames to the callback."""

    @abstractmethod
    def teardown(self) -> None:
        """Release the interface and clean up OS state."""
