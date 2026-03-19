from __future__ import annotations

from ferry.core.managers.llm_manager import llm_manager
from ferry.core.cbb.base_agent import BaseAgent
from ferry.core.flex.agent import FlexAgent
from ferry.actions.tools import tool_manager
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.cli import parse_args
from skill_creator_agent.data_agent_bridge import (
    DataAgentSession,
    _extract_reference_paths,
    _load_reference_sources_from_query,
    _ask_references_policy,
    _create_skill_policy,
    _execute_skill_policy,
    _inspect_schema_policy,
    _propose_plan_policy,
    build_data_agent_session,
    extract_last_message_text,
    load_config_dict,
)
from skill_creator_agent.runtime import SkillCreatorRuntime
from skill_creator_agent.paths import package_path


async def _async_value(value):
    return value


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

    config = session.preview_turn_ferry_config("创建吧", policy=_ask_references_policy())

    assert "Current stage: ask_references" in config["SCENARIO"]["chat"]["instructions"]
    assert "Ask only for reference documentation" in config["SCENARIO"]["chat"]["instructions"]
    assert "Do not ask whether the skill should be created again." not in config["SCENARIO"]["chat"]["instructions"]
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
    instructions = config["SCENARIO"]["chat"]["instructions"]

    assert "list_available_skills" in tool_names
    assert "execute_skill_script" in tool_names
    assert "execute it in this same turn" in instructions


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

    assert "Current stage: discover_existing_skill" in config["SCENARIO"]["chat"]["instructions"]
    assert "Available skill metadata:" in config["SCENARIO"]["chat"]["instructions"]
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


def test_idle_turn_explicitly_sets_user_goal(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-goal-idle",
        output_root=tmp_path / "outputs",
        workflow_stage="idle",
        user_goal="旧目标",
    )

    async def fake_run_stage(policy, query, *, clear_history):
        return {"messages": [type("Msg", (), {"content": "需要先创建技能吗？"})()]}

    monkeypatch.setattr(session, "_run_stage", fake_run_stage)
    monkeypatch.setattr(session, "_route_discovery_transition", lambda assistant_text: _async_value("awaiting_create_confirmation"))

    import asyncio

    asyncio.run(session.ask("新的用户目标"))

    assert session.user_goal == "新的用户目标"


def test_confirmation_turn_does_not_overwrite_existing_user_goal(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-goal-confirm",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_create_confirmation",
        user_goal="帮我查看数据库中有风险的用户",
    )

    async def fake_route(query: str) -> str:
        return "ask_references"

    session._route_confirmation_stage = fake_route  # type: ignore[method-assign]

    import asyncio

    asyncio.run(session.ask("创建"))

    assert session.user_goal == "帮我查看数据库中有风险的用户"


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

    assert "Current stage: inspect_schema" in config["SCENARIO"]["chat"]["instructions"]
    assert "Return only a concise internal handoff summary" in config["SCENARIO"]["chat"]["instructions"]
    assert "graph_get_object_types" in tool_names
    assert "create_skill_scaffold" not in tool_names
    assert "write_file" not in tool_names


def test_extract_reference_paths_finds_existing_file():
    paths = _extract_reference_paths(
        "有文档，位置在/Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md"
    )

    assert paths
    assert paths[0].name == "banks.md"


def test_extract_reference_paths_recovers_missing_leading_slash():
    paths = _extract_reference_paths(
        "有文档，位置在Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md"
    )

    assert paths
    assert str(paths[0]).endswith("/texts/banks.md")


def test_load_reference_sources_from_query_reads_file_content():
    sources = _load_reference_sources_from_query(
        "有文档，位置在/Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md"
    )

    assert len(sources) == 1
    assert sources[0]["path"].endswith("banks.md")
    assert "本外币公司存款日均余额" in sources[0]["content"]


def test_build_reference_summary_from_router_result_preserves_full_reference_source_content(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-reference-full",
        output_root=tmp_path / "outputs",
        user_goal="帮我分析深圳蛇口支行的本外币存款日均余额",
    )

    import asyncio

    summary = session._build_reference_summary_from_router_result(
        {
            "decision": "use_references",
            "document_paths": [
                "/Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md"
            ],
            "inline_reference_text": "",
        }
    )

    assert "## Source: /Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md" in summary
    assert "一、本外币公司存款日均余额" in summary
    assert "（四）分析计算方法" in summary


def test_reference_answer_turn_asks_again_when_router_needs_more_info(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-reference-ask-again",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_reference_answer",
        user_goal="帮我分析深圳蛇口支行的本外币存款日均余额",
    )

    async def fake_route_reference_response(query: str) -> dict[str, object]:
        return {"decision": "ask_again", "document_paths": [], "inline_reference_text": ""}

    monkeypatch.setattr(session, "_route_reference_response", fake_route_reference_response)

    import asyncio

    result = asyncio.run(session.ask("我有文档"))
    text = extract_last_message_text(result)

    assert "请提供可读取的参考文档路径" in text
    assert session.workflow_stage == "awaiting_reference_answer"
    assert session.active_turn_stage == "ask_references"


def test_reference_answer_turn_continues_after_valid_router_result(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config(
            {"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills", "graph_enabled": True}}
        ),
        source_config={"SKILL_CREATOR": {"graph_enabled": True}},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-reference-valid",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_reference_answer",
        user_goal="帮我分析深圳蛇口支行的本外币存款日均余额",
    )

    responses = [
        {"messages": [type("Msg", (), {"content": "SCHEMA SUMMARY:\n- relevant entities: Organ"})()]},
        {"messages": [type("Msg", (), {"content": "这是执行方案，请审批。"})()]},
    ]

    async def fake_route_reference_response(query: str) -> dict[str, object]:
        return {
            "decision": "use_references",
            "document_paths": ["/Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md"],
            "inline_reference_text": "",
        }

    async def fake_run_stage(policy, query, *, clear_history):
        return responses.pop(0)

    monkeypatch.setattr(session, "_route_reference_response", fake_route_reference_response)
    monkeypatch.setattr(session, "_run_stage", fake_run_stage)
    monkeypatch.setattr(session.runtime, "graph_get_object_types", lambda: ["Organ"])
    monkeypatch.setattr(
        session.runtime,
        "graph_get_entity_schema",
        lambda entity_type: {"entity_type": entity_type, "sample_properties": {"name": "深圳蛇口支行", "uuid": "Organ_1"}},
    )
    monkeypatch.setattr(session.runtime, "graph_query_examples", lambda entity_type, limit=1: [{"name": "深圳蛇口支行", "uuid": "Organ_1"}])

    import asyncio

    result = asyncio.run(session.ask("有文档，位置在/Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md"))

    assert "执行方案" in extract_last_message_text(result)
    assert "## Source: /Users/weichong/Documents/new_working_area/skill-creator-agent/texts/banks.md" in session.reference_summary
    assert session.workflow_stage == "awaiting_plan_approval"


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

    config = session.preview_turn_ferry_config("是，请创建技能", policy=_create_skill_policy())
    tool_names = {tool["name"] for tool in config["TOOLS"]["local_functions"]}
    instructions = config["SCENARIO"]["chat"]["instructions"]

    assert "Current stage: create_skill" in instructions
    assert "Do not ask for approval again." in instructions
    assert "Structured schema handoff:" in instructions
    assert "Original Step 5 template excerpt:" in instructions
    assert "### **Step 5: Create Complete Skill Package**" in instructions
    assert "Start with create_skill_scaffold using a slugified `skill_name`" in instructions
    assert "Do not put large bodies, SQL files, config files, or script content into the initial create_skill_scaffold call." in instructions
    assert "from connectors import GraphConnector" in instructions
    assert "GRAPH_DB_BASE_URL" in instructions
    assert "GRAPH_DB_TIMEOUT" in instructions
    assert "GraphConnector(base_url=base_url, timeout=timeout)" in instructions
    assert "When `get_all_properties=True`, GraphConnector returns a list of flat property dictionaries." in instructions
    assert "Do not use `n.name`, `n.uuid`, `n.properties`, or nested `properties` access" in instructions
    assert '{"customer_description": "CONTAINS ' in instructions
    assert 'Do not use nested filter objects like' in instructions
    assert "Do not hardcode graph URLs, sqlite paths, local database file paths" in instructions
    assert "The frontmatter `name` must stay equal to the directory slug" in instructions
    assert "Do not add a separate `slug` field" in instructions
    assert "create_skill_scaffold" in tool_names
    assert "reload_skill" in tool_names
    assert "write_file" in tool_names
    assert "graph_get_object_types" not in tool_names


def test_inspect_schema_stage_always_advances_to_plan_approval(tmp_path):
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

    import asyncio

    next_stage = asyncio.run(
        session._determine_next_workflow_stage(
            _inspect_schema_policy(graph_enabled=True),
            "任何 assistant 文本都不应该影响 inspect_schema 的阶段推进。",
        )
    )

    assert next_stage == "awaiting_plan_approval"


def test_propose_plan_stage_prefers_graph_connector_python_plan(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config(
            {"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills", "graph_enabled": True}}
        ),
        source_config={"SKILL_CREATOR": {"graph_enabled": True}},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-plan",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_plan_approval",
        user_goal="帮我查看数据库中有风险的用户",
        reference_summary="没有参考文档",
        schema_summary="SCHEMA SUMMARY: Person, customer_description",
    )

    config = session._build_turn_ferry_config(_propose_plan_policy())
    instructions = config["SCENARIO"]["chat"]["instructions"]

    assert "Propose a filesystem-safe skill slug" in instructions
    assert "from connectors import GraphConnector" in instructions
    assert "Do not propose sqlite files, local database configs" in instructions
    assert "prefer a small Python execution script plus SKILL.md" in instructions


def test_handle_reference_answer_turn_compacts_schema_then_plan(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config(
            {"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills", "graph_enabled": True}}
        ),
        source_config={"SKILL_CREATOR": {"graph_enabled": True}},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-4",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_reference_answer",
        user_goal="帮我查看数据库中有风险的用户",
    )

    responses = [
        {"messages": [type("Msg", (), {"content": "SCHEMA SUMMARY:\n- relevant entities: Person\n- key properties: customer_description"})()]},
        {"messages": [type("Msg", (), {"content": "这是执行方案，请审批。"})()]},
    ]

    monkeypatch.setattr(session.runtime, "graph_get_object_types", lambda: ["Person"])
    monkeypatch.setattr(
        session.runtime,
        "graph_get_entity_schema",
        lambda entity_type: {
            "entity_type": entity_type,
            "sample_properties": {
                "name": "测试客户",
                "party_id": "P001",
                "customer_description": "潜在风险客户标识:是",
                "uuid": "Person_001",
            },
        },
    )
    monkeypatch.setattr(
        session.runtime,
        "graph_query_examples",
        lambda entity_type, limit=1: [
            {
                "name": "测试客户",
                "party_id": "P001",
                "customer_description": "潜在风险客户标识:是",
                "uuid": "Person_001",
            }
        ],
    )

    async def fake_run_stage(policy, query, *, clear_history):
        return responses.pop(0)

    async def fake_route_reference_response(query: str) -> dict[str, object]:
        return {"decision": "no_references", "document_paths": [], "inline_reference_text": ""}

    monkeypatch.setattr(session, "_run_stage", fake_run_stage)
    monkeypatch.setattr(session, "_route_reference_response", fake_route_reference_response)

    import asyncio

    result = asyncio.run(session.ask("没有"))

    assert "执行方案" in extract_last_message_text(result)
    assert "Person" in session.schema_summary
    assert "STRUCTURED SCHEMA HANDOFF:" in session.structured_schema_handoff
    assert "flat result shape" in session.structured_schema_handoff
    assert "fields: customer_description, name, party_id, uuid" in session.structured_schema_handoff
    assert session.workflow_stage == "awaiting_plan_approval"
    assert session.active_turn_stage == "propose_plan"


def test_empty_discovery_stage_short_circuits_to_direct_create_question(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": str(tmp_path)}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-empty-short",
        output_root=tmp_path / "outputs",
        workflow_stage="idle",
        user_goal="帮我查看数据库中有风险的用户",
    )

    import asyncio

    result = asyncio.run(session.ask("帮我查看数据库中有风险的用户"))
    text = extract_last_message_text(result)

    assert "创建一个新的技能" in text
    assert "帮我查看数据库中有风险的用户" in text
    assert session.workflow_stage == "awaiting_create_confirmation"


def test_ask_references_stage_short_circuits_to_single_question(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-doc-short",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_create_confirmation",
        user_goal="帮我查看数据库中有风险的用户",
    )

    async def fake_route(query: str):
        return "ask_references"

    session._route_confirmation_stage = fake_route  # type: ignore[method-assign]

    import asyncio

    result = asyncio.run(session.ask("创建"))
    text = extract_last_message_text(result)

    assert "是否有可参考的资料" in text
    assert "如果没有，请直接回复“没有”" in text
    assert session.workflow_stage == "awaiting_reference_answer"


def test_stage_tool_registry_isolation_between_schema_and_create(tmp_path):
    session = build_data_agent_session(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path / "skills"),
                "graph_enabled": True,
            }
        },
        user_id="tester",
        output_root=tmp_path / "outputs",
        materialized_config_path=tmp_path / "rendered.yaml",
    )
    session.user_goal = "帮我查看数据库中有风险的用户"
    session.reference_summary = "没有"
    session.schema_summary = "SCHEMA SUMMARY: Person"
    session.workflow_stage = "awaiting_plan_approval"

    session._build_turn_data_agent(_inspect_schema_policy(graph_enabled=True), "inspect schema")
    assert "graph_get_object_types" in set(tool_manager.list_tools())

    session._build_turn_data_agent(_create_skill_policy(), "批准，请创建")
    tool_names = set(tool_manager.list_tools())

    assert "create_skill_scaffold" in tool_names
    assert "graph_get_object_types" not in tool_names


def test_handle_create_skill_turn_runs_serial_substages(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": str(tmp_path / "skills")}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-create-flow",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_plan_approval",
        user_goal="帮我查看数据库中有风险的用户",
        plan_summary="建议创建技能 `identify-risky-customers`，使用 GraphConnector 查询 Person 风险客户。",
    )

    stage_calls: list[str] = []
    reload_calls: list[str] = []

    async def fake_run_stage(policy, query, *, clear_history):
        stage_calls.append(policy.name)
        return {"messages": [type("Msg", (), {"content": f"{policy.name} done"})()]}

    monkeypatch.setattr(session, "_run_stage", fake_run_stage)
    monkeypatch.setattr(session.runtime, "reload_skill", lambda name: reload_calls.append(name) or object())
    monkeypatch.setattr(session, "_route_confirmation_stage", fake_route_create_skill)

    import asyncio

    result = asyncio.run(session.ask("批准，请创建"))
    text = extract_last_message_text(result)

    assert stage_calls == ["write_skill_doc", "write_skill_script"]
    assert reload_calls == ["identify-risky-customers"]
    assert session.created_skill_name == "identify-risky-customers"
    assert session.workflow_stage == "awaiting_execute_confirmation"
    assert "identify-risky-customers" in text
    assert "帮我查看数据库中有风险的用户" in text
    assert (tmp_path / "skills" / "identify-risky-customers" / "SKILL.md").exists()


def test_plan_approval_accepts_plain_pizhun_reply(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": str(tmp_path / "skills")}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-plan-approve",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_plan_approval",
        user_goal="帮我查看数据库中有风险的用户",
        plan_summary="建议创建技能 `identify-risky-customers`。",
    )

    async def fake_handle_create_skill_turn(query: str):
        return {"messages": [type("Msg", (), {"content": f"created from {query}"})()]}

    monkeypatch.setattr(session, "_handle_create_skill_turn", fake_handle_create_skill_turn)
    monkeypatch.setattr(session, "_route_confirmation_stage", fake_route_create_skill)

    import asyncio

    result = asyncio.run(session.ask("批准"))

    assert extract_last_message_text(result) == "created from 批准"
    assert session.next_run_id == 1


async def fake_route_create_skill(query: str) -> str:
    return "create_skill"


def test_execute_confirmation_uses_router_decision(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-execute",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_execute_confirmation",
    )

    async def fake_route(query: str) -> str:
        return "execute_skill"

    async def fake_run_stage(policy, query, *, clear_history):
        assert policy.name == _execute_skill_policy().name
        return {"messages": [type("Msg", (), {"content": "executed"})()]}

    monkeypatch.setattr(session, "_route_confirmation_stage", fake_route)
    monkeypatch.setattr(session, "_run_stage", fake_run_stage)

    import asyncio

    result = asyncio.run(session.ask("执行"))

    assert extract_last_message_text(result) == "executed"
    assert session.workflow_stage == "idle"


def test_router_decline_keeps_flow_out_of_creation(tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-decline",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_create_confirmation",
    )

    async def fake_route(query: str) -> str:
        return "idle"

    session._route_confirmation_stage = fake_route  # type: ignore[method-assign]

    import asyncio

    result = asyncio.run(session.ask("先不创建"))

    assert "先不继续这个创建流程" in extract_last_message_text(result)
    assert session.workflow_stage == "idle"


def test_confirmation_router_uses_llm_output(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-router",
        output_root=tmp_path / "outputs",
        workflow_stage="awaiting_create_confirmation",
    )

    class FakeLLM:
        async def ainvoke(self, chat_input, **kwargs):
            return type("Resp", (), {"content": '{"next_stage":"ask_references"}'})()

    monkeypatch.setattr(llm_manager, "get_llm", lambda name: FakeLLM())

    import asyncio

    result = asyncio.run(session._route_confirmation_stage("创建吧"))

    assert result == "ask_references"


def test_discovery_transition_uses_llm_output(monkeypatch, tmp_path):
    session = DataAgentSession(
        data_agent=object(),
        runtime=SkillCreatorRuntime.from_config({"SKILL_CREATOR": {"skills_root": "fixtures/minimal_skills"}}),
        source_config={},
        ferry_config_path=tmp_path / "rendered.yaml",
        user_id="tester",
        session_id="session-discovery-router",
        output_root=tmp_path / "outputs",
        workflow_stage="idle",
    )

    class FakeLLM:
        async def ainvoke(self, chat_input, **kwargs):
            return type("Resp", (), {"content": '{"next_workflow_stage":"awaiting_create_confirmation"}'})()

    monkeypatch.setattr(llm_manager, "get_llm", lambda name: FakeLLM())

    import asyncio

    result = asyncio.run(
        session._route_discovery_transition("当前没有匹配的技能。您是否希望我为您创建一个新的技能？")
    )

    assert result == "awaiting_create_confirmation"
