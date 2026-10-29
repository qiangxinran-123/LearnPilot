from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import MasteryHistory
from backend.app.schemas.progress_trend import ProgressTrend, ProgressTrendPoint
from backend.app.services.knowledge_graph_fingerprint import knowledge_graph_fingerprint
from backend.app.services.mastery_config import MASTERY_V1_CONFIG
from backend.app.services.progress_analytics_service import ProgressAnalyticsService


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ProgressTrendService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.analytics = ProgressAnalyticsService(session, settings)

    def trend(self, course_id: int, time_range: Literal["7d", "30d", "all"]) -> ProgressTrend:
        # Reuse M8 leaf definition and its course authorization and cycle checks.
        leaves = self.analytics.knowledge(course_id).nodes
        node_ids = {node.node_id for node in leaves}
        owner_id = self.analytics.mastery._require_owner_id()
        signature = knowledge_graph_fingerprint(self.session, course_id)
        rows = list(
            self.session.scalars(
                select(MasteryHistory)
                .where(MasteryHistory.user_id == owner_id, MasteryHistory.course_id == course_id)
                .order_by(MasteryHistory.recorded_at, MasteryHistory.id)
            )
        )
        incompatible = any(
            row.graph_fingerprint != signature or row.algorithm_version != MASTERY_V1_CONFIG.algorithm_version
            for row in rows
        )
        grouped: dict[datetime, list[MasteryHistory]] = defaultdict(list)
        for row in rows:
            grouped[_utc(row.recorded_at)].append(row)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=7 if time_range == "7d" else 30) if time_range != "all" else None
        current: dict[int, Decimal | None] = {}
        points = []
        segment = 0
        for at, changes in sorted(grouped.items()):
            if any(
                row.graph_fingerprint != signature or row.algorithm_version != MASTERY_V1_CONFIG.algorithm_version
                for row in changes
            ):
                current.clear()
                segment += 1
            for row in changes:
                if (
                    row.graph_fingerprint == signature
                    and row.algorithm_version == MASTERY_V1_CONFIG.algorithm_version
                    and row.knowledge_node_id in node_ids
                ):
                    current[row.knowledge_node_id] = row.mastery_score
            scores = [value for value in current.values() if value is not None]
            has_compatible_change = any(
                row.graph_fingerprint == signature
                and row.algorithm_version == MASTERY_V1_CONFIG.algorithm_version
                and row.knowledge_node_id in node_ids
                for row in changes
            )
            if not scores or not has_compatible_change or (cutoff is not None and at < cutoff) or at > now:
                continue
            points.append(
                ProgressTrendPoint(
                    recorded_at=at,
                    segment=segment,
                    overall_mastery=(sum(scores, Decimal(0)) / len(scores)).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                    evaluated_node_count=len(scores),
                    evaluable_node_count=len(node_ids),
                    coverage_ratio=len(scores) / len(node_ids),
                )
            )
        return ProgressTrend(
            course_id=course_id, range=time_range, points=points, excluded_incompatible_history=incompatible
        )
