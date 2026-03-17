from __future__ import annotations

from ferry.core.cbb.base_agent import BaseAgent
from ferry.core.flex.agent import FlexAgent
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.cli import parse_args
from skill_creator_agent.data_agent_bridge import (
    DataAgentSession,
    build_data_agent_session,
    extract_last_message_text,
    load_config_dict,
)
from skill_creator_agent.runtime import SkillCreatorRuntime
from skill_creator_agent.paths import package_path


def test_load_config_dict_reads_yaml_file():
    config = load_config_dict(package_path("skill_creator_debug.yaml"))

    assert config["AGENT_CONFIG"]["agent_type"] == "skill_creator"
    assert config["SKILL_CREATOR"]["graph_enabled"] is True


def test_build_data_agent_session_materializes_runtime_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    session = build_data_agent_session(
        {
            "SKILL_CREATOR": {
                "skills_root": "src/skill_creator_agent/fixtures/minimal_skills",
                "graph_enabled": False,
            }
        },
        user_id="tester",
        output_root=tmp_path / "outputs",
        materialized_config_path=tmp_path / "rendered.yaml",
    )

    chat_agent = session.data_agent.build_agent_graph("chat")

    assert isinstance(session.data_agent, DataAgent)
    assert session.ferry_config_path.exists()
    assert session.runtime.list_skills()[0]["name"] == "skill-creator-smoke"
    assert session.output_path == (tmp_path / "outputs" / session.session_id).resolve()
    assert isinstance(chat_agent, BaseAgent)
    assert isinstance(chat_agent, FlexAgent)


def test_extract_last_message_text_handles_dict_and_fallback():
    assert extract_last_message_text({"messages": [type("Msg", (), {"content": "done"})()]}) == "done"
    assert extract_last_message_text({"final_answer": "fallback"}) == "fallback"


def test_cli_parse_args_defaults():
    args = parse_args([])

    assert args.graph_base_url == "http://127.0.0.1:8000"
    assert args.turn == []
    assert args.disable_graph is False


def test_data_agent_session_injects_reference_doc_gate_after_create_confirmation(tmp_path):
    class FakeDataAgent:
        def __init__(self):
            self.queries: list[str] = []

        async def chat(self, query, **kwargs):
            self.queries.append(query)
            return {"messages": [type("Msg", (), {"content": "请提供参考文档或明确说明没有文档支持。"})()]}

    session = DataAgentSession(
        data_agent=FakeDataAgent(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-1",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_create_confirmation",
    )

    import asyncio

    asyncio.run(session.ask("创建吧"))

    assert "must execute only Step 2" in session.data_agent.queries[0]
    assert session.workflow_stage == "awaiting_reference_answer"


def test_data_agent_session_injects_plan_gate_after_reference_answer(tmp_path):
    class FakeDataAgent:
        def __init__(self):
            self.queries: list[str] = []

        async def chat(self, query, **kwargs):
            self.queries.append(query)
            return {"messages": [type("Msg", (), {"content": "📋 Skill Execution Flow Plan\nDoes this execution flow look correct? Should I proceed with creating the skill?"})()]}

    session = DataAgentSession(
        data_agent=FakeDataAgent(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-2",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_reference_answer",
    )

    import asyncio

    asyncio.run(session.ask("没有文档支撑"))

    assert "Do not create or modify files in this turn." in session.data_agent.queries[0]
    assert session.workflow_stage == "awaiting_plan_approval"
