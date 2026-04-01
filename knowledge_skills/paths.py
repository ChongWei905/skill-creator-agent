from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Return the root directory of the ``knowledge_skills`` package."""
    return Path(__file__).resolve().parent


def import_root() -> Path:
    """Return the parent directory that must be on ``sys.path`` to import this package."""
    return package_root().parent


def project_root() -> Path:
    """Return the project root directory."""
    return package_root()


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
    """Resolve a local path against the project root first, then the legacy repository root."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    project_candidate = (project_root() / candidate).resolve()
    if project_candidate.exists():
        return project_candidate

    legacy_candidate = (import_root() / candidate).resolve()
    if legacy_candidate.exists():
        return legacy_candidate

    return project_candidate
