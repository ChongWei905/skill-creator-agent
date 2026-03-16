from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parent


def project_root() -> Path:
    return package_root().parents[1]


def package_path(*parts: str) -> Path:
    path = package_root()
    for part in parts:
        path = path / part
    return path.resolve()


def project_path(*parts: str) -> Path:
    path = project_root()
    for part in parts:
        path = path / part
    return path.resolve()


def resolve_local_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    package_candidate = (package_root() / candidate).resolve()
    if package_candidate.exists():
        return package_candidate

    return (project_root() / candidate).resolve()
