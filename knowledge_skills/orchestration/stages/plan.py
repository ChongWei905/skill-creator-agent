from __future__ import annotations

import hashlib
import re

from knowledge_skills.orchestration.models import PlanVersion, SessionState, StageResult, StageSpec
from knowledge_skills.orchestration.stage_runner import StageRunner
from knowledge_skills.orchestration.toolsets import PLAN_GRAPH_TOOL_NAMES
from knowledge_skills.prompts import GRAPH_DB_INSTRUCTION, STAGE_CONTEXT_PLAN_AGENT, load_prompt
from knowledge_skills.runtime import SkillCreatorRuntime


class PlanAgent:
    stage_name = "plan"

    @staticmethod
    def register_plan(
        *,
        state: SessionState,
        artifact_ref: str,
        skill_name: str,
        skill_slug: str,
    ) -> PlanVersion:
        """Append one new plan version to session state and return it."""
        previous_plan = state.current_plan.version if state.current_plan else None
        plan = PlanVersion(
            version=state.next_plan_version(),
            artifact_ref=artifact_ref,
            status="proposed",
            skill_name=skill_name,
            skill_slug=skill_slug,
            based_on_plan_version=previous_plan,
        )
        state.plan_history.append(plan)
        return plan

    @classmethod
    def build_spec(
        cls,
        *,
        runtime: SkillCreatorRuntime,
        state: SessionState,
        previous_plan_text: str,
        revision_feedback_text: str,
    ) -> StageSpec:
        """Build the stage spec used to draft or revise the user-facing plan document."""
        reference_bundle = state.reference_summary or "未提供参考资料。"
        allowed_tools = set(PLAN_GRAPH_TOOL_NAMES) if runtime.settings.graph_enabled else set()
        return StageSpec(
            name=cls.stage_name,
            system_instructions=load_prompt(
                STAGE_CONTEXT_PLAN_AGENT,
                user_goal=state.user_goal,
                reference_bundle=reference_bundle,
                previous_plan=previous_plan_text or "无",
                revision_feedback=revision_feedback_text or "无",
                allowed_tools=", ".join(sorted(allowed_tools)) or "none",
                graph_db_instruction=load_prompt(GRAPH_DB_INSTRUCTION)
                if runtime.settings.graph_enabled
                else "Graph access is disabled for this session.",
            ),
            allowed_tool_names=allowed_tools,
            constraints=(
                "Produce a user-facing plan document only. "
                "Do not discuss internal file layouts or implementation-only details."
            ),
            include_skills=False,
            model_params_overrides={"max_tokens": 3072, "max_retries": 3},
        )

    @classmethod
    async def run(
        cls,
        *,
        runtime: SkillCreatorRuntime,
        stage_runner: StageRunner,
        state: SessionState,
        previous_plan_text: str,
        revision_feedback_text: str,
        user_id: str,
        stage_session_id: str,
        stage_output_path,
    ) -> tuple[StageResult, object]:
        """Run the planning stage and capture plan metadata from the returned text."""
        spec = cls.build_spec(
            runtime=runtime,
            state=state,
            previous_plan_text=previous_plan_text,
            revision_feedback_text=revision_feedback_text,
        )
        query = "Create or revise the user-facing plan document and ask for approval."
        execution = await stage_runner.run(
            spec=spec,
            runtime=runtime,
            query=query,
            user_id=user_id,
            stage_session_id=stage_session_id,
            stage_output_path=stage_output_path,
        )
        text = _extract_text(execution.response)
        skill_name = _extract_plan_field(text, "技能名称")
        skill_description = _extract_plan_field(text, "描述")
        skill_slug = _select_skill_slug(
            skill_name=skill_name,
            description=skill_description,
            user_goal=state.user_goal,
        )
        return (
            StageResult(
                stage_name=cls.stage_name,
                result_code="plan_ready",
                user_message=text,
                raw_response=execution.response,
                metadata={
                    "skill_name": skill_name,
                    "skill_description": skill_description,
                    "skill_slug": skill_slug,
                },
            ),
            execution.data_agent,
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


def _extract_plan_field(text: str, label: str) -> str:
    match = re.search(rf"\*\*{re.escape(label)}\*\*[：:]\s*(.+)", text)
    if match:
        return match.group(1).strip().strip("`")
    return ""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if slug:
        return slug
    normalized = text.strip()
    if not normalized:
        return "generated-skill"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"skill-{digest}"


def _select_skill_slug(*, skill_name: str, description: str, user_goal: str) -> str:
    for candidate in (skill_name, description):
        slug = _slugify(candidate)
        if slug and not slug.startswith("skill-"):
            return slug
    return _slugify(skill_name or description or user_goal or "generated-skill")
