from __future__ import annotations

import re

from skill_creator_agent.orchestration.drafts import DraftSkillContext, DraftSkillManager
from skill_creator_agent.orchestration.models import BuildVersion, SessionState, StageResult, StageSpec
from skill_creator_agent.orchestration.stage_runner import StageRunner
from skill_creator_agent.orchestration.toolsets import (
    BUILD_FILE_TOOL_NAMES,
    GRAPH_TOOL_NAMES,
    SKILL_CREATION_TOOL_NAMES,
)
from skill_creator_agent.prompts import (
    GRAPH_CONNECTOR_PYTHON_CONTRACT,
    STAGE_CONTEXT_BUILD_RUN,
    load_prompt,
)
from skill_creator_agent.runtime import SkillCreatorRuntime


class BuildRunAgent:
    stage_name = "build_run"

    @staticmethod
    def register_build(
        *,
        state: SessionState,
        artifact_ref: str,
        draft_id: str,
        skill_slug: str,
    ) -> BuildVersion:
        """Append one build version in review state to the session history."""
        approved_plan = state.approved_plan
        if approved_plan is None:
            raise RuntimeError("Cannot register build without an approved plan.")
        build = BuildVersion(
            version=state.next_build_version(),
            plan_version=approved_plan.version,
            draft_id=draft_id,
            artifact_ref=artifact_ref,
            status="in_review",
            skill_slug=skill_slug,
        )
        state.build_history.append(build)
        state.pending_review_build_version = build.version
        state.active_draft_id = draft_id
        return build

    @classmethod
    def build_spec(
        cls,
        *,
        runtime: SkillCreatorRuntime,
        state: SessionState,
        approved_plan: str,
        draft: DraftSkillContext,
    ) -> StageSpec:
        """Build the stage spec used to implement and execute one approved draft skill."""
        allowed_tools = (
            set(BUILD_FILE_TOOL_NAMES)
            | set(SKILL_CREATION_TOOL_NAMES)
            | {"execute_skill_script"}
        )
        if runtime.settings.graph_enabled:
            allowed_tools |= set(GRAPH_TOOL_NAMES)
        return StageSpec(
            name=cls.stage_name,
            system_instructions=load_prompt(
                STAGE_CONTEXT_BUILD_RUN,
                user_goal=state.user_goal,
                approved_plan=approved_plan,
                skill_slug=draft.skill_slug,
                skill_title=_titleize_slug(draft.skill_slug),
                skill_dir=str(draft.skill_dir),
                skill_md_path=str(draft.skill_md_path),
                scripts_dir=str(draft.scripts_dir),
                primary_script_path=str(draft.primary_script_path),
                allowed_tools=", ".join(sorted(allowed_tools)),
                graph_connector_python_contract=load_prompt(GRAPH_CONNECTOR_PYTHON_CONTRACT),
            ),
            allowed_tool_names=allowed_tools,
            constraints=(
                "Stay within the draft skill directory. "
                "Create or repair the draft until it runs successfully or reaches a clear hard failure."
            ),
            include_skills=False,
            model_params_overrides={"max_tokens": 4096, "max_retries": 3},
        )

    @classmethod
    async def run(
        cls,
        *,
        published_runtime: SkillCreatorRuntime,
        draft_manager: DraftSkillManager,
        stage_runner: StageRunner,
        state: SessionState,
        approved_plan: str,
        user_id: str,
        stage_session_id: str,
        stage_output_path,
    ) -> tuple[StageResult, object, DraftSkillContext]:
        """Run the build-and-execute stage for the currently approved plan."""
        approved = state.approved_plan
        if approved is None:
            raise RuntimeError("BuildRunAgent requires an approved plan.")
        build_version = state.next_build_version()
        draft = draft_manager.prepare_draft(
            skill_slug=approved.skill_slug or "generated-skill",
            build_version=build_version
        )
        draft_runtime = draft_manager.ensure_draft_scaffold(
            base_runtime=published_runtime,
            draft=draft,
            description=_derive_description(approved_plan, state.user_goal),
        )
        spec = cls.build_spec(runtime=draft_runtime, state=state, approved_plan=approved_plan, draft=draft)
        execution = await stage_runner.run(
            spec=spec,
            runtime=draft_runtime,
            query="Build, run, and refine the approved draft skill.",
            user_id=user_id,
            stage_session_id=stage_session_id,
            stage_output_path=stage_output_path,
        )
        text = _extract_text(execution.response)
        result_code = "hard_error" if "hard failure" in text.lower() or "未跑通" in text else "build_ready_for_review"
        return (
            StageResult(
                stage_name=cls.stage_name,
                result_code=result_code,
                user_message=text,
                raw_response=execution.response,
                metadata={
                    "draft_id": draft.draft_id,
                    "skill_slug": draft.skill_slug,
                },
            ),
            execution.data_agent,
            draft,
        )


def _extract_text(response: object) -> str:
    if isinstance(response, dict):
        messages = response.get("messages", [])
        if messages:
            return str(getattr(messages[-1], "content", messages[-1]))
        final_answer = response.get("final_answer")
        if final_answer is not None:
            return str(final_answer)
    return str(response)


def _derive_description(approved_plan: str, user_goal: str) -> str:
    match = re.search(r"\*\*描述\*\*[：:]\s*(.+)", approved_plan)
    if match:
        return match.group(1).strip()
    normalized_goal = user_goal.strip()
    if normalized_goal:
        return normalized_goal[:120]
    return "Generated skill draft"


def _titleize_slug(slug: str) -> str:
    parts = [part for part in slug.split("-") if part]
    if not parts:
        return "Generated Skill"
    return " ".join(part.capitalize() for part in parts)
