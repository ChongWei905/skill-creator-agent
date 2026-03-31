from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from knowledge_skills.runtime import SkillCreatorRuntime
from knowledge_skills.ferry_integration.argument_normalizer import (
    normalize_bool,
    normalize_cli_arguments,
    normalize_int,
    normalize_mapping_argument,
    normalize_nested_list,
    normalize_string_list,
)

_ACTIVE_RUNTIME: SkillCreatorRuntime | None = None


def configure_runtime_tools(
    *,
    config: Mapping[str, Any] | None = None,
    runtime: SkillCreatorRuntime | None = None,
) -> SkillCreatorRuntime:
    """Bind local tool calls to a concrete runtime instance."""
    global _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = runtime or SkillCreatorRuntime.from_config(config)
    return _ACTIVE_RUNTIME


def reset_runtime_tools() -> None:
    """Clear the globally bound runtime used by Ferry local functions."""
    global _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = None


def get_runtime_tools() -> SkillCreatorRuntime:
    """Return the active runtime, creating one from config on first access."""
    global _ACTIVE_RUNTIME
    if _ACTIVE_RUNTIME is None:
        _ACTIVE_RUNTIME = SkillCreatorRuntime.from_config()
    return _ACTIVE_RUNTIME


def list_available_skills() -> list[dict[str, Any]]:
    """List the currently available skills and their executable scripts."""
    return get_runtime_tools().list_skills()


def read_skill_content(skill_name: str) -> str:
    """Read the full SKILL.md content for a named skill."""
    return get_runtime_tools().read_skill_content(skill_name)


def list_skill_scripts(skill_name: str) -> list[dict[str, Any]]:
    """List the scripts exposed by a named skill."""
    return get_runtime_tools().list_skill_scripts(skill_name)


def read_script_source(skill_name: str, script_name: str) -> str:
    """Read a skill script source file to inspect its implementation."""
    return get_runtime_tools().read_script_source(skill_name, script_name)


def execute_skill_script(
    skill_name: str,
    script_name: str,
    arguments: list[str] | str | None = None,
    cwd: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Execute a script from a skill and return exit code, stdout, and stderr.

    Pass `arguments` as a native JSON array such as `["--branch_name", "蛇口支行"]`.
    Do not pass a quoted JSON string like `'["--branch_name", "蛇口支行"]'`.
    """
    return get_runtime_tools().execute_skill_script(
        skill_name,
        script_name,
        args=normalize_cli_arguments(arguments),
        cwd=Path(cwd).expanduser().resolve() if cwd else None,
        timeout=normalize_int(timeout, field_name="timeout") or 300,
    )


def reload_skill(skill_name: str) -> dict[str, Any]:
    """Reload a skill from disk after creating or updating its files."""
    skill = get_runtime_tools().reload_skill(skill_name)
    return get_runtime_tools().skill_to_dict(skill)


def create_skill_scaffold(
    skill_name: str,
    description: str,
    body: str = "",
    script_files: dict[str, str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a valid skill directory with SKILL.md and optional starter scripts.

    Use this as the first creation step after the user has approved the workflow plan.
    Provide:
    - `skill_name`: a filesystem-safe slug such as `risk-customer-query`
    - `description`: one concise sentence describing what the skill does
    - `body`: optional initial SKILL.md body content, but prefer leaving this minimal
    - `script_files`: optional starter files, but prefer creating substantive files later with
      `write_file` or `apply_patch`

    Important:
    - The first scaffold call should usually contain only a slugified `skill_name` and description
    - Keep the scaffolded `SKILL.md` YAML frontmatter valid: `name` must stay equal to the
      directory slug, and you should not add a separate `slug` field
    - For graph-backed skills, generate Python scripts that use
      `from knowledge_skills.connectors import GraphConnector`
    - Read `GRAPH_DB_BASE_URL` and `GRAPH_DB_TIMEOUT` from the environment inside those scripts
    - Do not hardcode sqlite/local database paths or fallback demo datasets

    After this tool succeeds, continue refining the created files with `write_file` or
    `apply_patch`, then call `reload_skill` to register the finished skill from disk.
    """
    return get_runtime_tools().create_skill_scaffold(
        skill_name,
        description,
        body=body,
        script_files=script_files,
        overwrite=overwrite,
    )


def graph_get_object_types() -> list[str]:
    """Get all graph object types currently exposed by the graph service."""
    return get_runtime_tools().graph_get_object_types()


def graph_get_object_relations() -> list[str]:
    """Get all graph relations currently exposed by the graph service."""
    return get_runtime_tools().graph_get_object_relations()


def graph_get_entity_schema(entity_type: str) -> dict[str, Any]:
    """Get a sample schema for a graph entity type."""
    return get_runtime_tools().graph_get_entity_schema(entity_type)


def graph_query_examples(
    entity_type: str,
    limit: int = 5,
    filter_dict: dict[str, Any] | str | None = None,
) -> list[dict[str, Any]]:
    """Query sample graph instances for a given entity type."""
    return get_runtime_tools().graph_query_examples(
        entity_type,
        limit=normalize_int(limit, field_name="limit") or 5,
        filter_dict=normalize_mapping_argument(filter_dict, field_name="filter_dict"),
    )


def graph_property_filter(
    element_class: str,
    element_type: str = "NODE",
    filter_dict: dict[str, Any] | str | None = None,
    get_all_properties: bool | str = False,
) -> list[dict[str, Any]]:
    """Filter graph elements by property conditions.

    `filter_dict` must map property names to Cypher-style condition strings.
    Supported patterns are:
    - numeric/string equality: `\"= '0400000012'\"`
    - range comparisons: `\"> 0\"`, `\"< 100\"`, `\">= 10\"`, `\"<= 20\"`
    - string matching: `\"CONTAINS '深圳'\"`, `\"STARTS WITH '04'\"`, `\"ENDS WITH '30'\"`
    - OR is allowed within a single property: `\"CONTAINS '深圳' OR CONTAINS '罗湖'\"`

    Do not pass raw values like `\"深圳\"` or `\"是\"`.
    Do not put `AND` inside one expression; use separate properties in `filter_dict` instead.
    For string literals, include single quotes explicitly.
    Pass `filter_dict` as a native JSON object, not as a quoted JSON string.
    """
    return get_runtime_tools().graph_property_filter(
        element_class,
        element_type,
        normalize_mapping_argument(filter_dict, field_name="filter_dict"),
        get_all_properties=normalize_bool(get_all_properties, field_name="get_all_properties"),
    )


def graph_property_info(
    element_class: str,
    element_type: str = "NODE",
    element_uuid: str | None = None,
) -> dict[str, Any]:
    """Get full property information for a specific graph element."""
    return get_runtime_tools().graph_property_info(
        element_class,
        element_type,
        element_uuid,
    )


def graph_hop_search(
    uuid: str,
    hop_num: int | str,
    accurate_flag: bool | str = False,
) -> list[dict[str, Any]]:
    """Run a hop search from a starting graph node."""
    return get_runtime_tools().graph_hop_search(
        uuid,
        normalize_int(hop_num, field_name="hop_num") or 0,
        accurate_flag=normalize_bool(accurate_flag, field_name="accurate_flag"),
    )


def graph_count_search(
    element_class: str,
    element_type: str = "NODE",
    filter_dict: dict[str, Any] | str | None = None,
) -> int:
    """Count graph elements that satisfy a filter."""
    return get_runtime_tools().graph_count_search(
        element_class,
        element_type,
        normalize_mapping_argument(filter_dict, field_name="filter_dict"),
    )


def graph_aggregate_search(
    element_class: str,
    element_type: str = "NODE",
    target_property: str | None = None,
    agg_func: str | None = None,
    filter_dict: dict[str, Any] | str | None = None,
) -> Any:
    """Aggregate a graph property using COUNT/SUM/AVG/MIN/MAX."""
    return get_runtime_tools().graph_aggregate_search(
        element_class,
        element_type,
        target_property,
        agg_func,
        normalize_mapping_argument(filter_dict, field_name="filter_dict"),
    )


def graph_sorted_search(
    element_class: str,
    element_type: str = "NODE",
    filter_dict: dict[str, Any] | str | None = None,
    return_properties: list[str] | str | None = None,
    sort_by: str | None = None,
    ascending: bool | str = True,
    limit: int | str | None = None,
) -> list[dict[str, Any]]:
    """Return graph query results with server-side sorting."""
    return get_runtime_tools().graph_sorted_search(
        element_class,
        element_type,
        filter_dict=normalize_mapping_argument(filter_dict, field_name="filter_dict"),
        return_properties=normalize_string_list(return_properties, field_name="return_properties"),
        sort_by=sort_by,
        ascending=normalize_bool(ascending, field_name="ascending"),
        limit=normalize_int(limit, field_name="limit"),
    )


def graph_pattern_search(
    path_pattern: list[list[Any]] | str,
    return_vars: list[str] | str | None = None,
) -> list[dict[str, Any]]:
    """Run a pattern search against the graph service."""
    return get_runtime_tools().graph_pattern_search(
        normalize_nested_list(path_pattern, field_name="path_pattern"),
        return_vars=normalize_string_list(return_vars, field_name="return_vars"),
    )
