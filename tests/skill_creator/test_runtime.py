from __future__ import annotations

import pytest

from skill_creator_agent.runtime import SkillCreatorRuntime
from skill_creator_agent.settings import DEFAULT_SKILLS_ROOT


def test_runtime_lists_and_reads_fixture_skill():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
            }
        }
    )

    skills = runtime.list_skills()
    content = runtime.read_skill_content("skill-creator-smoke")
    scripts = runtime.list_skill_scripts("skill-creator-smoke")

    assert len(skills) == 1
    assert skills[0]["name"] == "skill-creator-smoke"
    assert "Skill Creator Smoke" in content
    assert scripts[0]["name"] == "echo_input"


def test_runtime_executes_script_and_returns_structured_result():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
            }
        }
    )

    result = runtime.execute_skill_script("skill-creator-smoke", "echo_input", args=["runtime"])

    assert result["skill"] == "skill-creator-smoke"
    assert result["script"] == "echo_input"
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "runtime"
    assert result["stderr"] == ""


def test_runtime_builds_system_prompt_with_skill_context_and_reminder():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(DEFAULT_SKILLS_ROOT),
                "graph_enabled": False,
            }
        }
    )

    prompt = runtime.build_system_prompt(
        just_created_skill="skill-creator-smoke",
        original_intent="Create a smoke-test skill",
    )

    assert "skill-creator-smoke" in prompt
    assert "Create a smoke-test skill" in prompt
    assert "Available Skills" in prompt
    assert "Skill Creation Workflow" in prompt


def test_runtime_builds_direct_query_prompt_with_direct_fallback():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(DEFAULT_SKILLS_ROOT),
            }
        }
    )

    prompt = runtime.build_system_prompt(direct_query=True)

    assert "direct-query mode" in prompt
    assert "dedicated skill would be required" in prompt


def test_runtime_creates_skill_scaffold_and_reloads_it(tmp_path):
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path),
            }
        }
    )

    scaffold = runtime.create_skill_scaffold(
        "generated-skill",
        "Generated during tests.",
        body="# Generated Skill\n\n1. Run the script.",
        script_files={"run.sh": "#!/usr/bin/env bash\necho generated\n"},
    )
    skill = runtime.reload_skill("generated-skill")

    assert scaffold["skill_name"] == "generated-skill"
    assert (tmp_path / "generated-skill" / "SKILL.md").exists()
    assert skill.name == "generated-skill"
    assert skill.list_script_names() == ["run"]


def test_runtime_rejects_duplicate_skill_scaffold(tmp_path):
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path),
            }
        }
    )

    runtime.create_skill_scaffold("duplicate-skill", "Created once.")

    with pytest.raises(FileExistsError):
        runtime.create_skill_scaffold("duplicate-skill", "Created twice.")
