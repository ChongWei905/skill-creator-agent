from __future__ import annotations

from skill_creator_agent.orchestration.models import SessionState, StageResult, StageSpec
from skill_creator_agent.orchestration.stage_runner import StageRunner
from skill_creator_agent.orchestration.toolsets import SKILL_EXECUTION_TOOL_NAMES
from skill_creator_agent.prompts import STAGE_CONTEXT_EXISTING_SKILL, load_prompt
from skill_creator_agent.runtime import SkillCreatorRuntime


class ExistingSkillAgent:
    stage_name = "existing_skill"

    @classmethod
    def build_spec(cls, *, runtime: SkillCreatorRuntime, state: SessionState, query: str) -> StageSpec:
        """Build the stage spec used to discover or execute an existing skill."""
        skills = runtime.list_skills()
        allowed_tools = set(SKILL_EXECUTION_TOOL_NAMES) if skills else set()
        skill_metadata = "\n".join(f"- {item['name']}: {item['description']}" for item in skills[:20]) or "- None"
        return StageSpec(
            name=cls.stage_name,
            system_instructions=load_prompt(
                STAGE_CONTEXT_EXISTING_SKILL,
                user_goal=state.user_goal or query,
                allowed_tools=", ".join(sorted(allowed_tools)) or "none",
                skill_metadata=skill_metadata,
            ),
            allowed_tool_names=allowed_tools,
            constraints=(
                "Use only the registered skill inspection and execution tools in this stage. "
                "If no matching skill exists, ask whether a new skill should be created."
            ),
            include_skills=True,
        )

    @classmethod
    async def run(
        cls,
        *,
        runtime: SkillCreatorRuntime,
        stage_runner: StageRunner,
        state: SessionState,
        query: str,
        user_id: str,
        stage_session_id: str,
        stage_output_path,
    ) -> tuple[StageResult, object]:
        """Run the discovery stage and either answer directly or request creation."""
        skills = runtime.list_skills()
        if not skills:
            goal = state.user_goal or query or "当前需求"
            message = f"当前没有可用的技能可以直接处理“{goal}”。\n\n您是否希望我为您创建一个新的技能来处理这个需求？"
            return (
                StageResult(
                    stage_name=cls.stage_name,
                    result_code="need_create_confirmation",
                    user_message=message,
                ),
                None,
            )

        spec = cls.build_spec(runtime=runtime, state=state, query=query)
        execution = await stage_runner.run(
            spec=spec,
            runtime=runtime,
            query=query,
            user_id=user_id,
            stage_session_id=stage_session_id,
            stage_output_path=stage_output_path,
        )
        return (
            StageResult(
                stage_name=cls.stage_name,
                result_code="route_with_router",
                user_message=_extract_text(execution.response),
                raw_response=execution.response,
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
