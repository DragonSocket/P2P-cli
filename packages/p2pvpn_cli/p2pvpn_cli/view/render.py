"""Rich rendering: the only place that knows HOW state looks.

Status symbols are shared with the demo (OCP: add a new status → add a
mapping here, nothing else changes).
"""
from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

STATUS_STYLE = {
    "alive": ("●", "green"),
    "pending": ("○", "yellow"),
    "stale": ("◑", "yellow"),
    "dead": ("✕", "red"),
}


def render_banner() -> None:
    console.print(Panel(
        Text("P2P L2 VPN", style="bold cyan")
        + Text("  — Layer-2 mesh over UDP hole punching", style="dim"),
        border_style="cyan",
    ))


def render_ok(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def render_error(message: str) -> None:
    console.print(f"[red]✕[/red] {message}")


def render_status(status: dict) -> None:
    """Render a daemon status snapshot (GET_STATUS response data)."""
    public = status.get("public") or "not discovered"
    uptime = status.get("uptime", 0)

    head = Table(box=None, show_header=False, expand=False)
    head.add_row("Node", f"[bold]{status.get('local_ip', '?')}[/bold]")
    head.add_row("Listening", f":{status.get('listen_port', '?')}")
    head.add_row("Interface", status.get("tap_name", "?"))
    head.add_row("MTU", str(status.get("mtu", "?")))
    head.add_row("Public", public)
    head.add_row("Uptime", f"{uptime}s")
    head.add_row("Traffic", f"{status.get('frames_forwarded', 0)} fwd / "
                            f"{status.get('frames_received', 0)} recv")
    console.print(Panel(head, title="Status", border_style="blue"))

    peers = status.get("peers", [])
    if not peers:
        console.print("[dim]No peers connected.[/dim]")
        return

    table = Table(title="Peers", border_style="blue")
    table.add_column("Peer", style="cyan")
    table.add_column("State")
    table.add_column("Last seen", justify="right")
    table.add_column("Age", justify="right")
    table.add_column("MAC")

    for p in peers:
        sym, color = STATUS_STYLE.get(p["status"], ("?", "white"))
        age = "—" if p["age"] is None else f"{p['age']}s"
        seen = ("—" if p.get("last_seen_ago") is None
                else f"{p['last_seen_ago']}s ago")
        table.add_row(f"{p['host']}:{p['port']}",
                      Text(sym + " " + p["status"], style=color),
                      seen, age, p["mac"])

    console.print(table)

    counts = status.get("peer_counts", {})
    console.print(f"[dim]peers: {counts.get('alive', 0)} alive, "
                  f"{counts.get('pending', 0)} pending, "
                  f"{counts.get('stale', 0)} stale, "
                  f"{counts.get('dead', 0)} dead[/dim]")
