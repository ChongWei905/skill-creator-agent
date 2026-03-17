from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.ferry_config import materialize_ferry_config
from skill_creator_agent.ferry_tools import configure_runtime_tools
from skill_creator_agent.paths import package_path, project_path
from skill_creator_agent.runtime import SkillCreatorRuntime

DEFAULT_VERIFICATION_CONFIG = package_path("skill_creator_debug.yaml")
DEFAULT_VERIFICATION_OUTPUT_ROOT = project_path(".tmp", "data_agent_multiturn")
DEFAULT_MATERIALIZED_CONFIG_ROOT = project_path(".tmp", "generated_configs")


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

    @property
    def output_path(self) -> Path:
        return (self.output_root / self.session_id).resolve()

    async def ask(self, query: str, *, clear_history: bool = False) -> dict[str, Any]:
        effective_query = self._prepare_query(query)
        initial_state = {
            "user_id": self.user_id,
            "run_id": self.next_run_id,
            "sub_id": 0,
            "complete": False,
            "messages": [],
        }
        response = await self.data_agent.chat(
            effective_query,
            session_id=self.session_id,
            clear_history=clear_history,
            output_path=self.output_path,
            initial_state=initial_state,
        )
        self.last_assistant_text = extract_last_message_text(response)
        self._update_workflow_stage(self.last_assistant_text)
        self.next_run_id += 1
        return response

    def reset(self, *, session_id: str | None = None) -> None:
        self.session_id = session_id or _new_session_id()
        self.next_run_id = 0
        self.workflow_stage = "idle"
        self.last_assistant_text = ""

    def _prepare_query(self, query: str) -> str:
        normalized = query.strip()
        if self.workflow_stage == "awaiting_create_confirmation" and _is_affirmative(normalized):
            return (
                "Workflow gate: the user has just confirmed that a new skill should be created. "
                "This turn must execute only Step 2 of the original workflow. "
                "Ask whether the user has reference documentation, schemas, examples, sample commands, "
                "or business rules that should guide the skill. "
                "Do not call any tools. Do not inspect graph data. Do not create or modify files. "
                f"User response: {normalized}"
            )
        if self.workflow_stage == "awaiting_reference_answer":
            return (
                "Workflow gate: the user has now answered the documentation question. "
                "You may inspect only the required graph/schema information, then present a natural-language "
                "execution flow plan and ask for explicit approval. "
                "Do not create or modify files in this turn. "
                f"User response: {normalized}"
            )
        if self.workflow_stage == "awaiting_plan_approval" and _is_affirmative(normalized):
            return (
                "Workflow gate: the user has explicitly approved the execution flow. "
                "You may now create the skill package. "
                "Use real graph-backed logic where applicable. Never write mock data, simulated query results, "
                "or placeholder scripts into the skill. "
                f"User response: {normalized}"
            )
        return normalized

    def _update_workflow_stage(self, assistant_text: str) -> None:
        normalized = assistant_text.lower()
        if _looks_like_create_confirmation(assistant_text):
            self.workflow_stage = "awaiting_create_confirmation"
            return
        if _looks_like_reference_request(assistant_text):
            self.workflow_stage = "awaiting_reference_answer"
            return
        if _looks_like_plan_approval_request(assistant_text):
            self.workflow_stage = "awaiting_plan_approval"
            return
        if "skill" in normalized and ("created" in normalized or "创建" in assistant_text):
            self.workflow_stage = "idle"


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
    rendered_path = materialize_ferry_config(
        source_config,
        runtime=runtime,
        output_path=materialized_config_path,
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
    }
    return normalized in positives or any(token in normalized for token in ["创建吧", "创建", "可以", "确认", "好"])


def _looks_like_create_confirmation(text: str) -> bool:
    signals = [
        "是否希望我为您创建",
        "是否要创建一个新的 skill",
        "would you like me to create",
        "do you want me to create a new skill",
        "确认技能创建需求",
    ]
    return any(signal.lower() in text.lower() for signal in signals)


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
