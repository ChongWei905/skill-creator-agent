from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from skill_creator_agent.runtime import SkillCreatorRuntime

DEFAULT_CHAT_MAX_TOKENS = 4096

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

DEFAULT_GRAPH_TOOLS: list[dict[str, Any]] = [
    {
        "name": "graph_get_object_types",
        "function": "graph_get_object_types",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_get_object_relations",
        "function": "graph_get_object_relations",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_get_entity_schema",
        "function": "graph_get_entity_schema",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_query_examples",
        "function": "graph_query_examples",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_property_filter",
        "function": "graph_property_filter",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_property_info",
        "function": "graph_property_info",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_hop_search",
        "function": "graph_hop_search",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_count_search",
        "function": "graph_count_search",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_aggregate_search",
        "function": "graph_aggregate_search",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_sorted_search",
        "function": "graph_sorted_search",
        "module": "skill_creator_agent.ferry_tools",
    },
    {
        "name": "graph_pattern_search",
        "function": "graph_pattern_search",
        "module": "skill_creator_agent.ferry_tools",
    },
]


def build_ferry_config(
    config: Mapping[str, Any] | None,
    *,
    runtime: SkillCreatorRuntime,
    stage_instructions: str | None = None,
    system_instructions: str | None = None,
    system_constraints: str | None = None,
    allowed_local_tool_names: set[str] | list[str] | None = None,
    model_params_overrides: Mapping[str, Any] | None = None,
    include_skills: bool = True,
) -> dict[str, Any]:
    user_config = dict(config or {})
    base_config = _build_default_ferry_config(
        runtime=runtime,
        config=user_config,
        stage_instructions=stage_instructions,
        system_instructions=system_instructions,
        system_constraints=system_constraints,
        model_params_overrides=model_params_overrides,
        include_skills=include_skills,
    )
    merged = _deep_merge(base_config, user_config)
    return _normalize_ferry_config(
        merged,
        runtime=runtime,
        allowed_local_tool_names=allowed_local_tool_names,
        include_skills=include_skills,
    )


def materialize_ferry_config(
    config: Mapping[str, Any] | None,
    *,
    runtime: SkillCreatorRuntime,
    output_path: str | Path,
    stage_instructions: str | None = None,
    system_instructions: str | None = None,
    system_constraints: str | None = None,
    allowed_local_tool_names: set[str] | list[str] | None = None,
    model_params_overrides: Mapping[str, Any] | None = None,
    include_skills: bool = True,
) -> Path:
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = build_ferry_config(
        config,
        runtime=runtime,
        stage_instructions=stage_instructions,
        system_instructions=system_instructions,
        system_constraints=system_constraints,
        allowed_local_tool_names=allowed_local_tool_names,
        model_params_overrides=model_params_overrides,
        include_skills=include_skills,
    )
    target.write_text(
        yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target


def _build_default_ferry_config(
    *,
    runtime: SkillCreatorRuntime,
    config: Mapping[str, Any] | None,
    stage_instructions: str | None = None,
    system_instructions: str | None = None,
    system_constraints: str | None = None,
    model_params_overrides: Mapping[str, Any] | None = None,
    include_skills: bool = True,
) -> dict[str, Any]:
    chat_model_name = _resolve_chat_model_name(config)
    model_params = {
        "model": "deepseek-chat",
        "max_tokens": DEFAULT_CHAT_MAX_TOKENS,
    }
    if model_params_overrides:
        model_params.update(dict(model_params_overrides))
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
                "params": model_params,
            }
        },
        "SCENARIO": {
            "chat": {
                "instructions": _compose_instructions(
                    runtime,
                    stage_instructions=stage_instructions,
                    system_instructions=system_instructions,
                ),
                "constraints": system_constraints
                or (
                    "Use the dedicated skill runtime tools to inspect and execute existing skills. "
                    "When no matching skill exists, preserve the original workflow gates exactly: "
                    "after the user agrees to create a skill, your next turn must only ask for reference "
                    "documentation or an explicit confirmation that none is available. "
                    "Do not inspect graph schema, create files, call `create_skill_scaffold`, `write_file`, "
                    "`apply_patch`, or `reload_skill` until the user has answered the documentation question. "
                    "After that, inspect only the required graph/schema information, present a natural-language "
                    "execution plan, and wait for explicit approval. "
                    "Only after that approval may you call `create_skill_scaffold` to create a valid directory "
                    "layout, then use `write_file` or `apply_patch` to refine SKILL.md and script files, and "
                    "finally call `reload_skill` before asking whether to execute the new skill. "
                    "Never write mock data, placeholder scripts, or simulated query results into a newly created skill."
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
                *_build_runtime_tools(runtime),
            ],
            "skills": runtime.build_ferry_skill_registry() if include_skills else [],
        },
        "SKILL_CREATOR": {
            "skills_root": str(runtime.settings.skills_root),
            "graph_enabled": runtime.settings.graph_enabled,
            "graph_base_url": runtime.settings.graph_base_url,
            "graph_timeout": runtime.settings.graph_timeout,
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


def _normalize_ferry_config(
    config: dict[str, Any],
    *,
    runtime: SkillCreatorRuntime,
    allowed_local_tool_names: set[str] | list[str] | None = None,
    include_skills: bool = True,
) -> dict[str, Any]:
    normalized = dict(config)

    skill_creator_cfg = dict(normalized.get("SKILL_CREATOR", {}))
    skill_creator_cfg["skills_root"] = str(runtime.settings.skills_root)
    skill_creator_cfg["graph_enabled"] = runtime.settings.graph_enabled
    skill_creator_cfg["graph_base_url"] = runtime.settings.graph_base_url
    skill_creator_cfg["graph_timeout"] = runtime.settings.graph_timeout
    normalized["SKILL_CREATOR"] = skill_creator_cfg

    workspace_cfg = dict(normalized.get("WORKSPACE", {}))
    allowed_paths = [str(path) for path in workspace_cfg.get("allowed_paths", [])]
    workspace_cfg["allowed_paths"] = _dedupe_strings([str(runtime.settings.skills_root), *allowed_paths])
    normalized["WORKSPACE"] = workspace_cfg

    tools_cfg = dict(normalized.get("TOOLS", {}))
    tools_cfg["local_functions"] = _dedupe_local_functions(tools_cfg.get("local_functions", []))
    tools_cfg["local_functions"] = _filter_local_functions(
        tools_cfg["local_functions"],
        allowed_local_tool_names,
    )
    tools_cfg["skills"] = runtime.build_ferry_skill_registry() if include_skills else []
    normalized["TOOLS"] = tools_cfg

    return normalized


def _compose_instructions(
    runtime: SkillCreatorRuntime,
    *,
    stage_instructions: str | None,
    system_instructions: str | None = None,
) -> str:
    if system_instructions:
        return system_instructions.strip()
    base_instructions = runtime.build_system_prompt().rstrip()
    if not stage_instructions:
        return base_instructions
    return (
        f"{base_instructions}\n\n"
        "[CURRENT WORKFLOW STAGE]\n"
        f"{stage_instructions.strip()}"
    )


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


def _filter_local_functions(
    tools: list[dict[str, Any]],
    allowed_local_tool_names: set[str] | list[str] | None,
) -> list[dict[str, Any]]:
    if allowed_local_tool_names is None:
        return tools
    allowed = {str(name) for name in allowed_local_tool_names}
    return [tool for tool in tools if str(tool.get("name", "")) in allowed]


def _build_runtime_tools(runtime: SkillCreatorRuntime) -> list[dict[str, Any]]:
    tools = list(DEFAULT_RUNTIME_TOOLS)
    if runtime.settings.graph_enabled:
        tools.extend(DEFAULT_GRAPH_TOOLS)
    return tools


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
