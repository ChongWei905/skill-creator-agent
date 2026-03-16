from __future__ import annotations

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
