from __future__ import annotations

import re
from pathlib import Path

SKILL_CREATION_WORKFLOW = "skill_creation_workflow"
SYSTEM_PROMPT_BASE = "system_prompt_base"
SYSTEM_PROMPT_DIRECT_QUERY = "system_prompt_direct_query"
GRAPH_DB_INSTRUCTION = "graph_db_instruction"
GRAPH_CONNECTOR_PYTHON_CONTRACT = "graph_connector_python_contract"
SKILL_EXECUTION_REMINDER = "skill_execution_reminder"
NO_SKILL_FALLBACK = "no_skill_fallback"
NO_SKILL_FALLBACK_DIRECT = "no_skill_fallback_direct"
STAGE_CONTEXT_EXISTING_SKILL = "stage_context_existing_skill"
STAGE_CONTEXT_PLAN_AGENT = "stage_context_plan_agent"
STAGE_CONTEXT_BUILD_RUN = "stage_context_build_run"
UNIFIED_ROUTER = "unified_router"

PROMPTS = (
    GRAPH_CONNECTOR_PYTHON_CONTRACT,
    GRAPH_DB_INSTRUCTION,
    NO_SKILL_FALLBACK,
    NO_SKILL_FALLBACK_DIRECT,
    SKILL_CREATION_WORKFLOW,
    SKILL_EXECUTION_REMINDER,
    STAGE_CONTEXT_BUILD_RUN,
    STAGE_CONTEXT_EXISTING_SKILL,
    STAGE_CONTEXT_PLAN_AGENT,
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_DIRECT_QUERY,
    UNIFIED_ROUTER,
)

_PLACEHOLDER_PATTERN = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")


def available_prompts() -> tuple[str, ...]:
    """Return the list of prompt identifiers shipped with the package."""
    return PROMPTS


def prompt_path(prompt_name: str) -> Path:
    """Resolve the markdown file path for a named prompt."""
    path = Path(__file__).resolve().parent / f"{prompt_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path


def load_prompt(prompt_name: str, **kwargs: object) -> str:
    """Load a prompt file and replace any known placeholders."""
    content = prompt_path(prompt_name).read_text(encoding="utf-8")
    if not kwargs:
        return content

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in kwargs:
            return match.group(0)
        return str(kwargs[key])

    return _PLACEHOLDER_PATTERN.sub(replace, content)
