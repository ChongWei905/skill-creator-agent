from __future__ import annotations

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

PLAN_GRAPH_TOOL_NAMES = {
    "graph_get_object_types",
    "graph_get_object_relations",
    "graph_get_entity_schema",
    "graph_query_examples",
    "graph_property_filter",
}

FILE_TOOL_NAMES = {
    "bash",
    "read_file",
    "write_file",
    "apply_patch",
}

BUILD_FILE_TOOL_NAMES = {
    "read_file",
    "write_file",
    "apply_patch",
}

SKILL_CREATION_TOOL_NAMES = {
    "create_skill_scaffold",
    "reload_skill",
}
