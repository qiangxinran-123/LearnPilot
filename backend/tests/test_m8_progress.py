from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Assessment,
    KnowledgeEdge,
    KnowledgeNode,
    LearningEvidence,
    LearningSession,
    StudentKnowledgeState,
)
from backend.app.models import AssessmentType, EvidenceSourceType, KnowledgeRelationType
from backend.app.services.mastery_read_service import MasteryReadError, MasteryReadService
from backend.app.services.mastery_service import MasteryService
from backend.app.services.progress_analytics_service import ProgressAnalyticsService
from backend.tests.test_m5d_student_state_api import (
    _add_evidence,
    _node,
    _request,
    _seed_calculated_state,
)
from backend.tests.test_m5d_student_state_api import api_server as api_server
from backend.tests.test_m5d_student_state_api import database as database


def service(session):
    return ProgressAnalyticsService(session, Settings(database_url="sqlite://"))


def test_empty_and_no_evidence(database):
    factory, ids, _, _ = database
    with factory() as session:
        result = service(session).overview(ids["course"])
        assert result.overall_mastery is None
        assert result.coverage_ratio == 0
        assert result.evaluable_node_count == 2
        assert not result.weak_nodes
        session.rollback()
        for node in session.scalars(select(KnowledgeNode)):
            node.is_active = False
        session.commit()
        result = service(session).overview(ids["course"])
        assert result.evaluable_node_count == 0
        assert result.coverage_ratio is None


def test_m5_consistency_partial_and_stale(database):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        expected = MasteryReadService(session, Settings(database_url="sqlite://")).course_mastery(ids["course"])
        result = service(session).overview(ids["course"])
        assert result.coverage_ratio == 0.5
        assert result.overall_mastery == expected.nodes[0].mastery_score
        assert result.evaluated_node_count == 1
        session.rollback()
        _add_evidence(session, ids, score="0", offset=5)
        session.commit()
        result = service(session).overview(ids["course"])
        assert result.overall_mastery is None
        assert result.coverage_ratio == 0


def test_hierarchy_multi_parent_isolation_and_cycle(database):
    factory, ids, _, _ = database
    with factory() as session:
        child = _node(ids["course"], "child")
        session.add(child)
        session.flush()
        for parent in (ids["node"], ids["empty"]):
            session.add(
                KnowledgeEdge(
                    course_id=ids["course"],
                    source_node_id=parent,
                    target_node_id=child.id,
                    relation_type=KnowledgeRelationType.CONTAINS,
                )
            )
        session.commit()
        result = service(session).knowledge(ids["course"])
        assert len(result.nodes) == 1
        assert result.nodes[0].parent_ids == sorted([ids["node"], ids["empty"]])
        session.rollback()
        session.add(
            KnowledgeEdge(
                course_id=ids["course"],
                source_node_id=child.id,
                target_node_id=ids["node"],
                relation_type=KnowledgeRelationType.CONTAINS,
            )
        )
        session.commit()
        with pytest.raises(MasteryReadError, match="cycle"):
            service(session).overview(ids["course"])
        session.rollback()
        with pytest.raises(MasteryReadError, match="Course not found"):
            service(session).overview(ids["other_course"])


def test_api_read_only_and_ownership(database, api_server):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        before = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (LearningEvidence, StudentKnowledgeState, LearningSession)
        )
    status, result = _request(api_server, f"/api/courses/{ids['course']}/progress/overview")
    assert status == 200
    assert result["evaluated_node_count"] == 1
    status, _ = _request(api_server, f"/api/courses/{ids['other_course']}/progress/knowledge")
    assert status == 404
    with factory() as session:
        after = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (LearningEvidence, StudentKnowledgeState, LearningSession)
        )
    assert before == after


def test_practice_evidence_matches_m5(database):
    factory, ids, _, _ = database
    with factory() as session:
        for index in range(3):
            evidence = _add_evidence(session, ids, score="0", offset=index)
            evidence.source_type = EvidenceSourceType.PRACTICE
            session.get(Assessment, evidence.source_assessment_id).assessment_type = AssessmentType.PRACTICE
        session.commit()
        MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"]
        )
        session.commit()
        expected = MasteryReadService(session, Settings(database_url="sqlite://")).course_mastery(ids["course"])
        result = service(session).knowledge(ids["course"])
        assert result.nodes[0].mastery_score == expected.nodes[0].mastery_score
        assert result.nodes[0].confidence_level == expected.nodes[0].confidence_level
        assert result.nodes[0].evidence_count == 3
        assert result.nodes[0].mastery_score is not None
        assert result.nodes[0].mastery_status == expected.nodes[0].mastery_status
        session.rollback()
        overview = service(session).overview(ids["course"])
        assert [node.node_id for node in overview.weak_nodes] == [ids["node"]]
        assert overview.weak_nodes[0].confidence_level == expected.nodes[0].confidence_level


def test_missing_course_is_hidden(database, api_server):
    _, ids, _, _ = database
    for course_id in (0, 999999, ids["other_course"]):
        status, payload = _request(api_server, f"/api/courses/{course_id}/progress/overview")
        assert status == 404
        assert payload["error"]["code"] == "COURSE_NOT_FOUND"


def test_parent_score_excluded_and_isolated_leaf_included(database):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        other_ids = dict(ids, node=ids["empty"])
        for index in range(3):
            _add_evidence(session, other_ids, score="0", offset=10 + index)
        session.commit()
        MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["empty"]
        )
        session.commit()
        child = _node(ids["course"], "Unassessed child")
        session.add(child)
        session.flush()
        session.add(
            KnowledgeEdge(
                course_id=ids["course"],
                source_node_id=ids["node"],
                target_node_id=child.id,
                relation_type=KnowledgeRelationType.CONTAINS,
            )
        )
        session.commit()
        states = MasteryReadService(session, Settings(database_url="sqlite://")).course_mastery(ids["course"])
        expected = next(state for state in states.nodes if state.knowledge_node_id == ids["empty"])
        result = service(session).overview(ids["course"])
        assert result.evaluable_node_count == 2
        assert result.evaluated_node_count == 1
        assert result.overall_mastery == expected.mastery_score
        assert result.coverage_ratio == 0.5


def test_all_scored_leaves_are_averaged(database):
    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        other_ids = dict(ids, node=ids["empty"])
        for index in range(3):
            _add_evidence(session, other_ids, score="0", offset=10 + index)
        session.commit()
        MasteryService(session).refresh_state(
            user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["empty"]
        )
        session.commit()
        states = MasteryReadService(session, Settings(database_url="sqlite://")).course_mastery(ids["course"])
        expected = sum((node.mastery_score for node in states.nodes), Decimal(0)) / 2
        result = service(session).overview(ids["course"])
        assert result.overall_mastery == expected
        assert result.coverage_ratio == 1
        assert result.evaluated_node_count == 2
        assert sum(result.status_counts.values()) == 2
