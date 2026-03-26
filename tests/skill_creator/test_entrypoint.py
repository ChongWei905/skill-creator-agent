from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from skill_creator_agent import entrypoint


def test_ensure_ferry_importable_requires_installed_ferry(monkeypatch):
    monkeypatch.setattr(entrypoint, "_can_import_ferry", lambda: False)

    with pytest.raises(RuntimeError, match="Install Ferry into this interpreter"):
        entrypoint._ensure_ferry_importable()


def test_main_bootstraps_before_importing_cli(monkeypatch):
    calls: list[tuple[str, list[str]]] = []

    def fake_bootstrap():
        calls.append(("bootstrap", []))

    def fake_cli_main(argv):
        calls.append(("cli", list(argv)))
        return 7

    monkeypatch.setattr(entrypoint, "bootstrap_runtime", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "skill_creator_agent.cli", SimpleNamespace(main=fake_cli_main))

    result = entrypoint.main(["--turn", "hello"])

    assert result == 7
    assert calls == [
        ("bootstrap", []),
        ("cli", ["--turn", "hello"]),
    ]
