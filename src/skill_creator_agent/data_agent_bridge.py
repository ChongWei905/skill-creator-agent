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

    @property
    def output_path(self) -> Path:
        return (self.output_root / self.session_id).resolve()

    async def ask(self, query: str, *, clear_history: bool = False) -> dict[str, Any]:
        initial_state = {
            "user_id": self.user_id,
            "run_id": self.next_run_id,
            "sub_id": 0,
            "complete": False,
            "messages": [],
        }
        response = await self.data_agent.chat(
            query,
            session_id=self.session_id,
            clear_history=clear_history,
            output_path=self.output_path,
            initial_state=initial_state,
        )
        self.next_run_id += 1
        return response

    def reset(self, *, session_id: str | None = None) -> None:
        self.session_id = session_id or _new_session_id()
        self.next_run_id = 0


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
