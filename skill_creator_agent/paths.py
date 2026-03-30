from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Return the root directory of the ``skill_creator_agent`` package."""
    return Path(__file__).resolve().parent


def project_root() -> Path:
    """Return the repository root directory."""
    return package_root().parent


def package_path(*parts: str) -> Path:
    """Resolve a path relative to the package root."""
    path = package_root()
    for part in parts:
        path = path / part
    return path.resolve()


def project_path(*parts: str) -> Path:
    """Resolve a path relative to the repository root."""
    path = project_root()
    for part in parts:
        path = path / part
    return path.resolve()


def resolve_local_path(path: str | Path) -> Path:
    """Resolve a local path against the package root first, then the repository root."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    package_candidate = (package_root() / candidate).resolve()
    if package_candidate.exists():
        return package_candidate

    return (project_root() / candidate).resolve()
