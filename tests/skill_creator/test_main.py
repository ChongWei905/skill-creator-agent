from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_parse_args_leaves_config_backed_runtime_overrides_unset_by_default():
    args = main_module.parse_args([])

    assert args.skills_root is None
    assert args.graph_base_url is None
    assert args.graph_timeout is None
    assert args.disable_graph is False


def test_async_main_preserves_config_backed_graph_settings_when_flags_are_omitted(monkeypatch):
    calls: list[dict[str, object]] = []

    class DummySession:
        ferry_config_path = "ferry.yaml"
        session_id = "session-1"
        output_path = "output-dir"
        workflow_stage = "IDLE"
        active_turn_stage = "existing_skill"
        next_run_id = 0
        runtime = SimpleNamespace(
            settings=SimpleNamespace(
                skills_root="skills-from-config",
                graph_enabled=True,
                graph_base_url="http://127.0.0.1:9999",
            )
        )

        async def ask(self, query: str) -> dict[str, object]:
            return {"messages": [SimpleNamespace(content=f"echo:{query}")]}

    def fake_build_data_agent_session(config, **kwargs):
        calls.append({"config": config, **kwargs})
        return DummySession()

    monkeypatch.setattr(main_module, "_configure_logging", lambda: None)
    async def fake_run_turn(session, query, *, show_state_json):
        return None

    monkeypatch.setattr(main_module, "_run_turn", fake_run_turn)
    monkeypatch.setattr(
        main_module,
        "parse_args",
        lambda argv=None: SimpleNamespace(
            config="config.yaml",
            skills_root=None,
            disable_graph=False,
            graph_base_url=None,
            graph_timeout=None,
            user_id="user-1",
            session_id=None,
            output_root="out",
            materialized_config=None,
            turn=["hello"],
            show_state_json=False,
        ),
    )

    from skill_creator_agent.orchestration import session as session_module

    monkeypatch.setattr(session_module, "build_data_agent_session", fake_build_data_agent_session)

    result = asyncio.run(main_module.async_main([]))

    assert result == 0
    assert calls == [
        {
            "config": "config.yaml",
            "skills_root": None,
            "graph_enabled": None,
            "graph_base_url": None,
            "graph_timeout": None,
            "user_id": "user-1",
            "session_id": None,
            "output_root": "out",
            "materialized_config_path": None,
        }
    ]


def test_async_main_disables_graph_only_when_flag_is_present(monkeypatch):
    calls: list[dict[str, object]] = []

    class DummySession:
        ferry_config_path = "ferry.yaml"
        session_id = "session-1"
        output_path = "output-dir"
        workflow_stage = "IDLE"
        active_turn_stage = "existing_skill"
        next_run_id = 0
        runtime = SimpleNamespace(
            settings=SimpleNamespace(
                skills_root="skills-from-config",
                graph_enabled=False,
                graph_base_url="http://127.0.0.1:9999",
            )
        )

        async def ask(self, query: str) -> dict[str, object]:
            return {"messages": [SimpleNamespace(content=f"echo:{query}")]}

    def fake_build_data_agent_session(config, **kwargs):
        calls.append({"config": config, **kwargs})
        return DummySession()

    monkeypatch.setattr(main_module, "_configure_logging", lambda: None)
    async def fake_run_turn(session, query, *, show_state_json):
        return None

    monkeypatch.setattr(main_module, "_run_turn", fake_run_turn)
    monkeypatch.setattr(
        main_module,
        "parse_args",
        lambda argv=None: SimpleNamespace(
            config="config.yaml",
            skills_root=None,
            disable_graph=True,
            graph_base_url=None,
            graph_timeout=None,
            user_id="user-1",
            session_id=None,
            output_root="out",
            materialized_config=None,
            turn=["hello"],
            show_state_json=False,
        ),
    )

    from skill_creator_agent.orchestration import session as session_module

    monkeypatch.setattr(session_module, "build_data_agent_session", fake_build_data_agent_session)

    result = asyncio.run(main_module.async_main([]))

    assert result == 0
    assert calls[0]["graph_enabled"] is False
