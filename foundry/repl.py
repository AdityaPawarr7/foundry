"""Interactive REPL — the primary Foundry experience."""

from __future__ import annotations

import shlex

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory

from . import ui
from .bluelobster import BlueLobsterError
from .context import Context, ExitREPL
from .registry import completion_words, resolve


def dispatch(ctx: Context, parts: list[str]) -> None:
    """Run a single parsed command line. Raises ExitREPL for quit."""
    if not parts:
        return
    name, args = parts[0], parts[1:]
    cmd = resolve(name)
    if cmd is None:
        ui.error(ctx.console, f"Unknown command: {name!r}. Type /help to see commands.")
        return
    cmd.handler(ctx, args)


def run_repl(ctx: Context) -> None:
    ui.banner(ctx.console)

    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        completer=WordCompleter(completion_words(), ignore_case=True, sentence=True),
        complete_while_typing=True,
    )

    while True:
        try:
            line = session.prompt("foundry ▸ ")
        except (EOFError, KeyboardInterrupt):
            ctx.console.print()  # newline
            break

        line = line.strip()
        if not line:
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            ui.error(ctx.console, f"Could not parse input: {exc}")
            continue

        try:
            dispatch(ctx, parts)
        except ExitREPL:
            break
        except BlueLobsterError as exc:
            ui.error(ctx.console, str(exc))
        except KeyboardInterrupt:
            ui.info(ctx.console, "Interrupted.")
        except Exception as exc:  # keep the REPL alive on unexpected errors
            ui.error(ctx.console, f"{type(exc).__name__}: {exc}")

    ui.info(ctx.console, "Bye 🦞")
