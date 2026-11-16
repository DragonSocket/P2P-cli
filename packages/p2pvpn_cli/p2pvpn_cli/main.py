"""CLI entry point (View). Commands:

  connect  --config node.json [--skip-stun]   start daemon subprocess
  status                                     render daemon status
  add-peer  host:port                        register a peer
  remove-peer host:port                      forget a peer
  stop                                       shutdown daemon
  demo      [-d seconds]                     in-process demo, no root needed

Exit codes: 0 success, 1 runtime/connection error, 2 bad arguments/config.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

from p2pvpn_common.errors import IPCError, P2PVPNError
from p2pvpn_common.protocol.ipc import IPCCommand
from p2pvpn_cli.client import send_command
from p2pvpn_cli.demo import demo
from p2pvpn_cli.view.render import console, render_error, render_ok, render_status

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2


def cmd_connect(args: argparse.Namespace) -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "p2pvpn_daemon.main", "--config", args.config]
        + (["--skip-stun"] if args.skip_stun else [])
        + (["--fake"] if args.fake else [])
        + (["--verbose"] if args.verbose else []),
    )
    render_ok(f"Daemon started (pid {proc.pid}). Waiting for IPC…")

    for _ in range(20):
        try:
            resp = send_command(IPCCommand.GET_STATUS)
            if resp.status == "success":
                render_status(resp.data)
                return EXIT_OK
        except IPCError:
            pass
        if proc.poll() is not None:
            render_error(f"Daemon exited with code {proc.returncode}")
            return EXIT_RUNTIME
        time.sleep(0.5)

    render_error("Daemon did not respond within 10s. Check privileges and config.")
    proc.terminate()
    return EXIT_RUNTIME


def cmd_status(_: argparse.Namespace) -> int:
    try:
        resp = send_command(IPCCommand.GET_STATUS)
    except IPCError as exc:
        render_error(str(exc))
        return EXIT_RUNTIME
    if resp.status != "success":
        render_error(resp.message or "Daemon error")
        return EXIT_RUNTIME
    render_status(resp.data)
    return EXIT_OK


def cmd_peer(action: IPCCommand, peer: str) -> int:
    try:
        resp = send_command(action, {"peer": peer})
    except IPCError as exc:
        render_error(str(exc))
        return EXIT_RUNTIME
    if resp.status != "success":
        render_error(resp.message or "Daemon error")
        return EXIT_RUNTIME
    render_ok(f"{action.value.lower().replace('_', '-')}: {peer}")
    return EXIT_OK


def cmd_stop(_: argparse.Namespace) -> int:
    try:
        resp = send_command(IPCCommand.STOP)
    except IPCError as exc:
        render_error(str(exc))
        return EXIT_RUNTIME
    if resp.status != "success":
        render_error(resp.message or "Daemon error")
        return EXIT_RUNTIME
    render_ok("Daemon shutting down")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p2pvpn-cli",
        description="P2P L2 VPN — clean CLI front-end for the daemon",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_connect = sub.add_parser("connect", help="start daemon with a config")
    p_connect.add_argument("--config", required=True)
    p_connect.add_argument("--skip-stun", action="store_true")
    p_connect.add_argument(
        "--fake", action="store_true",
        help="run daemon with in-memory TAP/transport (no root, no network)",
    )

    sub.add_parser("status", help="show daemon status")

    p_add = sub.add_parser("add-peer", help="add peer host:port")
    p_add.add_argument("peer")

    p_rm = sub.add_parser("remove-peer", help="remove peer host:port")
    p_rm.add_argument("peer")

    sub.add_parser("stop", help="stop daemon")

    p_demo = sub.add_parser("demo", help="run in-process demo (no root, no network)")
    p_demo.add_argument("-d", "--duration", type=float, default=8.0)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "connect":
            return cmd_connect(args)
        if args.command == "status":
            return cmd_status(args)
        if args.command == "add-peer":
            return cmd_peer(IPCCommand.ADD_PEER, args.peer)
        if args.command == "remove-peer":
            return cmd_peer(IPCCommand.REMOVE_PEER, args.peer)
        if args.command == "stop":
            return cmd_stop(args)
        if args.command == "demo":
            return demo(args.duration)
    except P2PVPNError as exc:
        render_error(str(exc))
        return EXIT_RUNTIME

    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
