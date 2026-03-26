from __future__ import annotations

import importlib
import sys


def main(argv: list[str] | None = None) -> int:
    """Ensure Ferry is installed in the current environment and then run the CLI."""
    cli_argv = list(sys.argv[1:] if argv is None else argv)
    bootstrap_runtime()

    from skill_creator_agent.cli import main as cli_main

    return cli_main(cli_argv)


def bootstrap_runtime() -> None:
    """Ensure Ferry is importable before any Ferry-dependent modules are loaded."""
    _ensure_ferry_importable()


def _ensure_ferry_importable() -> None:
    if _can_import_ferry():
        return

    raise RuntimeError(
        "Ferry is not available in the current Python environment. "
        "Install Ferry into this interpreter before starting the CLI."
    )


def _can_import_ferry() -> bool:
    try:
        importlib.import_module("ferry.interface.sdk.agent")
        return True
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("ferry"):
            return False
        raise RuntimeError(
            "Ferry is present in the current Python environment, but a required dependency is missing: "
            f"{exc.name}. Install Ferry dependencies in this interpreter first."
        ) from exc
