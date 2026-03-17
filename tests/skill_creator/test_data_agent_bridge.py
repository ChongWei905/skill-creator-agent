from __future__ import annotations

from ferry.core.cbb.base_agent import BaseAgent
from ferry.core.flex.agent import FlexAgent
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.cli import parse_args
from skill_creator_agent.data_agent_bridge import (
    DataAgentSession,
    _looks_like_create_confirmation,
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


def test_data_agent_session_builds_reference_only_stage_config(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-1",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_create_confirmation",
    )

    config = session.preview_turn_ferry_config("创建吧")

    assert "[CURRENT WORKFLOW STAGE]" in config["SCENARIO"]["chat"]["instructions"]
    assert "Step 2 only" in config["SCENARIO"]["chat"]["instructions"]
    assert "Do not ask whether the skill should be created again." in config["SCENARIO"]["chat"]["instructions"]
    assert config["TOOLS"]["local_functions"] == []


def test_discovery_stage_does_not_expose_execute_tool(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-0",
        output_root=tmp_path / "outputs",
        workflow_stage="idle",
    )

    config = session.preview_turn_ferry_config("我想查看当前银行用户中哪些是有风险的用户")
    tool_names = {tool["name"] for tool in config["TOOLS"]["local_functions"]}

    assert "list_available_skills" in tool_names
    assert "execute_skill_script" not in tool_names


def test_discovery_stage_with_no_registered_skills_exposes_no_tools(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": str(tmp_path)}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-empty",
        output_root=tmp_path / "outputs",
        workflow_stage="idle",
    )

    config = session.preview_turn_ferry_config("帮我查看数据库中有风险的用户")

    assert "zero registered skills" in config["SCENARIO"]["chat"]["instructions"]
    assert "Do not ask for reference documentation" in config["SCENARIO"]["chat"]["instructions"]
    assert config["TOOLS"]["local_functions"] == []


def test_stage_prompt_keeps_original_user_goal_across_short_replies(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config(
            {"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills", "graph_enabled": True}}
        ),
        source_config={"SKILL_CREATOR": {"graph_enabled": True}},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-goal",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_reference_answer",
        user_goal="帮我查看数据库中有风险的用户",
    )

    config = session.preview_turn_ferry_config("没有")

    assert "Original user goal: 帮我查看数据库中有风险的用户" in config["SCENARIO"]["chat"]["instructions"]


def test_data_agent_session_builds_plan_stage_with_graph_tools_only(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config(
            {"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills", "graph_enabled": True}}
        ),
        source_config={"SKILL_CREATOR": {"graph_enabled": True}},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-2",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_reference_answer",
    )

    config = session.preview_turn_ferry_config("没有文档支撑")
    tool_names = {tool["name"] for tool in config["TOOLS"]["local_functions"]}

    assert "planned skill behavior" in config["SCENARIO"]["chat"]["instructions"]
    assert "Do not ask whether the user has documentation again." in config["SCENARIO"]["chat"]["instructions"]
    assert "graph_get_object_types" in tool_names
    assert "create_skill_scaffold" not in tool_names
    assert "write_file" not in tool_names


def test_data_agent_session_builds_create_stage_without_reasking_for_approval(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config(
            {"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills", "graph_enabled": True}}
        ),
        source_config={"SKILL_CREATOR": {"graph_enabled": True}},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-create",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_plan_approval",
        user_goal="帮我查看数据库中有风险的用户",
    )

    config = session.preview_turn_ferry_config("是，请创建技能")
    tool_names = {tool["name"] for tool in config["TOOLS"]["local_functions"]}
    instructions = config["SCENARIO"]["chat"]["instructions"]

    assert "Do not ask whether the skill should be created again." in instructions
    assert "Start by calling create_skill_scaffold" in instructions
    assert "create_skill_scaffold" in tool_names
    assert "reload_skill" in tool_names
    assert "write_file" in tool_names


def test_create_confirmation_detection_matches_real_chinese_prompt():
    assistant_text = (
        "目前没有现成的技能可以处理这个需求。\n\n"
        "请问您希望我为您创建一个新的技能来处理这个需求吗？\n"
        "请确认是否要创建这个新技能？"
    )

    assert _looks_like_create_confirmation(assistant_text) is True


def test_propose_plan_stage_does_not_advance_when_assistant_repeats_doc_question(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config(
            {"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills", "graph_enabled": True}}
        ),
        source_config={"SKILL_CREATOR": {"graph_enabled": True}},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-3",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_reference_answer",
    )

    session._advance_workflow_stage(
        session.resolve_turn_policy("没有"),
        "您是否有任何关于用户风险分析的参考文档可以帮助指导技能创建？",
    )

    assert session.workflow_stage == "awaiting_reference_answer"
