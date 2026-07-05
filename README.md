# Foundry 🔨

An interactive CLI for managing [Blue Lobster](https://api.bluelobster.ai) VMs — modeled on the
feel of Claude Code. See your fleet at a glance, inspect a VM's live stats, and spin up new
instances, all from a discoverable REPL.

> **Status:** Phase 1–2 — VM visibility & lifecycle. The GitHub contribution pipeline and
> Concentrate AI code-gen land in later phases (see `docs`/plan).

## Install

```bash
cd foundry
uv venv && source .venv/bin/activate   # or: python3 -m venv .venv && source .venv/bin/activate
uv pip install -e .                     # or: pip install -e .
```

## Configure

Foundry reads `~/.foundry/config.toml` (env vars override it):

```toml
[bluelobster]
api_key = "bl_..."          # or env BLUELOBSTER_API_KEY

[ssh]
public_key_path  = "~/.ssh/id_ed25519.pub"
private_key_path = "~/.ssh/id_ed25519"
username = "ubuntu"
```

The quickest start is just an env var:

```bash
export BLUELOBSTER_API_KEY=bl_...
```

## Use

```bash
foundry            # launch the interactive REPL
foundry vms        # or run any command one-shot
foundry vm <id>
```

Inside the REPL, type `/help` to list every command.

### Commands

| Command | What it does |
| --- | --- |
| `help` | List all commands |
| `vms` | List your VMs as a table |
| `vm <id>` | Show one VM's details + live stats |
| `create` | Launch a new VM (interactive) |
| `delete <id>` | Delete a VM |
| `reboot`/`stop`/`start <id>` | Power lifecycle |
| `config` | Show current configuration |
| `quit` | Exit the REPL |
