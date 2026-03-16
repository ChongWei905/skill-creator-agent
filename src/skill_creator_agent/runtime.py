from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from skill_creator_agent.loaders import SkillLoader
from skill_creator_agent.models import Skill
from skill_creator_agent.prompts import (
    GRAPH_DB_INSTRUCTION,
    NO_SKILL_FALLBACK,
    NO_SKILL_FALLBACK_DIRECT,
    SKILL_CREATION_WORKFLOW,
    SKILL_EXECUTION_REMINDER,
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_DIRECT_QUERY,
    load_prompt,
)
from skill_creator_agent.settings import SkillCreatorSettings, resolve_skill_creator_settings


class SkillCreatorRuntime:
    def __init__(self, settings: SkillCreatorSettings, loader: SkillLoader | None = None):
        self.settings = settings
        self.loader = loader or SkillLoader(settings.skills_root)
        self._skills_loaded = False

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None = None) -> "SkillCreatorRuntime":
        settings = resolve_skill_creator_settings(config)
        return cls(settings=settings)

    def load_skills(self, *, force: bool = False) -> dict[str, Skill]:
        if force or not self._skills_loaded:
            self.loader.load_all()
            self._skills_loaded = True
        return dict(self.loader.skills)

    def list_skills(self) -> list[dict[str, Any]]:
        self.load_skills()
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "path": skill.path,
                "scripts": [
                    {
                        "name": script.name,
                        "path": script.path,
                        "language": script.language,
                        "description": script.description,
                    }
                    for script in skill.scripts
                ],
            }
            for skill in self.loader.skills.values()
        ]

    def get_skill(self, name: str) -> Skill:
        self.load_skills()
        skill = self.loader.get_skill(name)
        if skill is None:
            raise KeyError(f"Unknown skill: {name}")
        return skill

    def read_skill_content(self, name: str) -> str:
        return self.get_skill(name).skill_md_path.read_text(encoding="utf-8")

    def list_skill_scripts(self, name: str) -> list[dict[str, Any]]:
        skill = self.get_skill(name)
        return [
            {
                "name": script.name,
                "path": script.path,
                "language": script.language,
                "description": script.description,
            }
            for script in skill.scripts
        ]

    def read_script_source(self, name: str, script_name: str) -> str:
        script = self._get_script(name, script_name)
        return script.path.read_text(encoding="utf-8")

    def execute_skill_script(
        self,
        name: str,
        script_name: str,
        args: list[str] | None = None,
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 300,
        graph_db_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        script = self._get_script(name, script_name)
        normalized_cwd = Path(cwd).expanduser().resolve() if cwd is not None else None
        exit_code, stdout, stderr = script.execute(
            args=args,
            cwd=normalized_cwd,
            env=env,
            timeout=timeout,
            graph_db_config=graph_db_config,
        )
        return {
            "skill": name,
            "script": script.name,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }

    def reload_skill(self, name: str) -> Skill:
        self.load_skills()
        return self.loader.reload_skill(name)

    def build_skills_context(self, *, full: bool = False) -> str:
        self.load_skills()
        render = Skill.to_full_context if full else Skill.to_metadata_context
        return "\n".join(render(skill) for skill in self.loader.skills.values())

    def build_system_prompt(
        self,
        *,
        direct_query: bool = False,
        just_created_skill: str | None = None,
        original_intent: str | None = None,
    ) -> str:
        skills_context = self.build_skills_context(full=False)
        graph_db_instruction = ""
        if self.settings.graph_enabled:
            graph_db_instruction = load_prompt(GRAPH_DB_INSTRUCTION)

        skill_execution_reminder = ""
        if just_created_skill and original_intent:
            skill_execution_reminder = load_prompt(
                SKILL_EXECUTION_REMINDER,
                skill_name=just_created_skill,
                original_intent=original_intent,
            )

        if direct_query:
            template_name = SYSTEM_PROMPT_DIRECT_QUERY
            missing_skill_instruction = load_prompt(NO_SKILL_FALLBACK_DIRECT)
        else:
            template_name = SYSTEM_PROMPT_BASE
            missing_skill_instruction = load_prompt(SKILL_CREATION_WORKFLOW)

        return load_prompt(
            template_name,
            skills_context=skills_context,
            graph_db_instruction=graph_db_instruction,
            skill_execution_reminder=skill_execution_reminder,
            missing_skill_instruction=missing_skill_instruction,
        )

    def build_missing_skill_prompt(self, *, direct_query: bool = False) -> str:
        prompt_name = NO_SKILL_FALLBACK_DIRECT if direct_query else NO_SKILL_FALLBACK
        return load_prompt(prompt_name)

    def _get_script(self, name: str, script_name: str):
        skill = self.get_skill(name)
        script = skill.get_script(script_name)
        if script is None:
            raise KeyError(f"Unknown script '{script_name}' for skill '{name}'")
        return script
