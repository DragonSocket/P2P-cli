"""Installed-style CLI and foreground daemon lifecycle in a child process."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
from test_network import free_port
from test_core import KEY
from p2pvpn.ipc import request


async def test_daemon_cli_logging_and_restart(tmp_path):
    sock = str(tmp_path / "control.sock")
    logfile = tmp_path / "daemon.log"
    cfg = tmp_path / "node.json"
    port, dht_port = free_port(), free_port()
    cfg.write_text(json.dumps(dict(name="alice", swarm="test", key=KEY, address="10.77.0.1/24",
                                  advertise=f"127.0.0.1:{port}", listen=f"127.0.0.1:{port}",
                                  dht_listen=f"127.0.0.1:{dht_port}", headless=True,
                                  socket=sock, log_file=str(logfile))))
    for iteration in range(2):
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "p2pvpn", "run", "--config", str(cfg),
                                                       stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            async with asyncio.timeout(10):
                while True:
                    if process.returncode is not None:
                        raise AssertionError(f"daemon exited: {process.returncode}")
                    try:
                        status = await request(sock, "status")
                        break
                    except (FileNotFoundError, ConnectionRefusedError):
                        await asyncio.sleep(.05)
            assert status["headless"] is True
            cli = await asyncio.create_subprocess_exec(sys.executable, "-m", "p2pvpn", "--socket", sock, "--json", "status",
                                                      stdout=asyncio.subprocess.PIPE)
            output, _ = await cli.communicate()
            assert cli.returncode == 0 and json.loads(output)["name"] == "alice"
            assert (await request(sock, "log-level", level="DEBUG"))["log_level"] == "DEBUG"
            if iteration:
                process.send_signal(signal.SIGTERM)
            else:
                assert (await request(sock, "stop"))["stopping"]
            await asyncio.wait_for(process.wait(), 10)
            assert process.returncode == 0
            assert not Path(sock).exists()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    assert "Daemon stopped" in logfile.read_text()
    assert KEY not in logfile.read_text()
