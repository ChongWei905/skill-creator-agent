from __future__ import annotations

import asyncio

import pytest

import skill_creator_agent.main as main_module


def test_ensure_ferry_importable_requires_installed_ferry(monkeypatch):
    monkeypatch.setattr(main_module, "_can_import_ferry", lambda: False)

    with pytest.raises(RuntimeError, match="Install Ferry into this interpreter"):
        main_module._ensure_ferry_importable()


def test_main_checks_ferry_before_running_async_cli(monkeypatch):
    calls: list[tuple[str, list[str]] | str] = []

    def fake_ensure() -> None:
        calls.append("ensure")

    async def fake_async_main(argv):
        calls.append(("async", list(argv)))
        return 7

    def fake_run(coro):
        calls.append(("run", []))
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(main_module, "_ensure_ferry_importable", fake_ensure)
    monkeypatch.setattr(main_module, "async_main", fake_async_main)
    monkeypatch.setattr(main_module.asyncio, "run", fake_run)

    result = main_module.main(["--turn", "hello"])

    assert result == 7
    assert calls == [
        "ensure",
        ("run", []),
        ("async", ["--turn", "hello"]),
    ]
