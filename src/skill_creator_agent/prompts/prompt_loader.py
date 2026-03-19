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
STAGE_CONTEXT_DISCOVER_EXISTING_SKILL = "stage_context_discover_existing_skill"
STAGE_CONTEXT_ASK_REFERENCES = "stage_context_ask_references"
STAGE_CONTEXT_INSPECT_SCHEMA = "stage_context_inspect_schema"
STAGE_CONTEXT_PROPOSE_PLAN = "stage_context_propose_plan"
STAGE_CONTEXT_CREATE_SKILL = "stage_context_create_skill"
STAGE_CONTEXT_WRITE_SKILL_DOC = "stage_context_write_skill_doc"
STAGE_CONTEXT_WRITE_SKILL_SCRIPT = "stage_context_write_skill_script"
STAGE_CONTEXT_EXECUTE_SKILL = "stage_context_execute_skill"
STAGE_ROUTER = "stage_router"
DISCOVERY_TRANSITION_ROUTER = "discovery_transition_router"
REFERENCE_DOCUMENT_SUMMARIZER = "reference_document_summarizer"
REFERENCE_RESPONSE_ROUTER = "reference_response_router"

PROMPTS = (
    DISCOVERY_TRANSITION_ROUTER,
    GRAPH_DB_INSTRUCTION,
    NO_SKILL_FALLBACK,
    NO_SKILL_FALLBACK_DIRECT,
    REFERENCE_DOCUMENT_SUMMARIZER,
    REFERENCE_RESPONSE_ROUTER,
    SKILL_CREATION_WORKFLOW,
    SKILL_EXECUTION_REMINDER,
    STAGE_CONTEXT_ASK_REFERENCES,
    STAGE_CONTEXT_CREATE_SKILL,
    STAGE_CONTEXT_DISCOVER_EXISTING_SKILL,
    STAGE_CONTEXT_EXECUTE_SKILL,
    STAGE_CONTEXT_INSPECT_SCHEMA,
    STAGE_CONTEXT_PROPOSE_PLAN,
    STAGE_CONTEXT_WRITE_SKILL_DOC,
    STAGE_CONTEXT_WRITE_SKILL_SCRIPT,
    STAGE_ROUTER,
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_DIRECT_QUERY,
)

_PLACEHOLDER_PATTERN = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")
STEP_1_START_MARKER = "### Step 1: Confirm Skill Creation Need"
STEP_2_START_MARKER = "### Step 2: Gather Reference Documentation (If Available)"
STEP_3_START_MARKER = "### Step 3: Query Graph Database Schema (CRITICAL - DO NOT SKIP)"
STEP_4_START_MARKER = "### Step 4: Design and Present Execution Flow (CRITICAL - MUST GET USER APPROVAL)"
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


def load_skill_creation_step1() -> str:
    return load_prompt_section(
        SKILL_CREATION_WORKFLOW,
        start_marker=STEP_1_START_MARKER,
        end_marker=STEP_2_START_MARKER,
    )


def load_skill_creation_step2() -> str:
    return load_prompt_section(
        SKILL_CREATION_WORKFLOW,
        start_marker=STEP_2_START_MARKER,
        end_marker=STEP_3_START_MARKER,
    )


def load_skill_creation_step3() -> str:
    return load_prompt_section(
        SKILL_CREATION_WORKFLOW,
        start_marker=STEP_3_START_MARKER,
        end_marker=STEP_4_START_MARKER,
    )


def load_skill_creation_step4() -> str:
    return load_prompt_section(
        SKILL_CREATION_WORKFLOW,
        start_marker=STEP_4_START_MARKER,
        end_marker=STEP_5_START_MARKER,
    )


def load_skill_creation_step6() -> str:
    return load_prompt_section(
        SKILL_CREATION_WORKFLOW,
        start_marker=STEP_6_START_MARKER,
        end_marker=None,
    )
