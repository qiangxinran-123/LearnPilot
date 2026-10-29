from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Assessment,
    LearningEvidence,
    LearningSession,
    MasteryHistory,
    Response,
    StudentKnowledgeState,
)
from backend.app.models import AssessmentType, EvidenceSourceType
from backend.app.services.mastery_service import MasteryService
from backend.app.services.review_risk_service import ReviewRiskService
from backend.tests.test_m5d_student_state_api import _add_evidence, _request
from backend.tests.test_m5d_student_state_api import api_server as api_server
from backend.tests.test_m5d_student_state_api import database as database

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def seed_practice(session, ids, age, score="1", count=6, now=NOW):
    for index in range(count):
        evidence = _add_evidence(session, ids, score=score, offset=index)
        evidence.source_type = EvidenceSourceType.PRACTICE
        assessment = session.get(Assessment, evidence.source_assessment_id)
        assessment.assessment_type = AssessmentType.PRACTICE
        response = session.get(Response, evidence.source_response_id)
        response.submitted_at = now - age - timedelta(hours=index)
        assessment.submitted_at = response.submitted_at
    session.commit()
    MasteryService(session).refresh_state(user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"])
    session.commit()


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0, "low_risk"), (13, "low_risk"), (14, "watch"), (29, "watch"), (30, "review_due"), (300, "review_due")],
)
def test_practice_intervals(database, days, expected):
    factory, ids, _, _ = database
    with factory() as session:
        seed_practice(session, ids, timedelta(days=days))
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.risk_level == expected
        assert node.days_since_practice == days
        assert node.last_practice_at == NOW - timedelta(days=days)
        assert result.counts["insufficient_data"] == 1


def test_weak_low_confidence_future_and_stale(database):
    factory, ids, _, _ = database
    with factory() as session:
        seed_practice(session, ids, timedelta(days=1), score="0", count=3)
        service = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW)
        result = service.assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.risk_level == "review_due"
        assert node.reason_code == "weak_mastery"
        assert node.mastery_status == "needs_attention"
        assert node.confidence_level == "low"
        session.rollback()
        response = session.scalar(select(Response).order_by(Response.id))
        response.submitted_at = NOW + timedelta(days=1)
        session.commit()
        result = service.assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.risk_level == "insufficient_data"
        assert node.reason_code == "invalid_practice_time"
        assert node.days_since_practice is None
        session.rollback()
        _add_evidence(session, ids, score="1", offset=20)
        session.commit()
        result = service.assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.reason_code == "stale_mastery"
        assert node.mastery_score is None


def test_no_practice_and_low_confidence_are_not_low_risk(database):
    factory, ids, _, _ = database
    with factory() as session:
        for index in range(3):
            _add_evidence(session, ids, score="1", offset=index)
        session.commit()
        MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"]
        )
        session.commit()
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        assert result.items[0].reason_code == "no_practice"
        assert result.items[0].risk_level == "watch"


def test_api_is_owned_stable_and_read_only(database, api_server):
    factory, ids, _, _ = database
    with factory() as session:
        seed_practice(session, ids, timedelta(days=1), now=datetime.now(timezone.utc))
        models = (LearningEvidence, StudentKnowledgeState, MasteryHistory, LearningSession)
        before = [session.scalar(select(func.count()).select_from(model)) for model in models]
    status, payload = _request(api_server, f"/api/courses/{ids['course']}/progress/review-risk")
    assert status == 200
    assert len(payload["items"]) == 2
    assert len({item["knowledge_node_id"] for item in payload["items"]}) == 2
    assert [item["risk_level"] for item in payload["items"]] == ["insufficient_data", "low_risk"]
    for course in (ids["other_course"], 999999):
        status, _ = _request(api_server, f"/api/courses/{course}/progress/review-risk")
        assert status == 404
    with factory() as session:
        after = [session.scalar(select(func.count()).select_from(model)) for model in models]
    assert before == after


def test_empty_course_and_missing_timestamp_are_not_low_risk(database):
    from backend.app.db.models import KnowledgeNode

    factory, ids, _, _ = database
    with factory() as session:
        seed_practice(session, ids, timedelta(days=1))
        response = session.scalar(select(Response).order_by(Response.id))
        response.submitted_at = None
        session.commit()
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.risk_level == "insufficient_data"
        assert node.last_practice_at is None
        session.rollback()
        for node in session.scalars(select(KnowledgeNode)):
            node.is_active = False
        session.commit()
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        assert result.total_node_count == 0
        assert result.items == []


def test_recent_practice_with_low_confidence_needs_more_evidence(database):
    factory, ids, _, _ = database
    with factory() as session:
        seed_practice(session, ids, timedelta(days=0), count=3)
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.risk_level == "watch"
        assert node.reason_code == "low_confidence"
        assert node.last_practice_at == NOW


def test_get_does_not_refresh_mastery_recommend_or_call_llm(database, monkeypatch):
    from backend.app.ai.client import ExplicitMockLLMClient, OpenAICompatibleLLMClient
    from backend.app.services.learning_plan_service import LearningPlanService

    factory, ids, _, _ = database
    with factory() as session:
        seed_practice(session, ids, timedelta(days=1))
        state = session.scalar(select(StudentKnowledgeState))
        before = (state.mastery_score, state.evidence_fingerprint, state.calculated_at)
        session.rollback()

        def forbidden(*args, **kwargs):
            raise AssertionError("write or recommendation was called")

        monkeypatch.setattr(MasteryService, "refresh_state", forbidden)
        monkeypatch.setattr(LearningPlanService, "generate", forbidden)
        monkeypatch.setattr(ExplicitMockLLMClient, "generate_structured", forbidden)
        monkeypatch.setattr(OpenAICompatibleLLMClient, "generate_structured", forbidden)
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        assert result.total_node_count == 2
        state = session.scalar(select(StudentKnowledgeState))
        assert (state.mastery_score, state.evidence_fingerprint, state.calculated_at) == before


def test_inconsistent_reread_does_not_publish_old_mastery(database, monkeypatch):
    import backend.app.services.review_risk_service as risk_module

    factory, ids, _, _ = database
    with factory() as session:
        seed_practice(session, ids, timedelta(days=1))
        monkeypatch.setattr(risk_module, "is_persisted_mastery_state_current", lambda **kwargs: False)
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.risk_level == "insufficient_data"
        assert node.mastery_score is None
        assert node.mastery_status == "not_assessed"
        assert node.confidence_level == "insufficient"
        assert node.calculation_state == "stale"


def test_no_evidence_nodes_have_stable_order_and_no_false_low_risk(database):
    factory, ids, _, _ = database
    with factory() as session:
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        assert [item.knowledge_node_id for item in result.items] == sorted([ids["node"], ids["empty"]])
        assert all(item.risk_level == "insufficient_data" for item in result.items)
        assert all(item.last_practice_at is None for item in result.items)
        assert result.counts["low_risk"] == 0


def test_one_recent_practice_is_not_sufficient_for_low_risk(database):
    factory, ids, _, _ = database
    with factory() as session:
        for index in range(6):
            _add_evidence(session, ids, score="1", offset=index)
        evidence = _add_evidence(session, ids, score="1", offset=10)
        evidence.source_type = EvidenceSourceType.PRACTICE
        session.get(Assessment, evidence.source_assessment_id).assessment_type = AssessmentType.PRACTICE
        session.get(Response, evidence.source_response_id).submitted_at = NOW - timedelta(days=1)
        session.commit()
        MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"]
        )
        session.commit()
        result = ReviewRiskService(session, Settings(database_url="sqlite://"), now=NOW).assess(ids["course"])
        node = next(item for item in result.items if item.knowledge_node_id == ids["node"])
        assert node.confidence_level == "medium"
        assert node.risk_level == "watch"
        assert node.reason_code == "limited_recent_practice"
