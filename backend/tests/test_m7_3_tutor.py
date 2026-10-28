from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from backend.app.ai.client import GeneratedStructuredOutput, LLMClient
from backend.app.ai.errors import AIServiceError
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeNode,
    KnowledgeSource,
    LearningEvidence,
    LearningPlan,
    Material,
    MaterialContent,
    StudentKnowledgeState,
    TutorMessage,
    User,
)
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance, TeachingStrategy
from backend.app.schemas.learning_session import LearningSessionCreate
from backend.app.schemas.tutor import TutorMessageCreate, TutorStructuredOutput
from backend.app.services.learning_session_service import LearningSessionService
from backend.app.services.tutor_service import STRATEGY_RULES, TutorError, TutorService


class FakeTutorClient(LLMClient):
    provider = "fake-provider"
    model = "fake-tutor"

    def __init__(self, *, invalid_reference: bool = False, error_code: str | None = None) -> None:
        self.invalid_reference = invalid_reference
        self.error_code = error_code
        self.calls: list[list[dict[str, str]]] = []

    def generate_structured(self, *, operation, messages, schema):
        assert operation == "learning_tutor"
        assert schema is TutorStructuredOutput
        self.calls.append(messages)
        if self.error_code:
            raise AIServiceError(self.error_code, "provider failure", retryable=False)
        joined = "\n".join(item["content"] for item in messages)
        mode = re.search(r"TEACHING_MODE=([a-z_]+)", joined)
        source = re.search(r'<source material_id="(\d+)" reference="([^"]+)"', joined)
        citations = []
        if self.invalid_reference:
            citations = [{"material_id": 999999, "source_reference": "PDF 第 99 页"}]
        elif source:
            citations = [{"material_id": int(source.group(1)), "source_reference": source.group(2)}]
        output = TutorStructuredOutput(
            answer="先检查最近一次访问顺序，再判断哪个缓存块最久未使用。",
            mode=TeachingStrategy(mode.group(1) if mode else "guided_question"),
            citations=citations,
            insufficient_evidence=source is None,
        )
        return GeneratedStructuredOutput(output, self.provider, self.model)


@pytest.fixture
def tutor_database(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'm7_3.sqlite3'}"
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
        networks = Course(owner_id=owner.id, name="Computer Networks", description="")
        session.add_all([systems, networks])
        session.flush()
        lru = KnowledgeNode(
            course_id=systems.id,
            name="LRU Replacement",
            normalized_name="lru replacement",
            description="Use access recency to select a cache block for replacement.",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
        )
        unsupported = KnowledgeNode(
            course_id=systems.id,
            name="Quantum Entanglement",
            normalized_name="quantum entanglement",
            description="",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
        )
        routing = KnowledgeNode(
            course_id=networks.id,
            name="LRU Routing",
            normalized_name="lru routing",
            description="A separate course context.",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
        )
        session.add_all([lru, unsupported, routing])
        session.flush()
        cache_notes = Material(
            course_id=systems.id,
            title="Cache Lecture",
            material_type="document",
            extension="pdf",
            extraction_status="SUCCESS",
            text_extracted=True,
        )
        network_notes = Material(
            course_id=networks.id,
            title="Routing Notes",
            material_type="document",
            extension="txt",
            extraction_status="SUCCESS",
            text_extracted=True,
        )
        session.add_all([cache_notes, network_notes])
        session.flush()
        session.add_all(
            [
                MaterialContent(
                    material_id=cache_notes.id,
                    plain_text="LRU replaces the least recently used cache block.",
                    segments=[
                        {
                            "text": "LRU replaces the least recently used cache block.",
                            "source_reference": "PDF 第 2 页",
                        }
                    ],
                    content_hash="a" * 64,
                    parser_name="pypdf",
                    parser_version="1",
                    page_count=2,
                ),
                MaterialContent(
                    material_id=network_notes.id,
                    plain_text="Network routing is isolated from the systems course.",
                    segments=[
                        {
                            "text": "Network routing is isolated from the systems course.",
                            "source_reference": "TXT segment 1",
                        }
                    ],
                    content_hash="b" * 64,
                    parser_name="text",
                    parser_version="1",
                    page_count=0,
                ),
            ]
        )
        session.add_all(
            [
                KnowledgeSource(
                    knowledge_node_id=lru.id,
                    material_id=cache_notes.id,
                    source_reference="PDF 第 2 页",
                ),
                KnowledgeSource(
                    knowledge_node_id=routing.id,
                    material_id=network_notes.id,
                    source_reference="TXT segment 1",
                ),
            ]
        )
        ids = {
            "systems": systems.id,
            "networks": networks.id,
            "lru": lru.id,
            "unsupported": unsupported.id,
            "routing": routing.id,
            "cache_material": cache_notes.id,
            "network_material": network_notes.id,
        }
    yield factory, ids, database_url
    engine.dispose()


def _settings(database_url: str, *, email: str = "legacy-bootstrap@learnpilot.local") -> Settings:
    return Settings(database_url=database_url, legacy_bootstrap_user=email, llm_mode="mock")


def _session(factory, ids, database_url: str, *, course: str = "systems", node: str = "lru") -> int:
    with factory() as db:
        result = LearningSessionService(db, _settings(database_url)).create_for_configured_user(
            LearningSessionCreate(
                course_id=ids[course],
                target_knowledge_node_id=ids[node],
            )
        )
        return result.session_id


def _service(factory, database_url: str, client: FakeTutorClient, *, email: str | None = None):
    db = factory()
    settings = _settings(database_url, email=email or "legacy-bootstrap@learnpilot.local")
    return db, TutorService(db, settings, llm_client_factory=lambda _settings: client)


def test_context_uses_owned_session_node_mastery_and_m7_2_sources(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
    db, service = _service(factory, database_url, FakeTutorClient())
    with db:
        context = service.build_context_for_configured_user(session_id, "为什么替换这个块？")
    assert context.course_id == ids["systems"]
    assert context.knowledge_node_id == ids["lru"]
    assert context.current_task.phase == "concept_learning"
    assert context.mastery_state.calculation_state == "not_calculated"
    assert context.source_context[0].material_id == ids["cache_material"]
    assert context.source_context[0].source_reference == "PDF 第 2 页"
    assert all(item.material_id != ids["network_material"] for item in context.source_context)


@pytest.mark.parametrize("mode", list(TeachingStrategy))
def test_all_five_modes_are_preserved_and_have_distinct_policy(tutor_database, mode) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
    client = FakeTutorClient()
    db, service = _service(factory, database_url, client)
    with db:
        result = service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message=f"请使用 {mode.value}", mode=mode),
            idempotency_key=f"mode-{mode.value}",
        )
    assert result.tutor_message.mode == mode
    assert STRATEGY_RULES[mode] in client.calls[0][0]["content"]
    assert len(set(STRATEGY_RULES.values())) == 5


def test_hint_and_full_explanation_prompts_have_different_disclosure_rules(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
    client = FakeTutorClient()
    db, service = _service(factory, database_url, client)
    with db:
        service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="给提示", mode=TeachingStrategy.HINT),
            idempotency_key="hint-key",
        )
        service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="完整解释", mode=TeachingStrategy.FULL_EXPLANATION),
            idempotency_key="full-key",
        )
    assert "不直接给出完整答案" in client.calls[0][0]["content"]
    assert "可以给出完整" in client.calls[1][0]["content"]


def test_idempotency_replays_pair_without_second_provider_call_and_restores_history(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
    client = FakeTutorClient()
    db, service = _service(factory, database_url, client)
    with db:
        first = service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="为什么替换？", mode="hint"),
            idempotency_key="same-key",
        )
        replay = service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="为什么替换？", mode="hint"),
            idempotency_key="same-key",
        )
        history = service.list_messages_for_configured_user(session_id)
    assert replay.reused is True
    assert replay.tutor_message.message_id == first.tutor_message.message_id
    assert len(client.calls) == 1
    assert [item.role.value for item in history.messages] == ["user", "assistant"]


def test_unknown_citation_is_rejected_without_writes(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
    db, service = _service(factory, database_url, FakeTutorClient(invalid_reference=True))
    with db, pytest.raises(TutorError) as captured:
        service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="引用在哪里？", mode="full_explanation"),
            idempotency_key="bad-citation",
        )
    assert captured.value.code == "TUTOR_INVALID_CITATION"
    with factory() as check:
        assert check.scalar(select(func.count()).select_from(TutorMessage)) == 0


def test_missing_sources_returns_explicit_insufficient_evidence(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url, node="unsupported")
    db, service = _service(factory, database_url, FakeTutorClient())
    with db:
        result = service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="资料里怎么解释？", mode="guided_question"),
            idempotency_key="empty-source",
        )
    assert result.tutor_message.insufficient_evidence is True
    assert result.tutor_message.grounded is False
    assert result.tutor_message.citations == []


@pytest.mark.parametrize("code", ["AI_TIMEOUT", "AI_INVALID_OUTPUT", "AI_PROVIDER_ERROR"])
def test_provider_failures_are_not_silently_mocked_or_persisted(tutor_database, code) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
    db, service = _service(factory, database_url, FakeTutorClient(error_code=code))
    with db, pytest.raises(AIServiceError) as captured:
        service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="请解释", mode="guided_question"),
            idempotency_key=f"error-{code}",
        )
    assert captured.value.code == code
    with factory() as check:
        assert check.scalar(select(func.count()).select_from(TutorMessage)) == 0


def test_sessions_and_courses_keep_messages_strictly_isolated(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    systems_session = _session(factory, ids, database_url)
    network_session = _session(factory, ids, database_url, course="networks", node="routing")
    client = FakeTutorClient()
    db, service = _service(factory, database_url, client)
    with db:
        service.send_message_for_configured_user(
            session_id=systems_session,
            payload=TutorMessageCreate(message="同一个问题", mode="hint"),
            idempotency_key="systems-question",
        )
        service.send_message_for_configured_user(
            session_id=network_session,
            payload=TutorMessageCreate(message="同一个问题", mode="hint"),
            idempotency_key="network-question",
        )
        systems_history = service.list_messages_for_configured_user(systems_session)
        network_history = service.list_messages_for_configured_user(network_session)
    assert {item.session_id for item in systems_history.messages} == {systems_session}
    assert {item.session_id for item in network_history.messages} == {network_session}
    assert "Computer Systems" in client.calls[0][1]["content"]
    assert "Computer Networks" in client.calls[1][1]["content"]
    assert "Routing Notes" not in client.calls[0][1]["content"]
    assert "Cache Lecture" not in client.calls[1][1]["content"]


def test_other_user_is_hidden_and_tutor_has_no_learning_state_side_effects(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
    db, other_service = _service(factory, database_url, FakeTutorClient(), email="other@example.test")
    with db, pytest.raises(TutorError) as captured:
        other_service.list_messages_for_configured_user(session_id)
    assert captured.value.code == "SESSION_NOT_FOUND"

    with factory() as before:
        counts_before = (
            before.scalar(select(func.count()).select_from(LearningEvidence)),
            before.scalar(select(func.count()).select_from(StudentKnowledgeState)),
            before.scalar(select(func.count()).select_from(LearningPlan)),
        )
    owner_db, owner_service = _service(factory, database_url, FakeTutorClient())
    with owner_db:
        owner_service.send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message="解释 LRU", mode="example"),
            idempotency_key="side-effect-check",
        )
    with factory() as after:
        counts_after = (
            after.scalar(select(func.count()).select_from(LearningEvidence)),
            after.scalar(select(func.count()).select_from(StudentKnowledgeState)),
            after.scalar(select(func.count()).select_from(LearningPlan)),
        )
    assert counts_after == counts_before


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _request(base_url: str, method: str, path: str, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Content-Type": "application/json"} if payload is not None else {}
    request_headers.update(headers or {})
    request = Request(f"{base_url}{path}", data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as error:
        with error:
            return error.code, json.loads(error.read().decode())


def test_http_tutor_contract_and_persistence(tutor_database) -> None:
    factory, ids, database_url = tutor_database
    session_id = _session(factory, ids, database_url)
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
                raise RuntimeError("M7-3 test server stopped during startup.")
            time.sleep(0.05)
    else:
        process.terminate()
        raise RuntimeError("M7-3 test server did not start.")
    try:
        status, created = _request(
            base_url,
            "POST",
            f"/api/learning/sessions/{session_id}/tutor/messages",
            {"message": "为什么需要替换？", "mode": "hint"},
            {"Idempotency-Key": "http-request-1"},
        )
        assert status == 200
        assert created["tutor_message"]["mode"] == "hint"
        assert created["tutor_message"]["citations"][0]["source_reference"] == "PDF 第 2 页"
        replay_status, replay = _request(
            base_url,
            "POST",
            f"/api/learning/sessions/{session_id}/tutor/messages",
            {"message": "为什么需要替换？", "mode": "hint"},
            {"Idempotency-Key": "http-request-1"},
        )
        assert replay_status == 200 and replay["reused"] is True
        history_status, history = _request(base_url, "GET", f"/api/learning/sessions/{session_id}/tutor/messages")
        assert history_status == 200
        assert [item["role"] for item in history["messages"]] == ["user", "assistant"]
        missing_key, body = _request(
            base_url,
            "POST",
            f"/api/learning/sessions/{session_id}/tutor/messages",
            {"message": "无幂等键", "mode": "hint"},
        )
        assert missing_key == 422
        assert body["error"]["code"] == "VALIDATION_ERROR"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_migration_upgrades_m7_2_database_and_preserves_existing_data(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'm7_2_upgrade.sqlite3'}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0015_m7_1_sessions"],
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
        session.add(Course(owner_id=owner.id, name="Existing M7-2 Course", description=""))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert "tutor_messages" in inspect(engine).get_table_names()
    with sessionmaker(bind=engine)() as session:
        assert session.scalar(select(func.count()).select_from(Course)) == 1
    engine.dispose()
