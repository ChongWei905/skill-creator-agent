from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from knowledge_skills.paths import project_path, resolve_local_path

ENV_SKILLS_ROOT = "SKILL_CREATOR_SKILLS_ROOT"
ENV_GRAPH_BASE_URL = "SKILL_CREATOR_GRAPH_BASE_URL"
ENV_GRAPH_URL_SUFFIX = "SKILL_CREATOR_GRAPH_URL_SUFFIX"
ENV_GRAPH_TIMEOUT = "SKILL_CREATOR_GRAPH_TIMEOUT"
DEFAULT_SKILLS_ROOT = project_path("skills")
DEFAULT_GRAPH_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_GRAPH_TIMEOUT = 30


@dataclass(frozen=True)
class SkillCreatorSettings:
    skills_root: Path
    graph_enabled: bool = False
    graph_base_url: str = DEFAULT_GRAPH_BASE_URL
    graph_url_suffix: str = ""
    graph_timeout: int = DEFAULT_GRAPH_TIMEOUT
    source: str = "default"


def resolve_skill_creator_settings(config: Mapping[str, Any] | None = None) -> SkillCreatorSettings:
    """Resolve runtime settings from defaults, config, and environment overrides."""
    section = _extract_section(config)
    graph_enabled = _as_bool(section.get("graph_enabled"), default=False)
    graph_base_url = str(section.get("graph_base_url") or DEFAULT_GRAPH_BASE_URL).rstrip("/")
    graph_url_suffix = _normalize_graph_url_suffix(section.get("graph_url_suffix"))
    graph_timeout = _as_int(section.get("graph_timeout"), default=DEFAULT_GRAPH_TIMEOUT)

    env_root = os.getenv(ENV_SKILLS_ROOT)
    env_graph_base_url = os.getenv(ENV_GRAPH_BASE_URL)
    env_graph_url_suffix = os.getenv(ENV_GRAPH_URL_SUFFIX)
    env_graph_timeout = os.getenv(ENV_GRAPH_TIMEOUT)
    if env_root:
        return SkillCreatorSettings(
            skills_root=_normalize_skills_root(env_root),
            graph_enabled=graph_enabled,
            graph_base_url=(env_graph_base_url or graph_base_url).rstrip("/"),
            graph_url_suffix=_normalize_graph_url_suffix(env_graph_url_suffix or graph_url_suffix),
            graph_timeout=_as_int(env_graph_timeout, default=graph_timeout),
            source="env",
        )

    config_root = section.get("skills_root")
    if config_root:
        return SkillCreatorSettings(
            skills_root=_normalize_skills_root(config_root),
            graph_enabled=graph_enabled,
            graph_base_url=(env_graph_base_url or graph_base_url).rstrip("/"),
            graph_url_suffix=_normalize_graph_url_suffix(env_graph_url_suffix or graph_url_suffix),
            graph_timeout=_as_int(env_graph_timeout, default=graph_timeout),
            source="config",
        )

    return SkillCreatorSettings(
        skills_root=DEFAULT_SKILLS_ROOT.resolve(),
        graph_enabled=graph_enabled,
        graph_base_url=(env_graph_base_url or graph_base_url).rstrip("/"),
        graph_url_suffix=_normalize_graph_url_suffix(env_graph_url_suffix or graph_url_suffix),
        graph_timeout=_as_int(env_graph_timeout, default=graph_timeout),
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
    if "SKILL_CREATOR.graph_base_url" in config and "graph_base_url" not in section:
        section["graph_base_url"] = config.get("SKILL_CREATOR.graph_base_url")
    if "SKILL_CREATOR.graph_url_suffix" in config and "graph_url_suffix" not in section:
        section["graph_url_suffix"] = config.get("SKILL_CREATOR.graph_url_suffix")
    if "SKILL_CREATOR.graph_timeout" in config and "graph_timeout" not in section:
        section["graph_timeout"] = config.get("SKILL_CREATOR.graph_timeout")
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


def _normalize_graph_url_suffix(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip()
    if not normalized:
        return ""
    if normalized.startswith(("?", "&")):
        return normalized
    return f"?{normalized}"


def _as_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
