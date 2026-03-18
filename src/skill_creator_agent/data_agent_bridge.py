from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import yaml
from ferry.actions.tools import tool_manager
from ferry.core.managers.llm_manager import llm_manager
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.ferry_config import materialize_ferry_config
from skill_creator_agent.ferry_tools import configure_runtime_tools
from skill_creator_agent.paths import package_path, project_path
from skill_creator_agent.prompts import (
    GRAPH_DB_INSTRUCTION,
    SKILL_EXECUTION_REMINDER,
    STAGE_CONTEXT_ASK_REFERENCES,
    STAGE_CONTEXT_CREATE_SKILL,
    STAGE_CONTEXT_DISCOVER_EXISTING_SKILL,
    STAGE_CONTEXT_EXECUTE_SKILL,
    STAGE_CONTEXT_INSPECT_SCHEMA,
    STAGE_CONTEXT_PROPOSE_PLAN,
    STAGE_CONTEXT_WRITE_SKILL_DOC,
    STAGE_CONTEXT_WRITE_SKILL_SCRIPT,
    STAGE_ROUTER,
    load_prompt,
    load_skill_creation_step1,
    load_skill_creation_step2,
    load_skill_creation_step3,
    load_skill_creation_step4,
    load_skill_creation_step5,
    load_skill_creation_step6,
)
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
STAGE_CONTEXT_PROMPTS = {
    "discover_existing_skill": STAGE_CONTEXT_DISCOVER_EXISTING_SKILL,
    "ask_references": STAGE_CONTEXT_ASK_REFERENCES,
    "inspect_schema": STAGE_CONTEXT_INSPECT_SCHEMA,
    "propose_plan": STAGE_CONTEXT_PROPOSE_PLAN,
    "create_skill": STAGE_CONTEXT_CREATE_SKILL,
    "write_skill_doc": STAGE_CONTEXT_WRITE_SKILL_DOC,
    "write_skill_script": STAGE_CONTEXT_WRITE_SKILL_SCRIPT,
    "execute_skill": STAGE_CONTEXT_EXECUTE_SKILL,
}
STAGE_WORKFLOW_LOADERS = {
    "discover_existing_skill": load_skill_creation_step1,
    "ask_references": load_skill_creation_step2,
    "inspect_schema": load_skill_creation_step3,
    "propose_plan": load_skill_creation_step4,
    "create_skill": load_skill_creation_step5,
    "write_skill_doc": load_skill_creation_step5,
    "write_skill_script": load_skill_creation_step5,
    "execute_skill": load_skill_creation_step6,
}


@dataclass(frozen=True)
class StagePolicy:
    name: str
    allowed_tool_names: set[str]
    constraints: str = "Follow the current stage exactly. Use only the registered tools for this stage."


CONFIRMATION_ROUTE_CHOICES: dict[str, tuple[str, ...]] = {
    "awaiting_create_confirmation": ("ask_references", "idle", "awaiting_create_confirmation"),
    "awaiting_plan_approval": ("create_skill", "awaiting_plan_approval"),
    "awaiting_execute_confirmation": ("execute_skill", "idle", "awaiting_execute_confirmation"),
}


def _format_allowed_tools(allowed_tool_names: set[str]) -> str:
    allowed_tools = sorted(allowed_tool_names)
    return ", ".join(allowed_tools) if allowed_tools else "none"


def _format_skill_metadata(runtime: SkillCreatorRuntime) -> str:
    skills = runtime.list_skills()
    if not skills:
        return "- None"
    return "\n".join(f"- {skill['name']}: {skill['description']}" for skill in skills[:20])


def _load_stage_workflow_excerpt(stage_name: str) -> str:
    loader = STAGE_WORKFLOW_LOADERS.get(stage_name)
    return loader() if loader is not None else ""


def _format_stage_router_choices(stage_name: str) -> str:
    choices = CONFIRMATION_ROUTE_CHOICES.get(stage_name, ())
    return "\n".join(f"- {choice}" for choice in choices)


def _render_stage_system_prompt(
    *,
    policy: StagePolicy,
    runtime: SkillCreatorRuntime,
    query: str,
    user_goal: str,
    reference_summary: str,
    schema_summary: str,
    structured_schema_handoff: str,
    plan_summary: str,
    created_skill_summary: str,
    created_skill_name: str,
) -> str:
    template_name = STAGE_CONTEXT_PROMPTS[policy.name]
    goal = user_goal or query or "Unknown goal"
    execution_reminder = ""
    if policy.name == "execute_skill":
        execution_reminder = load_prompt(
            SKILL_EXECUTION_REMINDER,
            skill_name=created_skill_name or "the created skill",
            original_intent=goal,
        )
    return load_prompt(
        template_name,
        user_goal=goal,
        allowed_tools=_format_allowed_tools(policy.allowed_tool_names),
        skill_metadata=_format_skill_metadata(runtime),
        reference_summary=reference_summary or "None provided.",
        schema_summary=schema_summary or "No schema summary available.",
        structured_schema_handoff=structured_schema_handoff or "No structured schema handoff available.",
        plan_summary=plan_summary or "No approved plan summary available.",
        created_skill_summary=created_skill_summary or "No created skill summary available.",
        created_skill_name=created_skill_name or "unknown",
        workflow_excerpt=_load_stage_workflow_excerpt(policy.name),
        graph_db_instruction=load_prompt(GRAPH_DB_INSTRUCTION),
        execution_reminder=execution_reminder,
    )


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
    next_call_id: int = 0
    workflow_stage: str = "idle"
    last_assistant_text: str = ""
    active_turn_stage: str = "discover_existing_skill"
    user_goal: str = ""
    reference_summary: str = ""
    no_references: bool = False
    schema_summary: str = ""
    structured_schema_handoff: str = ""
    plan_summary: str = ""
    created_skill_summary: str = ""
    created_skill_name: str = ""
    router_model_name: str = "skill_creator_chat"

    @property
    def output_path(self) -> Path:
        return (self.output_root / self.session_id).resolve()

    async def ask(self, query: str, *, clear_history: bool = False) -> dict[str, Any]:
        normalized = query.strip()
        self._maybe_capture_user_goal(normalized)
        if self.workflow_stage in CONFIRMATION_ROUTE_CHOICES:
            response = await self._handle_confirmation_turn(normalized, clear_history=clear_history)
            self.next_run_id += 1
            return response
        if self.workflow_stage == "awaiting_reference_answer":
            response = await self._handle_reference_answer_turn(normalized)
            self.next_run_id += 1
            return response

        policy = self.resolve_turn_policy(normalized)
        if self._should_short_circuit_stage(policy):
            response = self._build_short_circuit_response(policy)
        else:
            response = await self._run_stage(policy, normalized, clear_history=clear_history)
        self.last_assistant_text = extract_last_message_text(response)
        self.active_turn_stage = policy.name
        self._advance_workflow_stage(policy, self.last_assistant_text)
        if policy.name == "create_skill":
            self.created_skill_summary = _compact_text(self.last_assistant_text, limit=2200)
            extracted = _extract_created_skill_name(self.last_assistant_text)
            if extracted:
                self.created_skill_name = extracted
        self.next_run_id += 1
        return response

    def reset(self, *, session_id: str | None = None) -> None:
        self.session_id = session_id or _new_session_id()
        self.next_run_id = 0
        self.next_call_id = 0
        self.workflow_stage = "idle"
        self.last_assistant_text = ""
        self.active_turn_stage = "discover_existing_skill"
        self.user_goal = ""
        self.reference_summary = ""
        self.no_references = False
        self.schema_summary = ""
        self.structured_schema_handoff = ""
        self.plan_summary = ""
        self.created_skill_summary = ""
        self.created_skill_name = ""
        self.data_agent = self._build_turn_data_agent(self.resolve_turn_policy(""), "")

    def resolve_turn_policy(self, query: str) -> StagePolicy:
        if self.workflow_stage == "awaiting_reference_answer":
            return _inspect_schema_policy(graph_enabled=self.runtime.settings.graph_enabled)
        return _discover_existing_skill_policy(runtime=self.runtime)

    def preview_turn_ferry_config(self, query: str, *, policy: StagePolicy | None = None) -> dict[str, Any]:
        policy = policy or self.resolve_turn_policy(query)
        return self._build_turn_ferry_config(policy)

    def _advance_workflow_stage(self, policy: StagePolicy, assistant_text: str) -> None:
        if policy.name == "ask_references":
            self.workflow_stage = "awaiting_reference_answer"
            return
        if policy.name == "inspect_schema":
            self.workflow_stage = "awaiting_plan_approval"
            return
        if policy.name == "propose_plan":
            self.workflow_stage = "awaiting_plan_approval"
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

    async def _handle_confirmation_turn(self, query: str, *, clear_history: bool) -> dict[str, Any]:
        decision = await self._route_confirmation_stage(query)

        if decision == "ask_references":
            response = self._build_short_circuit_response(_ask_references_policy())
            self.last_assistant_text = extract_last_message_text(response)
            self.active_turn_stage = "ask_references"
            self.workflow_stage = "awaiting_reference_answer"
            return response

        if decision == "create_skill":
            return await self._handle_create_skill_turn(query)

        if decision == "execute_skill":
            policy = _execute_skill_policy()
            response = await self._run_stage(policy, query, clear_history=clear_history)
            self.last_assistant_text = extract_last_message_text(response)
            self.active_turn_stage = policy.name
            self.workflow_stage = "idle"
            return response

        if decision == "idle":
            if self.workflow_stage == "awaiting_execute_confirmation":
                text = "好的，当前先不执行这个技能。后续如果需要运行它，请直接告诉我。"
            else:
                text = "好的，当前先不继续这个创建流程了。如果之后需要继续创建技能，请直接告诉我。"
            response = _text_response(text)
            self.last_assistant_text = text
            self.active_turn_stage = "discover_existing_skill"
            self.workflow_stage = "idle"
            return response

        response = _text_response(_clarify_message_for_workflow_stage(self.workflow_stage))
        self.last_assistant_text = extract_last_message_text(response)
        return response

    async def _route_confirmation_stage(self, query: str) -> str:
        stage_name = self.workflow_stage
        allowed_choices = CONFIRMATION_ROUTE_CHOICES.get(stage_name)
        if not allowed_choices:
            raise ValueError(f"Unsupported confirmation stage: {stage_name}")

        llm = llm_manager.get_llm(self.router_model_name)
        if llm is None:
            raise RuntimeError(f"Router LLM not found: {self.router_model_name}")

        prompt = load_prompt(
            STAGE_ROUTER,
            current_workflow_stage=stage_name,
            allowed_next_stages=_format_stage_router_choices(stage_name),
            user_reply=query,
        )
        response = await llm.ainvoke(
            [
                {"role": "system", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed = _parse_router_json(response.content)
        next_stage = str(parsed.get("next_stage", "")).strip()
        if next_stage not in allowed_choices:
            return stage_name
        return next_stage

    async def _handle_reference_answer_turn(self, query: str) -> dict[str, Any]:
        self.reference_summary = _compact_text(query, limit=1000)
        self.no_references = _is_negative_reference_reply(query)

        if self.runtime.settings.graph_enabled:
            schema_response = await self._run_stage(
                _inspect_schema_policy(graph_enabled=True),
                _internal_stage_query("inspect_schema"),
                clear_history=True,
            )
            self.schema_summary = _compact_text(extract_last_message_text(schema_response), limit=2200)
            self.structured_schema_handoff = self._build_structured_schema_handoff()
        else:
            self.schema_summary = "Graph access is disabled. Rely only on the user-provided requirements."
            self.structured_schema_handoff = "Structured schema handoff unavailable because graph access is disabled."

        plan_response = await self._run_stage(
            _propose_plan_policy(),
            _internal_stage_query("propose_plan"),
            clear_history=True,
        )
        self.last_assistant_text = extract_last_message_text(plan_response)
        self.plan_summary = _compact_text(self.last_assistant_text, limit=2600)
        self.active_turn_stage = "propose_plan"
        self.workflow_stage = "awaiting_plan_approval"
        return plan_response

    async def _handle_create_skill_turn(self, query: str) -> dict[str, Any]:
        skill_name = _extract_planned_skill_slug(self.plan_summary) or _slugify_text(self.user_goal)
        if not skill_name:
            skill_name = "generated-skill"
        description = _build_scaffold_description(self.plan_summary, self.user_goal)

        scaffold_result = self.runtime.create_skill_scaffold(skill_name, description)
        self.created_skill_name = skill_name

        await self._run_stage(
            _write_skill_doc_policy(),
            _internal_stage_query("write_skill_doc"),
            clear_history=True,
        )
        await self._run_stage(
            _write_skill_script_policy(),
            _internal_stage_query("write_skill_script"),
            clear_history=True,
        )
        self.runtime.reload_skill(skill_name)

        skill_dir = scaffold_result.get("skill_dir", str((self.runtime.settings.skills_root / skill_name).resolve()))
        skill_md = scaffold_result.get("skill_md_path", str((self.runtime.settings.skills_root / skill_name / "SKILL.md").resolve()))
        scripts_dir = scaffold_result.get("scripts_dir", str((self.runtime.settings.skills_root / skill_name / "scripts").resolve()))
        summary = (
            f"已创建技能 `{skill_name}`。\n\n"
            f"- 目录: {skill_dir}\n"
            f"- 文档: {skill_md}\n"
            f"- 脚本目录: {scripts_dir}\n\n"
            "是否立即执行这个新技能来查询风险用户？"
        )
        self.created_skill_summary = summary
        self.last_assistant_text = summary
        self.active_turn_stage = "create_skill"
        self.workflow_stage = "awaiting_execute_confirmation"
        return _text_response(summary)

    async def _run_stage(
        self,
        policy: StagePolicy,
        query: str,
        *,
        clear_history: bool,
    ) -> dict[str, Any]:
        self.data_agent = self._build_turn_data_agent(policy, query)
        initial_state = {
            "user_id": self.user_id,
            "run_id": 0,
            "sub_id": 0,
            "complete": False,
            "messages": [],
        }
        stage_session_id = self._stage_session_id(policy.name)
        stage_output_path = self._stage_output_path(policy.name)
        response = await self.data_agent.chat(
            query,
            session_id=stage_session_id,
            clear_history=True if clear_history else True,
            output_path=stage_output_path,
            initial_state=initial_state,
        )
        self.next_call_id += 1
        return response

    def _build_turn_data_agent(self, policy: StagePolicy, query: str) -> DataAgent:
        rendered_path = self.ferry_config_path
        _reset_ferry_singletons()
        materialize_ferry_config(
            self.source_config,
            runtime=self.runtime,
            output_path=rendered_path,
            system_instructions=self._build_stage_system_prompt(policy, query),
            system_constraints=policy.constraints,
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
            system_instructions=self._build_stage_system_prompt(policy, ""),
            system_constraints=policy.constraints,
            allowed_local_tool_names=policy.allowed_tool_names,
        )

    def _build_stage_system_prompt(self, policy: StagePolicy, query: str) -> str:
        return _render_stage_system_prompt(
            policy=policy,
            runtime=self.runtime,
            query=query,
            user_goal=self.user_goal,
            reference_summary=self.reference_summary,
            schema_summary=self.schema_summary,
            structured_schema_handoff=self.structured_schema_handoff,
            plan_summary=self.plan_summary,
            created_skill_summary=self.created_skill_summary,
            created_skill_name=self.created_skill_name,
        )

    def _build_structured_schema_handoff(self) -> str:
        if not self.runtime.settings.graph_enabled:
            return "Graph access is disabled."

        entities = self._extract_relevant_entities()
        if not entities:
            return "No relevant graph entities were identified from the schema summary."

        handoff_lines = ["STRUCTURED SCHEMA HANDOFF:"]
        useful_filters = _extract_schema_line(self.schema_summary, "useful filters")
        if useful_filters:
            handoff_lines.append(f"- useful filters: {useful_filters}")
        handoff_lines.append(
            "- flat result shape: when GraphConnector.property_filter(..., get_all_properties=True) is used, "
            "each returned item is already a flat property dict."
        )

        for entity_name in entities[:3]:
            try:
                schema = self.runtime.graph_get_entity_schema(entity_name)
                examples = self.runtime.graph_query_examples(entity_name, limit=1)
            except Exception as exc:
                handoff_lines.append(f"- entity: {entity_name} (schema unavailable: {exc})")
                continue

            sample_properties = schema.get("sample_properties", {}) if isinstance(schema, dict) else {}
            if not isinstance(sample_properties, dict):
                sample_properties = {}
            field_names = sorted(sample_properties.keys())
            key_fields = field_names[:8]
            handoff_lines.append(f"- entity: {entity_name}")
            handoff_lines.append(f"  fields: {', '.join(key_fields) if key_fields else 'none'}")

            sample_uuid = ""
            if examples and isinstance(examples[0], dict):
                sample_uuid = str(examples[0].get("uuid", ""))
            if sample_uuid:
                handoff_lines.append(f"  sample uuid: {sample_uuid}")

            example_fields = self._select_example_fields(sample_properties)
            if example_fields:
                handoff_lines.append("  sample values:")
                for field_name, field_value in example_fields.items():
                    handoff_lines.append(f"    {field_name}: {_format_example_value(field_value)}")

        return "\n".join(handoff_lines)

    def _extract_relevant_entities(self) -> list[str]:
        try:
            available_entities = self.runtime.graph_get_object_types()
        except Exception:
            available_entities = []

        combined_text = "\n".join(
            part for part in [self.user_goal, self.reference_summary, self.schema_summary, self.plan_summary] if part
        )
        matches: list[str] = []
        for entity_name in available_entities:
            if re.search(rf"\b{re.escape(entity_name)}\b", combined_text):
                matches.append(entity_name)

        if matches:
            return matches

        if any(token in combined_text for token in ["用户", "客户", "risk", "风险"]):
            if "Person" in available_entities:
                return ["Person"]

        return available_entities[:1]

    @staticmethod
    def _select_example_fields(sample_properties: dict[str, Any]) -> dict[str, Any]:
        preferred_fields = [
            "name",
            "party_id",
            "customer_description",
            "balance",
            "organ_code",
            "uuid",
            "id",
        ]
        selected: dict[str, Any] = {}
        for field_name in preferred_fields:
            if field_name in sample_properties:
                selected[field_name] = sample_properties[field_name]
        return selected

    def _should_short_circuit_stage(self, policy: StagePolicy) -> bool:
        return (
            policy.name == "ask_references"
            or (
                policy.name == "discover_existing_skill"
                and not policy.allowed_tool_names
                and not self.runtime.list_skills()
            )
        )

    def _build_short_circuit_response(self, policy: StagePolicy) -> dict[str, Any]:
        if policy.name == "ask_references":
            text = (
                "可以，我会为这个需求创建一个新的技能。\n\n"
                "在继续之前，请告诉我是否有可参考的资料，例如业务规则、数据库字段说明、接口文档、样例查询或现成流程。"
                "如果没有，请直接回复“没有”。"
            )
        else:
            goal = self.user_goal or "这个需求"
            text = (
                f"当前没有可用的技能可以直接处理“{goal}”。\n\n"
                "您是否希望我为您创建一个新的技能来处理这个需求？"
            )
        return _text_response(text)

    def _stage_session_id(self, stage_name: str) -> str:
        return f"{self.session_id}-call{self.next_call_id:03d}-{stage_name}"

    def _stage_output_path(self, stage_name: str) -> Path:
        return (self.output_path / f"{self.next_call_id:03d}_{stage_name}").resolve()

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
        system_instructions=_render_stage_system_prompt(
            policy=initial_policy,
            runtime=runtime,
            query="",
            user_goal="",
            reference_summary="",
            schema_summary="",
            structured_schema_handoff="",
            plan_summary="",
            created_skill_summary="",
            created_skill_name="",
        ),
        system_constraints=initial_policy.constraints,
        allowed_local_tool_names=initial_policy.allowed_tool_names,
    )
    data_agent = DataAgent.from_config(rendered_path)
    router_model_name = _resolve_router_model_name(source_config)
    return DataAgentSession(
        data_agent=data_agent,
        runtime=runtime,
        source_config=source_config,
        ferry_config_path=rendered_path,
        user_id=user_id,
        session_id=resolved_session_id,
        output_root=resolved_output_root,
        active_turn_stage=initial_policy.name,
        router_model_name=router_model_name,
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


def _reset_ferry_singletons() -> None:
    registry = getattr(tool_manager, "tool_registry", None)
    if hasattr(tool_manager, "clear_internal_state"):
        tool_manager.clear_internal_state()
    if hasattr(tool_manager, "_skills"):
        tool_manager._skills.clear()
    if registry is not None:
        if hasattr(registry, "_tools"):
            registry._tools = {}
        if hasattr(registry, "_functions"):
            registry._functions = {}
    tool_manager.reset_instance()
    llm_manager.llm_cache.clear()


def _discover_existing_skill_policy(*, runtime: SkillCreatorRuntime) -> StagePolicy:
    available_skills = runtime.list_skills()
    if not available_skills:
        return StagePolicy(
            name="discover_existing_skill",
            allowed_tool_names=set(),
            constraints=(
                "No tools are available in this stage. Do not invent tools, file listing, or pseudo tool calls. "
                "If no skill metadata exists, ask directly whether a new skill should be created."
            ),
        )

    return StagePolicy(
        name="discover_existing_skill",
        allowed_tool_names=set(SKILL_EXECUTION_TOOL_NAMES),
        constraints=(
            "Use only the registered skill inspection and execution tools in this stage. "
            "If a matching skill can directly satisfy the user goal, execute it instead of only describing it. "
            "Do not invent tool calls or inspect the filesystem outside those tools."
        ),
    )


def _ask_references_policy() -> StagePolicy:
    return StagePolicy(
        name="ask_references",
        allowed_tool_names=set(),
        constraints="No tools are available in this stage. Ask only the documentation question.",
    )


def _inspect_schema_policy(*, graph_enabled: bool) -> StagePolicy:
    allowed_tool_names = set(GRAPH_TOOL_NAMES) if graph_enabled else set()
    return StagePolicy(
        name="inspect_schema",
        allowed_tool_names=allowed_tool_names,
        constraints=(
            "Use only the registered graph tools in this stage. "
            "Return only a concise schema handoff summary and do not address the user directly."
        ),
    )


def _propose_plan_policy() -> StagePolicy:
    return StagePolicy(
        name="propose_plan",
        allowed_tool_names=set(),
        constraints="No tools are available in this stage. Write only the user-facing execution plan and approval question.",
    )


def _create_skill_policy() -> StagePolicy:
    allowed_tool_names = {
        *FILE_TOOL_NAMES,
        *SKILL_READ_TOOL_NAMES,
        *SKILL_CREATION_TOOL_NAMES,
    }
    return StagePolicy(
        name="create_skill",
        allowed_tool_names=allowed_tool_names,
        constraints=(
            "Use only the registered skill creation and file tools in this stage. "
            "Do not ask for approval again. Create the skill package now."
        ),
    )


def _write_skill_doc_policy() -> StagePolicy:
    return StagePolicy(
        name="write_skill_doc",
        allowed_tool_names={"read_file", "write_file", "apply_patch"},
        constraints=(
            "Only update the scaffolded SKILL.md in this stage. "
            "Do not create scripts or call reload_skill."
        ),
    )


def _write_skill_script_policy() -> StagePolicy:
    return StagePolicy(
        name="write_skill_script",
        allowed_tool_names={"read_file", "write_file", "apply_patch"},
        constraints=(
            "Only create or update execution scripts in this stage. "
            "Do not call reload_skill or ask the user anything."
        ),
    )


def _execute_skill_policy() -> StagePolicy:
    allowed_tool_names = set(SKILL_EXECUTION_TOOL_NAMES)
    return StagePolicy(
        name="execute_skill",
        allowed_tool_names=allowed_tool_names,
        constraints="Use only the registered skill inspection and execution tools in this stage.",
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
        "批准",
        "批准吧",
        "批准创建",
        "同意",
        "同意创建",
        "通过",
        "approve",
        "approved",
        "proceed",
        "continue",
        "开始吧",
        "执行吧",
        "运行吧",
    }
    return normalized in positives or any(
        token in normalized
        for token in [
            "创建吧",
            "创建",
            "可以",
            "确认",
            "批准",
            "同意",
            "通过",
            "approve",
            "approved",
            "proceed",
            "continue",
            "执行吧",
            "运行吧",
        ]
    )


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
        "是否需要创建一个新技能",
        "是否需要创建新的技能",
        "是否应该创建一个新技能",
        "请问是否需要创建一个新技能",
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


def _is_negative_reference_reply(text: str) -> bool:
    normalized = text.strip().lower()
    negatives = {
        "没有",
        "没有文档",
        "没有文档支撑",
        "没有参考文档",
        "没有可用的参考文档",
        "无",
        "none",
        "no",
    }
    return normalized in negatives or "没有" in normalized


def _parse_router_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(0))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return {}


def _clarify_message_for_workflow_stage(stage_name: str) -> str:
    if stage_name == "awaiting_create_confirmation":
        return "我还不能确定您的意思。请明确告诉我，是要继续创建这个技能，还是先不创建。"
    if stage_name == "awaiting_plan_approval":
        return "我还不能确定您的意思。请明确告诉我，是批准当前方案开始创建，还是希望我继续调整方案。"
    if stage_name == "awaiting_execute_confirmation":
        return "我还不能确定您的意思。请明确告诉我，是否要立即执行这个技能。"
    return "我还不能确定您的意思，请再明确说明一下。"


def _compact_text(text: str, *, limit: int) -> str:
    normalized = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _extract_schema_line(text: str, label: str) -> str:
    pattern = re.compile(rf"-\s*{re.escape(label)}:\s*(.+)")
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            return match.group(1).strip()
    return ""


def _format_example_value(value: Any) -> str:
    text = str(value)
    if len(text) <= 160:
        return text
    return text[:157].rstrip() + "..."


def _internal_stage_query(stage_name: str) -> str:
    if stage_name == "inspect_schema":
        return "Inspect the minimum schema and data needed for the goal, then return only the requested schema handoff summary."
    if stage_name == "propose_plan":
        return "Use the available handoff summaries to produce the user-facing execution plan and ask for approval."
    if stage_name == "write_skill_doc":
        return "Update only the scaffolded SKILL.md so it fully documents the approved skill."
    if stage_name == "write_skill_script":
        return "Create or update only the execution script files so the approved skill is runnable."
    return ""


def _extract_created_skill_name(text: str) -> str | None:
    markers = [
        "技能名称：",
        "技能名称:",
        "skill name:",
        "skill name：",
    ]
    for line in text.splitlines():
        stripped = line.strip()
        for marker in markers:
            if stripped.lower().startswith(marker.lower()):
                value = stripped.split(marker, 1)[1].strip(" `")
                if value:
                    return value
    return None


def _extract_planned_skill_slug(text: str) -> str | None:
    slug_pattern = re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b")
    for match in slug_pattern.finditer(text):
        return match.group(0)
    extracted = _extract_created_skill_name(text)
    if extracted:
        slug = _slugify_text(extracted)
        if slug:
            return slug
    return None


def _slugify_text(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower())
    value = value.strip("-")
    value = re.sub(r"-{2,}", "-", value)
    return value[:80].strip("-")


def _build_scaffold_description(plan_summary: str, user_goal: str) -> str:
    source = plan_summary or user_goal or "Generated skill"
    first_line = source.splitlines()[0].strip()
    return _compact_text(first_line, limit=120)
