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
PLAYBOOK_PATH = "$HOME/foundry-app/CONCENTRATE_PLAYBOOK.md"

# Initial instruction handed to Claude Code. Single line, NO apostrophes
# (it is delivered via `tmux send-keys '<prompt>'`).
_AGENT_PROMPT = (
    "Read the playbook at ../CONCENTRATE_PLAYBOOK.md and follow it exactly to make this "
    "open-source project Concentrate-compatible. Start at Phase 0 (recon, read-only). "
    "Honor the phase gates: do NOT touch Concentrate until the software runs (Phase 1), "
    "and STOP at each phase exit for the human to confirm before continuing. Begin now by "
    "reading the playbook and doing Phase 0, then report your Phase 0 findings and wait."
)


def _load_playbook() -> str:
    """The Concentrate-compatibility playbook shipped with Foundry."""
    return (Path(__file__).parent / "playbook.md").read_text()

# Bootstrap script. Placeholders (__CONC_KEY__ etc.) are substituted in Python.
# Safe to pipe to `bash -s` over SSH *or* paste directly into a VM shell.
_BOOTSTRAP = r"""
log() { echo "[foundry] $*"; }

log "installing base tools (git, tmux, curl)..."
if command -v apt-get >/dev/null 2>&1; then
  sudo -n DEBIAN_FRONTEND=noninteractive apt-get update -y -q >/dev/null 2>&1 || sudo DEBIAN_FRONTEND=noninteractive apt-get update -y -q
  sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -q git curl tmux ca-certificates >/dev/null 2>&1 \
    || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q git curl tmux ca-certificates
fi

export PATH="$HOME/.local/bin:$PATH"
log "installing Claude Code (claude.ai/install.sh)..."
if ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
  curl -fsSL https://claude.ai/install.sh | bash
fi
export PATH="$HOME/.local/bin:$PATH"

log "configuring Concentrate (official setup-claude.sh)..."
curl -fsSL https://concentrate.ai/scripts/setup-claude.sh | bash -s -- --key "__CONC_KEY__"

log "cloning repo..."
mkdir -p "$HOME/foundry-app"
if [ -d "$HOME/foundry-app/repo/.git" ]; then
  git -C "$HOME/foundry-app/repo" pull --ff-only || true
else
  git clone "__REPO__" "$HOME/foundry-app/repo"
fi

log "writing the Concentrate-compatibility playbook..."
cat > "$HOME/foundry-app/CONCENTRATE_PLAYBOOK.md" <<'FOUNDRY_PLAYBOOK_EOF'
__PLAYBOOK__
FOUNDRY_PLAYBOOK_EOF

log "launching Claude Code agent in tmux session '__SESSION__'..."
tmux kill-session -t __SESSION__ 2>/dev/null || true
tmux new-session -d -s __SESSION__ -c "$HOME/foundry-app/repo"
# Launch Claude Code with the task as a launch argument so it starts working
# immediately — no send-keys timing race.
tmux send-keys -t __SESSION__ 'source ~/.profile 2>/dev/null; source ~/.bashrc 2>/dev/null; claude --dangerously-skip-permissions --model __MODEL__ "__PROMPT__"' C-m
log "done. Claude Code is working on the task in tmux session '__SESSION__'."
log "attach to watch/direct it:  tmux attach -t __SESSION__"
"""


def build_bootstrap_script(repo_url: str, concentrate_key: str, model: str, port: int) -> str:
    """The full setup script (installs Claude Code + Concentrate, clones, launches agent)."""
    return (
        _BOOTSTRAP.replace("__CONC_KEY__", concentrate_key)
        .replace("__REPO__", repo_url)
        .replace("__SESSION__", AGENT_SESSION)
        .replace("__MODEL__", model)
        .replace("__PROMPT__", _AGENT_PROMPT.format(port=port))
        .replace("__PLAYBOOK__", _load_playbook())
    )


def _ssh_base(key: Path | None, user: str, ip: str, connect_timeout: int = 15) -> list[str]:
    cmd = ["ssh"]
    if key and key.exists():
        cmd += ["-i", str(key)]
    cmd += [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ConnectTimeout={connect_timeout}",
        f"{user}@{ip}",
    ]
    return cmd


def check_ssh(key: Path | None, user: str, ip: str, connect_timeout: int = 15) -> bool:
    """Return True if we can authenticate (non-interactively) as ``user`` with the key."""
    cmd = _ssh_base(key, user, ip, connect_timeout) + ["-o", "BatchMode=yes", "echo ok"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=connect_timeout + 10)
    except subprocess.TimeoutExpired:
        return False
    return out.returncode == 0 and "ok" in out.stdout


def find_login_user(key: Path | None, ip: str, candidates: list[str], connect_timeout: int = 8) -> str | None:
    """Try each candidate username; return the first one the key authenticates as."""
    for user in candidates:
        if user and check_ssh(key, user, ip, connect_timeout):
            return user
    return None


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
    script = build_bootstrap_script(repo_url, concentrate_key, model, port)

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
