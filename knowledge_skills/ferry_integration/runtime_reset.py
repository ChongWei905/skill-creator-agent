from __future__ import annotations

import sys

import ferry.actions.tools as ferry_tools_module
from ferry.core.managers.llm_manager import llm_manager
from ferry.actions.tools.manager import ToolManager


def reset_ferry_singletons() -> None:
    """Clear Ferry tool and model singletons before materializing a new stage."""
    old_tool_manager = ferry_tools_module.tool_manager
    ToolManager.reset_instance()
    new_tool_manager = ToolManager()
    ferry_tools_module.tool_manager = new_tool_manager
    _rebind_imported_singleton("tool_manager", old_tool_manager, new_tool_manager)
    llm_manager.llm_cache.clear()


def _rebind_imported_singleton(name: str, previous: object, current: object) -> None:
    """Replace module-level singleton aliases that still point at an outdated Ferry object."""
    for module in list(sys.modules.values()):
        if module is None:
            continue
        if getattr(module, name, None) is previous:
            setattr(module, name, current)
