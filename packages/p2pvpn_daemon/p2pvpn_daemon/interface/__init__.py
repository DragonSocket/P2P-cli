from p2pvpn_daemon.interface.base import L2Interface
from p2pvpn_daemon.interface.factory import create_l2_interface, supported_platform
from p2pvpn_daemon.interface.linux_tap import LinuxTAP
from p2pvpn_daemon.interface.windows_tap import WindowsTAP

__all__ = ["L2Interface", "LinuxTAP", "WindowsTAP", "create_l2_interface", "supported_platform"]
