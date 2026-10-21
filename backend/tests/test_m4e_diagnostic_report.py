from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import Assessment, KnowledgeNode, Question
from backend.app.models import AssessmentStatus
from backend.app.schemas.diagnostic import ObjectiveAnswerSchema
from backend.app.services.diagnostic_domain_service import DiagnosticDomainService
from backend.app.services.diagnostic_report_service import (
    DIAGNOSTIC_REPORT_POLICY_VERSION,
    DiagnosticReportError,
    DiagnosticReportService,
)
from backend.tests.test_m4c_assessment_scoring import migrate_database, seed_foundation


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    from sqlalchemy import create_engine, event

    url = migrate_database(tmp_path / "m4e.sqlite")
    engine = create_engine(url)
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    database = factory()
    try:
        yield database
    finally:
        database.close()
        engine.dispose()


def _submitted_assessment(session: Session):
    seed = seed_foundation(session)
    questions = list(
        session.scalars(select(Question).where(Question.course_id == seed.course_id).order_by(Question.id))
    )
    node_zero = [item for item in questions if item.knowledge_links[0].knowledge_node_id == seed.node_ids[0]][:3]
    node_one = [item for item in questions if item.knowledge_links[0].knowledge_node_id == seed.node_ids[1]][:2]
    correct_keys = [item.correct_answer[0] for item in node_zero + node_one]
    incorrect_key = next(key["key"] for key in node_zero[1].options if key["key"] != correct_keys[1])
    question_ids = [item.id for item in node_zero + node_one]
    session.rollback()
    domain = DiagnosticDomainService(session)
    assessment = domain.create_assessment_draft(seed.owner_id, seed.course_id)
    assessment_id = assessment.id
    session.rollback()
    snapshots = domain.fix_question_snapshots(seed.owner_id, assessment_id, question_ids)
    snapshot_ids = [item.id for item in snapshots]
    session.rollback()
    domain.start_assessment(seed.owner_id, assessment_id)
    answers = {
        snapshot_ids[0]: ObjectiveAnswerSchema(selected_options=[correct_keys[0]]),
        snapshot_ids[1]: ObjectiveAnswerSchema(selected_options=[incorrect_key]),
        snapshot_ids[2]: ObjectiveAnswerSchema(),
        snapshot_ids[3]: ObjectiveAnswerSchema(selected_options=[correct_keys[3]]),
        snapshot_ids[4]: ObjectiveAnswerSchema(selected_options=[correct_keys[4]]),
    }
    domain.submit_assessment(seed.owner_id, assessment_id, answers)
    return seed, assessment_id


def test_report_uses_primary_snapshot_nodes_and_persisted_scores(session: Session) -> None:
    seed, assessment_id = _submitted_assessment(session)
    report = DiagnosticReportService(session).build_report(seed.owner_id, assessment_id)
    first = next(item for item in report.knowledge_performance if item.historical_node_id == seed.node_ids[0])
    second = next(item for item in report.knowledge_performance if item.historical_node_id == seed.node_ids[1])
    assert (first.question_count, first.correct_count, first.incorrect_count, first.unanswered_count) == (3, 1, 1, 1)
    assert first.accuracy == Decimal(1) / Decimal(3)
    assert first.evidence_status == "basic_evidence"
    assert first.preliminary_status == "needs_attention"
    assert (second.question_count, second.evidence_status, second.preliminary_status) == (
        2,
        "limited_evidence",
        "limited_evidence",
    )
    assert report.report_policy_version == DIAGNOSTIC_REPORT_POLICY_VERSION
    assert report.question_reviews[2].selected_options == []
    assert report.question_reviews[2].is_correct is False
    assert report.question_reviews[0].source_refs[0].is_accessible is False


def test_report_keeps_historical_node_name_and_has_no_write_side_effect(session: Session) -> None:
    seed, assessment_id = _submitted_assessment(session)
    with session.begin():
        node = session.get(KnowledgeNode, seed.node_ids[0])
        assert node is not None
        node.name = "Renamed live graph node"
    before = session.get(Assessment, assessment_id)
    assert before is not None
    before_version = before.report_policy_version
    session.rollback()
    report = DiagnosticReportService(session).build_report(seed.owner_id, assessment_id)
    after = session.get(Assessment, assessment_id)
    assert after is not None
    assert after.report_policy_version == before_version
    first = next(item for item in report.knowledge_performance if item.historical_node_id == seed.node_ids[0])
    assert first.historical_node_name == "Core node 1"


def test_report_rejects_unsubmitted_unknown_policy_and_other_owner(session: Session) -> None:
    seed, assessment_id = _submitted_assessment(session)
    with pytest.raises(DiagnosticReportError, match="not found"):
        DiagnosticReportService(session).build_report(seed.other_owner_id, assessment_id)
    with session.begin():
        assessment = session.get(Assessment, assessment_id)
        assert assessment is not None
        assessment.report_policy_version = "future_unavailable_policy"
    with pytest.raises(DiagnosticReportError) as error:
        DiagnosticReportService(session).build_report(seed.owner_id, assessment_id)
    assert error.value.code == "REPORT_POLICY_UNSUPPORTED"
    with session.begin():
        assessment.report_policy_version = DIAGNOSTIC_REPORT_POLICY_VERSION
        assessment.status = AssessmentStatus.IN_PROGRESS
    with pytest.raises(DiagnosticReportError) as error:
        DiagnosticReportService(session).build_report(seed.owner_id, assessment_id)
    assert error.value.code == "ASSESSMENT_NOT_SUBMITTED"
