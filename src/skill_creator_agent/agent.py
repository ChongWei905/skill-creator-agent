from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

import yaml

from skill_creator_agent.ferry_config import build_ferry_config, materialize_ferry_config
from skill_creator_agent.ferry_tools import configure_runtime_tools
from skill_creator_agent.runtime import SkillCreatorRuntime


class SkillCreatorAgent:
    def __init__(self, *, config: Mapping[str, Any], runtime: SkillCreatorRuntime | None = None):
        self.config = dict(config)
        self.runtime = runtime or SkillCreatorRuntime.from_config(self.config)
        configure_runtime_tools(config=self.config, runtime=self.runtime)

    @classmethod
    def from_config(cls, config: str | Path | Mapping[str, Any] | None = None) -> "SkillCreatorAgent":
        cfg = _config_to_dict(config)
        return cls(config=cfg)

    def list_skills(self) -> list[dict[str, Any]]:
        return self.runtime.list_skills()

    def read_skill_content(self, name: str) -> str:
        return self.runtime.read_skill_content(name)

    def list_skill_scripts(self, name: str) -> list[dict[str, Any]]:
        return self.runtime.list_skill_scripts(name)

    def read_script_source(self, name: str, script_name: str) -> str:
        return self.runtime.read_script_source(name, script_name)

    def execute_skill_script(
        self,
        name: str,
        script_name: str,
        args: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.runtime.execute_skill_script(name, script_name, args=args, **kwargs)

    def reload_skill(self, name: str):
        return self.runtime.reload_skill(name)

    def build_system_prompt(self, **kwargs: Any) -> str:
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
        return self.runtime.create_skill_scaffold(
            name,
            description,
            body=body,
            script_files=script_files,
            overwrite=overwrite,
        )

    def build_ferry_config(self) -> dict[str, Any]:
        return build_ferry_config(self.config, runtime=self.runtime)

    def materialize_ferry_config(self, output_path: str | Path) -> Path:
        return materialize_ferry_config(self.config, runtime=self.runtime, output_path=output_path)

    def create_ferry_agent(self, output_path: str | Path | None = None):
        from ferry.interface.sdk.agent import DataAgent

        if output_path is None:
            with NamedTemporaryFile("w", suffix=".yaml", delete=False) as temp_file:
                target_path = Path(temp_file.name)
            self.materialize_ferry_config(target_path)
        else:
            target_path = self.materialize_ferry_config(output_path)
        return DataAgent.from_config(target_path)


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
