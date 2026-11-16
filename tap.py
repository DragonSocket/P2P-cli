"""DEPRECATED shim — TAPDevice now delegates to p2pvpn_daemon.interfaces.

Old API preserved:
    tap = TAPDevice(name="tap0", ip="10.0.0.1", prefix=24, mtu=1420)
    tap.setup(); tap.start_reading(loop, on_frame); tap.write(b"..."); tap.teardown()
"""
from __future__ import annotations

import warnings

from p2pvpn_common.models.vpn_config import VPNConfig
from p2pvpn_common.utils.system import is_admin
from p2pvpn_daemon.interface.factory import create_l2_interface

warnings.warn(
    "tap.py is deprecated; use p2pvpn_daemon.interface (LinuxTAP/WindowsTAP)",
    DeprecationWarning,
    stacklevel=2,
)


class TAPDevice:
    def __init__(self, name: str, ip: str, prefix: int = 24, mtu: int = 1420):
        config = VPNConfig(local_ip=ip, prefix=prefix, mtu=mtu, tap_name=name)
        self._impl = create_l2_interface(config)

    @property
    def name(self) -> str:
        return self._impl.name

    def setup(self) -> None:
        self._impl.setup()

    def write(self, frame: bytes) -> None:
        self._impl.write(frame)

    def start_reading(self, loop, on_frame) -> None:
        self._impl.start_reading(loop, on_frame)

    def teardown(self) -> None:
        self._impl.teardown()
