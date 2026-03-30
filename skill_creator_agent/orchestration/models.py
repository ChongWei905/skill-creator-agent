from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

IDLE = "IDLE"
DISCOVERING = "DISCOVERING"
AWAIT_CREATE_CONFIRMATION = "AWAIT_CREATE_CONFIRMATION"
AWAIT_REFERENCES = "AWAIT_REFERENCES"
PLANNING = "PLANNING"
AWAIT_PLAN_APPROVAL = "AWAIT_PLAN_APPROVAL"
BUILDING_AND_RUNNING = "BUILDING_AND_RUNNING"
AWAIT_BUILD_REVIEW = "AWAIT_BUILD_REVIEW"
DONE = "DONE"
CANCELLED = "CANCELLED"
ERROR = "ERROR"


@dataclass
class PlanVersion:
    version: int
    artifact_ref: str
    status: str = "draft"
    skill_name: str = ""
    skill_slug: str = ""
    based_on_plan_version: int | None = None


@dataclass
class BuildVersion:
    version: int
    plan_version: int
    draft_id: str
    artifact_ref: str = ""
    status: str = "draft"
    skill_slug: str = ""


@dataclass
class SessionState:
    workflow_stage: str = IDLE
    active_turn_stage: str = "existing_skill"
    last_question_type: str = "none"
    last_user_reply: str = ""
    last_assistant_text: str = ""
    last_router_decision: str = ""
    user_goal: str = ""
    normalized_goal: str = ""
    reference_artifact_ref: str = ""
    reference_summary: str = ""
    latest_feedback_artifact_ref: str = ""
    plan_history: list[PlanVersion] = field(default_factory=list)
    approved_plan_version: int | None = None
    build_history: list[BuildVersion] = field(default_factory=list)
    pending_review_build_version: int | None = None
    active_draft_id: str = ""

    def reset(self) -> None:
        """Reset the session back to its initial idle state."""
        self.workflow_stage = IDLE
        self.active_turn_stage = "existing_skill"
        self.last_question_type = "none"
        self.last_user_reply = ""
        self.last_assistant_text = ""
        self.last_router_decision = ""
        self.user_goal = ""
        self.normalized_goal = ""
        self.reference_artifact_ref = ""
        self.reference_summary = ""
        self.latest_feedback_artifact_ref = ""
        self.plan_history.clear()
        self.approved_plan_version = None
        self.build_history.clear()
        self.pending_review_build_version = None
        self.active_draft_id = ""

    @property
    def current_plan(self) -> PlanVersion | None:
        """Return the most recent plan version recorded in this session."""
        if not self.plan_history:
            return None
        return self.plan_history[-1]

    @property
    def approved_plan(self) -> PlanVersion | None:
        """Return the plan version currently marked as approved, if any."""
        if self.approved_plan_version is None:
            return None
        for plan in reversed(self.plan_history):
            if plan.version == self.approved_plan_version:
                return plan
        return None

    @property
    def current_build(self) -> BuildVersion | None:
        """Return the most recent build version recorded in this session."""
        if not self.build_history:
            return None
        return self.build_history[-1]

    def next_plan_version(self) -> int:
        """Return the next sequential plan version number."""
        return len(self.plan_history) + 1

    def next_build_version(self) -> int:
        """Return the next sequential build version number."""
        return len(self.build_history) + 1

    def state_digest(self) -> dict[str, Any]:
        """Return a compact session summary for router prompting."""
        return {
            "reference_provided": bool(self.reference_artifact_ref),
            "current_plan_version": self.current_plan.version if self.current_plan else None,
            "approved_plan_version": self.approved_plan_version,
            "current_build_version": self.current_build.version if self.current_build else None,
            "pending_review_build_version": self.pending_review_build_version,
            "has_active_draft": bool(self.active_draft_id),
        }


@dataclass(frozen=True)
class StageSpec:
    name: str
    system_instructions: str
    allowed_tool_names: set[str]
    constraints: str
    include_skills: bool = False
    model_params_overrides: dict[str, Any] | None = None


@dataclass
class StageResult:
    stage_name: str
    result_code: str
    user_message: str
    raw_response: dict[str, Any] | None = None
    artifact_refs: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouterDecision:
    decision: str
    next_state: str
    confidence: float = 0.0
    needs_clarification: bool = False
    normalized_goal: str = ""
    feedback_type: str = "none"
    feedback_summary: str = ""
    next_question_type: str = "none"
    reuse_previous_plan: bool = False
