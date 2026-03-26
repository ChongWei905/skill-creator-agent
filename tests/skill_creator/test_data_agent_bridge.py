from __future__ import annotations

import asyncio
from pathlib import Path

import skill_creator_agent.data_agent_bridge as bridge_module

from skill_creator_agent.cli import parse_args
from skill_creator_agent.data_agent_bridge import (
    DEFAULT_VERIFICATION_CONFIG_EXAMPLE,
    DataAgentSession,
    _augment_build_review_message,
    _augment_build_response_with_final_result,
    _extract_reference_paths,
    _extract_markdown_section,
    _load_reference_sources_from_query,
    build_data_agent_session,
    extract_last_message_text,
    load_config_dict,
    resolve_default_verification_config_path,
)
from skill_creator_agent.orchestration import (
    AWAIT_BUILD_REVIEW,
    AWAIT_CREATE_CONFIRMATION,
    AWAIT_PLAN_APPROVAL,
    AWAIT_REFERENCES,
    BUILDING_AND_RUNNING,
    DONE,
)
from skill_creator_agent.orchestration.drafts import DraftSkillContext
from skill_creator_agent.orchestration.models import BuildVersion, RouterDecision, StageResult
from skill_creator_agent.orchestration.router import UnifiedRouter
from skill_creator_agent.orchestration.stages.plan import _select_skill_slug, _slugify


async def _async_value(value):
    return value


def _make_session(tmp_path: Path, *, skills_root: str | Path | None = None) -> DataAgentSession:
    return build_data_agent_session(
        {
            "SKILL_CREATOR": {
                "skills_root": str(skills_root or tmp_path / "skills"),
                "graph_enabled": False,
            }
        },
        user_id="tester",
        output_root=tmp_path / "outputs",
        materialized_config_path=tmp_path / "rendered.yaml",
    )


def test_load_config_dict_reads_yaml_file():
    config = load_config_dict(DEFAULT_VERIFICATION_CONFIG_EXAMPLE)

    assert config["AGENT_CONFIG"]["agent_type"] == "skill_creator"
    assert config["MODEL"]


def test_load_config_dict_merges_mapping_over_default_config():
    config = load_config_dict(
        {
            "SKILL_CREATOR": {
                "graph_enabled": False,
            }
        }
    )

    assert config["MODEL"]["skill_creator_chat"]["params"]["api_key"]
    assert config["SKILL_CREATOR"]["graph_enabled"] is False


def test_resolve_default_verification_config_path_falls_back_to_example(monkeypatch, tmp_path):
    missing_config = tmp_path / "config.yaml"
    example_config = tmp_path / "config.yaml.example"
    example_config.write_text("MODEL: {}\n", encoding="utf-8")

    monkeypatch.setattr(bridge_module, "DEFAULT_VERIFICATION_CONFIG", missing_config)
    monkeypatch.setattr(bridge_module, "DEFAULT_VERIFICATION_CONFIG_EXAMPLE", example_config)

    resolved = resolve_default_verification_config_path()

    assert resolved == example_config


def test_build_data_agent_session_materializes_runtime_bridge(tmp_path):
    session = _make_session(
        tmp_path,
        skills_root="src/skill_creator_agent/fixtures/minimal_skills",
    )

    chat_agent = session.data_agent.build_agent_graph("chat")

    assert session.ferry_config_path.exists()
    assert session.runtime.list_skills()[0]["name"] == "skill-creator-smoke"
    assert session.output_path == (tmp_path / "outputs" / session.session_id).resolve()
    assert chat_agent is not None


def test_extract_last_message_text_handles_dict_and_fallback():
    assert extract_last_message_text({"messages": [type("Msg", (), {"content": "done"})()]}) == "done"
    assert extract_last_message_text({"final_answer": "fallback"}) == "fallback"


def test_cli_parse_args_defaults():
    args = parse_args([])

    assert args.graph_base_url == "http://127.0.0.1:8000"
    assert args.turn == []
    assert args.disable_graph is False


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


def test_preview_turn_ferry_config_for_empty_discovery_has_no_local_tools(tmp_path):
    session = _make_session(tmp_path)

    config = session.preview_turn_ferry_config("帮我查风险客户")

    assert "Current stage: existing_skill" in config["SCENARIO"]["chat"]["instructions"]
    assert config["TOOLS"]["local_functions"] == []


def test_preview_turn_ferry_config_for_planning_uses_graph_tools_only(tmp_path):
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
    session.workflow_stage = AWAIT_REFERENCES
    session.state.user_goal = "帮我分析支行存款"
    session.state.reference_summary = "未提供参考资料。"

    config = session.preview_turn_ferry_config("")
    tool_names = {tool["name"] for tool in config["TOOLS"]["local_functions"]}

    assert "Current stage: planning" in config["SCENARIO"]["chat"]["instructions"]
    assert "graph_get_object_types" in tool_names
    assert "graph_sorted_search" not in tool_names
    assert "create_skill_scaffold" not in tool_names


def test_preview_turn_ferry_config_for_build_run_uses_minimal_build_tools(tmp_path):
    session = _make_session(tmp_path)
    session.state.user_goal = "帮我分析深圳蛇口支行的本外币存款日均余额"
    plan_ref = session.artifacts.write_text("plans/plan_v01.md", "# 技能执行流程计划\n\n已批准方案")
    plan = session.plan_agent.register_plan(
        state=session.state,
        artifact_ref=plan_ref,
        skill_name="深圳蛇口支行本外币公司存款日均余额分析",
        skill_slug="skill-bank-analysis",
    )
    plan.status = "approved"
    session.state.approved_plan_version = plan.version
    session.workflow_stage = BUILDING_AND_RUNNING

    config = session.preview_turn_ferry_config("")
    tool_names = {tool["name"] for tool in config["TOOLS"]["local_functions"]}

    assert "Current stage: building_and_running" in config["SCENARIO"]["chat"]["instructions"]
    assert "bash" not in tool_names
    assert "list_available_skills" not in tool_names
    assert "create_skill_scaffold" in tool_names
    assert "reload_skill" in tool_names
    assert "execute_skill_script" in tool_names
    assert "write_file" in tool_names
    assert "apply_patch" in tool_names


def test_slugify_falls_back_to_stable_hash_for_non_ascii_name():
    slug = _slugify("深圳蛇口支行本外币公司存款日均余额分析")

    assert slug.startswith("skill-")
    assert slug != "generated-skill"


def test_idle_turn_runs_existing_skill_agent_and_enters_create_confirmation(monkeypatch, tmp_path):
    session = _make_session(tmp_path)

    async def fake_run(**kwargs):
        return StageResult(
            stage_name="existing_skill",
            result_code="need_create_confirmation",
            user_message="没有现成技能，是否要创建新技能？",
        ), None

    monkeypatch.setattr(session.existing_skill_agent, "run", fake_run)

    result = asyncio.run(session.ask("帮我查看有风险的客户"))

    assert "是否要创建" in extract_last_message_text(result)
    assert session.user_goal == "帮我查看有风险的客户"
    assert session.workflow_stage == AWAIT_CREATE_CONFIRMATION


def test_idle_turn_routes_create_question_text_to_create_confirmation(monkeypatch, tmp_path):
    session = _make_session(tmp_path)

    async def fake_route_worker_result(state, *, worker_name, result_code, assistant_text):
        assert worker_name == "ExistingSkillAgent"
        assert result_code == "route_with_router"
        assert "是否需要创建一个新的技能" in assistant_text
        return RouterDecision(
            decision="need_create_confirmation",
            next_state=AWAIT_CREATE_CONFIRMATION,
            confidence=0.92,
            next_question_type="create_confirmation",
        )

    session.router.route_worker_result = fake_route_worker_result

    async def fake_run(**kwargs):
        return (
            StageResult(
                stage_name="existing_skill",
                result_code="route_with_router",
                user_message="现有技能无法满足用户需求。是否需要创建一个新的技能来处理银行分支机构存款余额分析？",
            ),
            None,
        )

    monkeypatch.setattr(session.existing_skill_agent, "run", fake_run)

    result = asyncio.run(session.ask("帮我分析深圳蛇口支行的本外币存款日均余额"))

    assert "是否需要创建一个新的技能" in extract_last_message_text(result)
    assert session.workflow_stage == AWAIT_CREATE_CONFIRMATION
    assert session.state.last_question_type == "create_confirmation"


def test_confirm_create_moves_to_reference_gate(tmp_path):
    session = _make_session(tmp_path)
    session.workflow_stage = AWAIT_CREATE_CONFIRMATION
    session.state.user_goal = "帮我查看有风险的客户"
    session.state.last_question_type = "create_confirmation"

    async def fake_route_user_reply(state, reply):
        return RouterDecision(
            decision="confirm_create",
            next_state=AWAIT_REFERENCES,
            confidence=1.0,
            next_question_type="references_request",
        )

    session.router.route_user_reply = fake_route_user_reply

    result = asyncio.run(session.ask("是，创建吧"))

    assert "请告诉我是否有可参考的资料" in extract_last_message_text(result)
    assert session.workflow_stage == AWAIT_REFERENCES
    assert session.active_turn_stage == "ask_references"


def test_reference_answer_runs_plan_agent_and_records_plan(monkeypatch, tmp_path):
    session = _make_session(tmp_path)
    session.workflow_stage = AWAIT_REFERENCES
    session.state.user_goal = "帮我分析支行存款"
    session.state.last_question_type = "references_request"

    async def fake_route_user_reply(state, reply):
        return RouterDecision(
            decision="no_references",
            next_state="PLANNING",
            confidence=1.0,
        )

    session.router.route_user_reply = fake_route_user_reply

    async def fake_run(**kwargs):
        return (
            StageResult(
                stage_name="plan",
                result_code="plan_ready",
                user_message=(
                    "# 技能执行流程计划\n\n"
                    "**技能名称**: branch-deposit-analysis\n"
                    "**描述**: 查询支行存款并做趋势分析\n\n"
                    "## 所需图数据库实体\n- Organ\n\n"
                    "## 执行步骤\n- step 1\n\n"
                    "## 最终输出格式\n{}\n\n"
                    "## 示例执行\n- demo\n\n"
                    "## 重要说明\n- note\n\n"
                    "## 本版相对上一版的修改\n- 初始版本\n\n"
                    "是否按这个方案创建并执行？"
                ),
                metadata={"skill_name": "branch-deposit-analysis", "skill_slug": "branch-deposit-analysis"},
            ),
            object(),
        )

    monkeypatch.setattr(session.plan_agent, "run", fake_run)

    result = asyncio.run(session.ask("没有"))

    assert "技能执行流程计划" in extract_last_message_text(result)
    assert session.workflow_stage == AWAIT_PLAN_APPROVAL
    assert session.state.current_plan is not None
    assert session.state.current_plan.skill_slug == "branch-deposit-analysis"


def test_plan_revision_runs_plan_agent_again_and_versions_history(monkeypatch, tmp_path):
    session = _make_session(tmp_path)
    session.state.user_goal = "帮我分析支行存款"
    first_plan_ref = session.artifacts.write_text("plans/plan_v01.md", "# 技能执行流程计划\n\n旧方案")
    session.plan_agent.register_plan(
        state=session.state,
        artifact_ref=first_plan_ref,
        skill_name="branch-deposit-analysis",
        skill_slug="branch-deposit-analysis",
    )
    session.workflow_stage = AWAIT_PLAN_APPROVAL
    session.state.last_question_type = "plan_approval"

    async def fake_route_user_reply(state, reply):
        return RouterDecision(
            decision="revise_plan",
            next_state="PLANNING",
            confidence=1.0,
            feedback_type="semantic_mismatch",
            feedback_summary=reply,
        )

    session.router.route_user_reply = fake_route_user_reply

    async def fake_run(**kwargs):
        return (
            StageResult(
                stage_name="plan",
                result_code="plan_ready",
                user_message=(
                    "# 技能执行流程计划\n\n"
                    "**技能名称**: branch-deposit-analysis\n"
                    "**描述**: 修订版\n\n"
                    "## 所需图数据库实体\n- Organ\n\n"
                    "## 执行步骤\n- step 1 revised\n\n"
                    "## 最终输出格式\n{}\n\n"
                    "## 示例执行\n- demo\n\n"
                    "## 重要说明\n- note\n\n"
                    "## 本版相对上一版的修改\n- 修正了步骤 2\n\n"
                    "是否按这个方案创建并执行？"
                ),
                metadata={"skill_name": "branch-deposit-analysis", "skill_slug": "branch-deposit-analysis"},
            ),
            object(),
        )

    monkeypatch.setattr(session.plan_agent, "run", fake_run)

    result = asyncio.run(session.ask("第2步逻辑不对，改一下"))

    assert "修订版" in extract_last_message_text(result)
    assert session.workflow_stage == AWAIT_PLAN_APPROVAL
    assert len(session.state.plan_history) == 2
    assert session.state.plan_history[0].status == "superseded"


def test_plan_approval_runs_build_and_enters_review(monkeypatch, tmp_path):
    session = _make_session(tmp_path)
    session.state.user_goal = "帮我分析支行存款"
    plan_ref = session.artifacts.write_text("plans/plan_v01.md", "# 技能执行流程计划\n\n已批准方案")
    plan = session.plan_agent.register_plan(
        state=session.state,
        artifact_ref=plan_ref,
        skill_name="branch-deposit-analysis",
        skill_slug="branch-deposit-analysis",
    )
    session.state.approved_plan_version = plan.version
    session.workflow_stage = AWAIT_PLAN_APPROVAL
    session.state.last_question_type = "plan_approval"

    async def fake_route_user_reply(state, reply):
        return RouterDecision(
            decision="approve_plan",
            next_state="BUILDING_AND_RUNNING",
            confidence=1.0,
        )

    session.router.route_user_reply = fake_route_user_reply

    async def fake_run(**kwargs):
        draft = session.draft_manager.prepare_draft(skill_slug="branch-deposit-analysis", build_version=1)
        return (
            StageResult(
                stage_name="build_run",
                result_code="build_ready_for_review",
                user_message="# 构建与执行结果\n\n## 本次结果结论\n已成功构建并执行",
                metadata={"draft_id": draft.draft_id, "skill_slug": draft.skill_slug},
            ),
            object(),
            draft,
        )

    monkeypatch.setattr(session.build_run_agent, "run", fake_run)

    result = asyncio.run(session.ask("批准，开始创建"))

    assert "构建与执行结果" in extract_last_message_text(result)
    assert "是否保存并正式发布这个 skill" in extract_last_message_text(result)
    assert session.workflow_stage == AWAIT_BUILD_REVIEW
    assert session.state.current_build is not None
    assert session.state.current_build.skill_slug == "branch-deposit-analysis"


def test_build_review_revision_returns_to_planning(monkeypatch, tmp_path):
    session = _make_session(tmp_path)
    session.state.user_goal = "帮我分析支行存款"
    plan_ref = session.artifacts.write_text("plans/plan_v01.md", "# 技能执行流程计划\n\n方案")
    plan = session.plan_agent.register_plan(
        state=session.state,
        artifact_ref=plan_ref,
        skill_name="branch-deposit-analysis",
        skill_slug="branch-deposit-analysis",
    )
    plan.status = "approved"
    session.state.approved_plan_version = plan.version
    session.state.build_history.append(
        BuildVersion(
            version=1,
            plan_version=plan.version,
            draft_id="build-v01",
            artifact_ref="builds/build_v01.md",
            status="in_review",
            skill_slug="branch-deposit-analysis",
        )
    )
    session.workflow_stage = AWAIT_BUILD_REVIEW
    session.state.last_question_type = "build_review"

    async def fake_route_user_reply(state, reply):
        return RouterDecision(
            decision="revise_plan",
            next_state="PLANNING",
            confidence=1.0,
            feedback_type="semantic_mismatch",
            feedback_summary=reply,
        )

    session.router.route_user_reply = fake_route_user_reply

    async def fake_run(**kwargs):
        return (
            StageResult(
                stage_name="plan",
                result_code="plan_ready",
                user_message="# 技能执行流程计划\n\n## 本版相对上一版的修改\n- 调整逻辑",
                metadata={"skill_name": "branch-deposit-analysis", "skill_slug": "branch-deposit-analysis"},
            ),
            object(),
        )

    monkeypatch.setattr(session.plan_agent, "run", fake_run)

    result = asyncio.run(session.ask("脚本能跑，但是统计逻辑不对，重新改方案"))

    assert "调整逻辑" in extract_last_message_text(result)
    assert session.workflow_stage == AWAIT_PLAN_APPROVAL
    assert session.state.build_history[0].status == "rejected"


def test_extract_markdown_section_returns_requested_build_output():
    markdown = (
        "# 构建与执行结果\n\n"
        "## 本次结果结论\nok\n\n"
        "## 本次实际输出\n"
        "- 当前值：13,017.93亿元\n"
        "- 同比：-3.16%\n\n"
        "## 与已批准方案的对照\n"
        "- 一致\n"
    )

    section = _extract_markdown_section(markdown, "## 本次实际输出")

    assert "当前值：13,017.93亿元" in section
    assert "与已批准方案的对照" not in section


def test_augment_build_response_appends_original_result_section():
    markdown = (
        "# 构建与执行结果\n\n"
        "## 本次结果结论\nok\n\n"
        "## 本次实际输出\n"
        "- 当前值：13,017.93亿元\n"
        "- 同比：-3.16%\n\n"
        "## 与已批准方案的对照\n"
        "- 一致\n"
    )

    augmented = _augment_build_response_with_final_result(markdown)

    assert "## 原始问题结果" in augmented
    assert "- 当前值：13,017.93亿元" in augmented


def test_augment_build_review_message_appends_save_question():
    markdown = (
        "# 构建与执行结果\n\n"
        "## 本次结果结论\nok\n\n"
        "## 本次实际输出\n"
        "- 当前值：13,017.93亿元\n"
    )

    augmented = _augment_build_review_message(markdown)

    assert "## 原始问题结果" in augmented
    assert "是否保存并正式发布这个 skill" in augmented


def test_select_skill_slug_prefers_english_description_when_name_is_non_ascii():
    slug = _select_skill_slug(
        skill_name="深圳蛇口支行本外币公司存款日均余额分析",
        description="branch deposit average balance analysis",
        user_goal="帮我分析深圳蛇口支行的本外币存款日均余额",
    )

    assert slug == "branch-deposit-average-balance-analysis"


def test_accept_build_promotes_draft_skill(tmp_path):
    session = _make_session(tmp_path)
    session.workflow_stage = AWAIT_BUILD_REVIEW
    session.state.user_goal = "帮我分析支行存款"
    session.state.last_question_type = "build_review"
    session.state.build_history.append(
        BuildVersion(
            version=1,
            plan_version=1,
            draft_id="build-v01",
            artifact_ref="builds/build_v01.md",
            status="in_review",
            skill_slug="branch-deposit-analysis",
        )
    )

    draft = session.draft_manager.prepare_draft(skill_slug="branch-deposit-analysis", build_version=1)
    draft.skill_dir.mkdir(parents=True, exist_ok=True)
    draft.scripts_dir.mkdir(parents=True, exist_ok=True)
    draft.skill_md_path.write_text(
        "---\nname: branch-deposit-analysis\ndescription: Branch deposit analysis.\n---\n\n# Skill\n",
        encoding="utf-8",
    )
    draft.primary_script_path.write_text(
        '"""Run branch deposit analysis."""\nprint("ok")\n',
        encoding="utf-8",
    )
    session._draft_contexts[draft.draft_id] = draft

    async def fake_route_user_reply(state, reply):
        return RouterDecision(
            decision="accept_build",
            next_state=DONE,
            confidence=1.0,
        )

    session.router.route_user_reply = fake_route_user_reply

    result = asyncio.run(session.ask("可以，就这版"))

    assert "发布了这版实现" in extract_last_message_text(result)
    assert session.workflow_stage == DONE
    published_skill = session.runtime.settings.skills_root / "branch-deposit-analysis" / "SKILL.md"
    assert published_skill.exists()


def test_route_user_reply_uses_llm_path_for_create_confirmation(monkeypatch):
    router = UnifiedRouter("skill_creator_chat")
    state = bridge_module.SessionState(
        workflow_stage=AWAIT_CREATE_CONFIRMATION,
        last_question_type="create_confirmation",
        user_goal="帮我分析深圳蛇口支行的本外币存款日均余额",
    )

    async def fake_invoke_router(**kwargs):
        assert kwargs["event_type"] == "user_reply"
        assert kwargs["latest_user_reply"] == "创建，但先按深圳分行口径来"
        return {
            "decision": "confirm_create",
            "next_state": "AWAIT_REFERENCES",
            "confidence": 0.9,
            "needs_clarification": False,
            "goal_action": {"type": "none", "normalized_goal": ""},
            "feedback_action": {"type": "none", "summary": ""},
            "question_action": {"next_question_type": "references_request", "reuse_previous_plan": False},
        }

    monkeypatch.setattr(router, "_invoke_router", fake_invoke_router)

    decision = asyncio.run(router.route_user_reply(state, "创建，但先按深圳分行口径来"))

    assert decision.decision == "confirm_create"
    assert decision.next_state == AWAIT_REFERENCES


def test_route_worker_result_uses_llm_path_for_existing_skill_prompt(monkeypatch):
    router = UnifiedRouter("skill_creator_chat")
    state = bridge_module.SessionState(
        workflow_stage="DISCOVERING",
        last_question_type="none",
        user_goal="帮我分析深圳蛇口支行的本外币存款日均余额",
    )

    async def fake_invoke_router(**kwargs):
        assert kwargs["event_type"] == "worker_result"
        assert kwargs["worker_result"]["worker_name"] == "ExistingSkillAgent"
        assert kwargs["worker_result"]["result_code"] == "route_with_router"
        assert "是否需要创建一个新的技能" in kwargs["worker_result"]["assistant_text"]
        return {
            "decision": "need_create_confirmation",
            "next_state": AWAIT_CREATE_CONFIRMATION,
            "confidence": 0.88,
            "needs_clarification": False,
            "goal_action": {"type": "none", "normalized_goal": ""},
            "feedback_action": {"type": "none", "summary": ""},
            "question_action": {"next_question_type": "create_confirmation", "reuse_previous_plan": False},
        }

    monkeypatch.setattr(router, "_invoke_router", fake_invoke_router)

    decision = asyncio.run(
        router.route_worker_result(
            state,
            worker_name="ExistingSkillAgent",
            result_code="route_with_router",
            assistant_text="现有技能无法满足用户需求。是否需要创建一个新的技能来处理银行分支机构存款余额分析？",
        )
    )

    assert decision.decision == "need_create_confirmation"
    assert decision.next_state == AWAIT_CREATE_CONFIRMATION
