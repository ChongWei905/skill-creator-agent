from __future__ import annotations

import re
from pathlib import Path

import yaml

from skill_creator_agent.paths import project_path, resolve_local_path
from skill_creator_agent.runtime import SkillCreatorRuntime

DEBUG_CONFIG_PATH = project_path("tests", "fixtures", "skill_creator_debug.yaml")
SMOKE_SKILL_REL_PATH = "tests/fixtures/minimal_skills/skill-creator-smoke"


def _parse_frontmatter(skill_md_path: Path) -> tuple[dict[str, str], str]:
    content = skill_md_path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    assert match is not None, "SKILL.md must contain YAML frontmatter"
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    return frontmatter, body


def test_phase0_smoke_skill_fixture_contract():
    skill_root = resolve_local_path(SMOKE_SKILL_REL_PATH)
    frontmatter, body = _parse_frontmatter(skill_root / "SKILL.md")
    scripts = sorted(path.name for path in (skill_root / "scripts").iterdir() if path.is_file())

    assert frontmatter["name"] == "skill-creator-smoke"
    assert frontmatter["description"]
    assert "When to use" in body
    assert scripts == ["echo_input.sh"]


def test_phase0_debug_config_registers_smoke_skill(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = yaml.safe_load(DEBUG_CONFIG_PATH.read_text(encoding="utf-8"))
    runtime = SkillCreatorRuntime.from_config(config)
    skill_root = resolve_local_path(SMOKE_SKILL_REL_PATH)
    skills = runtime.list_skills()
    skill_meta = skills[0]

    assert Path(config["SKILL_CREATOR"]["skills_root"]).resolve() == resolve_local_path("tests/fixtures/minimal_skills")
    assert skill_meta["name"] == "skill-creator-smoke"
    assert Path(skill_meta["path"]).resolve() == skill_root
    assert skill_meta["scripts"][0]["name"] == "echo_input"
