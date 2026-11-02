from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import Course, KnowledgeNode, User
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance

ROOT = Path(__file__).resolve().parents[2]


def _alembic(database: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{database}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_expected_schema(database: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        inspector = inspect(engine)
        users = {item["name"]: item for item in inspector.get_indexes("users")}
        unique = {item["name"]: item for item in inspector.get_unique_constraints("users")}
        candidates = {item["name"]: item for item in inspector.get_indexes("knowledge_candidates")}
        nodes = {item["name"]: item for item in inspector.get_indexes("knowledge_nodes")}
        assert users["ix_users_email"]["column_names"] == ["email"]
        assert not users["ix_users_email"]["unique"]
        assert unique["uq_users_email"]["column_names"] == ["email"]
        assert candidates["uq_knowledge_candidates_id_course"]["column_names"] == ["id", "course_id"]
        assert candidates["uq_knowledge_candidates_id_course"]["unique"]
        assert nodes["ix_knowledge_nodes_course_active"]["column_names"] == ["course_id", "is_active"]
        assert not nodes["ix_knowledge_nodes_course_active"]["unique"]
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert conn.exec_driver_sql("PRAGMA index_list(knowledge_candidates)").all()
    finally:
        engine.dispose()


def test_fresh_upgrade_check_and_constraint_behavior(tmp_path: Path) -> None:
    database = tmp_path / "fresh.sqlite3"
    _success(_alembic(database, "upgrade", "head"))
    _success(_alembic(database, "check"))
    _success(_alembic(database, "upgrade", "head"))
    _assert_expected_schema(database)

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with Session(engine) as session, session.begin():
            session.add_all(
                [
                    User(email="one@example.test", display_name="One", is_active=True),
                    User(email="two@example.test", display_name="Two", is_active=True),
                ]
            )
        with Session(engine) as session, pytest.raises(IntegrityError):
            with session.begin():
                session.add(User(email="one@example.test", display_name="Duplicate", is_active=True))
                session.flush()
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO courses (owner_id, name, description, created_at, updated_at) "
                        "VALUES (99999, :name, :description, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"name": "Invalid owner", "description": ""},
                )
    finally:
        engine.dispose()


def test_existing_database_upgrade_preserves_valid_data(tmp_path: Path) -> None:
    database = tmp_path / "existing.sqlite3"
    _success(_alembic(database, "upgrade", "0018_m7_5_practice_evidence"))
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with Session(engine) as session, session.begin():
            user = User(email="legacy@example.test", display_name="Legacy", is_active=True)
            session.add(user)
            session.flush()
            course = Course(owner_id=user.id, name="Existing", description="Preserve")
            session.add(course)
            session.flush()
            session.add(
                KnowledgeNode(
                    course_id=course.id,
                    name="Original",
                    normalized_name="original",
                    description="Preserve node",
                    importance=KnowledgeImportance.HIGH,
                    difficulty=KnowledgeDifficulty.BASIC,
                    is_active=True,
                )
            )
    finally:
        engine.dispose()
    _success(_alembic(database, "upgrade", "head"))
    _success(_alembic(database, "check"))
    _assert_expected_schema(database)
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with Session(engine) as session:
            assert session.query(User).filter_by(email="legacy@example.test").one().display_name == "Legacy"
            assert session.query(Course).filter_by(name="Existing").one().description == "Preserve"
            assert (
                session.query(KnowledgeNode).filter_by(normalized_name="original").one().description == "Preserve node"
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("index_name", ["ix_knowledge_nodes_course_active", "uq_knowledge_candidates_id_course"])
def test_actual_index_drift_is_detected(tmp_path: Path, index_name: str) -> None:
    database = tmp_path / "drift.sqlite3"
    _success(_alembic(database, "upgrade", "head"))
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP INDEX {index_name}")
    finally:
        engine.dispose()
    result = _alembic(database, "check")
    assert result.returncode != 0
    assert index_name in result.stdout + result.stderr
