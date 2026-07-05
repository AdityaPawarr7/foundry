"""Entry point: launch the REPL with no args, or run a single command one-shot."""

from __future__ import annotations

import sys

from rich.console import Console

from . import commands  # noqa: F401  (importing registers all commands)
from . import ui
from .bluelobster import BlueLobsterError
from .config import load_config
from .context import Context, ExitREPL
from .repl import dispatch, run_repl


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    console = Console()
    ctx = Context(config=load_config(), console=console)

    if not argv:
        run_repl(ctx)
        return 0

    # One-shot: `foundry <command> [args...]`
    try:
        dispatch(ctx, argv)
    except ExitREPL:
        return 0
    except BlueLobsterError as exc:
        ui.error(console, str(exc))
        return 1
    except Exception as exc:  # pragma: no cover
        ui.error(console, f"{type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
