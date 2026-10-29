from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.app.core.settings import Settings
from backend.app.db.models import KnowledgeEdge, MasteryHistory, StudentKnowledgeState
from backend.app.models import KnowledgeRelationType
from backend.app.services.mastery_service import MasteryService
from backend.app.services.progress_trend_service import ProgressTrendService
from backend.tests.test_m5d_student_state_api import _add_evidence, _node, _request, _seed_calculated_state
from backend.tests.test_m5d_student_state_api import api_server as api_server
from backend.tests.test_m5d_student_state_api import database as database
from backend.tests.test_m7_4_adaptive_practice import practice_database as practice_database


def test_real_versions_deduplicate_and_rollback(database):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        rows = list(session.scalars(select(MasteryHistory)))
        assert len(rows) == 1
        first = rows[0].evidence_fingerprint
        session.rollback()
        result = MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"]
        )
        assert result.updated is False
        session.rollback()
        _add_evidence(session, ids, score="0", offset=10)
        session.commit()
        with session.begin():
            MasteryService(session).refresh_state(
                user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"], in_transaction=True
            )
            session.rollback()
        assert session.scalar(select(func.count()).select_from(MasteryHistory)) == 1
        session.rollback()
        MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"]
        )
        rows = list(session.scalars(select(MasteryHistory).order_by(MasteryHistory.id)))
        assert len(rows) == 2
        assert rows[1].evidence_fingerprint != first
        state = session.scalar(select(StudentKnowledgeState))
        assert state.evidence_fingerprint == rows[1].evidence_fingerprint


def test_trend_does_not_backfill_and_rejects_changed_graph(database):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        service = ProgressTrendService(session, Settings(database_url="sqlite://"))
        trend = service.trend(ids["course"], "all")
        assert len(trend.points) == 1
        assert trend.points[0].evaluated_node_count == 1
        assert trend.points[0].evaluable_node_count == 2
        assert trend.points[0].coverage_ratio == 0.5
        session.rollback()
        row = session.scalar(select(MasteryHistory))
        row.recorded_at = datetime.now(timezone.utc) - timedelta(days=40)
        session.commit()
        trend = service.trend(ids["course"], "30d")
        assert trend.points == []
        session.rollback()
        node = _node(ids["course"], "new node")
        session.add(node)
        session.flush()
        session.add(
            KnowledgeEdge(
                course_id=ids["course"],
                source_node_id=ids["node"],
                target_node_id=node.id,
                relation_type=KnowledgeRelationType.CONTAINS,
            )
        )
        session.commit()
        trend = service.trend(ids["course"], "all")
        assert trend.points == []
        assert trend.excluded_incompatible_history


def test_m7_settlement_creates_one_history_on_retry(practice_database):
    from backend.app.services.learning_settlement_service import LearningSettlementService
    from backend.tests.test_m7_4_adaptive_practice import _settings
    from backend.tests.test_m7_5_settlement import _finished

    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url)
    with factory() as session:
        LearningSettlementService(session, _settings(url)).complete_for_configured_user(session_id)
    with factory() as session:
        LearningSettlementService(session, _settings(url)).complete_for_configured_user(session_id)
    with factory() as session:
        rows = list(session.scalars(select(MasteryHistory)))
        assert len(rows) == 1
        state = session.scalar(select(StudentKnowledgeState))
        assert rows[0].evidence_fingerprint == state.evidence_fingerprint
        assert rows[0].mastery_score == state.mastery_score


def test_incompatible_versions_break_the_line_and_do_not_carry_scores(database):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        row = session.scalar(select(MasteryHistory))
        now = datetime.now(timezone.utc)
        row.recorded_at = now - timedelta(days=3)
        for offset, signature, fingerprint in (
            (2, "b" * 64, "c" * 64),
            (1, row.graph_fingerprint, "d" * 64),
        ):
            session.add(
                MasteryHistory(
                    user_id=row.user_id,
                    course_id=row.course_id,
                    knowledge_node_id=row.knowledge_node_id,
                    mastery_score=row.mastery_score,
                    mastery_status=row.mastery_status,
                    confidence_level=row.confidence_level,
                    evidence_fingerprint=fingerprint,
                    algorithm_version=row.algorithm_version,
                    graph_fingerprint=signature,
                    recorded_at=now - timedelta(days=offset),
                )
            )
        session.commit()
        result = ProgressTrendService(session, Settings(database_url="sqlite://")).trend(ids["course"], "all")
        assert [point.segment for point in result.points] == [0, 1]
        assert result.excluded_incompatible_history


def test_trend_api_is_read_only_and_scoped(database, api_server):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        before = session.scalar(select(func.count()).select_from(MasteryHistory))
    status, response = _request(api_server, f"/api/courses/{ids['course']}/progress/trend?range=all")
    assert status == 200
    assert len(response["points"]) == 1
    status, _ = _request(api_server, f"/api/courses/{ids['other_course']}/progress/trend")
    assert status == 404
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MasteryHistory)) == before


def test_unsubmitted_evidence_never_creates_history(database):
    factory, ids, _, _ = database
    with factory() as session:
        for index in range(3):
            _add_evidence(session, ids, score="1", offset=index, submitted=False)
        session.commit()
        MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"]
        )
        assert session.scalar(select(func.count()).select_from(MasteryHistory)) == 0


def test_stale_current_does_not_replace_recorded_historical_fact(database):
    from backend.app.services.mastery_read_service import MasteryReadService

    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        _add_evidence(session, ids, score="0", offset=8)
        session.commit()
        current = MasteryReadService(session, Settings(database_url="sqlite://")).course_mastery(ids["course"])
        assert current.nodes[0].mastery_score is None
        assert current.nodes[0].calculation_state.value == "stale"
        trend = ProgressTrendService(session, Settings(database_url="sqlite://")).trend(ids["course"], "all")
        assert len(trend.points) == 1
        assert trend.points[0].overall_mastery is not None


def test_rolling_windows_filter_real_event_times(database):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        row = session.scalar(select(MasteryHistory))
        row.recorded_at = datetime.now(timezone.utc) - timedelta(days=10)
        session.commit()
        service = ProgressTrendService(session, Settings(database_url="sqlite://"))
        assert len(service.trend(ids["course"], "7d").points) == 0
        session.rollback()
        assert len(service.trend(ids["course"], "30d").points) == 1
