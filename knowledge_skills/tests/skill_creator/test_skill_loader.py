from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_skills.paths import resolve_local_path
from knowledge_skills.loaders import SkillLoader


def test_skill_loader_loads_fixture_skill():
    loader = SkillLoader(resolve_local_path("tests/fixtures/minimal_skills"))

    skills = loader.load_all()
    skill = skills["skill-creator-smoke"]

    assert loader.list_skill_names() == ["skill-creator-smoke"]
    assert skill.description
    assert skill.skill_md_path.exists()
    assert skill.list_script_names() == ["echo_input"]
    assert "available_scripts" in skill.to_full_context()

    code, stdout, stderr = skill.get_script("echo_input").execute(["phase1"])
    assert code == 0
    assert stdout.strip() == "phase1"
    assert stderr == ""


def test_skill_loader_skips_invalid_skill_when_not_strict(tmp_path: Path):
    valid_dir = tmp_path / "valid-skill"
    valid_dir.mkdir()
    (valid_dir / "SKILL.md").write_text(
        "---\nname: valid-skill\ndescription: Valid fixture skill.\n---\n\n# Valid\n",
        encoding="utf-8",
    )

    invalid_dir = tmp_path / "invalid-skill"
    invalid_dir.mkdir()
    (invalid_dir / "SKILL.md").write_text(
        "---\nname: mismatch-name\ndescription: Broken fixture skill.\n---\n\n# Invalid\n",
        encoding="utf-8",
    )

    loader = SkillLoader(tmp_path)
    skills = loader.load_all()

    assert list(skills) == ["valid-skill"]


def test_skill_loader_rejects_reserved_skill_name(tmp_path: Path):
    skill_dir = tmp_path / "anthropic"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: anthropic\ndescription: Reserved fixture skill.\n---\n\n# Reserved\n",
        encoding="utf-8",
    )

    loader = SkillLoader(tmp_path)

    with pytest.raises(ValueError, match="reserved skill name: anthropic"):
        loader.load_skill_dir(skill_dir)


def test_skill_loader_reload_skill_re_reads_disk(tmp_path: Path):
    skill_dir = tmp_path / "reloadable-skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: reloadable-skill\ndescription: First version.\n---\n\n# First\n",
        encoding="utf-8",
    )

    loader = SkillLoader(tmp_path)
    first = loader.load_all()["reloadable-skill"]
    assert first.description == "First version."

    skill_md.write_text(
        "---\nname: reloadable-skill\ndescription: Second version.\n---\n\n# Second\n",
        encoding="utf-8",
    )

    reloaded = loader.reload_skill("reloadable-skill")
    assert reloaded.description == "Second version."
