# Foundry 🔨🦞

**Go from an idea to a running open-source project on a real VM — in one command.**

Foundry is an interactive CLI (built to feel like Claude Code) for the
[Blue Lobster](https://api.bluelobster.ai) cloud. See your fleet at a glance, inspect a VM's live
stats, and spin up new instances from a discoverable REPL — no dashboards, no YAML, no ceremony.

```
foundry ▸ vms          # see everything you're running
foundry ▸ create       # launch a new box, interactively
foundry ▸ vm crew      # live stats for one VM
```

## Why this matters for spinning up OSS projects

Most open-source software dies at the first hurdle: **setup**. Trying a project means renting a
box, SSHing in, installing a toolchain, cloning, wiring up dependencies, opening ports — an hour
of undifferentiated plumbing before you see a single thing run. Contributing is worse: fork,
clone, reproduce the dev environment, make a change, figure out the PR etiquette.

Foundry collapses that whole path into a few discoverable commands:

- **Zero-to-running in one flow.** Pick an instance type, and Foundry launches the VM, waits for
  it, and hands you a reachable IP. The friction that stops people from *trying* OSS disappears.
- **Every project gets a clean, disposable home.** Spin a box per project, tear it down when
  you're done. No polluting your laptop, no "works on my machine."
- **A built-in contribution pipeline** *(in progress)* — fork an upstream repo into your own
  GitHub account (visible proof of your open-source work), clone it onto a VM, let
  [Concentrate AI](https://concentrate.ai) generate the change *on the box*, and open the PR back
  upstream. Idle compute becomes real contributions.
- **Discoverable by design.** `/help` lists every command with a description, so the tool teaches
  you as you use it — great for anyone still getting comfortable on the command line.

The bet: when standing up and contributing to open source costs seconds instead of an afternoon,
far more of it happens.

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 1–2 | VM visibility & lifecycle (`vms`, `vm`, `create`, `delete`, power, `connect`) | ✅ Done |
| 3 | `deploy`: clone a repo onto a VM, launch a Claude Code agent (Concentrate) that hosts it, open the firewall port; `attach` to direct it | ✅ Done |
| 4 | Fork upstream into your account → the agent opens the PR back upstream (full fork→PR pipeline) | 🔜 Planned |
| — | Read a Google Doc spec and render it in the CLI (task intake) | 💡 Future |

## Install

```bash
git clone https://github.com/AdityaPawarr7/foundry.git && cd foundry
uv tool install --editable .      # puts `foundry` on your PATH
```

(Requires [`uv`](https://docs.astral.sh/uv/). No `uv`? `python3 -m venv .venv && source .venv/bin/activate && pip install -e .`)

## Configure

Foundry reads `~/.foundry/config.toml` (env vars override it):

```toml
[bluelobster]
api_key = "..."          # or env BLUELOBSTER_API_KEY

[ssh]
public_key_path  = "~/.ssh/id_ed25519.pub"
private_key_path = "~/.ssh/id_ed25519"
username = "ubuntu"
```

## Usage

```bash
foundry            # launch the interactive REPL (type /help inside)
foundry vms        # or run any command one-shot
foundry vm <id>
```

### Commands

| Command | What it does |
| --- | --- |
| `help` | List all commands |
| `vms` | List your VMs as a table |
| `vm <id>` | Show one VM's details + live stats |
| `create` | Launch a new VM (interactive) |
| `delete <id>` | Delete a VM |
| `reboot` / `stop` / `start <id>` | Power lifecycle |
| `config` | Show current configuration |
| `quit` | Exit the REPL |

---

Built with Python, [rich](https://github.com/Textualize/rich), and
[prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit). Powered by
[Blue Lobster](https://api.bluelobster.ai) and [Concentrate AI](https://concentrate.ai).
