"""Rich rendering helpers: fleet tables, VM detail, and message styling."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

BRAND = "bold #ff6b4a"  # "lobster" orange


# -- ssh helpers ---------------------------------------------------------
def ssh_user_for(instance: dict, default_user: str = "ubuntu") -> str:
    """Best-effort login user for a VM (metadata we set, API field, or config default)."""
    meta = instance.get("metadata") or {}
    return (
        instance.get("vm_username")
        or (meta.get("foundry_user") if isinstance(meta, dict) else None)
        or default_user
    )


def ssh_command(instance: dict, default_user: str = "ubuntu") -> str | None:
    """The plain ``ssh user@ip`` command for a VM, or None if it has no IP yet."""
    ip = instance.get("ip_address")
    if not ip:
        return None
    return f"ssh {ssh_user_for(instance, default_user)}@{ip}"


def ssh_link(instance: dict, default_user: str = "ubuntu") -> str | None:
    """A clickable OSC-8 hyperlink (ssh:// scheme) that opens a session on click."""
    ip = instance.get("ip_address")
    if not ip:
        return None
    user = ssh_user_for(instance, default_user)
    return f"[link=ssh://{user}@{ip}][bold cyan]ssh {user}@{ip}[/bold cyan] ↗[/link]"


# -- message helpers -----------------------------------------------------
def info(console: Console, msg: str) -> None:
    console.print(f"[cyan]›[/cyan] {msg}")


def success(console: Console, msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def warn(console: Console, msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


def error(console: Console, msg: str) -> None:
    console.print(f"[bold red]✗[/bold red] {msg}")


# -- value formatting ----------------------------------------------------
def _power_style(status: str) -> str:
    s = (status or "").lower()
    if s in {"running", "on", "active", "poweron"}:
        return f"[green]{status}[/green]"
    if s in {"stopped", "off", "shutdown", "poweroff"}:
        return f"[red]{status}[/red]"
    return f"[yellow]{status or '?'}[/yellow]"


def _price(instance: dict) -> str:
    cents = instance.get("price_cents_per_hour")
    if cents is None:
        return "—"
    return f"${cents / 100:.2f}/hr"


def _mem(instance: dict) -> str:
    mem = instance.get("memory")
    return f"{mem} GB" if mem is not None else "—"


def _gpu(instance: dict) -> str:
    count = instance.get("gpu_count") or 0
    if not count:
        return "—"
    model = instance.get("gpu_model")
    return f"{count}× {model}" if model else str(count)


def _repo(instance: dict) -> str:
    meta = instance.get("metadata") or {}
    repo = meta.get("foundry_repo") if isinstance(meta, dict) else None
    if not repo:
        return "[dim]—[/dim]"
    # Shorten a full URL to owner/name for the table.
    trimmed = repo.rstrip("/").removesuffix(".git")
    parts = trimmed.split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else trimmed


def short_id(instance: dict) -> str:
    uid = str(instance.get("uuid") or instance.get("id") or "")
    return uid[:8] if uid else "—"


# -- tables --------------------------------------------------------------
def vm_table(console: Console, instances: list[dict]) -> None:
    if not instances:
        info(console, "No VMs found on this account.")
        return

    table = Table(title="Blue Lobster VMs", title_style=BRAND, header_style="bold")
    table.add_column("Name", style="bold")
    table.add_column("ID", style="dim")
    table.add_column("IP")
    table.add_column("Type")
    table.add_column("CPU", justify="right")
    table.add_column("Mem", justify="right")
    table.add_column("GPU")
    table.add_column("Power")
    table.add_column("Repo")
    table.add_column("Cost", justify="right")

    for inst in instances:
        table.add_row(
            str(inst.get("name") or "—"),
            short_id(inst),
            str(inst.get("ip_address") or "—"),
            str(inst.get("instance_type") or "—"),
            str(inst.get("cpu_cores") or "—"),
            _mem(inst),
            _gpu(inst),
            _power_style(str(inst.get("power_status") or "")),
            _repo(inst),
            _price(inst),
        )
    console.print(table)


def vm_detail(
    console: Console, instance: dict, stats: dict | None = None, ssh_default_user: str = "ubuntu"
) -> None:
    name = instance.get("name") or short_id(instance)
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()

    def row(label: str, value: Any) -> None:
        grid.add_row(label, "—" if value in (None, "") else str(value))

    row("UUID", instance.get("uuid") or instance.get("id"))
    row("Name", instance.get("name"))
    row("IP", instance.get("ip_address"))
    row("Internal IP", instance.get("internal_ip"))
    row("Region", instance.get("region"))
    row("Type", instance.get("instance_type"))
    row("CPU cores", instance.get("cpu_cores"))
    row("Memory", _mem(instance))
    row("Storage", f"{instance.get('storage')} GB" if instance.get("storage") else None)
    row("GPU", _gpu(instance))
    row("Power", instance.get("power_status"))
    row("OS", instance.get("os_type") or instance.get("template_name"))
    row("Cost", _price(instance))
    row("Team", instance.get("team_name"))
    row("Created", instance.get("created_at"))

    meta = instance.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("foundry_repo"):
        row("Repo", meta.get("foundry_repo"))

    if stats:
        for key in ("cpu_usage", "cpu", "memory_usage", "mem", "disk_usage", "uptime", "net_in", "net_out"):
            if key in stats:
                row(key.replace("_", " ").title(), stats[key])

    link = ssh_link(instance, ssh_default_user)
    if link:
        row("Connect", link)

    console.print(Panel(grid, title=f"[{BRAND}]{name}[/]", border_style="#ff6b4a"))
    if link:
        console.print(
            "[dim]⌘-click the ssh link to open a session, or run[/dim] "
            f"[bold]connect {name}[/bold] [dim]for a new terminal window.[/dim]"
        )
    elif str(instance.get("power_status") or "").lower() in {"stopped", "off"}:
        console.print("[dim]VM is stopped — start it to get a connectable IP.[/dim]")


def banner(console: Console) -> None:
    title = Text("FOUNDRY", style=BRAND)
    subtitle = Text(" — Blue Lobster VM console", style="dim")
    console.print(Panel(Text.assemble(title, subtitle), border_style="#ff6b4a"))
    console.print("[dim]Type[/dim] [bold]/help[/bold] [dim]to list commands, [/dim][bold]/quit[/bold] [dim]to exit.[/dim]\n")
