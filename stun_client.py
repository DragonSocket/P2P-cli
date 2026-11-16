"""DEPRECATED shim — STUN client moved to p2pvpn_common.protocol.stun."""
from __future__ import annotations

import warnings

from p2pvpn_common.protocol.stun import STUNResult, discover, discover_async

warnings.warn(
    "stun_client.py is deprecated; use p2pvpn_common.protocol.stun",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["STUNResult", "discover", "discover_async"]
