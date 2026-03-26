from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from skill_creator_agent import entrypoint


def test_resolve_config_path_uses_repo_default(tmp_path: Path):
    resolved = entrypoint._resolve_config_path(argv=[], repo_root=tmp_path)

    assert resolved == (tmp_path / "config.yaml").resolve()


def test_resolve_config_path_prefers_explicit_flag(tmp_path: Path):
    config_path = tmp_path / "custom.yaml"

    resolved = entrypoint._resolve_config_path(
        argv=["--config", str(config_path)],
        repo_root=tmp_path,
    )

    assert resolved == config_path.resolve()


def test_resolve_ferry_root_from_config_accepts_repo_relative_path(tmp_path: Path):
    ferry_repo = tmp_path / "ferry-src"
    ferry_pkg = ferry_repo / "ferry"
    ferry_pkg.mkdir(parents=True)
    (ferry_pkg / "__init__.py").write_text("", encoding="utf-8")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "BOOTSTRAP:\n"
        "  ferry_root: ./ferry-src\n",
        encoding="utf-8",
    )

    resolved = entrypoint._resolve_ferry_root_from_config(
        config_path=config_path,
        repo_root=tmp_path,
    )

    assert resolved == ferry_repo.resolve()


def test_main_bootstraps_before_importing_cli(monkeypatch):
    calls: list[tuple[str, list[str]]] = []

    def fake_bootstrap(argv):
        calls.append(("bootstrap", list(argv)))

    def fake_cli_main(argv):
        calls.append(("cli", list(argv)))
        return 7

    monkeypatch.setattr(entrypoint, "bootstrap_runtime", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "skill_creator_agent.cli", SimpleNamespace(main=fake_cli_main))

    result = entrypoint.main(["--turn", "hello"])

    assert result == 7
    assert calls == [
        ("bootstrap", ["--turn", "hello"]),
        ("cli", ["--turn", "hello"]),
    ]
