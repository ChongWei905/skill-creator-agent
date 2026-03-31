from __future__ import annotations

from pathlib import Path

from knowledge_skills.paths import resolve_local_path
from knowledge_skills.settings import (
    DEFAULT_GRAPH_BASE_URL,
    DEFAULT_SKILLS_ROOT,
    ENV_GRAPH_BASE_URL,
    ENV_GRAPH_URL_SUFFIX,
    ENV_GRAPH_TIMEOUT,
    ENV_SKILLS_ROOT,
    resolve_skill_creator_settings,
)


def test_skill_creator_settings_use_project_skills_default(monkeypatch):
    monkeypatch.delenv(ENV_SKILLS_ROOT, raising=False)

    settings = resolve_skill_creator_settings()

    assert settings.source == "default"
    assert settings.skills_root == DEFAULT_SKILLS_ROOT.resolve()
    assert settings.skills_root.name == "skills"
    assert settings.skills_root.exists()
    assert settings.graph_enabled is False
    assert settings.graph_base_url == DEFAULT_GRAPH_BASE_URL
    assert settings.graph_url_suffix == ""
    assert settings.graph_timeout == 30


def test_skill_creator_settings_allow_yaml_override(monkeypatch):
    monkeypatch.delenv(ENV_SKILLS_ROOT, raising=False)
    fixture_root = resolve_local_path("tests/fixtures/minimal_skills")

    settings = resolve_skill_creator_settings(
        {
            "SKILL_CREATOR": {
                "skills_root": "tests/fixtures/minimal_skills",
                "graph_enabled": True,
            }
        }
    )

    assert settings.source == "config"
    assert settings.skills_root == fixture_root
    assert settings.graph_enabled is True
    assert settings.graph_base_url == DEFAULT_GRAPH_BASE_URL
    assert settings.graph_url_suffix == ""


def test_skill_creator_settings_env_wins_over_config(monkeypatch, tmp_path: Path):
    env_root = tmp_path / "external-skills"
    env_root.mkdir()
    monkeypatch.setenv(ENV_SKILLS_ROOT, str(env_root))

    settings = resolve_skill_creator_settings(
        {
            "SKILL_CREATOR": {
                "skills_root": "tests/fixtures/minimal_skills",
                "graph_enabled": False,
            }
        }
    )

    assert settings.source == "env"
    assert settings.skills_root == env_root.resolve()


def test_skill_creator_settings_accept_graph_endpoint_overrides(monkeypatch):
    monkeypatch.delenv(ENV_SKILLS_ROOT, raising=False)
    monkeypatch.setenv(ENV_GRAPH_BASE_URL, "http://127.0.0.1:9000")
    monkeypatch.setenv(ENV_GRAPH_URL_SUFFIX, "?scene_name=gonghang")
    monkeypatch.setenv(ENV_GRAPH_TIMEOUT, "12")

    settings = resolve_skill_creator_settings(
        {
            "SKILL_CREATOR": {
                "skills_root": "tests/fixtures/minimal_skills",
                "graph_enabled": True,
                "graph_base_url": "http://127.0.0.1:8000",
                "graph_url_suffix": "?scene_name=retail",
                "graph_timeout": 30,
            }
        }
    )

    assert settings.graph_enabled is True
    assert settings.graph_base_url == "http://127.0.0.1:9000"
    assert settings.graph_url_suffix == "?scene_name=gonghang"
    assert settings.graph_timeout == 12


def test_skill_creator_settings_normalize_graph_url_suffix_from_config(monkeypatch):
    monkeypatch.delenv(ENV_SKILLS_ROOT, raising=False)
    monkeypatch.delenv(ENV_GRAPH_BASE_URL, raising=False)
    monkeypatch.delenv(ENV_GRAPH_URL_SUFFIX, raising=False)
    monkeypatch.delenv(ENV_GRAPH_TIMEOUT, raising=False)

    settings = resolve_skill_creator_settings(
        {
            "SKILL_CREATOR": {
                "skills_root": "tests/fixtures/minimal_skills",
                "graph_enabled": True,
                "graph_url_suffix": "scene_name=gonghang",
            }
        }
    )

    assert settings.graph_url_suffix == "?scene_name=gonghang"
