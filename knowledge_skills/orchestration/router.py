from __future__ import annotations

import json
from typing import Any

from ferry.core.managers.llm_manager import llm_manager

from knowledge_skills.orchestration.models import (
    AWAIT_BUILD_REVIEW,
    AWAIT_CREATE_CONFIRMATION,
    AWAIT_PLAN_APPROVAL,
    AWAIT_REFERENCES,
    BUILDING_AND_RUNNING,
    CANCELLED,
    DONE,
    ERROR,
    IDLE,
    PLANNING,
    RouterDecision,
    SessionState,
)
from knowledge_skills.prompts import UNIFIED_ROUTER, load_prompt

ALLOWED_USER_DECISIONS: dict[str, tuple[str, ...]] = {
    AWAIT_CREATE_CONFIRMATION: ("confirm_create", "decline_create", "switch_goal", "clarify", "cancel"),
    AWAIT_REFERENCES: (
        "provide_references",
        "no_references",
        "clarify_references",
        "switch_goal",
        "clarify",
        "cancel",
    ),
    AWAIT_PLAN_APPROVAL: ("approve_plan", "revise_plan", "switch_goal", "clarify", "cancel"),
    AWAIT_BUILD_REVIEW: ("accept_build", "revise_plan", "switch_goal", "clarify", "cancel"),
}

USER_NEXT_STATES: dict[str, dict[str, str]] = {
    AWAIT_CREATE_CONFIRMATION: {
        "confirm_create": AWAIT_REFERENCES,
        "decline_create": IDLE,
        "switch_goal": IDLE,
        "clarify": AWAIT_CREATE_CONFIRMATION,
        "cancel": CANCELLED,
    },
    AWAIT_REFERENCES: {
        "provide_references": PLANNING,
        "no_references": PLANNING,
        "clarify_references": AWAIT_REFERENCES,
        "switch_goal": IDLE,
        "clarify": AWAIT_REFERENCES,
        "cancel": CANCELLED,
    },
    AWAIT_PLAN_APPROVAL: {
        "approve_plan": BUILDING_AND_RUNNING,
        "revise_plan": PLANNING,
        "switch_goal": IDLE,
        "clarify": AWAIT_PLAN_APPROVAL,
        "cancel": CANCELLED,
    },
    AWAIT_BUILD_REVIEW: {
        "accept_build": DONE,
        "revise_plan": PLANNING,
        "switch_goal": IDLE,
        "clarify": AWAIT_BUILD_REVIEW,
        "cancel": CANCELLED,
    },
}

WORKER_DECISIONS: dict[str, tuple[str, str]] = {
    "task_answered": ("task_answered", DONE),
    "need_create_confirmation": ("need_create_confirmation", AWAIT_CREATE_CONFIRMATION),
    "plan_ready": ("plan_ready", AWAIT_PLAN_APPROVAL),
    "build_ready_for_review": ("build_ready_for_review", AWAIT_BUILD_REVIEW),
    "completed": ("completed", DONE),
    "hard_error": ("hard_error", ERROR),
}

WORKER_ALLOWED_DECISIONS: dict[str, tuple[str, ...]] = {
    "ExistingSkillAgent": ("task_answered", "need_create_confirmation", "hard_error"),
    "PlanAgent": ("plan_ready", "hard_error"),
    "BuildRunAgent": ("build_ready_for_review", "hard_error"),
}

WORKER_ALLOWED_STATES: dict[str, dict[str, str]] = {
    "ExistingSkillAgent": {
        "task_answered": DONE,
        "need_create_confirmation": AWAIT_CREATE_CONFIRMATION,
        "hard_error": ERROR,
    },
    "PlanAgent": {
        "plan_ready": AWAIT_PLAN_APPROVAL,
        "hard_error": ERROR,
    },
    "BuildRunAgent": {
        "build_ready_for_review": AWAIT_BUILD_REVIEW,
        "hard_error": ERROR,
    },
}


class UnifiedRouter:
    def __init__(self, model_name: str) -> None:
        """Create a router bound to one Ferry-managed LLM name."""
        self.model_name = model_name

    @staticmethod
    def _normalize_router_output(
        raw: dict[str, Any],
        *,
        fallback_state: str,
        fallback_decision: str,
        allowed_decisions: set[str],
        allowed_states: set[str],
    ) -> RouterDecision:
        decision = str(raw.get("decision", "")).strip()
        next_state = str(raw.get("next_state", "")).strip()
        if decision not in allowed_decisions:
            decision = fallback_decision
        if next_state not in allowed_states:
            next_state = fallback_state
        goal_action = raw.get("goal_action")
        feedback_action = raw.get("feedback_action")
        question_action = raw.get("question_action")
        router_decision = RouterDecision(
            decision=decision,
            next_state=next_state,
            confidence=float(raw.get("confidence", 0) or 0),
            needs_clarification=bool(raw.get("needs_clarification", False)),
            normalized_goal=str((goal_action or {}).get("normalized_goal", "")).strip(),
            feedback_type=str((feedback_action or {}).get("type", "none")).strip() or "none",
            feedback_summary=str((feedback_action or {}).get("summary", "")).strip(),
            next_question_type=str((question_action or {}).get("next_question_type", "none")).strip() or "none",
            reuse_previous_plan=bool((question_action or {}).get("reuse_previous_plan", False)),
        )
        if router_decision.next_question_type == "none":
            router_decision.next_question_type = _decision_question_type(decision)
        return router_decision

    async def route_user_reply(
        self,
        state: SessionState,
        reply: str,
        *,
        reference_intake: dict[str, Any] | None = None,
    ) -> RouterDecision:
        """Route one user reply from the current workflow state into the next state."""
        allowed = ALLOWED_USER_DECISIONS.get(state.workflow_stage)
        if not allowed:
            return RouterDecision(decision="clarify", next_state=state.workflow_stage, needs_clarification=True)

        next_states = [USER_NEXT_STATES[state.workflow_stage][item] for item in allowed]
        fallback_decision = "clarify_references" if state.workflow_stage == AWAIT_REFERENCES else "clarify"
        raw = await self._invoke_router(
            event_type="user_reply",
            state=state,
            allowed_decisions=allowed,
            allowed_next_states=next_states,
            latest_user_reply=reply,
            worker_result={},
            reference_intake=reference_intake,
        )
        return self._normalize_router_output(
            raw,
            fallback_state=state.workflow_stage,
            fallback_decision=fallback_decision,
            allowed_decisions=set(allowed),
            allowed_states=set(next_states),
        )

    async def route_worker_result(
        self,
        state: SessionState,
        *,
        worker_name: str,
        result_code: str,
        assistant_text: str,
    ) -> RouterDecision:
        """Route one stage result into the next workflow state."""
        if result_code in WORKER_DECISIONS:
            decision, next_state = WORKER_DECISIONS[result_code]
            return RouterDecision(
                decision=decision,
                next_state=next_state,
                confidence=1.0,
                next_question_type=_decision_question_type(decision),
            )
        allowed_decisions = WORKER_ALLOWED_DECISIONS.get(worker_name)
        allowed_state_map = WORKER_ALLOWED_STATES.get(worker_name)
        if allowed_decisions and allowed_state_map:
            raw = await self._invoke_router(
                event_type="worker_result",
                state=state,
                allowed_decisions=allowed_decisions,
                allowed_next_states=[allowed_state_map[item] for item in allowed_decisions],
                latest_user_reply="",
                worker_result={
                    "worker_name": worker_name,
                    "result_code": result_code,
                    "assistant_text": assistant_text,
                },
                reference_intake=None,
            )
            return self._normalize_router_output(
                raw,
                fallback_state=allowed_state_map[allowed_decisions[0]],
                fallback_decision=allowed_decisions[0],
                allowed_decisions=set(allowed_decisions),
                allowed_states=set(allowed_state_map.values()),
            )
        return RouterDecision(
            decision="clarify",
            next_state=state.workflow_stage,
            confidence=0.0,
            needs_clarification=True,
            next_question_type="clarification",
        )

    async def _invoke_router(
        self,
        *,
        event_type: str,
        state: SessionState,
        allowed_decisions: tuple[str, ...] | list[str],
        allowed_next_states: tuple[str, ...] | list[str],
        latest_user_reply: str,
        worker_result: dict[str, Any],
        reference_intake: dict[str, Any] | None,
    ) -> dict[str, Any]:
        llm = llm_manager.get_llm(self.model_name)
        if llm is None:
            raise RuntimeError(f"Router LLM not found: {self.model_name}")
        prompt = load_prompt(
            UNIFIED_ROUTER,
            event_type=event_type,
            current_state=state.workflow_stage,
            last_question_type=state.last_question_type,
            allowed_decisions="\n".join(f"- {item}" for item in allowed_decisions),
            allowed_next_states="\n".join(f"- {item}" for item in allowed_next_states),
            goal_digest=json.dumps(
                {
                    "original_user_goal": state.user_goal,
                    "normalized_goal": state.normalized_goal or state.user_goal,
                },
                ensure_ascii=False,
                indent=2,
            ),
            state_digest=json.dumps(state.state_digest(), ensure_ascii=False, indent=2),
            latest_user_reply=latest_user_reply or "(none)",
            worker_result=(
                json.dumps(worker_result, ensure_ascii=False, indent=2)
                if worker_result
                else "(none)"
            ),
            reference_intake=(
                json.dumps(reference_intake, ensure_ascii=False, indent=2)
                if reference_intake
                else "(none)"
            ),
        )
        response = await llm.ainvoke(
            [{"role": "system", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return _parse_json(response.content)


def _parse_json(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return {}
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _decision_question_type(decision: str) -> str:
    mapping = {
        "confirm_create": "references_request",
        "need_create_confirmation": "create_confirmation",
        "plan_ready": "plan_approval",
        "build_ready_for_review": "build_review",
        "clarify_references": "references_request",
        "clarify": "clarification",
    }
    return mapping.get(decision, "none")
