"""Composition root and service lifecycle."""
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import signal
from .adapters import LinuxConfigurator, LinuxTap, NullLink, UDPTransport
from .controller import Controller
from .discovery import DHTDiscovery
from .engine import Engine
from .ipc import IPCServer


def configure_logging(config):
    handlers = [logging.StreamHandler()]
    if config.log_file:
        handlers.append(RotatingFileHandler(config.log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"))
    logging.basicConfig(level=config.log_level, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)


async def run(config):
    configure_logging(config)
    link = NullLink() if config.headless else LinuxTap(config, LinuxConfigurator())
    engine = Engine(config, link, UDPTransport(config.listen), DHTDiscovery(config))
    ipc = IPCServer(config.socket, Controller(engine))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, engine.stop_event.set)
    try:
        await ipc.start()
        await engine.start()
        await engine.wait()
    finally:
        await ipc.close()
        await engine.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        logging.getLogger(__name__).info("Daemon stopped")
