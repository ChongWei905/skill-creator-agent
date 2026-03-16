from __future__ import annotations

from pathlib import Path

from skill_creator_agent.settings import (
    DEFAULT_SKILLS_ROOT,
    ENV_SKILLS_ROOT,
    resolve_skill_creator_settings,
)


def test_skill_creator_settings_use_fixture_default(monkeypatch):
    monkeypatch.delenv(ENV_SKILLS_ROOT, raising=False)

    settings = resolve_skill_creator_settings()

    assert settings.source == "default"
    assert settings.skills_root == DEFAULT_SKILLS_ROOT.resolve()
    assert settings.graph_enabled is False


def test_skill_creator_settings_allow_yaml_override(monkeypatch):
    monkeypatch.delenv(ENV_SKILLS_ROOT, raising=False)

    settings = resolve_skill_creator_settings(
        {
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
                "graph_enabled": True,
            }
        }
    )

    assert settings.source == "config"
    assert settings.skills_root == DEFAULT_SKILLS_ROOT.resolve()
    assert settings.graph_enabled is True


def test_skill_creator_settings_env_wins_over_config(monkeypatch, tmp_path: Path):
    env_root = tmp_path / "external-skills"
    env_root.mkdir()
    monkeypatch.setenv(ENV_SKILLS_ROOT, str(env_root))

    settings = resolve_skill_creator_settings(
        {
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
                "graph_enabled": False,
            }
        }
    )

    assert settings.source == "env"
    assert settings.skills_root == env_root.resolve()
