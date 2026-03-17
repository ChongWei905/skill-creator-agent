from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from ferry.actions.tools import tool_manager
from ferry.core.managers.llm_manager import llm_manager
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.ferry_config import materialize_ferry_config
from skill_creator_agent.ferry_tools import configure_runtime_tools
from skill_creator_agent.paths import package_path, project_path
from skill_creator_agent.runtime import SkillCreatorRuntime

DEFAULT_VERIFICATION_CONFIG = package_path("skill_creator_debug.yaml")
DEFAULT_VERIFICATION_OUTPUT_ROOT = project_path(".tmp", "data_agent_multiturn")
DEFAULT_MATERIALIZED_CONFIG_ROOT = project_path(".tmp", "generated_configs")

SKILL_READ_TOOL_NAMES = {
    "list_available_skills",
    "read_skill_content",
    "list_skill_scripts",
    "read_script_source",
}
SKILL_EXECUTION_TOOL_NAMES = {
    *SKILL_READ_TOOL_NAMES,
    "execute_skill_script",
}
GRAPH_TOOL_NAMES = {
    "graph_get_object_types",
    "graph_get_object_relations",
    "graph_get_entity_schema",
    "graph_query_examples",
    "graph_property_filter",
    "graph_property_info",
    "graph_hop_search",
    "graph_count_search",
    "graph_aggregate_search",
    "graph_sorted_search",
    "graph_pattern_search",
}
FILE_TOOL_NAMES = {
    "bash",
    "read_file",
    "write_file",
    "apply_patch",
}
SKILL_CREATION_TOOL_NAMES = {
    "create_skill_scaffold",
    "reload_skill",
}


@dataclass(frozen=True)
class StagePolicy:
    name: str
    prompt_overlay: str
    allowed_tool_names: set[str]


@dataclass
class DataAgentSession:
    data_agent: DataAgent
    runtime: SkillCreatorRuntime
    source_config: dict[str, Any]
    ferry_config_path: Path
    user_id: str
    session_id: str
    output_root: Path
    next_run_id: int = 0
    workflow_stage: str = "idle"
    last_assistant_text: str = ""
    active_turn_stage: str = "discover_existing_skill"
    user_goal: str = ""

    @property
    def output_path(self) -> Path:
        return (self.output_root / self.session_id).resolve()

    async def ask(self, query: str, *, clear_history: bool = False) -> dict[str, Any]:
        normalized = query.strip()
        self._maybe_capture_user_goal(normalized)
        policy = self.resolve_turn_policy(normalized)
        self.data_agent = self._build_turn_data_agent(policy)
        initial_state = {
            "user_id": self.user_id,
            "run_id": self.next_run_id,
            "sub_id": 0,
            "complete": False,
            "messages": [],
        }
        response = await self.data_agent.chat(
            normalized,
            session_id=self.session_id,
            clear_history=clear_history,
            output_path=self.output_path,
            initial_state=initial_state,
        )
        self.last_assistant_text = extract_last_message_text(response)
        self.active_turn_stage = policy.name
        self._advance_workflow_stage(policy, self.last_assistant_text)
        self.next_run_id += 1
        return response

    def reset(self, *, session_id: str | None = None) -> None:
        self.session_id = session_id or _new_session_id()
        self.next_run_id = 0
        self.workflow_stage = "idle"
        self.last_assistant_text = ""
        self.active_turn_stage = "discover_existing_skill"
        self.user_goal = ""
        self.data_agent = self._build_turn_data_agent(self.resolve_turn_policy(""))

    def resolve_turn_policy(self, query: str) -> StagePolicy:
        normalized = query.strip()
        if self.workflow_stage == "awaiting_create_confirmation" and _is_affirmative(normalized):
            return _ask_references_policy()
        if self.workflow_stage == "awaiting_reference_answer":
            return _propose_plan_policy(graph_enabled=self.runtime.settings.graph_enabled)
        if self.workflow_stage == "awaiting_plan_approval" and _is_affirmative(normalized):
            return _create_skill_policy(graph_enabled=self.runtime.settings.graph_enabled)
        if self.workflow_stage == "awaiting_execute_confirmation" and _is_affirmative(normalized):
            return _execute_skill_policy(graph_enabled=self.runtime.settings.graph_enabled)
        return _discover_existing_skill_policy(runtime=self.runtime)

    def preview_turn_ferry_config(self, query: str) -> dict[str, Any]:
        policy = self.resolve_turn_policy(query)
        return self._build_turn_ferry_config(policy)

    def _advance_workflow_stage(self, policy: StagePolicy, assistant_text: str) -> None:
        if policy.name == "ask_references":
            if _looks_like_reference_request(assistant_text):
                self.workflow_stage = "awaiting_reference_answer"
                return
            if _looks_like_plan_approval_request(assistant_text):
                self.workflow_stage = "awaiting_plan_approval"
                return
            self.workflow_stage = "awaiting_reference_answer"
            return
        if policy.name == "propose_plan":
            if _looks_like_plan_approval_request(assistant_text):
                self.workflow_stage = "awaiting_plan_approval"
                return
            if _looks_like_execute_request(assistant_text):
                self.workflow_stage = "awaiting_execute_confirmation"
                return
            self.workflow_stage = "awaiting_reference_answer"
            return
        if policy.name == "create_skill":
            if _looks_like_execute_request(assistant_text):
                self.workflow_stage = "awaiting_execute_confirmation"
                return
            self.workflow_stage = "idle"
            return
        if policy.name == "execute_skill":
            self.workflow_stage = "idle"
            return
        if _looks_like_create_confirmation(assistant_text):
            self.workflow_stage = "awaiting_create_confirmation"
            return
        if _looks_like_reference_request(assistant_text):
            self.workflow_stage = "awaiting_reference_answer"
            return
        if _looks_like_plan_approval_request(assistant_text):
            self.workflow_stage = "awaiting_plan_approval"
            return
        if _looks_like_execute_request(assistant_text):
            self.workflow_stage = "awaiting_execute_confirmation"
            return
        self.workflow_stage = "idle"

    def _build_turn_data_agent(self, policy: StagePolicy) -> DataAgent:
        rendered_path = self.ferry_config_path
        _reset_ferry_singletons()
        materialize_ferry_config(
            self.source_config,
            runtime=self.runtime,
            output_path=rendered_path,
            stage_instructions=self._render_stage_prompt(policy),
            allowed_local_tool_names=policy.allowed_tool_names,
        )
        configure_runtime_tools(config=self.source_config, runtime=self.runtime)
        self.ferry_config_path = rendered_path
        return DataAgent.from_config(rendered_path)

    def _build_turn_ferry_config(self, policy: StagePolicy) -> dict[str, Any]:
        from skill_creator_agent.ferry_config import build_ferry_config

        return build_ferry_config(
            self.source_config,
            runtime=self.runtime,
            stage_instructions=self._render_stage_prompt(policy),
            allowed_local_tool_names=policy.allowed_tool_names,
        )

    def _render_stage_prompt(self, policy: StagePolicy) -> str:
        if not self.user_goal:
            return policy.prompt_overlay
        return (
            f"Original user goal: {self.user_goal}\n"
            "Keep this original goal in scope for this turn even if the latest user reply is short.\n"
            f"{policy.prompt_overlay}"
        )

    def _maybe_capture_user_goal(self, query: str) -> None:
        if not query:
            return
        if self.next_run_id == 0 and not _is_short_control_reply(query):
            self.user_goal = query
            return
        if self.workflow_stage == "idle" and not _is_short_control_reply(query):
            self.user_goal = query


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

    initial_policy = _discover_existing_skill_policy(runtime=runtime)
    _reset_ferry_singletons()
    materialize_ferry_config(
        source_config,
        runtime=runtime,
        output_path=rendered_path,
        stage_instructions=initial_policy.prompt_overlay,
        allowed_local_tool_names=initial_policy.allowed_tool_names,
    )
    data_agent = DataAgent.from_config(rendered_path)
    return DataAgentSession(
        data_agent=data_agent,
        runtime=runtime,
        source_config=source_config,
        ferry_config_path=rendered_path,
        user_id=user_id,
        session_id=resolved_session_id,
        output_root=resolved_output_root,
        active_turn_stage=initial_policy.name,
    )


def load_config_dict(config: str | Path | Mapping[str, Any] | None = None) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, Mapping):
        return dict(config)

    path = Path(config).expanduser().resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Skill creator config must deserialize to a mapping.")
    return payload


def extract_last_message_text(response: Any) -> str:
    if isinstance(response, dict):
        messages = response.get("messages", [])
        if messages:
            last = messages[-1]
            return str(getattr(last, "content", last))
        final_answer = response.get("final_answer")
        if final_answer is not None:
            return str(final_answer)
    return str(response)


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


def _reset_ferry_singletons() -> None:
    tool_manager.reset_instance()
    llm_manager.llm_cache.clear()


def _discover_existing_skill_policy(*, runtime: SkillCreatorRuntime) -> StagePolicy:
    available_skills = runtime.list_skills()
    if not available_skills:
        return StagePolicy(
            name="discover_existing_skill",
            prompt_overlay=(
                "This turn is only for initial skill discovery and reuse. "
                "There are currently zero registered skills in the runtime. "
                "Do not call any skill inspection tools. "
                "Do not inspect graph data. Do not create or modify any files in this turn. "
                "Explain that no matching skill exists and ask only whether a new skill should be created. "
                "Do not ask for reference documentation, schemas, business rules, examples, or risk definitions yet. "
                "Do not bundle Step 2 questions into this response."
            ),
            allowed_tool_names=set(),
        )

    return StagePolicy(
        name="discover_existing_skill",
        prompt_overlay=(
            "This turn is only for initial skill discovery and reuse. "
            "Inspect existing skills first. If an existing skill can solve the task, explain that choice and use it. "
            "Only inspect skill names that were returned by list_available_skills in this turn or already exist in the runtime registry. "
            "Never invent skill names. "
            "If no existing skill matches, stop after asking only whether a new skill should be created. "
            "Do not ask for reference documentation, schemas, business rules, examples, or risk definitions yet. "
            "Do not inspect graph data. Do not execute skill scripts. Do not create or modify any files in this turn."
        ),
        allowed_tool_names=set(SKILL_READ_TOOL_NAMES),
    )


def _ask_references_policy() -> StagePolicy:
    return StagePolicy(
        name="ask_references",
        prompt_overlay=(
            "This turn is Step 2 only. The user has already confirmed that a new skill should be created. "
            "Do not ask whether the skill should be created again. "
            "Ask only for reference documentation, schemas, examples, sample commands, or business rules. "
            "If no reference material exists, ask the user to explicitly say that none is available. "
            "Do not call any tools. Do not inspect graph data. "
            "Do not create or modify any files. "
            "Keep the reply focused on this single documentation question."
        ),
        allowed_tool_names=set(),
    )


def _propose_plan_policy(*, graph_enabled: bool) -> StagePolicy:
    allowed_tool_names = set(GRAPH_TOOL_NAMES) if graph_enabled else set()
    prompt_overlay = (
        "This turn is only for understanding the available schema/data and proposing the execution flow in natural language. "
        "The user has already answered the documentation question in this turn. "
        "Treat short answers such as '没有', '没有文档', or '没有文档支撑' as explicit confirmation that no reference documentation is available. "
        "Do not ask whether the user has documentation again. "
        "Instead, acknowledge the lack of documentation, inspect only the minimum graph/schema information required, "
        "then present the planned skill behavior and wait for explicit approval to create the skill. "
        "Do not create or modify any files in this turn."
    )
    if not graph_enabled:
        prompt_overlay += " Graph access is disabled, so rely only on the user-provided information."
    return StagePolicy(
        name="propose_plan",
        prompt_overlay=prompt_overlay,
        allowed_tool_names=allowed_tool_names,
    )


def _create_skill_policy(*, graph_enabled: bool) -> StagePolicy:
    allowed_tool_names = {
        *FILE_TOOL_NAMES,
        *SKILL_READ_TOOL_NAMES,
        *SKILL_CREATION_TOOL_NAMES,
    }
    if graph_enabled:
        allowed_tool_names.update(GRAPH_TOOL_NAMES)
    return StagePolicy(
        name="create_skill",
        prompt_overlay=(
            "The user has approved the execution plan. You may now create the skill package and write the real SKILL.md/scripts. "
            "Use real graph-backed logic where applicable. Never write mock data, simulated query results, or placeholder scripts. "
            "After writing the package, call reload_skill, summarize what was created, and ask whether the user wants to execute the new skill."
        ),
        allowed_tool_names=allowed_tool_names,
    )


def _execute_skill_policy(*, graph_enabled: bool) -> StagePolicy:
    allowed_tool_names = set(SKILL_EXECUTION_TOOL_NAMES)
    if graph_enabled:
        allowed_tool_names.update(GRAPH_TOOL_NAMES)
    return StagePolicy(
        name="execute_skill",
        prompt_overlay=(
            "The user has approved execution of an existing or newly created skill. "
            "Inspect the relevant SKILL.md/scripts if needed, execute the correct script, and report the real result."
        ),
        allowed_tool_names=allowed_tool_names,
    )


def _is_affirmative(text: str) -> bool:
    normalized = text.strip().lower()
    positives = {
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
        "go ahead",
        "create it",
        "创建吧",
        "创建",
        "是",
        "是的",
        "好的",
        "好",
        "可以",
        "行",
        "确认",
        "开始吧",
        "执行吧",
        "运行吧",
    }
    return normalized in positives or any(token in normalized for token in ["创建吧", "创建", "可以", "确认", "执行吧", "运行吧"])


def _is_short_control_reply(text: str) -> bool:
    normalized = text.strip().lower()
    negatives = {
        "no",
        "n",
        "没有",
        "没有文档",
        "没有文档支撑",
        "无",
        "不用",
        "不需要",
    }
    if _is_affirmative(normalized):
        return True
    return normalized in negatives


def _looks_like_create_confirmation(text: str) -> bool:
    signals = [
        "是否希望我为您创建",
        "希望我为您创建",
        "是否要创建一个新的 skill",
        "是否要创建这个新技能",
        "请确认是否要创建",
        "请问您希望我为您创建",
        "would you like me to create",
        "do you want me to create a new skill",
        "确认技能创建需求",
    ]
    normalized = text.lower()
    if any(signal.lower() in normalized for signal in signals):
        return True
    return (
        ("没有现成的技能" in text or "没有匹配的技能" in text or "no matching skill" in normalized)
        and ("创建" in text or "create" in normalized)
        and ("技能" in text or "skill" in normalized)
    )


def _looks_like_reference_request(text: str) -> bool:
    signals = [
        "参考文档",
        "reference documentation",
        "schema",
        "sample commands",
        "business rules",
        "请提供",
    ]
    return any(signal.lower() in text.lower() for signal in signals)


def _looks_like_plan_approval_request(text: str) -> bool:
    signals = [
        "does this execution flow look correct",
        "should i proceed with creating the skill",
        "execution flow plan",
        "skill execution flow plan",
        "是否继续创建",
        "是否调整",
        "执行流程",
    ]
    return any(signal.lower() in text.lower() for signal in signals)


def _looks_like_execute_request(text: str) -> bool:
    signals = [
        "是否执行",
        "would you like me to execute",
        "do you want me to execute",
        "execute the new skill",
        "run the new skill",
    ]
    return any(signal.lower() in text.lower() for signal in signals)
