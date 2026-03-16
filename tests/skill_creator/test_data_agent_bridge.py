from __future__ import annotations

from ferry.core.cbb.base_agent import BaseAgent
from ferry.core.flex.agent import FlexAgent
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.data_agent_bridge import (
    build_data_agent_session,
    extract_last_message_text,
    load_config_dict,
)
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
