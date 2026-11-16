"""Bounded newline JSON over private Unix sockets, with single-instance lock."""
import asyncio
import fcntl
import json
import os
from pathlib import Path


class IPCServer:
    def __init__(self, path, controller):
        self.path = Path(path)
        self.controller = controller
        self.server = None
        self.lock = None
        self.clients = set()

    async def start(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = self.path.parent.stat()
        if directory.st_uid != os.geteuid() or directory.st_mode & 0o022:
            raise ValueError("control socket requires an owned directory without group/world write access")
        self.lock = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.lock)
            self.lock = None
            raise ValueError("another daemon owns this control socket")
        self.path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(self.handle, path=str(self.path), limit=8192)
        self.path.chmod(0o600)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.clients.add(task)
        try:
            if len(self.clients) > 32:
                return
            try:
                async with asyncio.timeout(15):
                    request = json.loads(await reader.readline())
                    result = await self.controller.execute(request)
                response = {"ok": True, "result": result}
            except (ValueError, TypeError, KeyError, LookupError, OSError, TimeoutError) as exc:
                response = {"ok": False, "error": str(exc)}
            writer.write(json.dumps(response).encode() + b"\n")
            async with asyncio.timeout(2):
                await writer.drain()
        except (ConnectionError, TimeoutError):
            pass
        finally:
            writer.close()
            self.clients.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            # Let STOP deliver its response before ending connections.
            if self.clients:
                _, pending = await asyncio.wait(self.clients, timeout=1)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            self.path.unlink(missing_ok=True)
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None


async def request(path, command, **args):
    async with asyncio.timeout(20):
        reader, writer = await asyncio.open_unix_connection(path, limit=262144)
        try:
            writer.write(json.dumps({"command": command, **args}).encode() + b"\n")
            await writer.drain()
            response = json.loads(await reader.readline())
            if not response["ok"]:
                raise ValueError(response["error"])
            return response["result"]
        finally:
            writer.close()
            await writer.wait_closed()
