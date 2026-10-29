from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import Response
from backend.app.models import ConfidenceLevel, EvidenceSourceType, MasteryStatus
from backend.app.repositories import StudentKnowledgeStateRepository
from backend.app.schemas.mastery_api import KnowledgeStateAvailability
from backend.app.schemas.review_risk import ReviewReason, ReviewRiskItem, ReviewRiskLevel, ReviewRiskResponse
from backend.app.services.mastery_read_service import is_persisted_mastery_state_current
from backend.app.services.progress_analytics_service import ProgressAnalyticsService

# Transparent V1 reminders, not estimates of forgetting or M6 priorities.
WATCH_INTERVAL = timedelta(days=14)
DUE_INTERVAL = timedelta(days=30)
MIN_RECENT_PRACTICE_FACTS = 3

REASONS = {
    ReviewReason.STALE_MASTERY: "当前掌握状态已过期，暂无法判断复习需求。",
    ReviewReason.UNAVAILABLE_MASTERY: "当前学习证据不足，暂无法判断复习需求。",
    ReviewReason.INVALID_PRACTICE_TIME: "练习时间异常，暂无法判断复习需求。",
    ReviewReason.WEAK_MASTERY: "当前掌握状态提示该知识点可能薄弱，值得巩固。",
    ReviewReason.REINFORCEMENT: "当前掌握状态提示仍需要巩固。",
    ReviewReason.NO_PRACTICE: "尚无有效练习记录，可考虑通过练习巩固。",
    ReviewReason.LOW_CONFIDENCE: "当前掌握度置信度较低，可通过练习增加证据。",
    ReviewReason.LONG_GAP: "距离最近一次有效练习已有较长时间，可考虑复习。",
    ReviewReason.MODERATE_GAP: "距离最近一次有效练习已有一段时间，可关注后续巩固。",
    ReviewReason.LIMITED_RECENT_PRACTICE: "近期有效练习证据较少，可继续积累练习记录。",
    ReviewReason.RECENT_PRACTICE: "近期有有效练习，当前没有明显复习提醒。",
}
ORDER = {
    ReviewRiskLevel.REVIEW_DUE: 0,
    ReviewRiskLevel.WATCH: 1,
    ReviewRiskLevel.INSUFFICIENT_DATA: 2,
    ReviewRiskLevel.LOW_RISK: 3,
}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ReviewRiskService:
    def __init__(self, session: Session, settings: Settings, *, now: datetime | None = None) -> None:
        self.session = session
        self.analytics = ProgressAnalyticsService(session, settings)
        self.now = utc(now or datetime.now(timezone.utc))

    def assess(self, course_id: int, *, limit: int = 100) -> ReviewRiskResponse:
        nodes = self.analytics.knowledge(course_id).nodes
        mastery = self.analytics.mastery
        owner_id = mastery._require_owner_id()
        rows = mastery.evidence.list_submitted_for_current_nodes(
            user_id=owner_id, course_id=course_id, knowledge_node_ids=[n.node_id for n in nodes]
        )
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.current_knowledge_node_id].append(row)
        submitted_times = dict(
            self.session.execute(
                select(Response.id, Response.submitted_at).where(
                    Response.id.in_([row.source_response_id for row in rows])
                )
            ).all()
        )
        states = {
            s.knowledge_node_id: s
            for s in StudentKnowledgeStateRepository(self.session).list_by_course_and_user(
                user_id=owner_id, course_id=course_id
            )
        }
        items = []
        counts = {level: 0 for level in ReviewRiskLevel}
        for node in nodes:
            state = states.get(node.node_id)
            evidence = grouped[node.node_id]
            valid = (
                node.calculation_state == KnowledgeStateAvailability.CALCULATED
                and node.mastery_score is not None
                and node.confidence_level != ConfidenceLevel.INSUFFICIENT
                and state is not None
                and state.mastery_score == node.mastery_score
                and state.mastery_status == node.mastery_status
                and state.confidence_level == node.confidence_level
                and state.evidence_count == node.evidence_count
                and is_persisted_mastery_state_current(node_id=node.node_id, state=state, rows=evidence)
            )
            practice = [row for row in evidence if row.source_type == EvidenceSourceType.PRACTICE]
            practice_times = [submitted_times.get(row.source_response_id) for row in practice]
            invalid_time = any(value is None or utc(value) > self.now for value in practice_times)
            last = max((utc(value) for value in practice_times if value is not None), default=None)
            invalid_reread = (
                node.calculation_state == KnowledgeStateAvailability.CALCULATED
                and node.mastery_score is not None
                and not valid
            )
            if not valid:
                level = ReviewRiskLevel.INSUFFICIENT_DATA
                reason = (
                    ReviewReason.STALE_MASTERY
                    if node.calculation_state == KnowledgeStateAvailability.STALE or invalid_reread
                    else ReviewReason.UNAVAILABLE_MASTERY
                )
                last = None
            elif invalid_time:
                level, reason, last = ReviewRiskLevel.INSUFFICIENT_DATA, ReviewReason.INVALID_PRACTICE_TIME, None
            elif node.mastery_status in {MasteryStatus.POSSIBLY_WEAK, MasteryStatus.NEEDS_ATTENTION}:
                level, reason = ReviewRiskLevel.REVIEW_DUE, ReviewReason.WEAK_MASTERY
            elif node.mastery_status == MasteryStatus.NEEDS_REINFORCEMENT:
                level, reason = ReviewRiskLevel.WATCH, ReviewReason.REINFORCEMENT
            elif last is None:
                level, reason = ReviewRiskLevel.WATCH, ReviewReason.NO_PRACTICE
            elif node.confidence_level == ConfidenceLevel.LOW:
                level, reason = ReviewRiskLevel.WATCH, ReviewReason.LOW_CONFIDENCE
            elif self.now - last >= DUE_INTERVAL:
                level, reason = ReviewRiskLevel.REVIEW_DUE, ReviewReason.LONG_GAP
            elif self.now - last >= WATCH_INTERVAL:
                level, reason = ReviewRiskLevel.WATCH, ReviewReason.MODERATE_GAP
            elif (
                len(
                    {
                        row.source_response_id
                        for row in practice
                        if submitted_times.get(row.source_response_id) is not None
                        and self.now - utc(submitted_times[row.source_response_id]) < WATCH_INTERVAL
                    }
                )
                < MIN_RECENT_PRACTICE_FACTS
            ):
                level, reason = ReviewRiskLevel.WATCH, ReviewReason.LIMITED_RECENT_PRACTICE
            else:
                level, reason = ReviewRiskLevel.LOW_RISK, ReviewReason.RECENT_PRACTICE
            counts[level] += 1
            items.append(
                ReviewRiskItem(
                    knowledge_node_id=node.node_id,
                    name=node.name,
                    mastery_score=str(node.mastery_score) if valid else None,
                    mastery_status=node.mastery_status if valid else MasteryStatus.NOT_ASSESSED,
                    confidence_level=node.confidence_level if valid else ConfidenceLevel.INSUFFICIENT,
                    calculation_state=KnowledgeStateAvailability.STALE if invalid_reread else node.calculation_state,
                    evidence_count=node.evidence_count if valid else 0,
                    risk_level=level,
                    reason_code=reason,
                    reason_text=REASONS[reason],
                    last_practice_at=last,
                    days_since_practice=(self.now - last).days if last else None,
                )
            )
        items.sort(key=lambda item: (ORDER[item.risk_level], item.knowledge_node_id))
        return ReviewRiskResponse(
            course_id=course_id, assessed_at=self.now, total_node_count=len(nodes), counts=counts, items=items[:limit]
        )
