from __future__ import annotations

from ferry.actions.tools import tool_manager
from ferry.core.managers.llm_manager import llm_manager


def reset_ferry_singletons() -> None:
    """Clear Ferry tool and model singletons before materializing a new stage."""
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
