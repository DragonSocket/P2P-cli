"""IPC JSON protocol between CLI (View) and daemon (Controller).

Request :  {"command": "GET_STATUS", "params": {...}}
Response:  {"status": "success", "data": {...}}
       or  {"status": "error", "message": "..."}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from p2pvpn_common.errors import IPCError


class IPCCommand(str, Enum):
    GET_STATUS = "GET_STATUS"
    ADD_PEER = "ADD_PEER"
    REMOVE_PEER = "REMOVE_PEER"
    STOP = "STOP"


@dataclass
class IPCRequest:
    command: IPCCommand
    params: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"command": self.command.value, "params": self.params})


@dataclass
class IPCResponse:
    status: str  # "success" | "error"
    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @staticmethod
    def ok(data: dict[str, Any]) -> "IPCResponse":
        return IPCResponse(status="success", data=data)

    @staticmethod
    def error(message: str) -> "IPCResponse":
        return IPCResponse(status="error", message=message)

    def to_json(self) -> str:
        payload: dict[str, Any] = {"status": self.status}
        if self.status == "success":
            payload["data"] = self.data
        else:
            payload["message"] = self.message
        return json.dumps(payload)


def parse_request(raw: str | bytes) -> IPCRequest:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IPCError(f"Malformed IPC request JSON: {exc}") from exc
    if not isinstance(obj, dict) or "command" not in obj:
        raise IPCError("IPC request must contain a 'command' field")
    try:
        command = IPCCommand(obj["command"])
    except ValueError as exc:
        raise IPCError(f"Unknown IPC command: {obj['command']!r}") from exc
    params = obj.get("params", {})
    if not isinstance(params, dict):
        raise IPCError("IPC request 'params' must be an object")
    return IPCRequest(command=command, params=params)


def parse_response(raw: str | bytes) -> IPCResponse:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IPCError(f"Malformed IPC response JSON: {exc}") from exc
    if not isinstance(obj, dict) or obj.get("status") not in ("success", "error"):
        raise IPCError("Malformed IPC response: missing/invalid 'status'")
    return IPCResponse(
        status=obj["status"],
        data=obj.get("data", {}),
        message=obj.get("message"),
    )
