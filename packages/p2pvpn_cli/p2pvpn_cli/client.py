"""IPC client: the View talks to the daemon Controller over UDS/TCP."""
from __future__ import annotations

import json
import socket
import sys

from p2pvpn_common.constants import IPC_SOCKET_PATH, IPC_TCP_PORT
from p2pvpn_common.errors import IPCError
from p2pvpn_common.protocol.ipc import IPCCommand, IPCRequest, parse_response


def _open_connection() -> socket.socket:
    if sys.platform == "win32":
        return socket.create_connection(("127.0.0.1", IPC_TCP_PORT), timeout=5)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(IPC_SOCKET_PATH)
    except OSError as exc:
        raise IPCError(
            f"Cannot connect to daemon at {IPC_SOCKET_PATH}. "
            "Is the daemon running? Start it with: p2pvpn-cli connect --config <file>"
        ) from exc
    return sock


def send_command(command: IPCCommand, params: dict | None = None) -> IPCResponse:
    request = IPCRequest(command=command, params=params or {})
    sock = _open_connection()
    try:
        sock.sendall((request.to_json() + "\n").encode())
        raw = sock.makefile("r", encoding="utf-8").readline()
        if not raw:
            raise IPCError("Daemon returned empty response")
        return parse_response(raw)
    finally:
        sock.close()
