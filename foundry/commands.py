"""Command handlers. Importing this module registers every command."""

from __future__ import annotations

import shlex
import subprocess
import sys

from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from . import ui
from .bluelobster import BlueLobsterError
from .context import Context, ExitREPL
from .registry import all_commands, command

BRAND = ui.BRAND


# -- helpers -------------------------------------------------------------
def _resolve_instance(ctx: Context, ref: str) -> dict:
    """Find an instance by exact/prefix uuid or by name."""
    instances = ctx.client().list_instances()
    ref_l = ref.lower()
    # Exact uuid/id
    for inst in instances:
        if str(inst.get("uuid") or inst.get("id")).lower() == ref_l:
            return inst
    # uuid prefix
    matches = [
        i for i in instances if str(i.get("uuid") or i.get("id") or "").lower().startswith(ref_l)
    ]
    # name (exact, then contains)
    matches += [i for i in instances if str(i.get("name") or "").lower() == ref_l]
    matches += [i for i in instances if ref_l in str(i.get("name") or "").lower()]
    # de-dupe preserving order
    seen: set[str] = set()
    unique = []
    for i in matches:
        key = str(i.get("uuid") or i.get("id"))
        if key not in seen:
            seen.add(key)
            unique.append(i)
    if not unique:
        raise BlueLobsterError(f"No VM matches {ref!r}.")
    if len(unique) > 1:
        names = ", ".join(f"{i.get('name')} ({ui.short_id(i)})" for i in unique)
        raise BlueLobsterError(f"{ref!r} is ambiguous — matches: {names}")
    return unique[0]


def _instance_id(inst: dict) -> str:
    return str(inst.get("uuid") or inst.get("id"))


def _describe_option(entry: dict) -> dict:
    """Flatten an /instances/available entry into a display-friendly dict.

    Shape: {id, instance_type: {name, description, price_cents_per_hour,
    specs: {vcpus, memory_gib, storage_gib, gpus, gpu_model?}},
    regions_with_capacity_available: [{name, description, location}]}.
    """
    it = entry.get("instance_type") or {}
    specs = it.get("specs") or {}
    gpus = specs.get("gpus") or 0
    model = specs.get("gpu_model")
    if isinstance(model, list):
        model = model[0] if model else None
    return {
        "id": entry.get("id") or it.get("name"),
        "desc": it.get("description") or "",
        "price": it.get("price_cents_per_hour"),
        "vcpus": specs.get("vcpus"),
        "mem": specs.get("memory_gib"),
        "storage": specs.get("storage_gib"),
        "gpu": (f"{gpus}× {model}" if model else str(gpus)) if gpus else "—",
        "regions": entry.get("regions_with_capacity_available") or [],
    }


def _open_terminal(command: str) -> bool:
    """Open a new terminal window running ``command``. Returns True on success.

    macOS: drives Terminal.app via AppleScript. Linux: tries common emulators.
    """
    if sys.platform == "darwin":
        script = (
            f'tell application "Terminal"\n'
            f'    do script "{command}"\n'
            f'    activate\n'
            f'end tell'
        )
        return subprocess.run(["osascript", "-e", script]).returncode == 0
    if sys.platform.startswith("linux"):
        import shutil

        for emu, flag in (
            ("x-terminal-emulator", "-e"),
            ("gnome-terminal", "--"),
            ("konsole", "-e"),
            ("xterm", "-e"),
        ):
            if shutil.which(emu):
                args = [emu, flag, "bash", "-lc", f"{command}; exec bash"]
                return subprocess.Popen(args).pid > 0
        return False
    return False


# -- commands ------------------------------------------------------------
@command("help", "List all commands and what they do.", aliases=("h", "?"), category="General")
def cmd_help(ctx: Context, args: list[str]) -> None:
    table = Table(title="Foundry commands", title_style=BRAND, header_style="bold")
    table.add_column("Command", style="bold cyan")
    table.add_column("Usage", style="dim")
    table.add_column("Description")
    for cmd in all_commands():
        alias_note = f"  [dim](aka {', '.join(cmd.aliases)})[/dim]" if cmd.aliases else ""
        table.add_row(cmd.name + alias_note, cmd.usage or cmd.name, cmd.help)
    ctx.console.print(table)
    ctx.console.print(
        "\n[dim]Tip: commands work with or without a leading slash "
        "(e.g. [/dim][bold]vms[/bold][dim] or [/dim][bold]/vms[/bold][dim]).[/dim]"
    )


@command("vms", "List all your VMs as a table.", aliases=("ls", "list"), category="VMs")
def cmd_vms(ctx: Context, args: list[str]) -> None:
    with ctx.console.status("Fetching VMs…", spinner="dots"):
        instances = ctx.client().list_instances()
    ui.vm_table(ctx.console, instances)


@command("vm", "Show one VM's details and live stats.", usage="vm <id|name>", category="VMs")
def cmd_vm(ctx: Context, args: list[str]) -> None:
    if not args:
        ui.error(ctx.console, "Usage: vm <id|name>")
        return
    with ctx.console.status("Fetching VM…", spinner="dots"):
        inst = _resolve_instance(ctx, args[0])
        iid = _instance_id(inst)
        # Enrich with the detailed view; fall back to the list entry.
        try:
            detail = ctx.client().get_instance(iid) or inst
        except BlueLobsterError:
            detail = inst
        stats = None
        try:
            stats = ctx.client().instance_stats(iid)
        except BlueLobsterError:
            pass
    ui.vm_detail(ctx.console, detail, stats, ssh_default_user=ctx.config.ssh_username)


@command(
    "connect",
    "Open a new terminal window SSH'd into a VM.",
    usage="connect <id|name>",
    aliases=("ssh",),
    category="VMs",
)
def cmd_connect(ctx: Context, args: list[str]) -> None:
    if not args:
        ui.error(ctx.console, "Usage: connect <id|name>")
        return
    inst = _resolve_instance(ctx, args[0])
    ip = inst.get("ip_address")
    if not ip:
        ui.error(ctx.console, "That VM has no IP address yet (is it started?).")
        return

    user = ui.ssh_user_for(inst, ctx.config.ssh_username)
    parts = ["ssh"]
    key = ctx.config.ssh_private_key_path
    if key and key.exists():
        parts += ["-i", str(key)]
    parts.append(f"{user}@{ip}")
    ssh_cmd = " ".join(shlex.quote(p) if " " in p else p for p in parts)

    if _open_terminal(ssh_cmd):
        ui.success(ctx.console, f"Opening a new terminal → [bold]{ssh_cmd}[/bold]")
    else:
        ui.warn(ctx.console, "Couldn't auto-open a terminal here. Run this yourself:")
        ctx.console.print(f"  [bold]{ssh_cmd}[/bold]")


@command("create", "Launch a new VM (interactive).", aliases=("new", "launch"), category="VMs")
def cmd_create(ctx: Context, args: list[str]) -> None:
    client = ctx.client()

    pubkey = ctx.config.ssh_public_key
    if not pubkey:
        ui.error(
            ctx.console,
            f"No SSH public key found at {ctx.config.ssh_public_key_path}. "
            "Generate one (ssh-keygen) or set [ssh].public_key_path in ~/.foundry/config.toml.",
        )
        return

    with ctx.console.status("Loading available instance types…", spinner="dots"):
        options = client.available()
    if not options:
        ui.error(ctx.console, "No available instance types returned by Blue Lobster.")
        return

    # Present a numbered menu of what's on offer.
    described = [_describe_option(o) for o in options]
    table = Table(title="Available instance types", title_style=BRAND, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Type", style="bold")
    table.add_column("vCPU", justify="right")
    table.add_column("RAM", justify="right")
    table.add_column("Disk", justify="right")
    table.add_column("GPU")
    table.add_column("$/hr", justify="right")
    table.add_column("Regions", style="dim")
    for idx, d in enumerate(described, start=1):
        price = f"${d['price'] / 100:.2f}" if d["price"] is not None else "—"
        regions = ", ".join(r.get("name", "?") for r in d["regions"]) or "—"
        table.add_row(
            str(idx),
            str(d["id"]),
            str(d["vcpus"] or "—"),
            f"{d['mem']} GB" if d["mem"] else "—",
            f"{d['storage']} GB" if d["storage"] else "—",
            d["gpu"],
            price,
            regions,
        )
    ctx.console.print(table)

    choice = IntPrompt.ask("Pick an instance type #", default=1)
    if choice < 1 or choice > len(described):
        ui.error(ctx.console, "Selection out of range.")
        return
    chosen = described[choice - 1]
    instance_type = chosen["id"]

    # Region: choose from the ones with capacity; send the region's `name`.
    regions = chosen["regions"]
    if not regions:
        region = Prompt.ask("Region")
    elif len(regions) == 1:
        region = regions[0].get("name")
        ui.info(ctx.console, f"Region: [bold]{region}[/bold] ({regions[0].get('description', '')})")
    else:
        rtable = Table(title="Regions with capacity", title_style=BRAND, header_style="bold")
        rtable.add_column("#", justify="right")
        rtable.add_column("Region", style="bold")
        rtable.add_column("Location", style="dim")
        for i, r in enumerate(regions, start=1):
            loc = r.get("location") or {}
            where = ", ".join(str(v) for v in (loc.get("city"), loc.get("state"), loc.get("country")) if v)
            rtable.add_row(str(i), str(r.get("name")), r.get("description") or where)
        ctx.console.print(rtable)
        ridx = IntPrompt.ask("Pick a region #", default=1)
        if ridx < 1 or ridx > len(regions):
            ui.error(ctx.console, "Selection out of range.")
            return
        region = regions[ridx - 1].get("name")

    name = Prompt.ask("VM name", default="foundry-vm")
    username = Prompt.ask("Login username", default=ctx.config.ssh_username)

    body = {
        "region": region,
        "instance_type": instance_type,
        "username": username,
        "ssh_key": pubkey,
        "name": name,
        "metadata": {"created_by": "foundry", "foundry_user": username},
    }

    ui.info(ctx.console, f"Launching [bold]{name}[/bold] ({instance_type}) in {region}…")
    resp = client.launch(**body)
    task_id = resp.get("task_id")
    assigned_ip = resp.get("assigned_ip")

    if task_id:
        with ctx.console.status("Provisioning VM…", spinner="dots") as status:
            def _tick(task: dict) -> None:
                state = task.get("status") or task.get("state") or "working"
                status.update(f"Provisioning VM… [dim]({state})[/dim]")

            client.poll_task(task_id, on_update=_tick)

    ui.success(ctx.console, f"VM [bold]{name}[/bold] is ready.")
    if assigned_ip:
        ctx.console.print(f"  IP: [bold]{assigned_ip}[/bold]")
        link = ui.ssh_link({"ip_address": assigned_ip, "vm_username": username}, username)
        if link:
            ctx.console.print(f"  Connect: {link}")
    ids = resp.get("instance_ids") or []
    if ids:
        ctx.console.print(f"  Instance: [dim]{ids[0]}[/dim]")
    ctx.console.print(
        f"[dim]⌘-click the link, or run[/dim] [bold]connect {name}[/bold] "
        "[dim]for a new terminal. Run[/dim] [bold]vms[/bold] [dim]to see the fleet.[/dim]"
    )


@command("delete", "Delete a VM.", usage="delete <id|name>", aliases=("rm", "destroy"), category="VMs")
def cmd_delete(ctx: Context, args: list[str]) -> None:
    if not args:
        ui.error(ctx.console, "Usage: delete <id|name>")
        return
    inst = _resolve_instance(ctx, args[0])
    name = inst.get("name") or ui.short_id(inst)
    if not Confirm.ask(f"Delete VM [bold red]{name}[/bold red] ({ui.short_id(inst)})?", default=False):
        ui.info(ctx.console, "Cancelled.")
        return
    with ctx.console.status("Deleting…", spinner="dots"):
        ctx.client().delete_instance(_instance_id(inst))
    ui.success(ctx.console, f"Deleted {name}.")


def _power_command(name: str, verb: str, method: str, aliases: tuple[str, ...] = ()) -> None:
    @command(name, f"{verb} a VM.", usage=f"{name} <id|name>", aliases=aliases, category="VMs")
    def _handler(ctx: Context, args: list[str], _method=method, _verb=verb) -> None:
        if not args:
            ui.error(ctx.console, f"Usage: {name} <id|name>")
            return
        inst = _resolve_instance(ctx, args[0])
        vm_name = inst.get("name") or ui.short_id(inst)
        with ctx.console.status(f"{_verb}ing {vm_name}…", spinner="dots"):
            getattr(ctx.client(), _method)(_instance_id(inst))
        ui.success(ctx.console, f"{_verb} requested for {vm_name}.")


_power_command("reboot", "Reboot", "reboot")
_power_command("stop", "Stop", "shutdown", aliases=("shutdown",))
_power_command("start", "Start", "power_on", aliases=("poweron",))


@command("config", "Show current Foundry configuration.", category="General")
def cmd_config(ctx: Context, args: list[str]) -> None:
    cfg = ctx.config

    def mask(secret: str | None) -> str:
        if not secret:
            return "[red]not set[/red]"
        return f"[green]set[/green] [dim](…{secret[-4:]})[/dim]"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()
    grid.add_row("Blue Lobster key", mask(cfg.bl_api_key))
    grid.add_row("Blue Lobster URL", cfg.bl_base_url)
    grid.add_row("Concentrate key", mask(cfg.concentrate_api_key))
    grid.add_row("Concentrate model", cfg.concentrate_model)
    grid.add_row("GitHub user", cfg.github_user or "[dim]—[/dim]")
    grid.add_row("SSH public key", str(cfg.ssh_public_key_path))
    grid.add_row("SSH username", cfg.ssh_username)
    ctx.console.print(grid)
    ctx.console.print("[dim]Config file: ~/.foundry/config.toml (env vars override it).[/dim]")


@command("quit", "Exit Foundry.", aliases=("exit", "q"), category="General")
def cmd_quit(ctx: Context, args: list[str]) -> None:
    raise ExitREPL()
