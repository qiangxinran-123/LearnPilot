from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeNode,
    KnowledgeSource,
    LearningEvidence,
    Material,
    MaterialContent,
    StudentKnowledgeState,
    User,
)
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance, LearningSessionTaskPhase
from backend.app.schemas.learning_session import LearningSessionCreate
from backend.app.services.learning_content_service import LearningContentError, LearningContentService
from backend.app.services.learning_session_service import LearningSessionService


@pytest.fixture
def content_database(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'm7_2.sqlite3'}"
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
        systems = Course(owner_id=owner.id, name="Computer Systems", description="")
        unrelated = Course(owner_id=owner.id, name="Operating Systems", description="")
        private = Course(owner_id=other.id, name="Private", description="")
        session.add_all([systems, unrelated, private])
        session.flush()
        mapping = KnowledgeNode(
            course_id=systems.id,
            name="Cache Mapping",
            normalized_name="cache mapping",
            description="Cache mapping uses temporal and spatial locality.",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
        )
        lru = KnowledgeNode(
            course_id=systems.id,
            name="LRU Replacement",
            normalized_name="lru replacement",
            description="Least recently used replacement policy.",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
        )
        empty = KnowledgeNode(
            course_id=systems.id,
            name="Quantum Entanglement",
            normalized_name="quantum entanglement",
            description="Photons and Bell inequalities.",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
        )
        foreign_node = KnowledgeNode(
            course_id=unrelated.id,
            name="Cache Mapping",
            normalized_name="cache mapping",
            description="A same-name term in another course.",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
        )
        session.add_all([mapping, lru, empty, foreign_node])
        session.flush()

        material_a = Material(
            course_id=systems.id,
            title="Cache Lecture",
            material_type="document",
            extension="pdf",
            extraction_status="SUCCESS",
            text_extracted=True,
        )
        material_b = Material(
            course_id=systems.id,
            title="Replacement Policies",
            material_type="document",
            extension="txt",
            extraction_status="SUCCESS",
            text_extracted=True,
        )
        material_c = Material(
            course_id=unrelated.id,
            title="Other Course Cache",
            material_type="document",
            extension="md",
            extraction_status="SUCCESS",
            text_extracted=True,
        )
        failed = Material(
            course_id=systems.id,
            title="Broken Notes",
            material_type="document",
            extension="docx",
            extraction_status="PARSE_FAILED",
            text_extracted=False,
        )
        session.add_all([material_a, material_b, material_c, failed])
        session.flush()
        mapping_text = (
            "Cache mapping places memory blocks into cache sets. Temporal locality reuses recent data, "
            "while spatial locality accesses nearby addresses."
        )
        lru_text = "LRU replaces the least recently used cache line in a set associative cache."
        session.add_all(
            [
                MaterialContent(
                    material_id=material_a.id,
                    plain_text=mapping_text,
                    segments=[
                        {"text": mapping_text, "source_reference": "PDF 第 2 页"},
                        {"text": mapping_text, "source_reference": "PDF 第 2 页"},
                    ],
                    content_hash="a" * 64,
                    parser_name="pypdf",
                    parser_version="1",
                    page_count=2,
                ),
                MaterialContent(
                    material_id=material_b.id,
                    plain_text=lru_text,
                    segments=[{"text": lru_text, "source_reference": "TXT segment 1"}],
                    content_hash="b" * 64,
                    parser_name="text",
                    parser_version="1",
                    page_count=0,
                ),
                MaterialContent(
                    material_id=material_c.id,
                    plain_text="Cache mapping in the wrong course must never leak.",
                    segments=[
                        {
                            "text": "Cache mapping in the wrong course must never leak.",
                            "source_reference": "MD 第1节",
                        }
                    ],
                    content_hash="c" * 64,
                    parser_name="markdown",
                    parser_version="1",
                    page_count=0,
                ),
                MaterialContent(
                    material_id=failed.id,
                    plain_text="Quantum entanglement should be ignored after parse failure.",
                    segments=[
                        {
                            "text": "Quantum entanglement should be ignored after parse failure.",
                            "source_reference": "DOCX 段落 1",
                        }
                    ],
                    content_hash="d" * 64,
                    parser_name="docx",
                    parser_version="1",
                    page_count=0,
                ),
            ]
        )
        session.add_all(
            [
                KnowledgeSource(
                    knowledge_node_id=mapping.id,
                    material_id=material_a.id,
                    source_reference="PDF 第 2 页",
                ),
                KnowledgeSource(
                    knowledge_node_id=mapping.id,
                    material_id=material_a.id,
                    source_reference="PDF 第 99 页",
                ),
            ]
        )
        ids = {
            "owner": owner.id,
            "other": other.id,
            "systems": systems.id,
            "unrelated": unrelated.id,
            "private": private.id,
            "mapping": mapping.id,
            "lru": lru.id,
            "empty": empty.id,
            "foreign_node": foreign_node.id,
            "material_a": material_a.id,
            "material_b": material_b.id,
            "material_c": material_c.id,
            "failed": failed.id,
        }
    yield factory, ids, database_url
    engine.dispose()


def _settings(database_url: str, *, email: str = "legacy-bootstrap@learnpilot.local") -> Settings:
    return Settings(database_url=database_url, legacy_bootstrap_user=email, llm_mode="mock")


def _create_session(factory, ids, database_url: str, node_key: str = "mapping") -> int:
    with factory() as session:
        created = LearningSessionService(session, _settings(database_url)).create_for_configured_user(
            LearningSessionCreate(course_id=ids["systems"], target_knowledge_node_id=ids[node_key])
        )
        return created.session_id


def _content(factory, database_url: str, session_id: int, *, settings: Settings | None = None):
    with factory() as session:
        return LearningContentService(session, settings or _settings(database_url)).get_for_configured_user(
            session_id=session_id,
            phase=LearningSessionTaskPhase.CONCEPT_LEARNING,
        )


def test_source_first_retrieval_is_traceable_deduplicated_and_stable(content_database) -> None:
    factory, ids, database_url = content_database
    session_id = _create_session(factory, ids, database_url)
    first = _content(factory, database_url, session_id)
    second = _content(factory, database_url, session_id)

    assert first.status == "ready"
    assert first.grounded is True
    assert first.segments[0].material_id == ids["material_a"]
    assert first.segments[0].source_reference == "PDF 第 2 页"
    assert first.segments[0].relevance == "direct"
    assert all(item.source_reference != "PDF 第 99 页" for item in first.segments)
    assert len({(item.material_id, item.source_reference, item.text) for item in first.segments}) == len(first.segments)
    assert first.model_dump() == second.model_dump()


def test_lexical_fallback_finds_second_material_without_cross_course_leak(content_database) -> None:
    factory, ids, database_url = content_database
    session_id = _create_session(factory, ids, database_url, "lru")
    result = _content(factory, database_url, session_id)

    assert result.status == "ready"
    assert result.grounded is False
    assert any(item.material_id == ids["material_b"] and item.relevance == "supplemental" for item in result.segments)
    assert all(item.material_id != ids["material_c"] for item in result.segments)


def test_empty_and_parse_failed_materials_do_not_fabricate_content(content_database) -> None:
    factory, ids, database_url = content_database
    session_id = _create_session(factory, ids, database_url, "empty")
    result = _content(factory, database_url, session_id)

    assert result.status == "empty"
    assert result.grounded is False
    assert result.segments == []


def test_deleted_material_and_sources_are_not_returned(content_database) -> None:
    factory, ids, database_url = content_database
    session_id = _create_session(factory, ids, database_url)
    with factory() as session, session.begin():
        session.execute(delete(KnowledgeSource).where(KnowledgeSource.material_id == ids["material_a"]))
        material = session.get(Material, ids["material_a"])
        assert material is not None
        session.delete(material)
    result = _content(factory, database_url, session_id)
    assert all(item.material_id != ids["material_a"] for item in result.segments)


def test_limits_and_per_material_cap_are_enforced(content_database) -> None:
    factory, ids, database_url = content_database
    with factory() as session, session.begin():
        content = session.scalar(select(MaterialContent).where(MaterialContent.material_id == ids["material_a"]))
        assert content is not None
        content.segments = [
            {"text": f"Cache mapping locality {index} " + ("x" * 900), "source_reference": f"PDF 第 {index + 1} 页"}
            for index in range(8)
        ]
        source = session.scalar(select(KnowledgeSource).where(KnowledgeSource.source_reference == "PDF 第 2 页"))
        assert source is not None
        source.source_reference = "PDF 第 1 页"
    session_id = _create_session(factory, ids, database_url)
    constrained = _settings(database_url).model_copy(
        update={"llm_context_chars": 2000, "llm_chunk_chars": 400, "llm_chunk_overlap_chars": 50}
    )
    result = _content(factory, database_url, session_id, settings=constrained)

    assert len(result.segments) <= result.limits.max_segments
    assert sum(len(item.text) for item in result.segments) <= result.limits.max_total_chars
    assert all(len(item.text) <= result.limits.max_segment_chars for item in result.segments)
    counts = {
        material_id: sum(item.material_id == material_id for item in result.segments) for material_id in ids.values()
    }
    assert max(counts.values()) <= result.limits.max_segments_per_material
    assert any(item.text_truncated for item in result.segments)


def test_session_ownership_and_adaptive_phase_are_rejected(content_database) -> None:
    factory, ids, database_url = content_database
    session_id = _create_session(factory, ids, database_url)
    with factory() as session:
        other_service = LearningContentService(session, _settings(database_url, email="other@example.test"))
        with pytest.raises(LearningContentError) as ownership:
            other_service.get_for_configured_user(
                session_id=session_id,
                phase=LearningSessionTaskPhase.CONCEPT_LEARNING,
            )
        assert ownership.value.code == "SESSION_NOT_FOUND"
    with factory() as session:
        service = LearningContentService(session, _settings(database_url))
        with pytest.raises(LearningContentError) as phase:
            service.get_for_configured_user(
                session_id=session_id,
                phase=LearningSessionTaskPhase.ADAPTIVE_PRACTICE,
            )
        assert phase.value.code == "CONTENT_PHASE_NOT_AVAILABLE"


def test_retrieval_is_read_only_for_learning_state(content_database) -> None:
    factory, ids, database_url = content_database
    session_id = _create_session(factory, ids, database_url)
    with factory() as session:
        before = (
            session.scalar(select(func.count()).select_from(LearningEvidence)),
            session.scalar(select(func.count()).select_from(StudentKnowledgeState)),
        )
    _content(factory, database_url, session_id)
    with factory() as session:
        after = (
            session.scalar(select(func.count()).select_from(LearningEvidence)),
            session.scalar(select(func.count()).select_from(StudentKnowledgeState)),
        )
    assert after == before


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _request(base_url: str, path: str):
    request = Request(f"{base_url}{path}", method="GET")
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as error:
        with error:
            return error.code, json.loads(error.read().decode())


def test_http_content_contract_and_error_envelope(content_database) -> None:
    factory, ids, database_url = content_database
    session_id = _create_session(factory, ids, database_url)
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
                raise RuntimeError("M7-2 test server stopped during startup.")
            time.sleep(0.05)
    else:
        process.terminate()
        raise RuntimeError("M7-2 test server did not start.")
    try:
        status, body = _request(base_url, f"/api/learning/sessions/{session_id}/content")
        assert status == 200
        assert body["session_id"] == session_id
        assert body["status"] == "ready"
        assert body["segments"][0]["source_reference"] == "PDF 第 2 页"

        blocked_status, blocked = _request(
            base_url,
            f"/api/learning/sessions/{session_id}/content?phase=adaptive_practice",
        )
        assert blocked_status == 409
        assert blocked["error"]["code"] == "CONTENT_PHASE_NOT_AVAILABLE"
        missing_status, missing = _request(base_url, "/api/learning/sessions/999999/content")
        assert missing_status == 404
        assert missing["error"]["code"] == "SESSION_NOT_FOUND"
    finally:
        process.terminate()
        process.wait(timeout=5)
