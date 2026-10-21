from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.models import Course, KnowledgeNode, Question, QuestionKnowledgeNode, User
from backend.app.models import (
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeRelationRole,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)


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


def _seed(url: str) -> tuple[int, int]:
    engine = create_engine(url)
    with Session(engine) as session, session.begin():
        owner = User(email="legacy-bootstrap@learnpilot.local", display_name="Owner", is_active=True)
        other = User(email="other-m4d@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="Operating Systems", description="Diagnostic-ready course")
        other_course = Course(owner_id=other.id, name="Private Course", description="")
        session.add_all([course, other_course])
        session.flush()
        node = KnowledgeNode(
            course_id=course.id,
            name="Process scheduling",
            normalized_name="process scheduling",
            description="Core scheduling concepts",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
            managed_by_canonicalization=True,
        )
        session.add(node)
        session.flush()
        types = [QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE, QuestionType.MULTIPLE_CHOICE]
        for index in range(8):
            question_type = types[index % len(types)]
            if question_type == QuestionType.TRUE_FALSE:
                options = [{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}]
                correct = ["TRUE"]
            else:
                options = [
                    {"key": "A", "text": "选项 A"},
                    {"key": "B", "text": "选项 B"},
                    {"key": "C", "text": "选项 C"},
                    {"key": "D", "text": "选项 D"},
                ]
                correct = ["A", "C"] if question_type == QuestionType.MULTIPLE_CHOICE else ["A"]
            question = Question(
                course_id=course.id,
                question_type=question_type,
                stem=f"Process scheduling diagnostic item {index + 1}?",
                options=options,
                correct_answer=correct,
                explanation="Grounded explanation.",
                difficulty=QuestionDifficulty.MEDIUM,
                validation_status=QuestionValidationStatus.VALIDATED,
                source_refs=[
                    {
                        "material_id": 1,
                        "material_title": "Scheduling notes",
                        "source_reference": f"TXT segment {index + 1}",
                    }
                ],
                generation_metadata={"prompt_version": "diagnostic_questions_v1"},
                content_version=1,
            )
            session.add(question)
            session.flush()
            session.add(
                QuestionKnowledgeNode(
                    course_id=course.id,
                    question_id=question.id,
                    knowledge_node_id=node.id,
                    relation_role=KnowledgeRelationRole.PRIMARY,
                )
            )
        course_id = course.id
        other_course_id = other_course.id
    engine.dispose()
    return course_id, other_course_id


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _request(base_url: str, method: str, path: str, payload: object | None = None) -> tuple[int, dict[str, object]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        with error:
            return error.code, json.loads(error.read().decode("utf-8"))


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[tuple[str, int, int], None, None]:
    url = _migrate(tmp_path / "m4d.sqlite3")
    course_id, other_course_id = _seed(url)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update({"DATABASE_URL": url, "APP_ENV": "test", "LLM_MODE": "mock"})
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
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
                raise RuntimeError("M4-D test server stopped during startup.")
            time.sleep(0.05)
    else:
        process.terminate()
        raise RuntimeError("M4-D test server did not start.")
    try:
        yield base_url, course_id, other_course_id
    finally:
        process.terminate()
        process.wait(timeout=5)


def _create_and_start(base_url: str, course_id: int) -> dict[str, object]:
    created_status, assessment = _request(base_url, "POST", "/api/diagnostics/assessments", {"course_id": course_id})
    assert created_status == 201
    started_status, started = _request(base_url, "POST", f"/api/diagnostics/assessments/{assessment['id']}/start")
    assert started_status == 200
    return started


def test_readiness_and_candidate_view_hide_private_answer_data(api_client) -> None:
    base_url, course_id, _ = api_client
    status, readiness = _request(base_url, "GET", f"/api/diagnostics/courses/{course_id}/readiness")
    assert status == 200
    assert readiness["can_start"] is True
    assessment = _create_and_start(base_url, course_id)
    assert assessment["status"] == "in_progress"
    assert assessment["question_count"] == 8
    serialized = str(assessment["questions"])
    assert "correct_answer" not in serialized
    assert "explanation" not in serialized
    assert "scoring_policy" not in serialized
    assert "source_refs" not in serialized


def test_create_is_idempotent_for_unfinished_course_assessment(api_client) -> None:
    base_url, course_id, _ = api_client
    _, first = _request(base_url, "POST", "/api/diagnostics/assessments", {"course_id": course_id})
    _, second = _request(base_url, "POST", "/api/diagnostics/assessments", {"course_id": course_id})
    assert second["id"] == first["id"]


def test_save_response_enforces_assessment_question_boundary_and_locks_after_submit(api_client) -> None:
    base_url, course_id, _ = api_client
    first = _create_and_start(base_url, course_id)
    first_question = first["questions"][0]
    saved_status, saved = _request(
        base_url,
        "PUT",
        f"/api/diagnostics/assessments/{first['id']}/responses/{first_question['assessment_question_id']}",
        {"schema_version": "objective_answer_v1", "selected_options": [first_question["options"][0]["key"]]},
    )
    assert saved_status == 200
    assert saved["selected_options"]

    _request(base_url, "POST", f"/api/diagnostics/assessments/{first['id']}/submit")
    locked_status, locked = _request(
        base_url,
        "PUT",
        f"/api/diagnostics/assessments/{first['id']}/responses/{first_question['assessment_question_id']}",
        {"selected_options": []},
    )
    assert locked_status == 409
    assert locked["error"]["code"] == "ASSESSMENT_INVALID_TRANSITION"


def test_submit_scores_saved_answers_and_unanswered_items_then_is_idempotent(api_client) -> None:
    base_url, course_id, _ = api_client
    assessment = _create_and_start(base_url, course_id)
    question = assessment["questions"][0]
    selected = question["options"][0]["key"]
    _request(
        base_url,
        "PUT",
        f"/api/diagnostics/assessments/{assessment['id']}/responses/{question['assessment_question_id']}",
        {"selected_options": [selected]},
    )
    first_status, first = _request(base_url, "POST", f"/api/diagnostics/assessments/{assessment['id']}/submit")
    second_status, second = _request(base_url, "POST", f"/api/diagnostics/assessments/{assessment['id']}/submit")
    assert first_status == second_status == 200
    assert first == second
    assert first["total_questions"] == 8
    assert first["answered_questions"] == 1
    _, restored = _request(base_url, "GET", f"/api/diagnostics/assessments/{assessment['id']}")
    assert restored["status"] == "submitted"
    assert restored["answered_count"] == 1


def test_foreign_course_and_assessment_are_hidden_from_bootstrap_owner(api_client) -> None:
    base_url, _, other_course_id = api_client
    readiness_status, readiness = _request(base_url, "GET", f"/api/diagnostics/courses/{other_course_id}/readiness")
    create_status, _ = _request(base_url, "POST", "/api/diagnostics/assessments", {"course_id": other_course_id})
    assert readiness_status == create_status == 404
    assert readiness["error"]["code"] == "COURSE_NOT_FOUND"


def test_invalid_assessment_id_returns_safe_not_found(api_client) -> None:
    base_url, _, _ = api_client
    status, response = _request(base_url, "GET", "/api/diagnostics/assessments/99999")
    assert status == 404
    assert response["error"]["code"] == "ASSESSMENT_NOT_FOUND"


def test_history_contains_only_owner_assessments_and_persisted_result(api_client) -> None:
    base_url, course_id, _ = api_client
    assessment = _create_and_start(base_url, course_id)
    _request(base_url, "POST", f"/api/diagnostics/assessments/{assessment['id']}/submit")
    history_status, history = _request(base_url, "GET", "/api/diagnostics/assessments")
    result_status, result = _request(base_url, "GET", f"/api/diagnostics/assessments/{assessment['id']}/result")
    assert history_status == result_status == 200
    assert history["count"] == 1
    assert history["assessments"][0]["status"] == "submitted"
    assert result["assessment_id"] == assessment["id"]


def test_full_isolated_http_diagnostic_flow(api_client) -> None:
    """Exercise the production HTTP boundary with an isolated migrated database.

    This is intentionally a service-backed acceptance path: no response, score, or
    report value is injected by the test.  The seeded question bank supplies all
    three supported objective types and the running FastAPI application owns the
    lifecycle, persistence, deterministic scoring, and report aggregation.
    """
    base_url, course_id, _ = api_client

    readiness_status, readiness = _request(base_url, "GET", f"/api/diagnostics/courses/{course_id}/readiness")
    assert readiness_status == 200
    assert readiness["can_start"] is True

    assessment = _create_and_start(base_url, course_id)
    assert assessment["question_count"] == 8
    candidates = assessment["questions"]
    serialized_candidate_view = str(candidates)
    for private_field in ("correct_answer", "answer_key", "explanation", "scoring_policy", "points_awarded"):
        assert private_field not in serialized_candidate_view

    by_type = {candidate["question_type"]: candidate for candidate in candidates}
    assert set(by_type) == {"single_choice", "true_false", "multiple_choice"}
    answers = {
        "single_choice": ["A"],
        "true_false": ["TRUE"],
        "multiple_choice": ["A", "C"],
    }
    saved_ids: set[int] = set()
    for question_type, selected_options in answers.items():
        candidate = by_type[question_type]
        saved_status, saved = _request(
            base_url,
            "PUT",
            f"/api/diagnostics/assessments/{assessment['id']}/responses/{candidate['assessment_question_id']}",
            {"schema_version": "objective_answer_v1", "selected_options": selected_options},
        )
        assert saved_status == 200
        assert saved["selected_options"] == selected_options
        saved_ids.add(candidate["assessment_question_id"])

    restored_status, restored = _request(base_url, "GET", f"/api/diagnostics/assessments/{assessment['id']}")
    assert restored_status == 200
    assert restored["status"] == "in_progress"
    assert restored["answered_count"] == 3
    restored_answers = {
        item["assessment_question_id"]: item["saved_answer"]
        for item in restored["questions"]
        if item["saved_answer"] is not None
    }
    assert set(restored_answers) == saved_ids
    assert sorted(restored_answers.values()) == [["A"], ["A", "C"], ["TRUE"]]

    submit_status, result = _request(base_url, "POST", f"/api/diagnostics/assessments/{assessment['id']}/submit")
    assert submit_status == 200
    assert result["total_questions"] == 8
    assert result["answered_questions"] == result["correct_questions"] == 3
    assert result["accuracy"] == "0.375"
    assert result["report_policy_version"] == "diagnostic_node_performance_v1"
    assert result["knowledge_performance"][0]["question_count"] == 8
    assert result["knowledge_performance"][0]["preliminary_status"] == "needs_attention"
    assert result["question_reviews"]
    assert any(not review["selected_options"] for review in result["question_reviews"])
    assert all(review["source_refs"] for review in result["question_reviews"])

    report_status, historical_result = _request(
        base_url, "GET", f"/api/diagnostics/assessments/{assessment['id']}/result"
    )
    repeated_submit_status, repeated_submit = _request(
        base_url, "POST", f"/api/diagnostics/assessments/{assessment['id']}/submit"
    )
    assert report_status == repeated_submit_status == 200
    assert historical_result == repeated_submit == result

    locked_status, locked = _request(
        base_url,
        "PUT",
        f"/api/diagnostics/assessments/{assessment['id']}/responses/"
        f"{by_type['single_choice']['assessment_question_id']}",
        {"schema_version": "objective_answer_v1", "selected_options": ["B"]},
    )
    assert locked_status == 409
    assert locked["error"]["code"] == "ASSESSMENT_INVALID_TRANSITION"
