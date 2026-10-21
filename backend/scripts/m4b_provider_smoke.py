from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    CourseKnowledgeBuildState,
    KnowledgeNode,
    KnowledgeSource,
    Material,
    MaterialContent,
    User,
)
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance, QuestionDifficulty, QuestionType
from backend.app.services.diagnostic_question_generation import (
    DiagnosticQuestionGenerationError,
    DiagnosticQuestionGenerationService,
)


def _upgrade(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    config = Config("alembic.ini")
    command.upgrade(config, "head")


def _seed(session: Session) -> tuple[int, int, int]:
    with session.begin():
        owner = User(email="m4b-smoke@example.test", display_name="M4B Smoke", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="M4B Isolated Smoke Course", description="")
        session.add(course)
        session.flush()
        node = KnowledgeNode(
            course_id=course.id,
            name="LRU Cache Replacement",
            normalized_name="lru cache replacement",
            description="Use recent access history to choose the least recently used cache block for replacement.",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
            managed_by_canonicalization=True,
        )
        session.add(node)
        session.flush()
        material = Material(
            course_id=course.id,
            title="LRU Smoke Notes",
            material_type="document",
            original_filename="lru-smoke.txt",
            extension="txt",
            extraction_status="SUCCESS",
            text_extracted=True,
            text_preview="LRU notes",
            text_length=360,
        )
        session.add(material)
        session.flush()
        reference = "TXT 第1段"
        text = (
            "LRU（Least Recently Used）依据访问历史选择替换对象。缓存已满且发生缺失时，"
            "它替换最长时间没有被访问的缓存块，而不是最近访问的块。实现可以维护每个块的访问次序。"
            "因此，正确识别最近使用次序是应用 LRU 的关键。"
        )
        session.add_all(
            [
                MaterialContent(
                    material_id=material.id,
                    plain_text=text,
                    segments=[{"source_reference": reference, "text": text}],
                    content_hash="1" * 64,
                    parser_name="smoke-text",
                    parser_version="1",
                    page_count=0,
                ),
                KnowledgeSource(
                    knowledge_node_id=node.id,
                    material_id=material.id,
                    source_reference=reference,
                    excerpt=text,
                ),
                CourseKnowledgeBuildState(course_id=course.id, status="success", stage="complete"),
            ]
        )
        return owner.id, course.id, node.id


def main() -> int:
    settings = Settings()
    safe_status = {
        "configured": bool(settings.llm_api_key and settings.llm_base_url and settings.llm_model),
        "mode": settings.llm_mode,
        "model": settings.llm_model or "UNSET",
    }
    if not safe_status["configured"] or settings.llm_mode == "mock":
        print(json.dumps({**safe_status, "status": "BLOCKED", "code": "AI_NOT_CONFIGURED"}, ensure_ascii=False))
        return 2

    with TemporaryDirectory(prefix="learnpilot-m4b-smoke-") as directory:
        database_url = f"sqlite+pysqlite:///{Path(directory) / 'smoke.sqlite3'}"
        _upgrade(database_url)
        engine = create_engine(database_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        try:
            with Session(engine, expire_on_commit=False) as session:
                owner_id, course_id, node_id = _seed(session)
                service = DiagnosticQuestionGenerationService(session, settings)
                plan = [
                    (QuestionType.SINGLE_CHOICE, QuestionDifficulty.EASY, 2),
                    (QuestionType.TRUE_FALSE, QuestionDifficulty.EASY, 1),
                    (QuestionType.MULTIPLE_CHOICE, QuestionDifficulty.MEDIUM, 1),
                ]
                results = []
                for question_type, difficulty, count in plan:
                    result = service.generate_questions_for_node(
                        owner_id=owner_id,
                        course_id=course_id,
                        knowledge_node_id=node_id,
                        question_type=question_type,
                        difficulty=difficulty,
                        count=count,
                    )
                    results.append(
                        {
                            "question_type": question_type.value,
                            "accepted": result.accepted_count,
                            "provider": result.provider,
                            "model": result.model,
                        }
                    )
                print(json.dumps({**safe_status, "status": "PASS", "results": results}, ensure_ascii=False))
                return 0
        except DiagnosticQuestionGenerationError as error:
            print(
                json.dumps(
                    {**safe_status, "status": "FAIL", "code": error.code, "message": error.message},
                    ensure_ascii=False,
                )
            )
            return 1
        finally:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
