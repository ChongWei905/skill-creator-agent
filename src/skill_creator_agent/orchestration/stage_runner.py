from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ferry.interface.sdk.agent import DataAgent

from skill_creator_agent.ferry_config import build_ferry_config, materialize_ferry_config
from skill_creator_agent.ferry_tools import configure_runtime_tools
from skill_creator_agent.orchestration.ferry import reset_ferry_singletons
from skill_creator_agent.orchestration.models import StageSpec
from skill_creator_agent.runtime import SkillCreatorRuntime


@dataclass
class StageExecutionResult:
    data_agent: DataAgent
    response: dict[str, Any]
    rendered_config_path: Path


class StageRunner:
    def __init__(
        self,
        *,
        source_config: Mapping[str, Any],
        ferry_config_path: Path,
    ) -> None:
        """Store the base config used to materialize one-off stage executions."""
        self.source_config = dict(source_config)
        self.ferry_config_path = ferry_config_path.resolve()

    async def run(
        self,
        *,
        spec: StageSpec,
        runtime: SkillCreatorRuntime,
        query: str,
        user_id: str,
        stage_session_id: str,
        stage_output_path: Path,
        clear_history: bool = True,
    ) -> StageExecutionResult:
        """Execute one stage through Ferry and return its response bundle."""
        data_agent = self.build_data_agent(spec=spec, runtime=runtime)
        response = await data_agent.chat(
            query,
            session_id=stage_session_id,
            clear_history=clear_history,
            output_path=stage_output_path,
            initial_state={
                "user_id": user_id,
                "run_id": 0,
                "sub_id": 0,
                "complete": False,
                "messages": [],
            },
        )
        return StageExecutionResult(
            data_agent=data_agent,
            response=response,
            rendered_config_path=self.ferry_config_path,
        )

    def build_data_agent(
        self,
        *,
        spec: StageSpec,
        runtime: SkillCreatorRuntime,
    ) -> DataAgent:
        """Materialize Ferry config for one stage and build its DataAgent instance."""
        reset_ferry_singletons()
        configure_runtime_tools(config=self.source_config, runtime=runtime)
        materialize_ferry_config(
            self.source_config,
            runtime=runtime,
            output_path=self.ferry_config_path,
            system_instructions=spec.system_instructions,
            system_constraints=spec.constraints,
            allowed_local_tool_names=spec.allowed_tool_names,
            model_params_overrides=spec.model_params_overrides,
            include_skills=spec.include_skills,
        )
        return DataAgent.from_config(self.ferry_config_path)

    def preview_config(
        self,
        *,
        spec: StageSpec,
        runtime: SkillCreatorRuntime,
    ) -> dict[str, Any]:
        """Preview the rendered Ferry config for one stage without executing it."""
        return build_ferry_config(
            self.source_config,
            runtime=runtime,
            system_instructions=spec.system_instructions,
            system_constraints=spec.constraints,
            allowed_local_tool_names=spec.allowed_tool_names,
            model_params_overrides=spec.model_params_overrides,
            include_skills=spec.include_skills,
        )
