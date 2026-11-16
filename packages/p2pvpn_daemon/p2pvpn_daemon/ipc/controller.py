"""IPCController — adapter between the wire IPC protocol and the engine.

The CLI (View) never touches the engine directly; it only speaks commands.
This is the 'C' in MVC: request → controller → model → response.
"""
from __future__ import annotations

import logging

from p2pvpn_common.models.vpn_config import PeerConfig
from p2pvpn_common.protocol.ipc import IPCCommand, IPCRequest, IPCResponse
from p2pvpn_daemon.core.engine import VPNEngine

log = logging.getLogger("p2pvpn.ipc")


class IPCController:
    def __init__(self, engine: VPNEngine):
        self._engine = engine

    def handle(self, request: IPCRequest) -> IPCResponse:
        try:
            if request.command == IPCCommand.GET_STATUS:
                return IPCResponse.ok(self._engine.status_snapshot())
            if request.command == IPCCommand.ADD_PEER:
                peer = PeerConfig.parse(request.params.get("peer", ""))
                return self._add_peer(peer)
            if request.command == IPCCommand.REMOVE_PEER:
                peer = PeerConfig.parse(request.params.get("peer", ""))
                removed = self._remove_peer(peer)
                return IPCResponse.ok({"removed": removed}) if removed else \
                    IPCResponse.error(f"Peer {peer.host}:{peer.port} not found")
            if request.command == IPCCommand.STOP:
                return IPCResponse.ok({"stopping": True})
            return IPCResponse.error(f"Unsupported command: {request.command}")
        except Exception as exc:
            log.exception("IPC handler failure")
            return IPCResponse.error(str(exc))

    def _add_peer(self, peer: PeerConfig) -> IPCResponse:
        self._engine.add_peer(peer.host, peer.port)
        return IPCResponse.ok({"added": f"{peer.host}:{peer.port}"})

    def _remove_peer(self, peer: PeerConfig) -> bool:
        return self._engine.remove_peer(peer.host, peer.port)
