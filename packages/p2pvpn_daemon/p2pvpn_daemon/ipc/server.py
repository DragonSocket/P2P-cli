"""IPC server: Unix domain socket on Linux, TCP loopback on Windows.

One class per backend (SRP), chosen by a small factory. The protocol is
newline-delimited JSON from p2pvpn_common.protocol.ipc.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

from p2pvpn_common.constants import IPC_SOCKET_PATH, IPC_TCP_PORT
from p2pvpn_common.protocol.ipc import parse_request
from p2pvpn_daemon.ipc.controller import IPCController

log = logging.getLogger("p2pvpn.ipc.server")


class IPCServer:
    def __init__(self, controller: IPCController):
        self._controller = controller

    def serve(self) -> asyncio.Server:
        raise NotImplementedError

    async def _dispatch(self, reader: asyncio.StreamReader,
                        writer: asyncio.StreamWriter) -> None:
        """One request per connection. Shared by both backends."""
        try:
            line = await reader.readline()
            if not line:
                return
            try:
                resp = self._controller.handle(parse_request(line))
                payload = resp.to_json()
            except Exception as exc:
                log.warning("IPC dispatch failure: %s", exc)
                payload = json.dumps({"status": "error", "message": str(exc)})
            writer.write((payload + "\n").encode())
            await writer.drain()
        finally:
            writer.close()


class UnixIPCServer(IPCServer):
    def __init__(self, controller: IPCController, path: str = IPC_SOCKET_PATH):
        super().__init__(controller)
        self._path = path

    async def serve(self) -> asyncio.Server:
        import os

        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

        server = await asyncio.start_unix_server(self._dispatch, path=self._path)
        log.info("IPC listening on %s", self._path)
        return server


class TcpIPCServer(IPCServer):
    def __init__(self, controller: IPCController, port: int = IPC_TCP_PORT):
        super().__init__(controller)
        self._port = port

    async def serve(self) -> asyncio.Server:
        server = await asyncio.start_server(self._dispatch, "127.0.0.1", self._port)
        log.info("IPC listening on 127.0.0.1:%d", self._port)
        return server


def create_ipc_server(controller: IPCController) -> IPCServer:
    if sys.platform == "win32":
        return TcpIPCServer(controller)
    return UnixIPCServer(controller)
