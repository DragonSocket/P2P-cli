"""Linux system configuration: ip, iptables (TCP MSS clamp), ethtool (offload off).

Command execution goes through a `run_command` callable so the configurator
is fully unit-testable with a fake runner (no root needed).
"""
from __future__ import annotations

import logging
import os
from typing import Callable, List

from p2pvpn_common.errors import InterfaceError
from p2pvpn_daemon.configurator.base import SystemConfigurator

log = logging.getLogger("p2pvpn.configurator.linux")

CommandRunner = Callable[[str], int]


def _default_runner(cmd: str) -> int:
    return os.system(cmd)


class LinuxSystemConfigurator(SystemConfigurator):
    def __init__(self, run_command: CommandRunner = _default_runner):
        self._run = run_command

    def configure(self, name: str, ip: str, prefix: int, mtu: int) -> None:
        """MTU, offload off, TCP MSS clamp — without offload TCP and large UDP
        packets "lie down" while ping still works."""
        mask = f"{ip}/{prefix}"
        mss = mtu - 40

        for cmd in (
            f"ip link set {name} mtu {mtu}",
            f"ip link set {name} up",
            f"ip addr replace {mask} dev {name}",
        ):
            if self._run(cmd) != 0:
                raise InterfaceError(f"Command failed: {cmd}")

        # Критично: без этого TCP и большие UDP «ложатся», ping работает
        if self._run(
            f"ethtool -K {name} tso off gso off gro off lro off tx off sg off 2>/dev/null"
        ) != 0:
            log.warning("ethtool not installed — TCP/large UDP may drop")

        rules: List[str] = []
        for chain, match in (("OUTPUT", f"-o {name}"), ("INPUT", f"-i {name}")):
            rule = (f"{chain} {match} -p tcp --tcp-flags SYN,RST SYN "
                    f"-j TCPMSS --set-mss {mss}")
            rules.append(rule)
            self._run(f"iptables -t mangle -C {rule} 2>/dev/null || iptables -t mangle -A {rule}")

        log.info("Configured %s  ip=%s  mtu=%d  mss=%d  (offload off)", name, mask, mtu, mss)

    def cleanup(self, name: str, mtu: int) -> None:
        mss = mtu - 40
        for chain, match in (("OUTPUT", f"-o {name}"), ("INPUT", f"-i {name}")):
            self._run(
                f"iptables -t mangle -D {chain} {match} -p tcp "
                f"--tcp-flags SYN,RST SYN -j TCPMSS --set-mss {mss} 2>/dev/null"
            )
        self._run(f"ip link set {name} down 2>/dev/null")
        self._run(f"ip addr flush dev {name} 2>/dev/null")
