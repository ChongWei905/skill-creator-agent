from __future__ import annotations

from skill_creator_agent.ferry_config import DEFAULT_RUNTIME_TOOLS
from skill_creator_agent.ferry_tools import configure_runtime_tools, reset_runtime_tools
from skill_creator_agent.runtime import SkillCreatorRuntime


def test_skill_creator_tools_register_with_ferry_tool_manager(tmp_path):
    from ferry.actions.tools.manager import ToolManager

    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path),
            }
        }
    )
    configure_runtime_tools(runtime=runtime)
    ToolManager.reset_instance()

    try:
        manager = ToolManager()
        manager.init_from_config({"TOOLS": {"local_functions": DEFAULT_RUNTIME_TOOLS}})

        created = manager.call(
            "create_skill_scaffold",
            skill_name="tool-created-skill",
            description="Created via ferry tool manager.",
            body="# Tool Created Skill",
        )
        reloaded = manager.call("reload_skill", skill_name="tool-created-skill")
        listed = manager.call("list_available_skills")

        assert created.success is True
        assert reloaded.success is True
        assert any(skill["name"] == "tool-created-skill" for skill in listed.data)
    finally:
        ToolManager.reset_instance()
        reset_runtime_tools()
