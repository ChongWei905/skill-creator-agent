from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from skill_creator_agent.runtime import SkillCreatorRuntime

DEFAULT_FERRY_FILE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "bash",
        "function": "bash",
        "module": "ferry.actions.tools.local_tool.tools",
    },
    {
        "name": "read_file",
        "function": "read_file",
        "module": "ferry.actions.tools.local_tool.tools",
    },
    {
        "name": "write_file",
        "function": "write_file",
        "module": "ferry.actions.tools.local_tool.tools",
    },
    {
        "name": "apply_patch",
        "function": "apply_patch",
        "module": "ferry.actions.tools.local_tool.tools",
    },
]

DEFAULT_RUNTIME_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_available_skills",
        "function": "list_available_skills",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "read_skill_content",
        "function": "read_skill_content",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "list_skill_scripts",
        "function": "list_skill_scripts",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "read_script_source",
        "function": "read_script_source",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "execute_skill_script",
        "function": "execute_skill_script",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "reload_skill",
        "function": "reload_skill",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "create_skill_scaffold",
        "function": "create_skill_scaffold",
        "module": "skill_creator_agent.ferry_tools",
    },
]


def build_ferry_config(
    config: Mapping[str, Any] | None,
    *,
    runtime: SkillCreatorRuntime,
) -> dict[str, Any]:
    user_config = dict(config or {})
    base_config = _build_default_ferry_config(runtime=runtime, config=user_config)
    merged = _deep_merge(base_config, user_config)
    return _normalize_ferry_config(merged, runtime=runtime)


def materialize_ferry_config(
    config: Mapping[str, Any] | None,
    *,
    runtime: SkillCreatorRuntime,
    output_path: str | Path,
) -> Path:
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = build_ferry_config(config, runtime=runtime)
    target.write_text(
        yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target


def _build_default_ferry_config(*, runtime: SkillCreatorRuntime, config: Mapping[str, Any] | None) -> dict[str, Any]:
    chat_model_name = _resolve_chat_model_name(config)
    return {
        "AGENT_CONFIG": {
            "name": "skill_creator",
            "backend": "langgraph",
            "type": "react",
            "agent_type": "skill_creator",
            "debug": True,
        },
        "WORKSPACE": {
            "allowed_paths": [str(runtime.settings.skills_root)],
        },
        "MODEL": {
            chat_model_name: {
                "provider": "openai",
                "model_type": "chat",
                "params": {
                    "model": "deepseek-chat",
                },
            }
        },
        "SCENARIO": {
            "chat": {
                "instructions": runtime.build_system_prompt(),
                "constraints": (
                    "Use the dedicated skill runtime tools to inspect and execute existing skills. "
                    "When you need to create a new skill, first call `create_skill_scaffold` to create a valid "
                    "directory layout, then use `write_file` or `apply_patch` to refine SKILL.md and script files, "
                    "and finally call `reload_skill` before executing the new skill."
                ),
            }
        },
        "PRE_WORKFLOW": [],
        "ACTOR_LOOP": [
            {
                "node": "planner_flex",
                "module": "ferry.core.flex.nodes.constrained_actor.ConstrainedActor",
                "chat_model": {"name": chat_model_name},
            },
            {
                "node": "executor",
                "module": "ferry.core.flex.nodes.executor.Executor",
            },
        ],
        "POST_WORKFLOW": [],
        "TOOLS": {
            "local_functions": [
                *DEFAULT_FERRY_FILE_TOOLS,
                *DEFAULT_RUNTIME_TOOLS,
            ],
            "skills": runtime.build_ferry_skill_registry(),
        },
        "SKILL_CREATOR": {
            "skills_root": str(runtime.settings.skills_root),
            "graph_enabled": runtime.settings.graph_enabled,
        },
    }


def _resolve_chat_model_name(config: Mapping[str, Any] | None) -> str:
    model_cfg = (config or {}).get("MODEL")
    if isinstance(model_cfg, Mapping):
        for model_name in model_cfg:
            return str(model_name)
    return "skill_creator_chat"


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, Mapping):
        merged = dict(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    if isinstance(base, list) and isinstance(override, list):
        return [*base, *override]
    return override


def _normalize_ferry_config(config: dict[str, Any], *, runtime: SkillCreatorRuntime) -> dict[str, Any]:
    normalized = dict(config)

    skill_creator_cfg = dict(normalized.get("SKILL_CREATOR", {}))
    skill_creator_cfg["skills_root"] = str(runtime.settings.skills_root)
    skill_creator_cfg["graph_enabled"] = runtime.settings.graph_enabled
    normalized["SKILL_CREATOR"] = skill_creator_cfg

    workspace_cfg = dict(normalized.get("WORKSPACE", {}))
    allowed_paths = [str(path) for path in workspace_cfg.get("allowed_paths", [])]
    workspace_cfg["allowed_paths"] = _dedupe_strings([str(runtime.settings.skills_root), *allowed_paths])
    normalized["WORKSPACE"] = workspace_cfg

    tools_cfg = dict(normalized.get("TOOLS", {}))
    tools_cfg["local_functions"] = _dedupe_local_functions(tools_cfg.get("local_functions", []))
    tools_cfg["skills"] = runtime.build_ferry_skill_registry()
    normalized["TOOLS"] = tools_cfg

    return normalized


def _dedupe_local_functions(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        key = (str(tool.get("name") or ""), str(tool.get("function") or tool.get("name") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tool)
    return deduped


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
