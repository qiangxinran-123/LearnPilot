from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.app.db.models import Assessment, LearningEvidence, LearningSession, StudentKnowledgeState
from backend.app.models import AssessmentStatus, LearningSessionStatus, RecommendationRefreshStatus
from backend.tests.test_m5d_student_state_api import _add_evidence, _request
from backend.tests.test_m5d_student_state_api import api_server as api_server
from backend.tests.test_m5d_student_state_api import database as database


def test_history_pages_only_completed_and_is_read_only(database, api_server):
    factory, ids, _, _ = database
    with factory() as session:
        _add_evidence(session, ids, score="1", offset=0)
        _add_evidence(session, ids, score="0", offset=1)
        _add_evidence(session, ids, score="1", offset=2, submitted=False)
        at = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)
        session.add_all(
            [
                LearningSession(
                    user_id=ids["owner"],
                    course_id=ids["course"],
                    target_knowledge_node_id=ids["node"],
                    status=LearningSessionStatus.COMPLETED,
                    active_slot=None,
                    session_contract_version="v1",
                    completed_at=at,
                    recommendation_refresh_status=RecommendationRefreshStatus.SUCCEEDED,
                ),
                LearningSession(
                    user_id=ids["owner"],
                    course_id=ids["course"],
                    target_knowledge_node_id=ids["empty"],
                    status=LearningSessionStatus.IN_PROGRESS,
                    active_slot=1,
                    session_contract_version="v1",
                    recommendation_refresh_status=RecommendationRefreshStatus.NOT_REQUESTED,
                ),
            ]
        )
        session.commit()
        before = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Assessment, LearningEvidence, StudentKnowledgeState, LearningSession)
        )
    events = []
    cursor = None
    for _ in range(5):
        suffix = f"?limit=1&cursor={cursor}" if cursor else "?limit=1"
        status, page = _request(api_server, f"/api/courses/{ids['course']}/progress/history{suffix}")
        assert status == 200
        events.extend(page["events"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(events) == 3
    assert len({event["id"] for event in events}) == 3
    assert [event["event_type"] for event in events].count("learning_session_completed") == 1
    assert [event["occurred_at"] for event in events] == sorted(
        [event["occurred_at"] for event in events], reverse=True
    )
    status, _ = _request(api_server, f"/api/courses/{ids['other_course']}/progress/history")
    assert status == 404
    status, _ = _request(api_server, f"/api/courses/{ids['course']}/progress/history?cursor=invalid")
    assert status == 400
    with factory() as session:
        after = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Assessment, LearningEvidence, StudentKnowledgeState, LearningSession)
        )
        assert (
            session.scalar(
                select(func.count()).select_from(Assessment).where(Assessment.status == AssessmentStatus.IN_PROGRESS)
            )
            == 1
        )
    assert before == after
