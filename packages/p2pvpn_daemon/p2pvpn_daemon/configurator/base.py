"""OS-level configuration abstraction (SRP): tap backends do I/O only,
configurators touch the system (ip/iptables/netsh). Injected into interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod


class SystemConfigurator(ABC):
    @abstractmethod
    def configure(self, name: str, ip: str, prefix: int, mtu: int) -> None:
        """Bring the interface up with the given address and MTU."""

    @abstractmethod
    def cleanup(self, name: str, mtu: int) -> None:
        """Remove configuration applied by configure()."""
