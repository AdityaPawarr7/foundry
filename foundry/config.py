"""Load Foundry configuration from ~/.foundry/config.toml with environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.10
    import tomli as tomllib  # type: ignore

CONFIG_DIR = Path.home() / ".foundry"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DEFAULT_BASE_URL = "https://api.bluelobster.ai"
DEFAULT_CONCENTRATE_URL = "https://api.concentrate.ai/v1"


@dataclass
class Config:
    # Blue Lobster
    bl_api_key: str | None
    bl_base_url: str
    # Concentrate AI (used in later phases)
    concentrate_api_key: str | None
    concentrate_base_url: str
    concentrate_model: str
    concentrate_gh_token: str | None
    # GitHub (later phases)
    github_user: str | None
    # SSH
    ssh_public_key_path: Path | None
    ssh_private_key_path: Path | None
    ssh_username: str

    @property
    def ssh_public_key(self) -> str | None:
        """Return the contents of the configured SSH public key, if present."""
        if self.ssh_public_key_path and self.ssh_public_key_path.exists():
            return self.ssh_public_key_path.read_text().strip()
        return None


def _expand(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def load_config(path: Path = CONFIG_PATH) -> Config:
    data: dict = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)

    bl = data.get("bluelobster", {})
    con = data.get("concentrate", {})
    gh = data.get("github", {})
    ssh = data.get("ssh", {})

    return Config(
        bl_api_key=os.environ.get("BLUELOBSTER_API_KEY") or bl.get("api_key"),
        bl_base_url=bl.get("base_url", DEFAULT_BASE_URL),
        concentrate_api_key=os.environ.get("CONCENTRATE_API_KEY") or con.get("api_key"),
        concentrate_base_url=con.get("base_url", DEFAULT_CONCENTRATE_URL),
        concentrate_model=con.get("default_model", "auto"),
        concentrate_gh_token=os.environ.get("CONCENTRATE_GH_TOKEN") or con.get("github_token"),
        github_user=gh.get("personal_user"),
        ssh_public_key_path=_expand(ssh.get("public_key_path", "~/.ssh/id_ed25519.pub")),
        ssh_private_key_path=_expand(ssh.get("private_key_path", "~/.ssh/id_ed25519")),
        ssh_username=ssh.get("username", "ubuntu"),
    )
