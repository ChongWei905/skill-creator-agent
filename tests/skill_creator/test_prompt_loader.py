from __future__ import annotations

import pytest

from skill_creator_agent.prompts import (
    NO_SKILL_FALLBACK,
    SKILL_CREATION_WORKFLOW,
    SYSTEM_PROMPT_BASE,
    available_prompts,
    load_prompt,
    prompt_path,
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
