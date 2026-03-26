from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from ferry.actions.tools import tool_manager
from ferry.core.flex.agent import FlexAgent
from ferry.core.managers.action_manager import mechanism_manager
from ferry.core.managers.llm_manager import llm_manager
from ferry.core.managers.prompt_manager import prompt_manager

from skill_creator_agent.ferry_config import build_ferry_config, materialize_ferry_config
from skill_creator_agent.ferry_tools import configure_runtime_tools
from skill_creator_agent.runtime import SkillCreatorRuntime


class SkillCreatorAgent(FlexAgent):
    @classmethod
    def from_config(cls, config: str | Path | Mapping[str, Any] | None = None) -> "SkillCreatorAgent":
        """Build a Ferry FlexAgent instance backed by the skill creator runtime."""
        source_cfg = _config_to_dict(config)
        runtime = SkillCreatorRuntime.from_config(source_cfg)
        configure_runtime_tools(config=source_cfg, runtime=runtime)
        ferry_cfg = build_ferry_config(source_cfg, runtime=runtime)
        _ensure_global_init(ferry_cfg)

        agent = super().from_config(ferry_cfg)
        if not isinstance(agent, cls):
            raise TypeError(f"Expected {cls.__name__}, got {type(agent).__name__}")

        agent.runtime = runtime
        agent.source_config = source_cfg
        agent.ferry_config = ferry_cfg
        return agent

    def list_skills(self) -> list[dict[str, Any]]:
        """Return all skills currently visible to this agent runtime."""
        return self.runtime.list_skills()

    def read_skill_content(self, name: str) -> str:
        """Read the SKILL.md content for one registered skill."""
        return self.runtime.read_skill_content(name)

    def list_skill_scripts(self, name: str) -> list[dict[str, Any]]:
        """Return metadata for every script bundled in one skill package."""
        return self.runtime.list_skill_scripts(name)

    def read_script_source(self, name: str, script_name: str) -> str:
        """Read the source code for one script inside a skill package."""
        return self.runtime.read_script_source(name, script_name)

    def execute_skill_script(
        self,
        name: str,
        script_name: str,
        args: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute one skill script through the runtime and return its structured result."""
        return self.runtime.execute_skill_script(name, script_name, args=args, **kwargs)

    def reload_skill(self, name: str):
        """Reload one skill from disk into the runtime registry."""
        return self.runtime.reload_skill(name)

    def build_system_prompt(self, **kwargs: Any) -> str:
        """Render the runtime system prompt used by the wrapped Ferry agent."""
        return self.runtime.build_system_prompt(**kwargs)

    def create_skill_scaffold(
        self,
        name: str,
        description: str,
        *,
        body: str = "",
        script_files: dict[str, str] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a new skill scaffold through the runtime helper."""
        return self.runtime.create_skill_scaffold(
            name,
            description,
            body=body,
            script_files=script_files,
            overwrite=overwrite,
        )

    def build_ferry_config(self) -> dict[str, Any]:
        """Return a copy of the effective Ferry configuration for this agent."""
        return dict(self.ferry_config)

    def materialize_ferry_config(self, output_path: str | Path) -> Path:
        """Write the effective Ferry configuration to disk and return the path."""
        return materialize_ferry_config(self.source_config, runtime=self.runtime, output_path=output_path)


def _config_to_dict(config: str | Path | Mapping[str, Any] | None) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, Mapping):
        return dict(config)
    path = Path(config).expanduser()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("SkillCreatorAgent config must deserialize to a mapping")
    return data


def _ensure_global_init(config: dict[str, Any]) -> None:
    llm_manager.init_from_config(config)
    prompt_manager.init_from_config(config)
    tool_manager.init_from_config(config)
    mechanism_manager.init_from_config(config)
    tool_manager.enable_auto_discover()
