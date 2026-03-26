from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from skill_creator_agent.models import Skill, SkillScript

logger = logging.getLogger(__name__)


class SkillLoader:
    SCRIPT_EXTENSIONS = {
        ".py": "python",
        ".sh": "bash",
        ".bash": "bash",
        ".js": "node",
        ".ts": "tsx",
    }

    def __init__(self, skills_root: str | Path):
        """Initialize a loader bound to one skill root directory."""
        self.skills_root = Path(skills_root).expanduser().resolve()
        self.skills: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        """Load every valid skill package found under the configured root."""
        if not self.skills_root.exists():
            raise FileNotFoundError(f"Skills directory not found: {self.skills_root}")

        loaded: dict[str, Skill] = {}
        for skill_dir in sorted(self.skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill = self.load_skill_dir(skill_dir, strict=False)
            if skill:
                loaded[skill.name] = skill
        self.skills = loaded
        return dict(self.skills)

    def load_skill_dir(self, skill_dir: str | Path, *, strict: bool = True) -> Skill | None:
        """Load one skill directory and optionally skip invalid packages."""
        skill_path = Path(skill_dir).expanduser().resolve()
        skill_md_path = skill_path / "SKILL.md"
        if not skill_md_path.exists():
            if strict:
                raise FileNotFoundError(f"SKILL.md not found: {skill_md_path}")
            return None

        try:
            skill = self._parse_skill(skill_md_path)
        except ValueError as exc:
            if strict:
                raise
            logger.warning("Skipping invalid skill '%s': %s", skill_path.name, exc)
            return None

        self.skills[skill.name] = skill
        return skill

    def get_skill(self, name: str) -> Skill | None:
        """Return one loaded skill by name if it is currently cached."""
        return self.skills.get(name)

    def list_skill_names(self) -> list[str]:
        """Return all loaded skill names in stable sorted order."""
        return sorted(self.skills)

    def reload_skill(self, name: str) -> Skill:
        """Reload one skill from disk and refresh the cached representation."""
        current = self.skills.get(name)
        target_dir = current.path if current else self.skills_root / name
        skill = self.load_skill_dir(target_dir, strict=True)
        assert skill is not None
        return skill

    def validate_frontmatter(self, frontmatter: dict, skill_dir: str | Path) -> None:
        """Validate frontmatter against the loader's current skill package rules."""
        self._validate_frontmatter(frontmatter, Path(skill_dir).expanduser().resolve())

    def _parse_skill(self, skill_md_path: Path) -> Skill:
        frontmatter, body = self._split_frontmatter(skill_md_path.read_text(encoding="utf-8"))
        skill_dir = skill_md_path.parent
        self._validate_frontmatter(frontmatter, skill_dir)

        scripts = self._load_scripts(skill_dir)
        name = str(frontmatter.get("name") or skill_dir.name)
        description = str(frontmatter.get("description") or "")
        metadata = frontmatter.get("metadata")
        allowed_tools = frontmatter.get("allowed-tools")

        return Skill(
            name=name,
            description=description,
            content=body,
            path=skill_dir,
            allowed_tools=allowed_tools,
            metadata=metadata,
            scripts=scripts,
        )

    def _split_frontmatter(self, content: str) -> tuple[dict, str]:
        if not content.startswith("---"):
            raise ValueError("SKILL.md must start with YAML frontmatter")

        match = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
        if not match:
            raise ValueError("Unable to parse YAML frontmatter block")

        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise ValueError("Invalid YAML frontmatter") from exc

        if not isinstance(frontmatter, dict):
            raise ValueError("Frontmatter must deserialize to a mapping")
        return frontmatter, match.group(2).strip()

    def _validate_frontmatter(self, frontmatter: dict, skill_dir: Path) -> None:
        name = str(frontmatter.get("name") or skill_dir.name)
        description = str(frontmatter.get("description") or "")

        if name != skill_dir.name:
            raise ValueError("Skill directory name must match frontmatter name")
        if len(name) > 64:
            raise ValueError(f"name exceeds 64 characters: {len(name)}")
        if not re.match(r"^[a-z0-9-]+$", name):
            raise ValueError("name can only contain lowercase letters, numbers, and hyphens")
        if name.lower() in {"anthropic", "claude"}:
            raise ValueError(f"reserved skill name: {name}")
        if "<" in name or ">" in name:
            raise ValueError("name cannot contain XML tags")

        if not description.strip():
            raise ValueError("description cannot be empty")
        if len(description) > 1024:
            raise ValueError(f"description exceeds 1024 characters: {len(description)}")
        if "<" in description or ">" in description:
            raise ValueError("description cannot contain XML tags")

    def _load_scripts(self, skill_dir: Path) -> list[SkillScript]:
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.exists():
            return []

        loaded: list[SkillScript] = []
        for script_path in sorted(scripts_dir.iterdir()):
            if not script_path.is_file():
                continue
            language = self.SCRIPT_EXTENSIONS.get(script_path.suffix.lower())
            if not language:
                continue
            loaded.append(
                SkillScript(
                    name=script_path.stem,
                    path=script_path,
                    language=language,
                    description=self._extract_script_description(script_path),
                )
            )
        return loaded

    def _extract_script_description(self, script_path: Path) -> str:
        try:
            content = script_path.read_text(encoding="utf-8")
        except Exception:
            return ""

        if script_path.suffix == ".py":
            match = re.search(r'^"""(.*?)"""', content, re.DOTALL)
            if match:
                return match.group(1).strip().splitlines()[0]
        for line in content.splitlines()[:10]:
            if line.startswith("#") and not line.startswith("#!"):
                return line[1:].strip()
        return ""
