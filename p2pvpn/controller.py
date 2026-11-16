"""Controller: validated commands expose a narrow application API."""
import logging
from .models import name


class Controller:
    def __init__(self, engine):
        self.engine = engine

    async def execute(self, request):
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        command = request.get("command")
        if command == "status":
            return self.engine.status()
        if command == "peers":
            return self.engine.peers.snapshot()
        if command in ("resolve", "connect"):
            peer_name = name(request.get("name"))
            result = await (self.engine.connect(peer_name) if command == "connect" else self.engine.resolve(peer_name))
            if command == "connect":
                self.engine.targets.add(peer_name)
            return result
        if command == "stop":
            self.engine.stop_event.set()
            return {"stopping": True}
        if command == "log-level":
            level = request.get("level")
            if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                raise ValueError("invalid log level")
            logging.getLogger().setLevel(level)
            return {"log_level": level}
        raise ValueError("unknown command")
