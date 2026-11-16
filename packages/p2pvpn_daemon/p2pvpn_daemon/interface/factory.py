"""Platform factory: the only place that knows *which* backend to use.

Adding macOS/BSD = adding a new L2Interface + factory branch, no existing
class changes (OCP).
"""
from __future__ import annotations

import sys

from p2pvpn_common.errors import InterfaceError
from p2pvpn_common.models.vpn_config import VPNConfig
from p2pvpn_daemon.configurator.linux import LinuxSystemConfigurator
from p2pvpn_daemon.configurator.windows import WindowsSystemConfigurator
from p2pvpn_daemon.interface.base import L2Interface
from p2pvpn_daemon.interface.linux_tap import LinuxTAP
from p2pvpn_daemon.interface.windows_tap import WindowsTAP


def supported_platform() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    raise InterfaceError(
        f"Unsupported platform: {sys.platform}. Only Linux and Windows are supported."
    )


def create_l2_interface(config: VPNConfig) -> L2Interface:
    platform = supported_platform()
    if platform == "linux":
        return LinuxTAP(
            name=config.tap_name, ip=config.local_ip,
            prefix=config.prefix, mtu=config.mtu,
            configurator=LinuxSystemConfigurator(),
        )
    return WindowsTAP(
        name=config.tap_name, ip=config.local_ip,
        prefix=config.prefix, mtu=config.mtu,
        configurator=WindowsSystemConfigurator(),
    )
