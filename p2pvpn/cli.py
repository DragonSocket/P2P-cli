"""CLI view and dispatch. Daemon assembly is imported only for `run`."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
from .ipc import request
from .models import Config
from .views import render


async def control(args):
    command = args.command
    if command == "tui":
        if not sys.stdout.isatty():
            raise ValueError("tui requires an interactive terminal")
        try:
            print("\033[?25l", end="", flush=True)
            while True:
                value = await request(args.socket, "status")
                print("\033[2J\033[H", end="")
                render(value)
                print("\nCtrl-C — exit monitor; daemon keeps running")
                await asyncio.sleep(1)
        finally:
            print("\033[?25h", end="", flush=True)
    else:
        payload = {}
        if command in ("resolve", "connect"):
            payload["name"] = args.name
        if command == "log-level":
            payload["level"] = args.level
        value = await request(args.socket, command, **payload)
        if args.json:
            print(json.dumps(value))
        else:
            render(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description="P2P Linux virtual LAN and DHT discovery")
    parser.add_argument("--socket", default="/run/p2pvpn/control.sock")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run daemon in foreground (use systemd for background lifecycle)")
    run.add_argument("--config", required=True)
    init = commands.add_parser("init", help="write a private config with a random swarm key")
    init.add_argument("--config", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--swarm", default="friends")
    init.add_argument("--address", required=True, help="virtual IPv4/prefix")
    init.add_argument("--advertise", required=True, help="reachable UDP IPv4:port")
    for command in ("status", "peers", "stop", "tui"):
        commands.add_parser(command)
    for command in ("resolve", "connect"):
        commands.add_parser(command).add_argument("name")
    commands.add_parser("log-level").add_argument("level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            data = dict(name=args.name, swarm=args.swarm, key=secrets.token_hex(32),
                        address=args.address, advertise=args.advertise, socket=args.socket)
            Config(**data)
            fd = os.open(args.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
            print(f"Config written: {args.config}")
        elif args.command == "run":
            from .daemon import run
            asyncio.run(run(Config.load(args.config)))
        else:
            asyncio.run(control(args))
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError, TimeoutError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
