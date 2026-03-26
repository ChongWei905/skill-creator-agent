from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Sequence

import yaml

BOOTSTRAP_SECTION = "BOOTSTRAP"
FERRY_ROOT_KEY = "ferry_root"


def bootstrap_script_imports(argv: Sequence[str] | None = None) -> None:
    """Prepare ``sys.path`` so the repository script can import the local package and Ferry."""
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    src_root_text = str(src_root)
    if src_root_text not in sys.path:
        sys.path.insert(0, src_root_text)

    _ensure_ferry_importable(argv=argv or sys.argv, repo_root=repo_root)


def _ensure_ferry_importable(*, argv: Sequence[str], repo_root: Path) -> None:
    if _can_import_ferry():
        return

    config_path = _resolve_config_path(argv=argv, repo_root=repo_root)
    ferry_root = _resolve_ferry_root_from_config(config_path=config_path, repo_root=repo_root)
    if ferry_root is None:
        raise RuntimeError(
            "Ferry is not available in the current Python environment. "
            "Configure BOOTSTRAP.ferry_root in config.yaml or install Ferry into this interpreter."
        )

    ferry_root_text = str(ferry_root)
    if ferry_root_text not in sys.path:
        sys.path.insert(0, ferry_root_text)

    try:
        importlib.import_module("ferry.interface.sdk.agent")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Ferry was found via config at {ferry_root}, but a required dependency is missing: "
            f"{exc.name}. Install Ferry dependencies in the current Python environment first."
        ) from exc


def _can_import_ferry() -> bool:
    try:
        importlib.import_module("ferry.interface.sdk.agent")
        return True
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("ferry"):
            return False
        raise RuntimeError(
            f"Ferry is present in the current Python environment, but a required dependency is missing: "
            f"{exc.name}. Install Ferry dependencies in this interpreter first."
        ) from exc


def _resolve_config_path(*, argv: Sequence[str], repo_root: Path) -> Path:
    for index, item in enumerate(argv):
        if item == "--config" and index + 1 < len(argv):
            return Path(argv[index + 1]).expanduser().resolve()
        if item.startswith("--config="):
            return Path(item.split("=", 1)[1]).expanduser().resolve()
    return (repo_root / "config.yaml").resolve()


def _resolve_ferry_root_from_config(*, config_path: Path, repo_root: Path) -> Path | None:
    if not config_path.exists():
        return None

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return None

    section = payload.get(BOOTSTRAP_SECTION)
    if not isinstance(section, dict):
        return None

    ferry_root = section.get(FERRY_ROOT_KEY)
    if not ferry_root:
        return None

    candidate = Path(str(ferry_root)).expanduser()
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    return _normalize_ferry_root(candidate)


def _normalize_ferry_root(candidate: Path) -> Path | None:
    if not candidate.exists():
        return None

    resolved = candidate.resolve()
    package_root = resolved / "ferry"
    if package_root.is_dir() and (package_root / "__init__.py").exists():
        return resolved

    if resolved.name == "ferry" and resolved.is_dir() and (resolved / "__init__.py").exists():
        return resolved.parent

    return None
