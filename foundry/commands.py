"""Command handlers. Importing this module registers every command."""

from __future__ import annotations

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
    ui.vm_detail(ctx.console, detail, stats)


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
    table = Table(title="Available instance types", title_style=BRAND, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Type", style="bold")
    table.add_column("Region")
    table.add_column("Details", style="dim")
    for idx, opt in enumerate(options, start=1):
        itype = opt.get("instance_type") or opt.get("name") or opt.get("type") or "?"
        region = opt.get("region") or "—"
        details = ", ".join(
            f"{k}={v}"
            for k, v in opt.items()
            if k not in {"instance_type", "name", "type", "region"} and v not in (None, "")
        )
        table.add_row(str(idx), str(itype), str(region), details[:60])
    ctx.console.print(table)

    choice = IntPrompt.ask("Pick an instance type #", default=1)
    if choice < 1 or choice > len(options):
        ui.error(ctx.console, "Selection out of range.")
        return
    chosen = options[choice - 1]

    instance_type = chosen.get("instance_type") or chosen.get("name") or chosen.get("type")
    region = chosen.get("region") or Prompt.ask("Region")
    name = Prompt.ask("VM name", default="foundry-vm")
    username = Prompt.ask("Login username", default=ctx.config.ssh_username)

    body = {
        "region": region,
        "instance_type": instance_type,
        "username": username,
        "ssh_key": pubkey,
        "name": name,
        "metadata": {"created_by": "foundry"},
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
    ids = resp.get("instance_ids") or []
    if ids:
        ctx.console.print(f"  Instance: [dim]{ids[0]}[/dim]")
    ctx.console.print("[dim]Run[/dim] [bold]vms[/bold] [dim]to see it in the fleet.[/dim]")


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
