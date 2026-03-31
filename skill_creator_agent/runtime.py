from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from skill_creator_agent.connectors import GraphConnector
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
        """Initialize the runtime with settings and an optional prebuilt skill loader."""
        self.settings = settings
        self.loader = loader or SkillLoader(settings.skills_root)
        self._skills_loaded = False
        self._graph_connector: GraphConnector | None = None

    @staticmethod
    def _render_skill_md(frontmatter: dict[str, Any], body: str) -> str:
        """Render canonical SKILL.md content from frontmatter and body text."""
        frontmatter_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        rendered_body = body.strip() or "# Skill\n\nDescribe the workflow and execution steps for this skill."
        return f"---\n{frontmatter_text}\n---\n\n{rendered_body}\n"

    @staticmethod
    def _resolve_script_path(scripts_dir: Path, relative_path: str) -> Path:
        """Resolve one script path while enforcing that it stays under scripts/."""
        candidate = (scripts_dir / relative_path).resolve()
        if not candidate.is_relative_to(scripts_dir.resolve()):
            raise ValueError(f"Script path must stay within scripts/: {relative_path}")
        return candidate

    @staticmethod
    def build_missing_skill_prompt(*, direct_query: bool = False) -> str:
        """Render the fallback prompt used when no existing skill is a fit."""
        prompt_name = NO_SKILL_FALLBACK_DIRECT if direct_query else NO_SKILL_FALLBACK
        return load_prompt(prompt_name)

    @staticmethod
    def skill_to_dict(skill: Skill) -> dict[str, Any]:
        """Convert one loaded skill into a serializable metadata dictionary."""
        return {
            "name": skill.name,
            "description": skill.description,
            "path": str(skill.path),
            "scripts": [
                {
                    "name": script.name,
                    "path": str(script.path),
                    "language": script.language,
                    "description": script.description,
                }
                for script in skill.scripts
            ],
        }

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None = None) -> "SkillCreatorRuntime":
        """Build a runtime directly from a raw configuration mapping."""
        settings = resolve_skill_creator_settings(config)
        return cls(settings=settings)

    def load_skills(self, *, force: bool = False) -> dict[str, Skill]:
        """Load skills from disk and return the current in-memory registry."""
        if force or not self._skills_loaded:
            skills_root = self.ensure_skills_root()
            self.loader.skills_root = skills_root
            loaded_skills = self.loader.load_all()
            self._skills_loaded = True
            return loaded_skills
        return dict(self.loader.skills)

    def ensure_skills_root(self) -> Path:
        """Create the configured skills root if needed and return its resolved path."""
        self.settings.skills_root.mkdir(parents=True, exist_ok=True)
        return self.settings.skills_root

    def list_skills(self) -> list[dict[str, Any]]:
        """Return all known skills as serializable metadata dictionaries."""
        loaded_skills = self.load_skills()
        return [self.skill_to_dict(skill) for skill in loaded_skills.values()]

    def get_skill(self, name: str) -> Skill:
        """Return one loaded skill by name or raise if it does not exist."""
        loaded_skills = self.load_skills()
        skill = loaded_skills.get(name)
        if skill is None:
            raise KeyError(f"Unknown skill: {name}")
        return skill

    def read_skill_content(self, name: str) -> str:
        """Read and return the raw SKILL.md content for one skill."""
        return self.get_skill(name).skill_md_path.read_text(encoding="utf-8")

    def list_skill_scripts(self, name: str) -> list[dict[str, Any]]:
        """Return all scripts registered under one skill package."""
        skill = self.get_skill(name)
        return [
            {
                "name": script.name,
                "path": str(script.path),
                "language": script.language,
                "description": script.description,
            }
            for script in skill.scripts
        ]

    def read_script_source(self, name: str, script_name: str) -> str:
        """Read one script file from a loaded skill package."""
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
        """Execute a skill script and return a structured process result payload."""
        script = self._get_script(name, script_name)
        normalized_cwd = Path(cwd).expanduser().resolve() if cwd is not None else None
        if graph_db_config is None and self.settings.graph_enabled:
            graph_db_config = self.graph_db_config()
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

    def graph_db_config(self) -> dict[str, Any]:
        """Return the graph connection settings exposed to generated scripts."""
        return {
            "base_url": self.settings.graph_base_url,
            "timeout": self.settings.graph_timeout,
        }

    def get_graph_connector(self) -> GraphConnector:
        """Return a cached graph connector for the configured graph endpoint."""
        if not self.settings.graph_enabled:
            raise RuntimeError("Graph access is disabled for this runtime.")
        if self._graph_connector is None:
            self._graph_connector = GraphConnector(
                base_url=self.settings.graph_base_url,
                timeout=self.settings.graph_timeout,
            )
        return self._graph_connector

    def graph_get_object_types(self) -> list[str]:
        """List all graph object types available from the configured graph service."""
        return self.get_graph_connector().get_object_types()

    def graph_get_object_relations(self) -> list[str]:
        """List all graph relation types available from the configured graph service."""
        return self.get_graph_connector().get_object_relations()

    def graph_get_entity_schema(self, entity_type: str) -> dict[str, Any]:
        """Return a lightweight schema snapshot for one graph entity type."""
        return self.get_graph_connector().get_entity_schema(entity_type)

    def graph_query_examples(
        self,
        entity_type: str,
        *,
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch example records for one graph entity type."""
        return self.get_graph_connector().query_examples(
            entity_type,
            limit=limit,
            filter_dict=filter_dict,
        )

    def graph_property_filter(
        self,
        element_class: str,
        element_type: str = "NODE",
        filter_dict: dict[str, Any] | None = None,
        *,
        get_all_properties: bool = False,
    ) -> list[dict[str, Any]]:
        """Run a property filter query through the graph connector."""
        return self.get_graph_connector().property_filter(
            element_class,
            element_type,
            filter_dict,
            get_all_properties=get_all_properties,
        )

    def graph_property_info(
        self,
        element_class: str,
        element_type: str = "NODE",
        element_uuid: str | None = None,
    ) -> dict[str, Any]:
        """Fetch one graph element's property payload by UUID."""
        return self.get_graph_connector().property_info_search(
            element_class,
            element_type,
            element_uuid,
        )

    def graph_hop_search(
        self,
        uuid: str,
        hop_num: int,
        accurate_flag: bool = False,
    ) -> list[dict[str, Any]]:
        """Run a hop search starting from one graph UUID."""
        return self.get_graph_connector().hop_search(
            uuid,
            hop_num,
            accurate_flag,
        )

    def graph_count_search(
        self,
        element_class: str,
        element_type: str = "NODE",
        filter_dict: dict[str, Any] | None = None,
    ) -> int:
        """Count graph elements that satisfy the provided filters."""
        return self.get_graph_connector().count_search(
            element_class,
            element_type,
            filter_dict,
        )

    def graph_aggregate_search(
        self,
        element_class: str,
        element_type: str = "NODE",
        target_property: str | None = None,
        agg_func: str | None = None,
        filter_dict: dict[str, Any] | None = None,
    ) -> Any:
        """Run an aggregate search through the graph connector."""
        return self.get_graph_connector().aggregate_search(
            element_class,
            element_type,
            target_property,
            agg_func,
            filter_dict,
        )

    def graph_sorted_search(
        self,
        element_class: str,
        element_type: str = "NODE",
        filter_dict: dict[str, Any] | None = None,
        return_properties: list[str] | None = None,
        sort_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Run a sorted graph search with optional return property constraints."""
        kwargs: dict[str, Any] = {
            "filter_dict": filter_dict,
            "return_properties": return_properties,
            "sort_by": sort_by,
            "ascending": ascending,
        }
        if limit is not None:
            kwargs["limit"] = limit
        return self.get_graph_connector().sorted_search(
            element_class,
            element_type,
            **kwargs,
        )

    def graph_pattern_search(
        self,
        path_pattern: list[list[Any]],
        return_vars: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a graph pattern search with optional return variable projection."""
        return self.get_graph_connector().pattern_search(
            path_pattern,
            return_vars=return_vars,
        )

    def reload_skill(self, name: str) -> Skill:
        """Reload one skill from disk and refresh the runtime cache."""
        loaded_skills = self.load_skills()
        if name not in loaded_skills and not (self.settings.skills_root / name).exists():
            raise KeyError(f"Unknown skill: {name}")
        return self.loader.reload_skill(name)

    def create_skill_scaffold(
        self,
        name: str,
        description: str,
        *,
        body: str = "",
        script_files: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a new skill package skeleton on disk and return its file inventory."""
        skills_root = self.ensure_skills_root()
        target_dir = (skills_root / name).resolve()
        frontmatter = {
            "name": name,
            "description": description,
        }
        if metadata:
            frontmatter["metadata"] = metadata
        if allowed_tools:
            frontmatter["allowed-tools"] = allowed_tools
        self.loader.validate_frontmatter(frontmatter, target_dir)

        if target_dir.exists() and any(target_dir.iterdir()) and not overwrite:
            raise FileExistsError(f"Skill already exists: {target_dir}")

        target_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir = target_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        skill_md_path = target_dir / "SKILL.md"
        skill_md_path.write_text(
            self._render_skill_md(frontmatter, body),
            encoding="utf-8",
        )

        created_files = [skill_md_path]
        for relative_path, content in (script_files or {}).items():
            script_path = self._resolve_script_path(scripts_dir, relative_path)
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(content, encoding="utf-8")
            created_files.append(script_path)

        self._skills_loaded = False
        return {
            "skill_name": name,
            "skill_dir": str(target_dir),
            "skill_md_path": str(skill_md_path),
            "scripts_dir": str(scripts_dir),
            "created_files": [str(path) for path in created_files],
            "next_step": "Update SKILL.md/scripts if needed, then call reload_skill to register the new skill.",
        }

    def build_ferry_skill_registry(self) -> list[dict[str, Any]]:
        """Build the skill registry payload expected by Ferry configuration rendering."""
        loaded_skills = self.load_skills()
        registry: list[dict[str, Any]] = []
        for skill in loaded_skills.values():
            tags: list[str] = []
            if isinstance(skill.metadata, dict):
                raw_tags = skill.metadata.get("tags")
                if isinstance(raw_tags, list):
                    tags = [str(tag) for tag in raw_tags]
            registry.append(
                {
                    "name": skill.name,
                    "path": str(skill.path),
                    "category": "workflow",
                    "description": skill.description,
                    "tags": tags,
                }
            )
        return registry

    def build_skills_context(self, *, full: bool = False) -> str:
        """Render all loaded skills into the context block format used by prompts."""
        loaded_skills = self.load_skills()
        render = Skill.to_full_context if full else Skill.to_metadata_context
        return "\n".join(render(skill) for skill in loaded_skills.values())

    def build_system_prompt(
        self,
        *,
        direct_query: bool = False,
        just_created_skill: str | None = None,
        original_intent: str | None = None,
    ) -> str:
        """Render the effective system prompt for one runtime interaction mode."""
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

    def _get_script(self, name: str, script_name: str):
        skill = self.get_skill(name)
        script = skill.get_script(script_name)
        if script is None:
            raise KeyError(f"Unknown script '{script_name}' for skill '{name}'")
        return script
