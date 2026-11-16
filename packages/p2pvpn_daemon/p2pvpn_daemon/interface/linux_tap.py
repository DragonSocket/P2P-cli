"""Linux TAP backend: /dev/net/tun + ioctl + epoll reader.

OS configuration is delegated to an injected SystemConfigurator (SRP):
this class only does device I/O.
"""
from __future__ import annotations

import asyncio
import logging
import os
import struct
from typing import Callable, Optional

from p2pvpn_common.constants import MAX_FRAME
from p2pvpn_common.errors import InterfaceError
from p2pvpn_daemon.configurator.base import SystemConfigurator
from p2pvpn_daemon.interface.base import L2Interface

log = logging.getLogger("p2pvpn.interface.linux")

TUNSETIFF = 0x400454CA
IFF_TAP = 0x0002
IFF_NO_PI = 0x1000


class LinuxTAP(L2Interface):
    def __init__(self, name: str, ip: str, prefix: int, mtu: int,
                 configurator: SystemConfigurator):
        self.name = name
        self.ip = ip
        self.prefix = prefix
        self.mtu = mtu
        self._configurator = configurator
        self._fd: Optional[int] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._on_frame: Optional[Callable[[bytes], None]] = None

    def setup(self) -> None:
        import fcntl

        try:
            fd = os.open("/dev/net/tun", os.O_RDWR | os.O_NONBLOCK)
        except OSError as exc:
            raise InterfaceError(f"Cannot open /dev/net/tun (root required?): {exc}") from exc

        ifr = struct.pack("16sH22x", self.name.encode(), IFF_TAP | IFF_NO_PI)
        try:
            actual = fcntl.ioctl(fd, TUNSETIFF, ifr)
        except OSError as exc:
            os.close(fd)
            raise InterfaceError(f"TUNSETIFF failed: {exc}") from exc

        self.name = actual[:16].rstrip(b"\x00").decode()
        self._fd = fd
        log.info("Linux TAP opened: %s (fd=%d)", self.name, fd)
        self._configurator.configure(self.name, self.ip, self.prefix, self.mtu)

    def teardown(self) -> None:
        if self._fd is None:
            return
        self._configurator.cleanup(self.name, self.mtu)
        try:
            if self._loop:
                self._loop.remove_reader(self._fd)
            os.close(self._fd)
        except Exception:
            pass
        self._fd = None
        log.info("Linux TAP %s torn down", self.name)

    def write(self, frame: bytes) -> None:
        try:
            os.write(self._fd, frame)
        except BlockingIOError:
            log.warning("TAP write buffer full, dropped %d bytes", len(frame))
        except OSError as exc:
            log.warning("TAP write error: %s", exc)

    def start_reading(self, loop: asyncio.AbstractEventLoop,
                      on_frame: Callable[[bytes], None]) -> None:
        self._loop = loop
        self._on_frame = on_frame
        loop.add_reader(self._fd, self._drain)
        log.debug("Linux TAP reader registered via epoll")

    def _drain(self) -> None:
        try:
            while True:
                try:
                    frame = os.read(self._fd, MAX_FRAME)
                    if frame:
                        self._on_frame(frame)
                except BlockingIOError:
                    return
        except OSError as exc:
            log.error("TAP read error: %s", exc)
