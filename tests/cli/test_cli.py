"""CLI tests: argument parsing, demo mode, and a real daemon subprocess
speaking over a real Unix domain socket (View ↔ Controller ↔ Model)."""
import os
import subprocess
import sys
import time

TEST_SOCKET = "/tmp/p2pvpn-cli-test.sock"
os.environ["P2PVPN_IPC_PATH"] = TEST_SOCKET

import pytest  # noqa: E402

from p2pvpn_common.errors import IPCError  # noqa: E402
from p2pvpn_common.protocol.ipc import IPCCommand  # noqa: E402
from p2pvpn_cli.client import send_command  # noqa: E402
from p2pvpn_cli.main import build_parser, main  # noqa: E402

NODE_CONFIG = {
    "local_ip": "10.0.0.1",
    "prefix": 24,
    "listen_port": 5555,
    "tap_name": "tap0",
    "peers": [{"host": "203.0.113.50", "port": 5555}],
}


@pytest.fixture
def fake_daemon():
    """Daemon subprocess with in-memory backends: no root, no network."""
    cfg = "/tmp/p2pvpn-cli-test-config.json"
    with open(cfg, "w") as fh:
        fh.write(str(NODE_CONFIG).replace("'", '"'))

    env = os.environ.copy()
    env["P2PVPN_IPC_PATH"] = TEST_SOCKET
    proc = subprocess.Popen(
        [sys.executable, "-m", "p2pvpn_daemon.main", "--config", cfg, "--fake"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                if send_command(IPCCommand.GET_STATUS).status == "success":
                    break
            except IPCError:
                time.sleep(0.25)
        else:
            proc.terminate()
            proc.wait(timeout=5)
            pytest.fail("fake daemon never answered GET_STATUS")
        yield proc
    finally:
        try:
            send_command(IPCCommand.STOP)
        except IPCError:
            pass
        proc.terminate()
        proc.wait(timeout=5)


def test_parser_requires_subcommand():
    parser = build_parser()
    args = parser.parse_args(["add-peer", "1.2.3.4:5555"])
    assert args.command == "add-peer"
    assert args.peer == "1.2.3.4:5555"


def test_demo_runs_without_privileges():
    assert main(["demo", "-d", "1.0"]) == 0


def test_status_without_daemon_returns_runtime_error():
    assert main(["status"]) == 1


def test_cli_talks_to_real_daemon(fake_daemon):
    resp = send_command(IPCCommand.GET_STATUS)
    assert resp.status == "success"
    data = resp.data
    assert data["running"] is True
    assert data["local_ip"] == "10.0.0.1"
    assert data["listen_port"] == 5555
    assert any(p["host"] == "203.0.113.50" for p in data["peers"])

    added = send_command(IPCCommand.ADD_PEER, {"peer": "198.51.100.7:6000"})
    assert added.status == "success"
    assert added.data["added"] == "198.51.100.7:6000"

    removed = send_command(IPCCommand.REMOVE_PEER, {"peer": "198.51.100.7:6000"})
    assert removed.status == "success"

    bad = send_command(IPCCommand.ADD_PEER, {"peer": "not-a-peer"})
    assert bad.status == "error"
