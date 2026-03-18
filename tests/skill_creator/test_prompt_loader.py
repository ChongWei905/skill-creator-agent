from __future__ import annotations

from pathlib import Path

import pytest

from skill_creator_agent.prompts import (
    GRAPH_DB_INSTRUCTION,
    NO_SKILL_FALLBACK,
    NO_SKILL_FALLBACK_DIRECT,
    SKILL_CREATION_WORKFLOW,
    SKILL_EXECUTION_REMINDER,
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_DIRECT_QUERY,
    available_prompts,
    load_prompt,
    load_skill_creation_step5,
    prompt_path,
)

WORKFLOW_SVC_PROMPTS = Path("/Users/weichong/Documents/new_working_area/workflow-svc/prompts")
PROMPT_NAMES = (
    GRAPH_DB_INSTRUCTION,
    NO_SKILL_FALLBACK,
    NO_SKILL_FALLBACK_DIRECT,
    SKILL_CREATION_WORKFLOW,
    SKILL_EXECUTION_REMINDER,
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_DIRECT_QUERY,
)


def test_prompt_loader_lists_expected_prompts():
    prompts = available_prompts()

    assert SYSTEM_PROMPT_BASE in prompts
    assert SKILL_CREATION_WORKFLOW in prompts
    assert NO_SKILL_FALLBACK in prompts
    assert prompt_path(SYSTEM_PROMPT_BASE).name == "system_prompt_base.md"


def test_prompt_loader_replaces_known_placeholders_only():
    content = load_prompt(
        SYSTEM_PROMPT_BASE,
        skills_context="<skill />",
        missing_skill_instruction="create one",
    )

    assert "<skill />" in content
    assert "create one" in content
    assert "{graph_db_instruction}" in content


def test_prompt_loader_raises_for_unknown_prompt():
    with pytest.raises(FileNotFoundError):
        prompt_path("does_not_exist")


def test_prompt_markdown_matches_workflow_svc_sources():
    if not WORKFLOW_SVC_PROMPTS.exists():
        pytest.skip("workflow-svc prompt sources are not available in this environment")

    for prompt_name in PROMPT_NAMES:
        current = prompt_path(prompt_name).read_text(encoding="utf-8")
        original = (WORKFLOW_SVC_PROMPTS / f"{prompt_name}.md").read_text(encoding="utf-8")
        assert current == original, prompt_name


def test_load_skill_creation_step5_matches_original_section():
    current = load_skill_creation_step5()
    original = (WORKFLOW_SVC_PROMPTS / "skill_creation_workflow.md").read_text(encoding="utf-8")
    start = original.index("### **Step 5: Create Complete Skill Package**")
    end = original.index("### Step 6: Execution-Time Graph Queries (When Running the Skill)")

    assert current == original[start:end].strip()
