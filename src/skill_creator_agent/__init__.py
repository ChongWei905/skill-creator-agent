from __future__ import annotations

from importlib import import_module

__all__ = [
    "SkillCreatorAgent",
    "GraphConnector",
    "SkillCreatorRuntime",
    "DataAgentSession",
    "build_data_agent_session",
    "extract_last_message_text",
    "build_ferry_config",
    "materialize_ferry_config",
    "DEFAULT_VERIFICATION_CONFIG",
    "DEFAULT_VERIFICATION_CONFIG_EXAMPLE",
    "DEFAULT_VERIFICATION_OUTPUT_ROOT",
    "resolve_default_verification_config_path",
    "DEFAULT_SKILLS_ROOT",
    "DEFAULT_GRAPH_BASE_URL",
    "ENV_SKILLS_ROOT",
    "ENV_GRAPH_BASE_URL",
    "ENV_GRAPH_TIMEOUT",
    "SkillCreatorSettings",
    "resolve_skill_creator_settings",
]


_EXPORTS = {
    "SkillCreatorAgent": ("skill_creator_agent.agent", "SkillCreatorAgent"),
    "GraphConnector": ("skill_creator_agent.connectors", "GraphConnector"),
    "SkillCreatorRuntime": ("skill_creator_agent.runtime", "SkillCreatorRuntime"),
    "DataAgentSession": ("skill_creator_agent.data_agent_bridge", "DataAgentSession"),
    "build_data_agent_session": ("skill_creator_agent.data_agent_bridge", "build_data_agent_session"),
    "extract_last_message_text": ("skill_creator_agent.data_agent_bridge", "extract_last_message_text"),
    "DEFAULT_VERIFICATION_CONFIG": ("skill_creator_agent.data_agent_bridge", "DEFAULT_VERIFICATION_CONFIG"),
    "DEFAULT_VERIFICATION_CONFIG_EXAMPLE": (
        "skill_creator_agent.data_agent_bridge",
        "DEFAULT_VERIFICATION_CONFIG_EXAMPLE",
    ),
    "DEFAULT_VERIFICATION_OUTPUT_ROOT": (
        "skill_creator_agent.data_agent_bridge",
        "DEFAULT_VERIFICATION_OUTPUT_ROOT",
    ),
    "resolve_default_verification_config_path": (
        "skill_creator_agent.data_agent_bridge",
        "resolve_default_verification_config_path",
    ),
    "build_ferry_config": ("skill_creator_agent.ferry_config", "build_ferry_config"),
    "materialize_ferry_config": ("skill_creator_agent.ferry_config", "materialize_ferry_config"),
    "DEFAULT_SKILLS_ROOT": ("skill_creator_agent.settings", "DEFAULT_SKILLS_ROOT"),
    "DEFAULT_GRAPH_BASE_URL": ("skill_creator_agent.settings", "DEFAULT_GRAPH_BASE_URL"),
    "ENV_SKILLS_ROOT": ("skill_creator_agent.settings", "ENV_SKILLS_ROOT"),
    "ENV_GRAPH_BASE_URL": ("skill_creator_agent.settings", "ENV_GRAPH_BASE_URL"),
    "ENV_GRAPH_TIMEOUT": ("skill_creator_agent.settings", "ENV_GRAPH_TIMEOUT"),
    "SkillCreatorSettings": ("skill_creator_agent.settings", "SkillCreatorSettings"),
    "resolve_skill_creator_settings": ("skill_creator_agent.settings", "resolve_skill_creator_settings"),
}


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name)
    return getattr(module, attr_name)
