from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Mapping

import yaml
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.ferry_tools import configure_runtime_tools
from skill_creator_agent.orchestration import (
    AWAIT_BUILD_REVIEW,
    AWAIT_CREATE_CONFIRMATION,
    AWAIT_PLAN_APPROVAL,
    AWAIT_REFERENCES,
    BUILDING_AND_RUNNING,
    CANCELLED,
    DISCOVERING,
    DONE,
    ERROR,
    IDLE,
    PLANNING,
    ArtifactStore,
    BuildRunAgent,
    DraftSkillManager,
    ExistingSkillAgent,
    PlanAgent,
    SessionState,
    StageRunner,
    UnifiedRouter,
    build_reference_bundle,
)
from skill_creator_agent.paths import project_path
from skill_creator_agent.runtime import SkillCreatorRuntime

DEFAULT_VERIFICATION_CONFIG = project_path("config.yaml")
DEFAULT_VERIFICATION_OUTPUT_ROOT = project_path(".tmp", "data_agent_multiturn")
DEFAULT_MATERIALIZED_CONFIG_ROOT = project_path(".tmp", "generated_configs")


class DataAgentSession:
    def __init__(
        self,
        *,
        data_agent: DataAgent,
        runtime: SkillCreatorRuntime,
        source_config: Mapping[str, Any],
        ferry_config_path: Path,
        user_id: str,
        session_id: str,
        output_root: Path,
        router_model_name: str,
    ) -> None:
        """Initialize one stateful multi-turn session over Ferry-backed stage agents.

        Args:
            data_agent: The bootstrap Ferry ``DataAgent`` instance created for the session.
                It is replaced as needed when later stages materialize a different stage agent.
            runtime: The shared ``SkillCreatorRuntime`` used to inspect skills, execute scripts,
                and access graph-backed helpers during this session.
            source_config: The effective configuration mapping after loading defaults and applying
                caller overrides. This mapping is reused whenever a stage-specific Ferry config
                needs to be rendered.
            ferry_config_path: The filesystem path where the current materialized Ferry YAML config
                is written. Stage execution reuses this location and overwrites it per stage.
            user_id: The logical user identifier injected into Ferry state for all stage calls.
            session_id: The stable workflow session identifier. It is used to group stage outputs,
                artifact storage, and draft skill directories under one session root.
            output_root: The parent directory under which this session writes stage outputs,
                artifacts, and draft skill workspaces.
            router_model_name: The Ferry model name used by ``UnifiedRouter`` when it needs an
                LLM decision for user replies or non-deterministic worker results.
        """
        self.data_agent = data_agent
        self.runtime = runtime
        self.source_config = dict(source_config)
        self.ferry_config_path = ferry_config_path.resolve()
        self.user_id = user_id
        self.session_id = session_id
        self.output_root = output_root.resolve()
        self.router_model_name = router_model_name
        self.next_run_id = 0
        self.next_call_id = 0

        self.state = SessionState()
        self.stage_runner = StageRunner(
            source_config=self.source_config,
            ferry_config_path=self.ferry_config_path,
        )
        self.router = UnifiedRouter(router_model_name)
        self.existing_skill_agent = ExistingSkillAgent()
        self.plan_agent = PlanAgent()
        self.build_run_agent = BuildRunAgent()
        self._draft_contexts: dict[str, Any] = {}

        self._refresh_session_storage()

    @property
    def output_path(self) -> Path:
        """Return the session-specific output directory."""
        return (self.output_root / self.session_id).resolve()

    @property
    def workflow_stage(self) -> str:
        """Return the current high-level workflow stage."""
        return self.state.workflow_stage

    @workflow_stage.setter
    def workflow_stage(self, value: str) -> None:
        """Update the current high-level workflow stage."""
        self.state.workflow_stage = value

    @property
    def active_turn_stage(self) -> str:
        """Return the active internal stage handling the current turn."""
        return self.state.active_turn_stage

    @active_turn_stage.setter
    def active_turn_stage(self, value: str) -> None:
        """Update the active internal stage handling the current turn."""
        self.state.active_turn_stage = value

    async def ask(self, query: str) -> dict[str, Any]:
        """Process one user turn and advance the orchestrated workflow state."""
        normalized = query.strip()
        if not normalized:
            return _text_response("请输入需要处理的内容。")

        if self.workflow_stage in {DONE, CANCELLED, ERROR}:
            self.state.reset()

        self.state.last_user_reply = normalized

        if self.workflow_stage == IDLE:
            self.state.user_goal = normalized
            self.state.normalized_goal = normalized
            response = await self._run_existing_skill_turn(normalized)
        elif self.workflow_stage == AWAIT_CREATE_CONFIRMATION:
            response = await self._handle_create_confirmation(normalized)
        elif self.workflow_stage == AWAIT_REFERENCES:
            response = await self._handle_references(normalized)
        elif self.workflow_stage == AWAIT_PLAN_APPROVAL:
            response = await self._handle_plan_approval(normalized)
        elif self.workflow_stage == AWAIT_BUILD_REVIEW:
            response = await self._handle_build_review(normalized)
        else:
            self.state.reset()
            self.state.user_goal = normalized
            self.state.normalized_goal = normalized
            response = await self._run_existing_skill_turn(normalized)

        self.next_run_id += 1
        return response

    def reset(self, *, session_id: str | None = None) -> None:
        """Reset the session state and rebuild the bootstrap stage agent."""
        self.session_id = session_id or _new_session_id()
        self.next_run_id = 0
        self.next_call_id = 0
        self.state.reset()
        self._draft_contexts.clear()
        self._refresh_session_storage()
        self.data_agent = self.stage_runner.build_data_agent(
            spec=self.existing_skill_agent.build_spec(
                runtime=self.runtime,
                state=self.state,
                query="",
            ),
            runtime=self.runtime,
        )

    async def _run_existing_skill_turn(self, query: str) -> dict[str, Any]:
        self.workflow_stage = DISCOVERING
        self.active_turn_stage = "existing_skill"
        result, data_agent = await self.existing_skill_agent.run(
            runtime=self.runtime,
            stage_runner=self.stage_runner,
            state=self.state,
            query=query,
            user_id=self.user_id,
            stage_session_id=self._stage_session_id("existing_skill"),
            stage_output_path=self._stage_output_path("existing_skill"),
        )
        if data_agent is not None:
            self.data_agent = data_agent

        decision = await self.router.route_worker_result(
            self.state,
            worker_name="ExistingSkillAgent",
            result_code=result.result_code,
            assistant_text=result.user_message,
        )
        self.state.last_router_decision = decision.decision
        self.state.last_assistant_text = result.user_message
        self.workflow_stage = decision.next_state
        self.state.last_question_type = decision.next_question_type
        self.active_turn_stage = "existing_skill"
        return result.raw_response or _text_response(result.user_message)

    async def _handle_create_confirmation(self, reply: str) -> dict[str, Any]:
        decision = await self.router.route_user_reply(self.state, reply)
        self.state.last_router_decision = decision.decision

        if decision.decision == "confirm_create":
            self.workflow_stage = AWAIT_REFERENCES
            self.active_turn_stage = "ask_references"
            self.state.last_question_type = "references_request"
            text = (
                "可以，我会为这个需求创建一个新的技能。\n\n"
                "在继续之前，请告诉我是否有可参考的资料，例如业务规则、字段说明、接口文档、样例查询或现成流程。"
                "如果没有，请直接回复“没有”。"
            )
            self.state.last_assistant_text = text
            return _text_response(text)

        return await self._handle_non_worker_decision(decision, reply)

    async def _handle_references(self, reply: str) -> dict[str, Any]:
        decision = await self.router.route_user_reply(self.state, reply)
        self.state.last_router_decision = decision.decision

        if decision.decision in {"provide_references", "no_references"}:
            bundle = "未提供参考资料。" if decision.decision == "no_references" else build_reference_bundle(reply)
            artifact_ref = self.artifacts.write_text(
                f"references/reference_bundle_{self.next_call_id:03d}.md",
                bundle,
            )
            self.state.reference_artifact_ref = artifact_ref
            self.state.reference_summary = _compact_text(bundle, limit=12000)
            self.state.latest_feedback_artifact_ref = ""
            return await self._run_plan_turn()

        return await self._handle_non_worker_decision(decision, reply)

    async def _handle_plan_approval(self, reply: str) -> dict[str, Any]:
        decision = await self.router.route_user_reply(self.state, reply)
        self.state.last_router_decision = decision.decision

        if decision.decision == "approve_plan":
            approved = self.state.current_plan
            if approved is None:
                text = "当前还没有可批准的方案，请先重新生成方案。"
                self.state.last_assistant_text = text
                return _text_response(text)
            approved.status = "approved"
            self.state.approved_plan_version = approved.version
            self.state.latest_feedback_artifact_ref = ""
            return await self._run_build_turn()

        if decision.decision == "revise_plan":
            self.state.latest_feedback_artifact_ref = self.artifacts.write_text(
                f"feedback/plan_feedback_{self.next_call_id:03d}.md",
                reply,
            )
            return await self._run_plan_turn()

        return await self._handle_non_worker_decision(decision, reply)

    async def _handle_build_review(self, reply: str) -> dict[str, Any]:
        decision = await self.router.route_user_reply(self.state, reply)
        self.state.last_router_decision = decision.decision

        if decision.decision == "accept_build":
            return self._accept_current_build()

        if decision.decision == "revise_plan":
            current_build = self.state.current_build
            if current_build is not None:
                current_build.status = "rejected"
            self.state.latest_feedback_artifact_ref = self.artifacts.write_text(
                f"feedback/build_feedback_{self.next_call_id:03d}.md",
                reply,
            )
            return await self._run_plan_turn()

        return await self._handle_non_worker_decision(decision, reply)

    async def _run_plan_turn(self) -> dict[str, Any]:
        self.workflow_stage = PLANNING
        self.active_turn_stage = "plan"

        previous_plan_text = ""
        if self.state.current_plan is not None:
            self.state.current_plan.status = "superseded"
            previous_plan_text = self.artifacts.read_text(self.state.current_plan.artifact_ref)
        revision_feedback_text = ""
        if self.state.latest_feedback_artifact_ref:
            revision_feedback_text = self.artifacts.read_text(self.state.latest_feedback_artifact_ref)

        result, data_agent = await self.plan_agent.run(
            runtime=self.runtime,
            stage_runner=self.stage_runner,
            state=self.state,
            previous_plan_text=previous_plan_text,
            revision_feedback_text=revision_feedback_text,
            user_id=self.user_id,
            stage_session_id=self._stage_session_id("plan"),
            stage_output_path=self._stage_output_path("plan"),
        )
        self.data_agent = data_agent

        artifact_ref = self.artifacts.write_text(
            f"plans/plan_v{self.state.next_plan_version():02d}.md",
            result.user_message,
        )
        plan = self.plan_agent.register_plan(
            state=self.state,
            artifact_ref=artifact_ref,
            skill_name=str(result.metadata.get("skill_name", "")),
            skill_slug=str(result.metadata.get("skill_slug", "")),
        )
        self.state.last_assistant_text = result.user_message
        self.workflow_stage = AWAIT_PLAN_APPROVAL
        self.active_turn_stage = "plan"
        self.state.last_question_type = "plan_approval"
        self.state.last_router_decision = "plan_ready"
        plan.status = "proposed"
        return result.raw_response or _text_response(result.user_message)

    async def _run_build_turn(self) -> dict[str, Any]:
        approved_plan = self.state.approved_plan
        if approved_plan is None:
            text = "当前还没有已批准的方案，无法开始创建和执行。"
            self.state.last_assistant_text = text
            self.workflow_stage = ERROR
            return _text_response(text)

        self.workflow_stage = BUILDING_AND_RUNNING
        self.active_turn_stage = "build_run"

        approved_plan_text = self.artifacts.read_text(approved_plan.artifact_ref)
        result, data_agent, draft = await self.build_run_agent.run(
            published_runtime=self.runtime,
            draft_manager=self.draft_manager,
            stage_runner=self.stage_runner,
            state=self.state,
            approved_plan=approved_plan_text,
            user_id=self.user_id,
            stage_session_id=self._stage_session_id("build_run"),
            stage_output_path=self._stage_output_path("build_run"),
        )
        self.data_agent = data_agent

        artifact_ref = self.artifacts.write_text(
            f"builds/build_v{self.state.next_build_version():02d}.md",
            result.user_message,
        )
        build = self.build_run_agent.register_build(
            state=self.state,
            artifact_ref=artifact_ref,
            draft_id=draft.draft_id,
            skill_slug=draft.skill_slug,
        )
        self._draft_contexts[draft.draft_id] = draft
        self.state.last_assistant_text = _augment_build_review_message(result.user_message)
        if result.result_code == "hard_error":
            build.status = "failed"
            self.workflow_stage = ERROR
            self.state.last_question_type = "none"
        else:
            self.workflow_stage = AWAIT_BUILD_REVIEW
            self.state.last_question_type = "build_review"
        self.active_turn_stage = "build_run"
        return _text_response(self.state.last_assistant_text)

    async def _handle_non_worker_decision(
        self,
        decision,
        reply: str,
    ) -> dict[str, Any]:
        if decision.decision == "switch_goal":
            self.state.reset()
            self.state.user_goal = decision.normalized_goal or reply
            self.state.normalized_goal = self.state.user_goal
            return await self._run_existing_skill_turn(self.state.user_goal)

        if decision.decision == "cancel":
            self.workflow_stage = CANCELLED
            self.active_turn_stage = "cancelled"
            self.state.last_question_type = "none"
            text = "好的，当前流程已取消。后续如果要重新开始，请直接告诉我新的需求。"
            self.state.last_assistant_text = text
            return _text_response(text)

        if decision.decision in {"decline_create"}:
            self.workflow_stage = IDLE
            self.active_turn_stage = "existing_skill"
            self.state.last_question_type = "none"
            text = "好的，当前先不继续创建流程了。如果之后需要继续创建技能，请直接告诉我。"
            self.state.last_assistant_text = text
            return _text_response(text)

        self.state.last_question_type = "clarification"
        text = self._clarify_message()
        self.state.last_assistant_text = text
        return _text_response(text)

    def _accept_current_build(self) -> dict[str, Any]:
        current_build = self.state.current_build
        if current_build is None:
            text = "当前没有可接受的构建结果。"
            self.state.last_assistant_text = text
            return _text_response(text)

        draft = self._draft_contexts.get(current_build.draft_id)
        if draft is None:
            text = "没有找到当前草稿技能，无法发布。"
            self.state.last_assistant_text = text
            self.workflow_stage = ERROR
            return _text_response(text)

        published_path = self.draft_manager.promote_draft(
            draft=draft,
            published_runtime=self.runtime,
        )
        current_build.status = "accepted"
        self.workflow_stage = DONE
        self.active_turn_stage = "build_review"
        self.state.last_question_type = "none"
        text = (
            "好的，我保留并发布了这版实现，后续可以直接复用这个技能。\n\n"
            f"- skill: {current_build.skill_slug}\n"
            f"- path: {published_path}"
        )
        if current_build.artifact_ref:
            build_report_path = self.artifacts.resolve(current_build.artifact_ref)
            if build_report_path.exists():
                build_report = build_report_path.read_text(encoding="utf-8")
                final_result = _extract_markdown_section(build_report, "## 本次实际输出")
                if final_result:
                    text = (
                        f"{text}\n\n"
                        "## 原始问题结果\n"
                        f"{final_result.strip()}"
                    )
        self.state.last_assistant_text = text
        return _text_response(text)

    def _stage_session_id(self, stage_name: str) -> str:
        return f"{self.session_id}-call{self.next_call_id:03d}-{stage_name}"

    def _stage_output_path(self, stage_name: str) -> Path:
        path = (self.output_path / f"{self.next_call_id:03d}_{stage_name}").resolve()
        self.next_call_id += 1
        return path

    def _refresh_session_storage(self) -> None:
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.artifacts = ArtifactStore(self.output_path / "artifacts")
        self.draft_manager = DraftSkillManager(self.output_path)

    def _clarify_message(self) -> str:
        if self.workflow_stage == AWAIT_CREATE_CONFIRMATION:
            return "请明确告诉我是否需要继续创建这个技能。"
        if self.workflow_stage == AWAIT_REFERENCES:
            return "请提供参考资料，或者直接回复“没有”。"
        if self.workflow_stage == AWAIT_PLAN_APPROVAL:
            return "请告诉我是批准当前方案，还是希望我按您的反馈继续修改方案。"
        if self.workflow_stage == AWAIT_BUILD_REVIEW:
            return "请告诉我是接受当前实现，还是希望我回退到方案阶段继续修改逻辑。"
        return "请再明确说明一下您的意图。"


def build_data_agent_session(
    config: str | Path | Mapping[str, Any] | None = None,
    *,
    skills_root: str | Path | None = None,
    graph_enabled: bool | None = None,
    graph_base_url: str | None = None,
    graph_timeout: int | None = None,
    user_id: str = "manual_verifier",
    session_id: str | None = None,
    output_root: str | Path | None = None,
    materialized_config_path: str | Path | None = None,
) -> DataAgentSession:
    """Build a stateful multi-turn session backed by Ferry DataAgent stages."""
    source_config = load_config_dict(config)
    _apply_skill_creator_overrides(
        source_config,
        skills_root=skills_root,
        graph_enabled=graph_enabled,
        graph_base_url=graph_base_url,
        graph_timeout=graph_timeout,
    )
    runtime = SkillCreatorRuntime.from_config(source_config)
    configure_runtime_tools(config=source_config, runtime=runtime)

    resolved_output_root = Path(output_root).expanduser().resolve() if output_root else DEFAULT_VERIFICATION_OUTPUT_ROOT
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    resolved_session_id = session_id or _new_session_id()
    if materialized_config_path is None:
        materialized_config_path = DEFAULT_MATERIALIZED_CONFIG_ROOT / f"{resolved_session_id}.yaml"
    rendered_path = Path(materialized_config_path).expanduser().resolve()

    bootstrap_state = SessionState()
    bootstrap_runner = StageRunner(source_config=source_config, ferry_config_path=rendered_path)
    bootstrap_spec = ExistingSkillAgent().build_spec(runtime=runtime, state=bootstrap_state, query="")
    data_agent = bootstrap_runner.build_data_agent(spec=bootstrap_spec, runtime=runtime)

    return DataAgentSession(
        data_agent=data_agent,
        runtime=runtime,
        source_config=source_config,
        ferry_config_path=rendered_path,
        user_id=user_id,
        session_id=resolved_session_id,
        output_root=resolved_output_root,
        router_model_name=_resolve_router_model_name(source_config),
    )


def load_config_dict(config: str | Path | Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Load the effective configuration mapping, merging local overrides over defaults."""
    base_config = _load_default_config()
    if config is None:
        return base_config
    if isinstance(config, Mapping):
        return _deep_merge_dicts(base_config, dict(config))
    path = Path(config).expanduser().resolve()
    payload = _load_yaml_mapping(path, required=path != DEFAULT_VERIFICATION_CONFIG)
    return _deep_merge_dicts(base_config, payload)


def extract_last_message_text(response: Any) -> str:
    """Extract the last assistant-visible text from a Ferry chat response payload."""
    if isinstance(response, dict):
        messages = response.get("messages", [])
        if messages:
            last = messages[-1]
            return str(getattr(last, "content", last))
        final_answer = response.get("final_answer")
        if final_answer is not None:
            return str(final_answer)
    return str(response)


def _load_default_config() -> dict[str, Any]:
    if not DEFAULT_VERIFICATION_CONFIG.exists():
        return {}
    return _load_yaml_mapping(DEFAULT_VERIFICATION_CONFIG, required=True)


def _load_yaml_mapping(path: str | Path, *, required: bool = False) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        if required:
            raise FileNotFoundError(f"Config file not found: {resolved}")
        return {}
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Skill creator config must deserialize to a mapping.")
    return payload


def _deep_merge_dicts(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


def _resolve_router_model_name(config: Mapping[str, Any] | None) -> str:
    model_cfg = (config or {}).get("MODEL")
    if isinstance(model_cfg, Mapping):
        for model_name in model_cfg:
            return str(model_name)
    return "skill_creator_chat"


def _apply_skill_creator_overrides(
    config: dict[str, Any],
    *,
    skills_root: str | Path | None,
    graph_enabled: bool | None,
    graph_base_url: str | None,
    graph_timeout: int | None,
) -> None:
    section = config.setdefault("SKILL_CREATOR", {})
    if not isinstance(section, dict):
        section = {}
        config["SKILL_CREATOR"] = section
    if skills_root is not None:
        section["skills_root"] = str(Path(skills_root).expanduser())
    if graph_enabled is not None:
        section["graph_enabled"] = graph_enabled
    if graph_base_url is not None:
        section["graph_base_url"] = graph_base_url
    if graph_timeout is not None:
        section["graph_timeout"] = graph_timeout


def _new_session_id() -> str:
    return f"skill-creator-{uuid.uuid4().hex[:12]}"


def _text_response(text: str) -> dict[str, Any]:
    return {"messages": [type("Msg", (), {"content": text})()]}


def _extract_markdown_section(markdown: str, heading: str) -> str:
    pattern = rf"{re.escape(heading)}\s*\n(.*?)(?=\n## |\n# |\Z)"
    match = re.search(pattern, markdown, re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _augment_build_response_with_final_result(build_report: str) -> str:
    final_result = _extract_markdown_section(build_report, "## 本次实际输出")
    if not final_result or "## 原始问题结果" in build_report:
        return build_report
    return (
        f"{build_report.rstrip()}\n\n"
        "## 原始问题结果\n"
        f"{final_result}\n"
    )


def _augment_build_review_message(build_report: str) -> str:
    augmented = _augment_build_response_with_final_result(build_report)
    if "是否保存并正式发布这个 skill" in augmented:
        return augmented
    return (
        f"{augmented.rstrip()}\n\n"
        "请确认是否保存并正式发布这个 skill。"
        "如果你对当前逻辑或输出不满意，请直接指出，我会回退到方案阶段继续修改。\n"
    )


def _compact_text(text: str, *, limit: int) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[: limit - 3].rstrip()}..."
