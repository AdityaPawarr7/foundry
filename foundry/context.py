"""Shared runtime context passed to every command handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import Console

from .config import Config

if TYPE_CHECKING:
    from .bluelobster import BlueLobsterClient


class ExitREPL(Exception):
    """Raised by a command to cleanly exit the interactive loop."""


@dataclass
class Context:
    config: Config
    console: Console = field(default_factory=Console)
    _client: "BlueLobsterClient | None" = None

    def client(self) -> "BlueLobsterClient":
        """Lazily build (and cache) the Blue Lobster API client."""
        from .bluelobster import BlueLobsterClient

        if self._client is None:
            self._client = BlueLobsterClient(
                api_key=self.config.bl_api_key,
                base_url=self.config.bl_base_url,
            )
        return self._client
