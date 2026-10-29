import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import Course, MasteryHistory, User
from backend.app.services.progress_trend_service import ProgressTrendService
from backend.tests.test_m5d_student_state_api import _node
from backend.tests.test_m5d_student_state_api import database as database


def test_upgrade_populated_0018_enables_empty_trend_without_backfill(tmp_path: Path):
    url = f"sqlite+pysqlite:///{tmp_path / 'pre_m8.sqlite3'}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0018_m7_5_practice_evidence"],
        check=True,
        env=env,
        capture_output=True,
    )
    engine = create_engine(url)
    with Session(engine) as session, session.begin():
        owner = User(email="legacy-bootstrap@learnpilot.local", display_name="Owner", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="Existing course", description="")
        session.add(course)
        session.flush()
        session.add(_node(course.id, "Existing node"))
        course_id = course.id
    assert "mastery_history" not in inspect(engine).get_table_names()
    with Session(engine) as session, pytest.raises(OperationalError, match="no such table: mastery_history"):
        ProgressTrendService(session, Settings(database_url=url)).trend(course_id, "30d")
    engine.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env, capture_output=True)
    engine = create_engine(url)
    with Session(engine) as session:
        result = ProgressTrendService(session, Settings(database_url=url)).trend(course_id, "30d")
        assert result.points == []
        assert result.course_id == course_id
        assert session.scalar(select(func.count()).select_from(Course)) == 1
        assert session.scalar(select(func.count()).select_from(MasteryHistory)) == 0
    engine.dispose()


def test_other_owned_course_history_does_not_change_trend(database):
    from backend.app.db.models import LearningEvidence, StudentKnowledgeState
    from backend.app.services.mastery_service import MasteryService
    from backend.tests.test_m5d_student_state_api import _add_evidence, _seed_calculated_state

    factory, ids, _, _ = database
    with factory() as session:
        _seed_calculated_state(session, ids)
        other = Course(owner_id=ids["owner"], name="Other course", description="")
        session.add(other)
        session.flush()
        node = _node(other.id, "Other node")
        session.add(node)
        session.flush()
        other_ids = {"owner": ids["owner"], "course": other.id, "node": node.id}
        for index in range(3):
            _add_evidence(session, other_ids, score="0", offset=index)
        session.commit()
        MasteryService(session).refresh_state(user_id=ids["owner"], course_id=other.id, knowledge_node_id=node.id)
        session.commit()
        before = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (MasteryHistory, StudentKnowledgeState, LearningEvidence)
        )
        before_states = session.execute(
            select(
                StudentKnowledgeState.id,
                StudentKnowledgeState.mastery_score,
                StudentKnowledgeState.evidence_fingerprint,
                StudentKnowledgeState.calculated_at,
            ).order_by(StudentKnowledgeState.id)
        ).all()
        session.rollback()
        trend = ProgressTrendService(session, Settings(database_url="sqlite://")).trend(ids["course"], "all")
        assert len(trend.points) == 1
        assert trend.course_id == ids["course"]
        assert not trend.excluded_incompatible_history
        session.rollback()
        after = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (MasteryHistory, StudentKnowledgeState, LearningEvidence)
        )
        assert before == after
        after_states = session.execute(
            select(
                StudentKnowledgeState.id,
                StudentKnowledgeState.mastery_score,
                StudentKnowledgeState.evidence_fingerprint,
                StudentKnowledgeState.calculated_at,
            ).order_by(StudentKnowledgeState.id)
        ).all()
        assert before_states == after_states
