from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeNode,
    LearningEvidence,
    Response,
    StudentKnowledgeState,
    User,
)
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    EvidenceSourceType,
    KnowledgeDifficulty,
    KnowledgeImportance,
    QuestionDifficulty,
)
from backend.app.services.mastery_read_service import MasteryReadService
from backend.app.services.mastery_service import MasteryService


def _migrate(path: Path) -> str:
    url = f"sqlite+pysqlite:///{path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return url


@pytest.fixture
def database(tmp_path: Path):
    engine = create_engine(_migrate(tmp_path / "m5d.sqlite3"), connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        owner = User(email="legacy-bootstrap@learnpilot.local", display_name="Owner", is_active=True)
        other_owner = User(email="other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other_owner])
        session.flush()
        course = Course(owner_id=owner.id, name="M5-D", description="")
        other_course = Course(owner_id=other_owner.id, name="Private", description="")
        session.add_all([course, other_course])
        session.flush()
        node = _node(course.id, "Current node")
        empty_node = _node(course.id, "Unassessed node")
        session.add_all([node, empty_node])
        session.flush()
        ids = {
            "owner": owner.id,
            "course": course.id,
            "other_course": other_course.id,
            "node": node.id,
            "empty": empty_node.id,
        }
    yield factory, ids, engine, f"sqlite+pysqlite:///{tmp_path / 'm5d.sqlite3'}"
    engine.dispose()


def _node(course_id: int, name: str) -> KnowledgeNode:
    return KnowledgeNode(
        course_id=course_id,
        name=name,
        normalized_name=name.lower(),
        description="",
        importance=KnowledgeImportance.MEDIUM,
        difficulty=KnowledgeDifficulty.INTERMEDIATE,
        is_active=True,
        managed_by_canonicalization=True,
    )


def _add_evidence(
    session: Session,
    ids: dict[str, int],
    *,
    score: str,
    offset: int,
    submitted: bool = True,
    historical_node_id: int | None = None,
) -> LearningEvidence:
    occurred_at = datetime(2026, 10, 20, 8, tzinfo=timezone.utc) + timedelta(hours=offset)
    assessment = Assessment(
        course_id=ids["course"],
        owner_id=ids["owner"],
        assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
        status=AssessmentStatus.SUBMITTED if submitted else AssessmentStatus.IN_PROGRESS,
        submitted_at=occurred_at if submitted else None,
    )
    session.add(assessment)
    session.flush()
    question = AssessmentQuestion(
        assessment_id=assessment.id,
        question_id=None,
        order_index=0,
        question_snapshot={"private": "immutable snapshot"},
    )
    session.add(question)
    session.flush()
    response = Response(
        assessment_id=assessment.id,
        assessment_question_id=question.id,
        answer_payload={"selected_options": ["SECRET_OPTION"]},
        answered_at=occurred_at,
        submitted_at=occurred_at if submitted else None,
        is_correct=Decimal(score) == Decimal("1"),
        points_awarded=Decimal(score),
    )
    session.add(response)
    session.flush()
    item = LearningEvidence(
        user_id=ids["owner"],
        course_id=ids["course"],
        source_type=EvidenceSourceType.DIAGNOSTIC,
        source_assessment_id=assessment.id,
        source_question_snapshot_id=question.id,
        source_response_id=response.id,
        historical_knowledge_node_ref=historical_node_id or ids["node"],
        current_knowledge_node_id=ids["node"],
        knowledge_model_version="knowledge_v1",
        normalized_score=Decimal(score),
        difficulty=QuestionDifficulty.MEDIUM,
        attribution_weight=Decimal("1"),
        source_scoring_version="objective_exact_match_v1",
        evidence_schema_version="learning_evidence_v1",
        occurred_at=occurred_at,
    )
    session.add(item)
    session.flush()
    return item


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _request(base_url: str, path: str) -> tuple[int, dict[str, object]]:
    try:
        with urlopen(Request(f"{base_url}{path}", method="GET"), timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        with error:
            return error.code, json.loads(error.read().decode("utf-8"))


@pytest.fixture
def api_server(database) -> str:
    _factory, _ids, _engine, url = database
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update({"DATABASE_URL": url, "APP_ENV": "test", "LLM_MODE": "mock"})
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=0.25):
                break
        except URLError, TimeoutError:
            if process.poll() is not None:
                raise RuntimeError("M5-D test server stopped during startup.")
            time.sleep(0.05)
    else:
        process.terminate()
        raise RuntimeError("M5-D test server did not start.")
    try:
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=5)


def _seed_calculated_state(session: Session, ids: dict[str, int]) -> list[LearningEvidence]:
    evidence = [_add_evidence(session, ids, score="1", offset=index) for index in range(3)]
    session.commit()
    MasteryService(session).refresh_state(user_id=ids["owner"], course_id=ids["course"], knowledge_node_id=ids["node"])
    session.commit()
    return evidence


def test_read_apis_return_persisted_state_and_never_write(database, api_server) -> None:
    factory, ids, engine, _url = database
    with factory() as session:
        evidence = _seed_calculated_state(session, ids)
        before_state = session.scalar(select(StudentKnowledgeState))
        assert before_state is not None
        before = (
            before_state.calculated_at,
            before_state.evidence_fingerprint,
            session.query(LearningEvidence).count(),
        )
        writes: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def track_writes(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                writes.append(statement)

        course_status, course = _request(api_server, f"/api/courses/{ids['course']}/mastery")
        mastery_status, mastery = _request(
            api_server,
            f"/api/courses/{ids['course']}/knowledge/{ids['node']}/mastery",
        )
        explanation_status, explanation = _request(
            api_server,
            f"/api/courses/{ids['course']}/knowledge/{ids['node']}/evidence",
        )
        empty_status, empty = _request(
            api_server,
            f"/api/courses/{ids['course']}/knowledge/{ids['empty']}/mastery",
        )
        event.remove(engine, "before_cursor_execute", track_writes)

        assert course_status == mastery_status == explanation_status == empty_status == 200
        assert mastery["calculation_state"] == "calculated"
        assert mastery["mastery_score"] == "82.14"
        assert empty["calculation_state"] == "not_calculated"
        assert empty["mastery_score"] is None
        payload = explanation
        assert payload["summary"]["effective_evidence_count"] == 3
        assert {item["evidence_id"] for item in payload["evidence"]} == {item.id for item in evidence}
        assert "answer_payload" not in str(payload)
        assert "SECRET_OPTION" not in str(payload)
        assert "question_snapshot" not in str(payload)
        session.expire_all()
        after_state = session.scalar(select(StudentKnowledgeState))
        assert after_state is not None
        assert (
            after_state.calculated_at,
            after_state.evidence_fingerprint,
            session.query(LearningEvidence).count(),
        ) == before
        assert writes == []


def test_read_service_emits_no_database_writes(database) -> None:
    factory, ids, engine, _url = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        writes: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def track_writes(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                writes.append(statement)

        service = MasteryReadService(session, Settings(database_url="sqlite://"))
        service.course_mastery(ids["course"])
        service.node_mastery(ids["course"], ids["node"])
        service.node_evidence(ids["course"], ids["node"], offset=0, limit=20)
        event.remove(engine, "before_cursor_execute", track_writes)
        assert writes == []


def test_unsubmitted_evidence_is_hidden_and_course_ownership_is_enforced(database, api_server) -> None:
    factory, ids, _engine, _url = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        draft = _add_evidence(session, ids, score="1", offset=10, submitted=False)
        session.commit()
        response_status, response = _request(
            api_server,
            f"/api/courses/{ids['course']}/knowledge/{ids['node']}/evidence",
        )
        foreign_status, foreign = _request(api_server, f"/api/courses/{ids['other_course']}/mastery")
        assert response_status == 200
        assert response["state"]["calculation_state"] == "calculated"
        assert draft.id not in {item["evidence_id"] for item in response["evidence"]}
        assert foreign_status == 404
        assert foreign["error"]["code"] == "COURSE_NOT_FOUND"


def test_changed_or_invalid_historical_mapping_is_reported_stale_without_repair(database, api_server) -> None:
    factory, ids, _engine, _url = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        _add_evidence(session, ids, score="0", offset=10)
        session.commit()
        stale_status, stale = _request(
            api_server,
            f"/api/courses/{ids['course']}/knowledge/{ids['node']}/mastery",
        )
        explanation_status, explanation = _request(
            api_server,
            f"/api/courses/{ids['course']}/knowledge/{ids['node']}/evidence",
        )
        assert stale_status == explanation_status == 200
        assert stale["calculation_state"] == "stale"
        assert stale["mastery_score"] is None
        assert explanation["evidence"] == []
