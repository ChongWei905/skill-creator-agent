from __future__ import annotations

import re
from pathlib import Path

SKILL_CREATION_WORKFLOW = "skill_creation_workflow"
SYSTEM_PROMPT_BASE = "system_prompt_base"
SYSTEM_PROMPT_DIRECT_QUERY = "system_prompt_direct_query"
GRAPH_DB_INSTRUCTION = "graph_db_instruction"
SKILL_EXECUTION_REMINDER = "skill_execution_reminder"
NO_SKILL_FALLBACK = "no_skill_fallback"
NO_SKILL_FALLBACK_DIRECT = "no_skill_fallback_direct"

PROMPTS = (
    GRAPH_DB_INSTRUCTION,
    NO_SKILL_FALLBACK,
    NO_SKILL_FALLBACK_DIRECT,
    SKILL_CREATION_WORKFLOW,
    SKILL_EXECUTION_REMINDER,
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_DIRECT_QUERY,
)

_PLACEHOLDER_PATTERN = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")
STEP_5_START_MARKER = "### **Step 5: Create Complete Skill Package**"
STEP_6_START_MARKER = "### Step 6: Execution-Time Graph Queries (When Running the Skill)"


def available_prompts() -> tuple[str, ...]:
    return PROMPTS


def prompt_path(prompt_name: str) -> Path:
    path = Path(__file__).resolve().parent / f"{prompt_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path


def load_prompt(prompt_name: str, **kwargs: object) -> str:
    content = prompt_path(prompt_name).read_text(encoding="utf-8")
    if not kwargs:
        return content

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in kwargs:
            return match.group(0)
        return str(kwargs[key])

    return _PLACEHOLDER_PATTERN.sub(replace, content)


def load_prompt_section(prompt_name: str, *, start_marker: str, end_marker: str | None = None) -> str:
    content = load_prompt(prompt_name)
    start_index = content.find(start_marker)
    if start_index < 0:
        raise ValueError(f"Start marker not found in prompt '{prompt_name}': {start_marker}")

    if end_marker is None:
        end_index = len(content)
    else:
        end_index = content.find(end_marker, start_index)
        if end_index < 0:
            raise ValueError(f"End marker not found in prompt '{prompt_name}': {end_marker}")

    return content[start_index:end_index].strip()


def load_skill_creation_step5() -> str:
    return load_prompt_section(
        SKILL_CREATION_WORKFLOW,
        start_marker=STEP_5_START_MARKER,
        end_marker=STEP_6_START_MARKER,
    )
