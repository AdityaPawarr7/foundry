"""Command registry — the single source of truth that also powers ``/help``.

Every user-facing action registers a :class:`Command` here. The REPL, one-shot
dispatcher, and the help listing all read from this one table, so the documented
commands can never drift from what actually exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# A handler takes the runtime Context and the list of string args.
Handler = Callable[["object", list[str]], None]


@dataclass(frozen=True)
class Command:
    name: str
    handler: Handler
    help: str
    usage: str = ""
    aliases: tuple[str, ...] = ()
    category: str = "General"


_BY_NAME: dict[str, Command] = {}
_ORDER: list[str] = []


def register(cmd: Command) -> Command:
    _BY_NAME[cmd.name] = cmd
    _ORDER.append(cmd.name)
    for alias in cmd.aliases:
        _BY_NAME[alias] = cmd
    return cmd


def command(
    name: str,
    help: str,
    usage: str = "",
    aliases: tuple[str, ...] = (),
    category: str = "General",
) -> Callable[[Handler], Handler]:
    """Decorator to register a handler as a command."""

    def decorator(fn: Handler) -> Handler:
        register(Command(name, fn, help, usage, tuple(aliases), category))
        return fn

    return decorator


def resolve(name: str) -> Command | None:
    """Look up a command by name or alias (a leading ``/`` is ignored)."""
    return _BY_NAME.get(name.lstrip("/").lower())


def all_commands() -> list[Command]:
    """All registered commands in registration order, de-duplicated by name."""
    seen: set[str] = set()
    out: list[Command] = []
    for name in _ORDER:
        cmd = _BY_NAME[name]
        if cmd.name not in seen:
            seen.add(cmd.name)
            out.append(cmd)
    return out


def completion_words() -> list[str]:
    """Names + aliases (plain and slash-prefixed) for REPL autocompletion."""
    words: list[str] = []
    for key in _BY_NAME:
        words.append(key)
        words.append("/" + key)
    return sorted(set(words))
