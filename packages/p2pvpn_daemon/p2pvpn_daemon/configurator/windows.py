"""Windows system configuration: netsh + PowerShell (offload off)."""
from __future__ import annotations

import ipaddress
import logging
import subprocess

from p2pvpn_daemon.configurator.base import SystemConfigurator

log = logging.getLogger("p2pvpn.configurator.windows")


class WindowsSystemConfigurator(SystemConfigurator):
    def __init__(self, run=subprocess.run):
        self._run = run

    def configure(self, name: str, ip: str, prefix: int, mtu: int) -> None:
        mask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}", strict=False).netmask)

        # IP + маска
        self._run([
            "netsh", "interface", "ipv4", "set", "address",
            f"name={name}", "source=static", f"address={ip}", f"mask={mask}",
        ], check=True)
        # MTU (store=active — до перезагрузки)
        self._run([
            "netsh", "interface", "ipv4", "set", "subinterface",
            name, f"mtu={mtu}", "store=active",
        ], check=True)
        # Отключить offload на адаптере
        self._run(
            ["powershell", "-NoProfile", "-Command",
             f"Disable-NetAdapterLso -Name '{name}' -ErrorAction SilentlyContinue; "
             f"Disable-NetAdapterChecksumOffload -Name '{name}' -ErrorAction SilentlyContinue"],
            check=False,
        )
        log.info("Configured %s  ip=%s/%d  mtu=%d  (offload off)", name, ip, prefix, mtu)

    def cleanup(self, name: str, mtu: int) -> None:
        self._run(
            ["netsh", "interface", "ipv4", "reset", name],
            check=False,
        )
