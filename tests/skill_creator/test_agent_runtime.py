from __future__ import annotations

from ferry.core.cbb.base_agent import BaseAgent
from ferry.core.flex.agent import FlexAgent

from skill_creator_agent.agent import SkillCreatorAgent
from skill_creator_agent.paths import package_path


def test_skill_creator_agent_from_yaml_uses_runtime_fixture(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = SkillCreatorAgent.from_config(
        package_path("skill_creator_debug.yaml")
    )

    skills = agent.list_skills()

    assert isinstance(agent, BaseAgent)
    assert isinstance(agent, FlexAgent)
    assert len(skills) == 1
    assert skills[0]["name"] == "skill-creator-smoke"
    assert skills[0]["scripts"][0]["name"] == "echo_input"


def test_skill_creator_agent_delegates_script_execution(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = SkillCreatorAgent.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
            }
        }
    )

    result = agent.execute_skill_script("skill-creator-smoke", "echo_input", args=["agent"])

    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "agent"


def test_skill_creator_agent_builds_ferry_config_with_runtime_tools(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = SkillCreatorAgent.from_config(
        {
            "MODEL": {
                "demo_chat": {
                    "provider": "openai",
                    "model_type": "chat",
                    "params": {"model": "gpt-4o-mini"},
                }
            },
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
                "graph_enabled": True,
            },
        }
    )

    config = agent.build_ferry_config()
    local_tool_names = [tool["name"] for tool in config["TOOLS"]["local_functions"]]

    assert config["AGENT_CONFIG"]["agent_type"] == "skill_creator"
    assert config["ACTOR_LOOP"][0]["chat_model"]["name"] == "demo_chat"
    assert "create_skill_scaffold" in local_tool_names
    assert "read_skill_content" in local_tool_names
    assert "graph_get_object_types" in local_tool_names
    assert config["TOOLS"]["skills"][0]["name"] == "skill-creator-smoke"
    assert config["SKILL_CREATOR"]["graph_base_url"] == "http://127.0.0.1:8000"


def test_skill_creator_agent_materializes_ferry_config(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = SkillCreatorAgent.from_config(
        {
            "MODEL": {
                "demo_chat": {
                    "provider": "openai",
                    "model_type": "chat",
                    "params": {"model": "gpt-4o-mini"},
                }
            },
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
            },
        }
    )

    path = agent.materialize_ferry_config(tmp_path / "skill_creator_ferry.yaml")
    rendered = path.read_text(encoding="utf-8")

    assert path.exists()
    assert "agent_type: skill_creator" in rendered
    assert "create_skill_scaffold" in rendered
