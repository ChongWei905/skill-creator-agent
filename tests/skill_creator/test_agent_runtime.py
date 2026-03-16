from __future__ import annotations

from pathlib import Path

from skill_creator_agent.agent import SkillCreatorAgent
from skill_creator_agent.paths import package_path


def test_skill_creator_agent_from_yaml_uses_runtime_fixture():
    agent = SkillCreatorAgent.from_config(
        package_path("skill_creator_debug.yaml")
    )

    skills = agent.list_skills()

    assert len(skills) == 1
    assert skills[0]["name"] == "skill-creator-smoke"
    assert skills[0]["scripts"][0]["name"] == "echo_input"


def test_skill_creator_agent_delegates_script_execution():
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


def test_skill_creator_agent_builds_ferry_config_with_runtime_tools():
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

    config = agent.build_ferry_config()
    local_tool_names = [tool["name"] for tool in config["TOOLS"]["local_functions"]]

    assert config["AGENT_CONFIG"]["agent_type"] == "skill_creator"
    assert config["ACTOR_LOOP"][0]["chat_model"]["name"] == "demo_chat"
    assert "create_skill_scaffold" in local_tool_names
    assert "read_skill_content" in local_tool_names
    assert config["TOOLS"]["skills"][0]["name"] == "skill-creator-smoke"


def test_skill_creator_agent_materializes_ferry_config_and_delegates_to_data_agent(monkeypatch, tmp_path):
    import ferry.interface.sdk.agent as ferry_agent_module

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
    observed: dict[str, Path] = {}

    monkeypatch.setattr(
        ferry_agent_module.DataAgent,
        "from_config",
        classmethod(lambda cls, config: observed.setdefault("config_path", Path(config))),
    )

    result = agent.create_ferry_agent(tmp_path / "skill_creator_ferry.yaml")

    assert result == observed["config_path"]
    assert observed["config_path"].exists()
