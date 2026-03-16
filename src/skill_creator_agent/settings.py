from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from skill_creator_agent.paths import project_path, resolve_local_path

ENV_SKILLS_ROOT = "SKILL_CREATOR_SKILLS_ROOT"
DEFAULT_SKILLS_ROOT = project_path("skills")


@dataclass(frozen=True)
class SkillCreatorSettings:
    skills_root: Path
    graph_enabled: bool = False
    source: str = "default"


def resolve_skill_creator_settings(config: Mapping[str, Any] | None = None) -> SkillCreatorSettings:
    section = _extract_section(config)
    graph_enabled = _as_bool(section.get("graph_enabled"), default=False)

    env_root = os.getenv(ENV_SKILLS_ROOT)
    if env_root:
        return SkillCreatorSettings(
            skills_root=_normalize_skills_root(env_root),
            graph_enabled=graph_enabled,
            source="env",
        )

    config_root = section.get("skills_root")
    if config_root:
        return SkillCreatorSettings(
            skills_root=_normalize_skills_root(config_root),
            graph_enabled=graph_enabled,
            source="config",
        )

    return SkillCreatorSettings(
        skills_root=DEFAULT_SKILLS_ROOT.resolve(),
        graph_enabled=graph_enabled,
        source="default",
    )


def _extract_section(config: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        return {}

    section: dict[str, Any] = {}
    nested = config.get("SKILL_CREATOR")
    if isinstance(nested, Mapping):
        section.update(nested)

    if "SKILL_CREATOR.skills_root" in config and "skills_root" not in section:
        section["skills_root"] = config.get("SKILL_CREATOR.skills_root")
    if "SKILL_CREATOR.graph_enabled" in config and "graph_enabled" not in section:
        section["graph_enabled"] = config.get("SKILL_CREATOR.graph_enabled")
    return section


def _normalize_skills_root(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return resolve_local_path(candidate)


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)
