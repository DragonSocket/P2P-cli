"""DEPRECATED shim — VPNNode is now split into VPNEngine + collaborators.

    from p2pvpn_daemon.core.engine import VPNEngine
    from p2pvpn_daemon.core.peer_manager import PeerManager
    from p2pvpn_daemon.transport.udp import UDPTransport
    from p2pvpn_daemon.interface.factory import create_l2_interface
"""
from __future__ import annotations

import warnings

from p2pvpn_common.protocol.stun import STUNResult, discover, discover_async
from p2pvpn_daemon.core.engine import VPNEngine
from p2pvpn_daemon.core.peer_manager import PeerManager, PeerManagerConfig

warnings.warn(
    "vpn_node.py is deprecated; use p2pvpn_daemon (VPNEngine + PeerManager)",
    DeprecationWarning,
    stacklevel=2,
)

# Old name kept for scripts that still import it.
VPNNode = VPNEngine

__all__ = ["VPNNode", "VPNEngine", "PeerManager", "PeerManagerConfig",
           "STUNResult", "discover", "discover_async"]
