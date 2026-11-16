"""Transport abstraction (DIP): the engine only talks to this interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

DatagramHandler = Callable[[bytes, tuple[str, int]], None]


class Transport(ABC):
    """A network channel capable of sending raw packets to peer addresses."""

    @abstractmethod
    async def start(self, loop) -> None:
        """Open the channel and begin delivering datagrams to the handler."""

    @abstractmethod
    def send(self, packet: bytes, addr: tuple[str, int]) -> None:
        """Send a wire-encoded packet to an peer address."""

    @abstractmethod
    def close(self) -> None:
        """Release the channel."""
