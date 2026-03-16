from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from skill_creator_agent.runtime import SkillCreatorRuntime

_ACTIVE_RUNTIME: SkillCreatorRuntime | None = None


def configure_runtime_tools(
    *,
    config: Mapping[str, Any] | None = None,
    runtime: SkillCreatorRuntime | None = None,
) -> SkillCreatorRuntime:
    """Bind local tool calls to a concrete runtime instance."""
    global _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = runtime or SkillCreatorRuntime.from_config(config)
    return _ACTIVE_RUNTIME


def reset_runtime_tools() -> None:
    global _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = None


def get_runtime_tools() -> SkillCreatorRuntime:
    global _ACTIVE_RUNTIME
    if _ACTIVE_RUNTIME is None:
        _ACTIVE_RUNTIME = SkillCreatorRuntime.from_config()
    return _ACTIVE_RUNTIME


def list_available_skills() -> list[dict[str, Any]]:
    """List the currently available skills and their executable scripts."""
    return get_runtime_tools().list_skills()


def read_skill_content(skill_name: str) -> str:
    """Read the full SKILL.md content for a named skill."""
    return get_runtime_tools().read_skill_content(skill_name)


def list_skill_scripts(skill_name: str) -> list[dict[str, Any]]:
    """List the scripts exposed by a named skill."""
    return get_runtime_tools().list_skill_scripts(skill_name)


def read_script_source(skill_name: str, script_name: str) -> str:
    """Read a skill script source file to inspect its implementation."""
    return get_runtime_tools().read_script_source(skill_name, script_name)


def execute_skill_script(
    skill_name: str,
    script_name: str,
    arguments: list[str] | None = None,
    cwd: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Execute a script from a skill and return exit code, stdout, and stderr."""
    return get_runtime_tools().execute_skill_script(
        skill_name,
        script_name,
        args=arguments,
        cwd=Path(cwd).expanduser().resolve() if cwd else None,
        timeout=timeout,
    )


def reload_skill(skill_name: str) -> dict[str, Any]:
    """Reload a skill from disk after creating or updating its files."""
    skill = get_runtime_tools().reload_skill(skill_name)
    return get_runtime_tools().skill_to_dict(skill)


def create_skill_scaffold(
    skill_name: str,
    description: str,
    body: str = "",
    script_files: dict[str, str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a valid skill directory with SKILL.md and an empty scripts/ area."""
    return get_runtime_tools().create_skill_scaffold(
        skill_name,
        description,
        body=body,
        script_files=script_files,
        overwrite=overwrite,
    )
