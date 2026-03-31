from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_skills.prompts import (
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
    available_prompts,
    load_prompt,
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
    assert STAGE_CONTEXT_EXISTING_SKILL in prompts
    assert STAGE_CONTEXT_PLAN_AGENT in prompts
    assert STAGE_CONTEXT_BUILD_RUN in prompts
    assert UNIFIED_ROUTER in prompts
    assert GRAPH_CONNECTOR_PYTHON_CONTRACT in prompts
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
