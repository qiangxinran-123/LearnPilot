from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import LearningPlan, LearningTask
from backend.app.db.session import get_db
from backend.app.models import (
    LearningPlanAvailability,
    LearningPlanLevel,
    LearningPlanStatus,
    LearningTaskType,
    RecommendationAvailabilityStatus,
    RecommendationReasonCode,
)
from backend.app.repositories import LearningPlanRepository, UserRepository
from backend.app.schemas.learning_plan import LearningPlanRead, LearningPlanResponse, LearningTaskRead
from backend.app.schemas.recommendation import RecommendationContext, RecommendationResult
from backend.app.services.recommendation_context_service import (
    RecommendationContextError,
    RecommendationContextService,
)
from backend.app.services.recommendation_engine import RecommendationEngine

PLAN_SCHEMA_VERSION = "learning_plan_v1"
TASK_TEMPLATE_VERSION = "learning_task_templates_v1"


class LearningPlanError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class _TaskSpec:
    task_type: LearningTaskType
    title: str
    description: str
    estimated_minutes: int | None


class LearningPlanService:
    """Persist deterministic M6-2 results as small, reusable learning plans."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        recommendation_engine: RecommendationEngine | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.plans = LearningPlanRepository(session)
        self.users = UserRepository(session)
        self.contexts = RecommendationContextService(session)
        self.engine = recommendation_engine or RecommendationEngine()

    def get_current_for_configured_user(self, course_id: int) -> LearningPlanResponse:
        return self.get_current(user_id=self._configured_user_id(), course_id=course_id)

    def generate_for_configured_user(self, course_id: int) -> LearningPlanResponse:
        return self.generate(user_id=self._configured_user_id(), course_id=course_id)

    def get_current(self, *, user_id: int, course_id: int) -> LearningPlanResponse:
        context, recommendation = self._recommend(user_id=user_id, course_id=course_id)
        fingerprint = recommendation_context_fingerprint(context, recommendation)
        with self.session.begin():
            current = self.plans.get_current(user_id=user_id, course_id=course_id)
            if current is None:
                return LearningPlanResponse(
                    availability=LearningPlanAvailability.NOT_AVAILABLE,
                    recommendation_status=recommendation.availability_status,
                    plan_level=recommendation.plan_level,
                )
            available = (
                recommendation.availability_status == RecommendationAvailabilityStatus.AVAILABLE
                and current.context_fingerprint == fingerprint
                and current.target_node_id == recommendation.recommended_node_id
            )
            return LearningPlanResponse(
                availability=(LearningPlanAvailability.AVAILABLE if available else LearningPlanAvailability.STALE),
                recommendation_status=recommendation.availability_status,
                plan_level=recommendation.plan_level,
                plan=_read_plan(current),
            )

    def generate(self, *, user_id: int, course_id: int) -> LearningPlanResponse:
        context, recommendation = self._recommend(user_id=user_id, course_id=course_id)
        if recommendation.availability_status != RecommendationAvailabilityStatus.AVAILABLE:
            with self.session.begin():
                current = self.plans.get_current(user_id=user_id, course_id=course_id, for_update=True)
                if current is not None:
                    self.plans.supersede(current)
            return LearningPlanResponse(
                availability=LearningPlanAvailability.NOT_AVAILABLE,
                recommendation_status=recommendation.availability_status,
                plan_level=recommendation.plan_level,
            )

        target_id = recommendation.recommended_node_id
        total_priority = recommendation.priority_breakdown.total_priority
        if target_id is None or total_priority is None:
            raise LearningPlanError("INVALID_RECOMMENDATION", "Available recommendation is incomplete.")
        nodes = {node.knowledge_node_id: node for node in context.knowledge_nodes}
        target = nodes.get(target_id)
        if target is None or target.course_id != course_id:
            raise LearningPlanError("RECOMMENDED_NODE_NOT_FOUND", "Recommended knowledge node is not available.")
        fingerprint = recommendation_context_fingerprint(context, recommendation)
        task_specs = _task_specs(target.name, recommendation)

        try:
            with self.session.begin():
                current = self.plans.get_current(user_id=user_id, course_id=course_id, for_update=True)
                if current is not None and current.context_fingerprint == fingerprint:
                    return LearningPlanResponse(
                        availability=LearningPlanAvailability.AVAILABLE,
                        recommendation_status=recommendation.availability_status,
                        plan_level=recommendation.plan_level,
                        plan=_read_plan(current),
                        reused=True,
                    )
                if current is not None:
                    self.plans.supersede(current)
                plan = LearningPlan(
                    user_id=user_id,
                    course_id=course_id,
                    target_node_id=target_id,
                    reason_codes=[code.value for code in recommendation.reason_codes],
                    priority_score=total_priority,
                    priority_breakdown=recommendation.priority_breakdown.model_dump(mode="json"),
                    prerequisite_evidence=[
                        item.model_dump(mode="json") for item in recommendation.prerequisite_evidence
                    ],
                    blocked_target_node_ids=recommendation.blocked_target_node_ids,
                    context_fingerprint=fingerprint,
                    status=LearningPlanStatus.AVAILABLE,
                    active_slot=1,
                    plan_schema_version=PLAN_SCHEMA_VERSION,
                    tasks=[
                        LearningTask(
                            knowledge_node_id=target_id,
                            task_type=spec.task_type,
                            title=spec.title,
                            description=spec.description,
                            order_index=index,
                            estimated_minutes=spec.estimated_minutes,
                        )
                        for index, spec in enumerate(task_specs)
                    ],
                )
                self.plans.add(plan)
                response = LearningPlanResponse(
                    availability=LearningPlanAvailability.AVAILABLE,
                    recommendation_status=recommendation.availability_status,
                    plan_level=recommendation.plan_level,
                    plan=_read_plan(plan),
                )
            return response
        except IntegrityError as error:
            self.session.rollback()
            with self.session.begin():
                winner = self.plans.get_current(user_id=user_id, course_id=course_id)
                if winner is not None and winner.context_fingerprint == fingerprint:
                    return LearningPlanResponse(
                        availability=LearningPlanAvailability.AVAILABLE,
                        recommendation_status=recommendation.availability_status,
                        plan_level=recommendation.plan_level,
                        plan=_read_plan(winner),
                        reused=True,
                    )
            raise LearningPlanError(
                "LEARNING_PLAN_CONFLICT",
                "The learning plan changed concurrently; retry the request.",
            ) from error

    def _configured_user_id(self) -> int:
        with self.session.begin():
            user = self.users.get_by_email(self.settings.legacy_bootstrap_user)
            if user is None:
                raise LearningPlanError("USER_NOT_FOUND", "User not found.")
            return user.id

    def _recommend(self, *, user_id: int, course_id: int) -> tuple[RecommendationContext, RecommendationResult]:
        try:
            context = self.contexts.build_recommendation_context(user_id=user_id, course_id=course_id)
        except RecommendationContextError as error:
            raise LearningPlanError(error.code, str(error)) from error
        recommendation = self.engine.recommend(context)
        if recommendation.user_id != user_id or recommendation.course_id != course_id:
            raise LearningPlanError("INVALID_RECOMMENDATION", "Recommendation ownership does not match the request.")
        return context, recommendation


def recommendation_context_fingerprint(
    context: RecommendationContext,
    recommendation: RecommendationResult,
) -> str:
    payload = {
        "context": context.model_dump(mode="json"),
        "recommendation": recommendation.model_dump(mode="json"),
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "task_template_version": TASK_TEMPLATE_VERSION,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _task_specs(node_name: str, recommendation: RecommendationResult) -> tuple[_TaskSpec, ...]:
    safe_name = node_name.strip()[:180]
    if recommendation.plan_level == LearningPlanLevel.FOUNDATIONAL:
        return (
            _TaskSpec(
                LearningTaskType.CONCEPT_REVIEW,
                f"建立「{safe_name}」基础",
                "根据课程知识结构梳理核心定义与前置概念；本路线尚未使用个人掌握度作判断。",
                15,
            ),
            _TaskSpec(
                LearningTaskType.EXAMPLE_WALKTHROUGH,
                f"理解「{safe_name}」的基本用法",
                "从已有课程材料中选择相关示例并整理关键步骤；如资料不足，不虚构示例或来源。",
                20,
            ),
        )
    if recommendation.plan_level == LearningPlanLevel.PRELIMINARY:
        return (
            _TaskSpec(
                LearningTaskType.CONCEPT_REVIEW,
                f"核对「{safe_name}」核心概念",
                "结合当前有限的诊断依据复核定义、条件与易错点，并记录仍需进一步确认的问题。",
                15,
            ),
            _TaskSpec(
                LearningTaskType.TARGETED_PRACTICE,
                f"初步巩固「{safe_name}」",
                "使用已有练习做一次针对性核验；当前建议会随后续诊断与学习记录继续完善。",
                20,
            ),
        )
    if RecommendationReasonCode.REVIEW_NEEDED in recommendation.reason_codes:
        return (
            _TaskSpec(
                LearningTaskType.TARGETED_PRACTICE,
                f"巩固「{safe_name}」",
                "使用已有学习材料完成一次针对性巩固，并记录仍不确定的步骤；本任务不预设具体题目。",
                20,
            ),
        )
    return (
        _TaskSpec(
            LearningTaskType.CONCEPT_REVIEW,
            f"回顾「{safe_name}」核心概念",
            "梳理定义、关键条件与常见误区；如缺少课程资料，仅记录需要进一步确认的问题。",
            15,
        ),
        _TaskSpec(
            LearningTaskType.EXAMPLE_WALKTHROUGH,
            f"分析「{safe_name}」示例思路",
            "从已有材料中选择相关示例并整理分析步骤；如无可用示例，不虚构题目或来源。",
            20,
        ),
        _TaskSpec(
            LearningTaskType.TARGETED_PRACTICE,
            f"练习「{safe_name}」",
            "使用已有练习进行针对性巩固并记录疑点；本任务只描述学习活动，不生成练习内容。",
            20,
        ),
    )


def _read_plan(plan: LearningPlan) -> LearningPlanRead:
    tasks = sorted(plan.tasks, key=lambda task: (task.order_index, task.id or 0))
    return LearningPlanRead(
        plan_id=plan.id,
        user_id=plan.user_id,
        course_id=plan.course_id,
        target_node_id=plan.target_node_id,
        reason_codes=plan.reason_codes,
        priority_score=plan.priority_score,
        priority_breakdown=plan.priority_breakdown,
        prerequisite_evidence=plan.prerequisite_evidence,
        blocked_target_node_ids=plan.blocked_target_node_ids,
        status=plan.status,
        tasks=[
            LearningTaskRead(
                task_id=task.id,
                knowledge_node_id=task.knowledge_node_id,
                task_type=task.task_type,
                title=task.title,
                description=task.description,
                order_index=task.order_index,
                estimated_minutes=task.estimated_minutes,
            )
            for task in tasks
        ],
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def get_learning_plan_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LearningPlanService:
    return LearningPlanService(session, settings)


__all__ = [
    "LearningPlanError",
    "LearningPlanService",
    "get_learning_plan_service",
    "recommendation_context_fingerprint",
]
