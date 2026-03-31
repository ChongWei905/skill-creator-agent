from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from skill_creator_agent.runtime import SkillCreatorRuntime


@dataclass(frozen=True)
class DraftSkillContext:
    draft_id: str
    draft_root: Path
    skill_slug: str
    skill_dir: Path
    skill_md_path: Path
    scripts_dir: Path
    primary_script_path: Path


class DraftSkillManager:
    def __init__(self, session_root: Path):
        """Initialize draft and archive directories for one session."""
        self.session_root = session_root.resolve()
        self.drafts_root = (self.session_root / "drafts").resolve()
        self.archives_root = (self.session_root / "draft_archives").resolve()
        self.drafts_root.mkdir(parents=True, exist_ok=True)
        self.archives_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def build_runtime(
        *,
        base_runtime: SkillCreatorRuntime,
        draft: DraftSkillContext,
    ) -> SkillCreatorRuntime:
        """Build a runtime that points at the draft root instead of published skills."""
        config = {
            "SKILL_CREATOR": {
                "skills_root": str(draft.draft_root),
                "graph_enabled": base_runtime.settings.graph_enabled,
                "graph_base_url": base_runtime.settings.graph_base_url,
                "graph_url_suffix": base_runtime.settings.graph_url_suffix,
                "graph_timeout": base_runtime.settings.graph_timeout,
            }
        }
        return SkillCreatorRuntime.from_config(config)

    @staticmethod
    def ensure_draft_scaffold(
        *,
        base_runtime: SkillCreatorRuntime,
        draft: DraftSkillContext,
        description: str,
    ) -> SkillCreatorRuntime:
        """Ensure the draft skill scaffold exists and return its dedicated runtime."""
        draft_runtime = DraftSkillManager.build_runtime(base_runtime=base_runtime, draft=draft)
        if draft.skill_md_path.exists():
            return draft_runtime
        draft_runtime.create_skill_scaffold(
            draft.skill_slug,
            description or draft.skill_slug,
        )
        return draft_runtime

    @staticmethod
    def promote_draft(
        *,
        draft: DraftSkillContext,
        published_runtime: SkillCreatorRuntime,
    ) -> Path:
        """Promote one reviewed draft into the published skills directory."""
        published_root = published_runtime.ensure_skills_root()
        target = (published_root / draft.skill_slug).resolve()
        if not draft.skill_dir.exists():
            raise FileNotFoundError(f"Draft skill does not exist: {draft.skill_dir}")
        shutil.copytree(draft.skill_dir, target, dirs_exist_ok=True)
        published_runtime.reload_skill(draft.skill_slug)
        return target

    def prepare_draft(self, *, skill_slug: str, build_version: int) -> DraftSkillContext:
        """Create the filesystem context metadata for one new draft build."""
        draft_id = f"build-v{build_version:02d}"
        draft_root = (self.drafts_root / draft_id).resolve()
        draft_root.mkdir(parents=True, exist_ok=True)
        skill_dir = (draft_root / skill_slug).resolve()
        scripts_dir = (skill_dir / "scripts").resolve()
        skill_md_path = (skill_dir / "SKILL.md").resolve()
        primary_script_path = (scripts_dir / f"{skill_slug.replace('-', '_')}.py").resolve()
        return DraftSkillContext(
            draft_id=draft_id,
            draft_root=draft_root,
            skill_slug=skill_slug,
            skill_dir=skill_dir,
            skill_md_path=skill_md_path,
            scripts_dir=scripts_dir,
            primary_script_path=primary_script_path,
        )

    def archive_draft(self, draft: DraftSkillContext) -> Path:
        """Copy one draft directory into the archive area and return the archive path."""
        if not draft.draft_root.exists():
            return draft.draft_root
        target = (self.archives_root / draft.draft_id).resolve()
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(draft.draft_root, target)
        return target
