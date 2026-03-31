from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skill_creator_agent.paths import project_path


@dataclass
class SkillScript:
    name: str
    path: Path
    language: str
    description: str = ""

    def execute(
        self,
        args: list[str] | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 300,
        graph_db_config: dict[str, Any] | None = None,
    ) -> tuple[int, str, str]:
        """Execute the script with the runtime environment expected by generated skills."""
        cmd = self._build_command(args or [])
        run_env = os.environ.copy()
        if env:
            run_env.update({str(key): str(value) for key, value in env.items()})
        if graph_db_config:
            run_env["GRAPH_DB_BASE_URL"] = str(graph_db_config.get("base_url", "http://localhost:8080"))
            run_env["GRAPH_DB_URL_SUFFIX"] = str(graph_db_config.get("url_suffix", ""))
            run_env["GRAPH_DB_TIMEOUT"] = str(graph_db_config.get("timeout", 30))

        run_cwd = cwd.resolve() if cwd else self.infer_default_cwd()
        if self.language == "python":
            pythonpath_entries = [
                str(project_path()),
                str(run_cwd),
            ]
            existing_pythonpath = run_env.get("PYTHONPATH")
            if existing_pythonpath:
                pythonpath_entries.append(existing_pythonpath)
            run_env["PYTHONPATH"] = os.pathsep.join(
                entry for entry in pythonpath_entries if entry
            )

        try:
            result = subprocess.run(
                cmd,
                cwd=run_cwd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return -1, "", "Script execution timed out"
        except Exception as exc:
            return -1, "", str(exc)
        return result.returncode, result.stdout, result.stderr

    def infer_default_cwd(self) -> Path:
        """Infer the default working directory used when this script is executed."""
        skill_root = self.path.parent.parent.resolve()
        for ancestor in skill_root.parents:
            skills_dir = ancestor / "skills"
            if skills_dir.exists() and skill_root.is_relative_to(skills_dir):
                return ancestor.resolve()
        return skill_root

    def _build_command(self, args: list[str]) -> list[str]:
        script_path = str(self.path.resolve())
        if self.language == "python":
            return [sys.executable, script_path, *args]
        if self.language == "bash":
            return ["bash", script_path, *args]
        if self.language == "node":
            return ["node", script_path, *args]
        if self.language == "tsx":
            return ["npx", "tsx", script_path, *args]
        return [script_path, *args]


@dataclass
class Skill:
    name: str
    description: str
    content: str
    path: Path
    allowed_tools: list[str] | None = None
    metadata: dict[str, Any] | None = None
    scripts: list[SkillScript] = field(default_factory=list)

    @property
    def skill_md_path(self) -> Path:
        """Return the canonical SKILL.md path for this skill package."""
        return self.path / "SKILL.md"

    def list_script_names(self) -> list[str]:
        """Return all registered script names for this skill."""
        return [script.name for script in self.scripts]

    def get_script(self, name: str) -> SkillScript | None:
        """Return one script by logical name or filename if it exists."""
        for script in self.scripts:
            if name in (script.name, script.path.name):
                return script
        return None

    def to_metadata_context(self) -> str:
        """Render a compact XML-like context block without embedding full SKILL.md content."""
        scripts_info = self._render_scripts_block()
        return (
            f'<skill name="{self.name}" path="{self.path}">\n'
            f"<description>{self.description}</description>"
            f"{scripts_info}\n"
            "</skill>"
        )

    def to_full_context(self) -> str:
        """Render a full XML-like context block that includes the skill body content."""
        scripts_info = self._render_scripts_block()
        return (
            f'<skill name="{self.name}" path="{self.path}">\n'
            f"<description>{self.description}</description>"
            f"{scripts_info}\n"
            "<content>\n"
            f"{self.content}\n"
            "</content>\n"
            "</skill>"
        )

    def to_context(self) -> str:
        """Render the default context representation used by the runtime."""
        return self.to_metadata_context()

    def _render_scripts_block(self) -> str:
        if not self.scripts:
            return ""
        scripts_list = "\n".join(
            f"  - {script.name} ({script.language}): {script.description or 'No description'}"
            for script in self.scripts
        )
        return f"\n<available_scripts>\n{scripts_list}\n</available_scripts>"
