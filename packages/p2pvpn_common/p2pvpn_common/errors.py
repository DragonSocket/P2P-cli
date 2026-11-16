"""Unified exception hierarchy for the whole project."""


class P2PVPNError(Exception):
    """Base error for every subsystem."""


class ConfigError(P2PVPNError):
    """Invalid or missing configuration."""


class ProtocolError(P2PVPNError):
    """Malformed wire packet."""


class IPCError(P2PVPNError):
    """Daemon IPC protocol violation or unreachable daemon."""


class TransportError(P2PVPNError):
    """UDP transport failure."""


class InterfaceError(P2PVPNError):
    """TAP interface / system configuration failure."""
