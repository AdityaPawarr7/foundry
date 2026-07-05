"""Provision a VM over SSH: install Claude Code (Concentrate-powered), clone a
repo, and launch an autonomous agent in a tmux session that hosts the app.

We shell out to the system ``ssh`` binary (no extra dependency) and pipe a
bootstrap script over stdin, so secrets never appear in the VM's process list.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

# The tmux session the agent runs in (attach with `foundry attach <vm>`).
AGENT_SESSION = "agent"
APP_DIR = "$HOME/foundry-app/repo"

# Initial instruction handed to Claude Code. Single line, NO apostrophes
# (it is delivered via `tmux send-keys '<prompt>'`).
_AGENT_PROMPT = (
    "This directory is a cloned git repository. Figure out what the project is, "
    "install its dependencies, then build and run it so it listens on 0.0.0.0 port {port} "
    "and is reachable from outside the machine (bind to 0.0.0.0, not localhost). "
    "Prefer the projects own dev/start script or docker compose if present. "
    "When it is serving, print a short summary of what you did and the exact URL to view it, "
    "then stop and wait for my next instruction."
)

# Bootstrap script. Placeholders (__CONC_KEY__ etc.) are substituted in Python;
# it is piped to `bash -s` on the VM.
_BOOTSTRAP = r"""
set -uo pipefail
log() { echo "[foundry] $*"; }

log "installing base tools (git, tmux, curl)..."
if command -v apt-get >/dev/null 2>&1; then
  sudo -n DEBIAN_FRONTEND=noninteractive apt-get update -y -q >/dev/null 2>&1 || sudo DEBIAN_FRONTEND=noninteractive apt-get update -y -q
  sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -q git curl tmux ca-certificates >/dev/null 2>&1 \
    || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q git curl tmux ca-certificates
fi

export PATH="$HOME/.local/bin:$PATH"
log "installing Claude Code..."
if ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
  curl -fsSL https://claude.com/install.sh | bash
fi
export PATH="$HOME/.local/bin:$PATH"

log "configuring Concentrate credentials in ~/.bashrc..."
if ! grep -q ANTHROPIC_BASE_URL "$HOME/.bashrc" 2>/dev/null; then
  cat >> "$HOME/.bashrc" <<EOF
export CONCENTRATE_API_KEY="__CONC_KEY__"
export ANTHROPIC_BASE_URL="https://api.concentrate.ai"
export ANTHROPIC_AUTH_TOKEN="\$CONCENTRATE_API_KEY"
export ANTHROPIC_API_KEY=""
export PATH="\$HOME/.local/bin:\$PATH"
EOF
fi

log "cloning repo..."
mkdir -p "$HOME/foundry-app"
if [ -d "$HOME/foundry-app/repo/.git" ]; then
  git -C "$HOME/foundry-app/repo" pull --ff-only || true
else
  git clone "__REPO__" "$HOME/foundry-app/repo"
fi

log "launching Claude Code agent in tmux session '__SESSION__'..."
tmux kill-session -t __SESSION__ 2>/dev/null || true
tmux new-session -d -s __SESSION__ -c "$HOME/foundry-app/repo"
tmux send-keys -t __SESSION__ 'source ~/.bashrc' C-m
sleep 1
tmux send-keys -t __SESSION__ 'claude --dangerously-skip-permissions --model __MODEL__' C-m
sleep 7
tmux send-keys -t __SESSION__ '__PROMPT__' C-m
log "done. Claude Code is running in tmux session '__SESSION__'."
"""


def _ssh_base(key: Path | None, user: str, ip: str) -> list[str]:
    cmd = ["ssh"]
    if key and key.exists():
        cmd += ["-i", str(key)]
    cmd += [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        f"{user}@{ip}",
    ]
    return cmd


def check_ssh(key: Path | None, user: str, ip: str) -> bool:
    """Quick connectivity probe before we try to provision."""
    cmd = _ssh_base(key, user, ip) + ["-o", "BatchMode=yes", "echo ok"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        return False
    return out.returncode == 0 and "ok" in out.stdout


def deploy_agent(
    console: Console,
    ip: str,
    user: str,
    key: Path | None,
    repo_url: str,
    concentrate_key: str,
    model: str,
    port: int,
) -> int:
    """Run the bootstrap on the VM, streaming output. Returns the exit code."""
    script = (
        _BOOTSTRAP.replace("__CONC_KEY__", concentrate_key)
        .replace("__REPO__", repo_url)
        .replace("__SESSION__", AGENT_SESSION)
        .replace("__MODEL__", model)
        .replace("__PROMPT__", _AGENT_PROMPT.format(port=port))
    )

    cmd = _ssh_base(key, user, ip) + ["bash -s"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdin and proc.stdout
    proc.stdin.write(script)
    proc.stdin.close()
    for line in proc.stdout:
        console.print("  " + line.rstrip(), style="dim", markup=False, highlight=False)
    return proc.wait()


def attach_command(key: Path | None, user: str, ip: str) -> str:
    """The ssh command that attaches to the agent's tmux session."""
    parts = _ssh_base(key, user, ip)
    # -t forces a TTY; create the session if it does not exist yet.
    inner = f"tmux attach -t {AGENT_SESSION} || tmux new -s {AGENT_SESSION}"
    return " ".join(parts[:-1] + ["-t", parts[-1], f"'{inner}'"])
