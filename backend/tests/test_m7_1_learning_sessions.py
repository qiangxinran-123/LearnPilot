from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeNode,
    LearningPlan,
    LearningSession,
    LearningSessionTaskState,
    LearningTask,
    User,
)
from backend.app.models import (
    KnowledgeDifficulty,
    KnowledgeImportance,
    LearningPlanStatus,
    LearningSessionStatus,
    LearningSessionTaskPhase,
    LearningSessionTaskStatus,
    LearningTaskType,
)
from backend.app.schemas.learning_session import LearningSessionCreate, LearningSessionTaskUpdate
from backend.app.services.learning_session_service import LearningSessionError, LearningSessionService


@pytest.fixture
def database(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'm7_1.sqlite3'}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        owner = User(email="legacy-bootstrap@learnpilot.local", display_name="Owner", is_active=True)
        other = User(email="other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="Algorithms", description="")
        other_course = Course(owner_id=other.id, name="Private", description="")
        session.add_all([course, other_course])
        session.flush()
        node = KnowledgeNode(
            course_id=course.id,
            name="Graph traversal",
            normalized_name="graph traversal",
            description="",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
            managed_by_canonicalization=True,
        )
        other_node = KnowledgeNode(
            course_id=other_course.id,
            name="Private node",
            normalized_name="private node",
            description="",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
            managed_by_canonicalization=True,
        )
        session.add_all([node, other_node])
        session.flush()
        plan = LearningPlan(
            user_id=owner.id,
            course_id=course.id,
            target_node_id=node.id,
            reason_codes=["knowledge_gap"],
            priority_score=Decimal("0.5000"),
            priority_breakdown={
                "knowledge_gap": "0.5000",
                "dependency_importance": "0.5000",
                "course_importance": "0.5000",
                "review_risk": "0.5000",
                "total_priority": "0.5000",
            },
            prerequisite_evidence=[],
            blocked_target_node_ids=[],
            context_fingerprint="a" * 64,
            status=LearningPlanStatus.AVAILABLE,
            active_slot=1,
            plan_schema_version="learning_plan_v1",
            tasks=[
                LearningTask(
                    knowledge_node_id=node.id,
                    task_type=LearningTaskType.CONCEPT_REVIEW,
                    title="Review",
                    description="Review graph traversal.",
                    order_index=0,
                    estimated_minutes=10,
                ),
                LearningTask(
                    knowledge_node_id=node.id,
                    task_type=LearningTaskType.EXAMPLE_WALKTHROUGH,
                    title="Example",
                    description="Inspect an example.",
                    order_index=1,
                    estimated_minutes=10,
                ),
            ],
        )
        session.add(plan)
        session.flush()
        ids = {
            "owner": owner.id,
            "other": other.id,
            "course": course.id,
            "other_course": other_course.id,
            "node": node.id,
            "other_node": other_node.id,
            "plan": plan.id,
        }
    yield factory, ids, database_url
    engine.dispose()


def _service(factory, *, email: str = "legacy-bootstrap@learnpilot.local"):
    session = factory()
    return session, LearningSessionService(
        session, Settings(database_url="sqlite+pysqlite://", legacy_bootstrap_user=email)
    )


def test_create_from_available_plan_initializes_frozen_tasks_and_reuses(database) -> None:
    factory, ids, _url = database
    session, service = _service(factory)
    with session:
        created = service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], learning_plan_id=ids["plan"])
        )
        repeated = service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], learning_plan_id=ids["plan"])
        )
        assert created.status == LearningSessionStatus.CREATED
        assert repeated.reused is True
        assert repeated.session_id == created.session_id
        assert [task.phase for task in created.tasks] == list(LearningSessionTaskPhase)
        assert all(task.status == LearningSessionTaskStatus.NOT_STARTED for task in created.tasks)
        assert created.tasks[0].source_learning_task_id is not None
        assert created.tasks[1].source_learning_task_id is not None
        assert created.tasks[2].source_learning_task_id is None
        assert session.scalar(select(func.count()).select_from(LearningSession)) == 1
        assert session.scalar(select(func.count()).select_from(LearningSessionTaskState)) == 3


@pytest.mark.parametrize("kind", ["course", "node", "cross_course"])
def test_creation_rejects_invalid_scope(database, kind: str) -> None:
    factory, ids, _url = database
    session, service = _service(factory)
    with session, pytest.raises(LearningSessionError) as captured:
        if kind == "course":
            payload = LearningSessionCreate(course_id=99999, target_knowledge_node_id=ids["node"])
        elif kind == "node":
            payload = LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=99999)
        else:
            payload = LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=ids["other_node"])
        service.create_for_configured_user(payload)
    expected = "COURSE_NOT_FOUND" if kind == "course" else "KNOWLEDGE_NODE_NOT_FOUND"
    assert captured.value.code == expected


def test_task_state_machine_resume_and_cancel_are_persistent(database) -> None:
    factory, ids, _url = database
    session, service = _service(factory)
    with session:
        created = service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=ids["node"])
        )
        with pytest.raises(LearningSessionError) as order_error:
            service.update_task_for_configured_user(
                session_id=created.session_id,
                phase=LearningSessionTaskPhase.GUIDED_EXAMPLE,
                payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.IN_PROGRESS),
            )
        assert order_error.value.code == "TASK_ORDER_VIOLATION"

        started = service.update_task_for_configured_user(
            session_id=created.session_id,
            phase=LearningSessionTaskPhase.CONCEPT_LEARNING,
            payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.IN_PROGRESS),
        )
        replay = service.update_task_for_configured_user(
            session_id=created.session_id,
            phase=LearningSessionTaskPhase.CONCEPT_LEARNING,
            payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.IN_PROGRESS),
        )
        assert started.status == LearningSessionStatus.IN_PROGRESS
        assert replay.tasks[0].started_at == started.tasks[0].started_at
        with pytest.raises(LearningSessionError) as skip_error:
            service.update_task_for_configured_user(
                session_id=created.session_id,
                phase=LearningSessionTaskPhase.CONCEPT_LEARNING,
                payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.NOT_STARTED),
            )
        assert skip_error.value.code == "INVALID_TASK_TRANSITION"

    restarted, restarted_service = _service(factory)
    with restarted:
        restored = restarted_service.get_for_configured_user(created.session_id)
        assert restored.status == LearningSessionStatus.IN_PROGRESS
        assert restored.tasks[0].status == LearningSessionTaskStatus.IN_PROGRESS
        active = restarted_service.get_active_for_configured_user(ids["course"])
        assert active.session is not None and active.session.session_id == created.session_id
        cancelled = restarted_service.cancel_for_configured_user(created.session_id)
        repeated_cancel = restarted_service.cancel_for_configured_user(created.session_id)
        assert cancelled.status == LearningSessionStatus.CANCELLED
        assert repeated_cancel.cancelled_at is not None and cancelled.cancelled_at is not None
        assert repeated_cancel.cancelled_at.replace(tzinfo=None) == cancelled.cancelled_at.replace(tzinfo=None)
        assert restarted_service.get_active_for_configured_user(ids["course"]).session is None
        with pytest.raises(LearningSessionError) as write_error:
            restarted_service.update_task_for_configured_user(
                session_id=created.session_id,
                phase=LearningSessionTaskPhase.CONCEPT_LEARNING,
                payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.COMPLETED),
            )
        assert write_error.value.code == "SESSION_NOT_WRITABLE"


def test_adaptive_practice_cannot_be_fabricated(database) -> None:
    factory, ids, _url = database
    session, service = _service(factory)
    with session:
        created = service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=ids["node"])
        )
        with pytest.raises(LearningSessionError) as captured:
            service.update_task_for_configured_user(
                session_id=created.session_id,
                phase=LearningSessionTaskPhase.ADAPTIVE_PRACTICE,
                payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.IN_PROGRESS),
            )
        assert captured.value.code == "TASK_PHASE_NOT_AVAILABLE"
        stored = service.get_for_configured_user(created.session_id)
        assert stored.tasks[2].status == LearningSessionTaskStatus.NOT_STARTED
        assert stored.status == LearningSessionStatus.CREATED


def test_other_user_cannot_read_or_reuse_session(database) -> None:
    factory, ids, _url = database
    owner_session, owner_service = _service(factory)
    with owner_session:
        created = owner_service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=ids["node"])
        )
    other_session, other_service = _service(factory, email="other@example.test")
    with other_session, pytest.raises(LearningSessionError) as captured:
        other_service.get_for_configured_user(created.session_id)
    assert captured.value.code == "SESSION_NOT_FOUND"


def test_inactive_target_keeps_history_readable_but_blocks_progress(database) -> None:
    factory, ids, _url = database
    owner_session, owner_service = _service(factory)
    with owner_session:
        created = owner_service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=ids["node"])
        )
    with factory() as session, session.begin():
        node = session.get(KnowledgeNode, ids["node"])
        assert node is not None
        node.is_active = False
    restarted, restarted_service = _service(factory)
    with restarted:
        assert restarted_service.get_for_configured_user(created.session_id).session_id == created.session_id
        with pytest.raises(LearningSessionError) as captured:
            restarted_service.update_task_for_configured_user(
                session_id=created.session_id,
                phase=LearningSessionTaskPhase.CONCEPT_LEARNING,
                payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.IN_PROGRESS),
            )
        assert captured.value.code == "KNOWLEDGE_NODE_INACTIVE"


def test_migration_upgrades_a_populated_m6_database(tmp_path: Path) -> None:
    path = tmp_path / "populated-m6.sqlite3"
    database_url = f"sqlite+pysqlite:///{path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0014_m6_ux_fix4_sync_counts"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    engine = create_engine(database_url)
    with sessionmaker(bind=engine)() as session, session.begin():
        owner = User(email="migration@example.test", display_name="Migration", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="Existing M6 Course", description="")
        session.add(course)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    inspector = inspect(engine)
    assert {"learning_sessions", "learning_session_task_states"}.issubset(inspector.get_table_names())
    with sessionmaker(bind=engine)() as session:
        assert session.scalar(select(func.count()).select_from(Course)) == 1
    engine.dispose()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _request(base_url: str, method: str, path: str, payload: object | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as error:
        with error:
            return error.code, json.loads(error.read().decode())


def test_http_contract_and_error_envelope(database) -> None:
    _factory, ids, database_url = database
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update({"DATABASE_URL": database_url, "APP_ENV": "test", "LLM_MODE": "mock"})
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
                raise RuntimeError("M7-1 test server stopped during startup.")
            time.sleep(0.05)
    else:
        process.terminate()
        raise RuntimeError("M7-1 test server did not start.")
    try:
        status, created = _request(
            base_url,
            "POST",
            "/api/learning/sessions",
            {"course_id": ids["course"], "learning_plan_id": ids["plan"]},
        )
        assert status == 201
        session_id = created["session_id"]
        assert _request(base_url, "GET", f"/api/learning/sessions/{session_id}")[0] == 200
        active_status, active = _request(base_url, "GET", f"/api/learning/sessions/active?course_id={ids['course']}")
        assert active_status == 200 and active["session"]["session_id"] == session_id
        blocked_status, blocked = _request(
            base_url,
            "PATCH",
            f"/api/learning/sessions/{session_id}/tasks/adaptive_practice",
            {"status": "completed"},
        )
        assert blocked_status == 409
        assert blocked["error"]["code"] == "TASK_PHASE_NOT_AVAILABLE"
        assert _request(base_url, "POST", f"/api/learning/sessions/{session_id}/cancel")[0] == 200
        missing_status, missing = _request(base_url, "GET", "/api/learning/sessions/999999")
        assert missing_status == 404
        assert missing["error"]["code"] == "SESSION_NOT_FOUND"
    finally:
        process.terminate()
        process.wait(timeout=5)
