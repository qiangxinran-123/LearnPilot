from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai import AIServiceError, GeneratedStructuredOutput, LLMClient
from backend.app.ai.models import KnowledgeExtractionOutput
from backend.app.api.knowledge import extract_material_knowledge, get_material_knowledge_extraction
from backend.app.core.errors import ApiError
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeCandidate,
    KnowledgeCandidateSource,
    KnowledgeExtractionRun,
    KnowledgeNode,
    Material,
    MaterialContent,
    User,
)
from backend.app.models import KnowledgeExtractionStatus
from backend.app.repositories import (
    CourseRepository,
    KnowledgeCandidateRepository,
    KnowledgeCandidateSourceRepository,
    KnowledgeExtractionRunRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.schemas.knowledge import (
    KnowledgeExtractionRequest,
    KnowledgeExtractionResponse,
)
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_extraction_service import (
    KnowledgeExtractionError,
    KnowledgeExtractionService,
)


def migrate_database(tmp_path: Path, revision: str = "head", *, name: str = "m3b.sqlite3") -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / name}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return database_url


def make_engine(database_url: str):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_settings(database_url: str, tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": database_url,
        "upload_root": tmp_path / "uploads",
        "legacy_bootstrap_user": "extraction-owner@example.test",
        "legacy_bootstrap_user_display_name": "Extraction Owner",
        "llm_mode": "mock",
        "llm_max_attempts": 2,
    }
    values.update(overrides)
    return Settings(**values)


class ScriptedClient(LLMClient):
    provider = "scripted"
    model = "m3b-test-model"

    def __init__(self, responses: list[dict[str, object] | Exception]) -> None:
        self.responses = responses
        self.calls = 0
        self.messages: list[list[dict[str, str]]] = []

    def generate_structured(self, *, operation, messages, schema):
        del operation
        self.messages.append(messages)
        index = min(self.calls, len(self.responses) - 1)
        response = self.responses[index]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return GeneratedStructuredOutput(schema.model_validate(response), self.provider, self.model)


class ContextAwareClient(LLMClient):
    provider = "scripted"
    model = "m3b-test-model"

    def __init__(self, *, candidates_per_call: int = 1) -> None:
        self.candidates_per_call = candidates_per_call
        self.calls = 0
        self.context_lengths: list[int] = []

    def generate_structured(self, *, operation, messages, schema):
        del operation
        user_content = messages[1]["content"]
        context = user_content.split("\n\n", 1)[1]
        self.context_lengths.append(len(context))
        references = re.findall(r"^\[([^\]\n]+)\]$", context, flags=re.MULTILINE)
        reference = references[0]
        call_number = self.calls
        self.calls += 1
        payload = {
            "candidates": [
                {
                    "name": f"Topic {call_number}-{index}",
                    "description": "A bounded material concept.",
                    "importance": "medium",
                    "difficulty": "intermediate",
                    "source_references": [reference],
                }
                for index in range(self.candidates_per_call)
            ]
        }
        return GeneratedStructuredOutput(schema.model_validate(payload), self.provider, self.model)


@dataclass(frozen=True)
class Seed:
    course_id: int
    second_course_id: int
    private_course_id: int
    material_id: int
    second_material_id: int
    foreign_material_id: int
    not_ready_material_id: int


def seed_data(session: Session, settings: Settings) -> Seed:
    with session.begin():
        owner = User(
            email=settings.legacy_bootstrap_user,
            display_name=settings.legacy_bootstrap_user_display_name,
            is_active=True,
        )
        other_owner = User(email="other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other_owner])
        session.flush()
        course = Course(owner_id=owner.id, name="Computer Systems", description="")
        second_course = Course(owner_id=owner.id, name="Algorithms", description="")
        private_course = Course(owner_id=other_owner.id, name="Private", description="")
        session.add_all([course, second_course, private_course])
        session.flush()

        def material(course_id: int, title: str, status: str = "SUCCESS") -> Material:
            return Material(
                course_id=course_id,
                title=title,
                material_type="txt",
                summary="",
                storage_status="NOT_STORED",
                extraction_status=status,
                text_extracted=status == "SUCCESS",
                text_length=1,
                text_preview="x",
            )

        first = material(course.id, "Cache notes")
        second = material(course.id, "More cache notes")
        foreign = material(second_course.id, "Graph notes")
        not_ready = material(course.id, "Pending notes", "NOT_REQUESTED")
        session.add_all([first, second, foreign, not_ready])
        session.flush()

        contents = [
            (
                first,
                [
                    {
                        "text": (
                            "Cache exploits temporal and spatial locality. LRU replaces the least recently used line."
                        ),
                        "source_reference": "PDF 第 1 页",
                    }
                ],
            ),
            (
                second,
                [{"text": "Cache reduces average memory access time.", "source_reference": "TXT segment 1"}],
            ),
            (
                foreign,
                [{"text": "Breadth-first search explores a graph by levels.", "source_reference": "TXT segment 1"}],
            ),
        ]
        for item, segments in contents:
            text = "\n".join(str(segment["text"]) for segment in segments)
            session.add(
                MaterialContent(
                    material_id=item.id,
                    plain_text=text,
                    segments=segments,
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    parser_name="test-parser",
                    parser_version="1",
                    page_count=1,
                )
            )
        session.flush()
        return Seed(
            course.id,
            second_course.id,
            private_course.id,
            first.id,
            second.id,
            foreign.id,
            not_ready.id,
        )


def make_service(session: Session, settings: Settings, client: LLMClient) -> KnowledgeExtractionService:
    return KnowledgeExtractionService(
        session=session,
        course_repository=CourseRepository(session),
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        run_repository=KnowledgeExtractionRunRepository(session),
        candidate_repository=KnowledgeCandidateRepository(session),
        source_repository=KnowledgeCandidateSourceRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
        llm_client_factory=lambda _settings: client,
    )


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Settings], None, None]:
    database_url = migrate_database(tmp_path)
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory, make_settings(database_url, tmp_path)
    engine.dispose()


def candidate(
    name: str = "Cache",
    *,
    reference: str = "PDF 第 1 页",
) -> dict[str, object]:
    return {
        "name": name,
        "description": f"{name} is a learnable systems concept.",
        "importance": "high",
        "difficulty": "intermediate",
        "source_references": [reference],
    }


def test_fresh_and_m3a_upgrade_create_candidate_staging_schema(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path, name="fresh.sqlite3")
    engine = make_engine(database_url)
    inspector = inspect(engine)
    assert {
        "knowledge_extraction_runs",
        "knowledge_candidates",
        "knowledge_candidate_sources",
    }.issubset(inspector.get_table_names())
    run_checks = {item["name"] for item in inspector.get_check_constraints("knowledge_extraction_runs")}
    candidate_unique = {item["name"] for item in inspector.get_unique_constraints("knowledge_candidates")}
    assert "knowledge_extraction_status" in run_checks
    assert "ck_knowledge_extraction_runs_candidate_count" in run_checks
    assert "uq_knowledge_candidates_run_normalized_name" in candidate_unique
    engine.dispose()

    database_url = migrate_database(tmp_path, "0003_m3a_knowledge_model", name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session, session.begin():
        owner = User(email="upgrade@example.test", display_name="Upgrade", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="Existing M3-A Course", description="")
        session.add(course)
        session.flush()
        course_id = course.id
    engine.dispose()
    migrate_database(tmp_path, name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session:
        assert session.get(Course, course_id).name == "Existing M3-A Course"
    engine.dispose()


def test_run_status_candidate_and_source_repositories(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(session, settings)
        with session.begin():
            run_repository = KnowledgeExtractionRunRepository(session)
            run = run_repository.create(
                KnowledgeExtractionRun(
                    course_id=seed.course_id,
                    material_id=seed.material_id,
                    material_content_hash="a" * 64,
                    status=KnowledgeExtractionStatus.PENDING,
                    provider="scripted",
                    model="m3b-test-model",
                    prompt_version="knowledge_extraction_v1",
                    candidate_count=0,
                    is_current=False,
                )
            )
            run.status = KnowledgeExtractionStatus.RUNNING
            run_repository.save(run)
            item = KnowledgeCandidateRepository(session).create(
                KnowledgeCandidate(
                    extraction_run_id=run.id,
                    course_id=seed.course_id,
                    material_id=seed.material_id,
                    name="Cache",
                    normalized_name="cache",
                    description="A cache.",
                    importance="high",
                    difficulty="basic",
                )
            )
            source = KnowledgeCandidateSourceRepository(session).create(
                KnowledgeCandidateSource(
                    candidate_id=item.id,
                    material_id=seed.material_id,
                    source_reference="PDF 第 1 页",
                    excerpt="Cache exploits temporal locality.",
                )
            )
        assert run.status == KnowledgeExtractionStatus.RUNNING
        assert KnowledgeCandidateRepository(session).list_for_run(run.id)[0].id == item.id
        assert KnowledgeCandidateSourceRepository(session).list_for_candidate(item.id) == [source]


def test_small_extraction_persists_real_evidence_and_no_canonical_node(database) -> None:
    factory, settings = database
    client = ScriptedClient(
        [
            {
                "candidates": [
                    candidate("Cache", reference="[PDF 第1页]"),
                    candidate("Temporal Locality"),
                ]
            }
        ]
    )
    with factory() as session:
        seed = seed_data(session, settings)
        result = make_service(session, settings, client).extract(seed.course_id, seed.material_id)
        assert result.run.status == KnowledgeExtractionStatus.SUCCESS
        assert result.run.prompt_version == "knowledge_extraction_v1"
        assert result.run.candidate_count == 2
        assert result.run.is_current is True
        assert {item.name for item in result.candidates} == {"Cache", "Temporal Locality"}
        assert all(item.sources for item in result.candidates)
        assert all(item.sources[0].source_reference == "PDF 第 1 页" for item in result.candidates)
        assert all(item.sources[0].excerpt.startswith("Cache exploits") for item in result.candidates)
        assert session.scalar(select(KnowledgeNode)) is None


def test_exact_duplicate_cleanup_unions_evidence_without_semantic_merge(database) -> None:
    factory, settings = database
    client = ScriptedClient(
        [
            {
                "candidates": [
                    candidate(" Cache "),
                    candidate("CACHE"),
                    candidate("Least Recently Used Replacement"),
                    candidate("LRU Replacement"),
                ]
            }
        ]
    )
    with factory() as session:
        seed = seed_data(session, settings)
        result = make_service(session, settings, client).extract(seed.course_id, seed.material_id)
        assert [item.normalized_name for item in result.candidates].count("cache") == 1
        assert {item.normalized_name for item in result.candidates} >= {
            "least recently used replacement",
            "lru replacement",
        }
        assert result.run.candidate_count == 3


def test_invalid_citation_retries_then_succeeds(database) -> None:
    factory, settings = database
    client = ScriptedClient(
        [
            {"candidates": [candidate(reference="PDF 第 99 页")]},
            {"candidates": [candidate(reference="[PDF 第1页]")]},
        ]
    )
    with factory() as session:
        seed = seed_data(session, settings)
        result = make_service(session, settings, client).extract(seed.course_id, seed.material_id)
        assert result.run.status == KnowledgeExtractionStatus.SUCCESS
        assert client.calls == 2
        assert result.candidates[0].sources[0].source_reference == "PDF 第 1 页"


def test_invalid_citation_exhaustion_marks_failed_without_partial_candidates(database) -> None:
    factory, settings = database
    client = ScriptedClient(
        [
            {"candidates": [candidate(reference="PDF 第 99 页")]},
            {"candidates": [candidate(reference="PDF 第 100 页")]},
        ]
    )
    with factory() as session:
        seed = seed_data(session, settings)
        service = make_service(session, settings, client)
        with pytest.raises(KnowledgeExtractionError) as captured:
            service.extract(seed.course_id, seed.material_id)
        assert captured.value.code == "KNOWLEDGE_EXTRACTION_INVALID_REFERENCE"
        run = KnowledgeExtractionRunRepository(session).get_latest_for_material(seed.material_id)
        assert run.status == KnowledgeExtractionStatus.FAILED
        assert run.candidate_count == 0
        assert KnowledgeCandidateRepository(session).list_for_run(run.id) == []


def test_repeated_extraction_is_idempotent_and_regeneration_can_replace_current(database) -> None:
    factory, settings = database
    client = ScriptedClient(
        [
            {"candidates": [candidate("Cache")]},
            {"candidates": [candidate("Spatial Locality")]},
        ]
    )
    with factory() as session:
        seed = seed_data(session, settings)
        service = make_service(session, settings, client)
        first = service.extract(seed.course_id, seed.material_id)
        reused = service.extract(seed.course_id, seed.material_id)
        regenerated = service.extract(seed.course_id, seed.material_id, regenerate=True)
        assert reused.reused is True
        assert reused.run.id == first.run.id
        assert client.calls == 2
        assert regenerated.run.id != first.run.id
        assert regenerated.run.is_current is True
        assert first.run.is_current is False
        assert [item.name for item in regenerated.candidates] == ["Spatial Locality"]


def test_content_hash_change_invalidates_old_current_result(database) -> None:
    factory, settings = database
    client = ScriptedClient([{"candidates": [candidate("Cache")]}])
    with factory() as session:
        seed = seed_data(session, settings)
        service = make_service(session, settings, client)
        old = service.extract(seed.course_id, seed.material_id)
        with session.begin():
            content = MaterialContentRepository(session).get_for_material(seed.material_id)
            content.plain_text = f"{content.plain_text} New version."
            content.content_hash = hashlib.sha256(content.plain_text.encode()).hexdigest()
        with pytest.raises(KnowledgeExtractionError) as captured:
            service.get_extraction(seed.course_id, seed.material_id)
        assert captured.value.code == "KNOWLEDGE_EXTRACTION_NOT_READY"
        assert old.run.is_current is True


def test_failed_regeneration_preserves_previous_success(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(session, settings)
        successful = make_service(
            session,
            settings,
            ScriptedClient([{"candidates": [candidate("Cache")]}]),
        ).extract(seed.course_id, seed.material_id)
        failing = ScriptedClient(
            [
                AIServiceError(
                    "AI_TIMEOUT",
                    "timeout",
                    retryable=True,
                )
            ]
        )
        with pytest.raises(KnowledgeExtractionError) as captured:
            make_service(session, settings, failing).extract(
                seed.course_id,
                seed.material_id,
                regenerate=True,
            )
        assert captured.value.code == "KNOWLEDGE_EXTRACTION_FAILED"
        current = make_service(session, settings, failing).get_extraction(seed.course_id, seed.material_id)
        assert current.run.id == successful.run.id
        assert current.run.is_current is True
        latest = KnowledgeExtractionRunRepository(session).get_latest_for_material(seed.material_id)
        assert latest.status == KnowledgeExtractionStatus.FAILED
        assert latest.is_current is False


def test_course_material_and_readiness_validation_happen_before_llm(database) -> None:
    factory, settings = database
    client = ScriptedClient([{"candidates": [candidate()]}])
    with factory() as session:
        seed = seed_data(session, settings)
        service = make_service(session, settings, client)
        with pytest.raises(ResourceNotFoundError):
            service.extract(seed.course_id, seed.foreign_material_id)
        with pytest.raises(ResourceNotFoundError):
            service.extract(seed.private_course_id, seed.material_id)
        with pytest.raises(KnowledgeExtractionError) as captured:
            service.extract(seed.course_id, seed.not_ready_material_id)
        assert captured.value.code == "KNOWLEDGE_EXTRACTION_NOT_READY"
        assert client.calls == 0


def test_cross_material_candidates_remain_separate(database) -> None:
    factory, settings = database
    first_client = ScriptedClient([{"candidates": [candidate("Cache")]}])
    second_client = ScriptedClient([{"candidates": [candidate("Cache", reference="TXT segment 1")]}])
    with factory() as session:
        seed = seed_data(session, settings)
        first = make_service(session, settings, first_client).extract(seed.course_id, seed.material_id)
        second = make_service(session, settings, second_client).extract(
            seed.course_id,
            seed.second_material_id,
        )
        assert first.candidates[0].id != second.candidates[0].id
        assert first.candidates[0].material_id != second.candidates[0].material_id
        assert session.scalars(select(KnowledgeCandidate)).all().__len__() == 2


def test_large_material_is_batched_with_bounded_context(database) -> None:
    factory, base_settings = database
    settings = base_settings.model_copy(
        update={"llm_context_chars": 2000, "llm_chunk_chars": 500, "llm_chunk_overlap_chars": 50}
    )
    client = ContextAwareClient()
    with factory() as session:
        seed = seed_data(session, settings)
        long_segments = [
            {
                "text": (f"Concept {index} evidence. " * 60).strip(),
                "source_reference": f"PDF 第 {index + 1} 页",
            }
            for index in range(5)
        ]
        plain_text = "\n".join(str(segment["text"]) for segment in long_segments)
        with session.begin():
            content = MaterialContentRepository(session).get_for_material(seed.material_id)
            content.plain_text = plain_text
            content.segments = long_segments
            content.content_hash = hashlib.sha256(plain_text.encode()).hexdigest()
        result = make_service(session, settings, client).extract(seed.course_id, seed.material_id)
        assert client.calls > 1
        assert all(length <= settings.llm_context_chars for length in client.context_lengths)
        assert result.run.candidate_count == client.calls


def test_empty_candidates_are_valid_and_global_candidate_limit_is_enforced(database) -> None:
    factory, base_settings = database
    with factory() as session:
        seed = seed_data(session, base_settings)
        empty = make_service(
            session,
            base_settings,
            ScriptedClient([{"candidates": []}]),
        ).extract(seed.course_id, seed.material_id)
        assert empty.run.status == KnowledgeExtractionStatus.SUCCESS
        assert empty.run.candidate_count == 0
        assert empty.candidates == []

    settings = base_settings.model_copy(
        update={
            "llm_context_chars": 2000,
            "llm_chunk_chars": 500,
            "llm_chunk_overlap_chars": 0,
            "knowledge_extraction_max_candidates": 20,
        }
    )
    with factory() as session:
        with session.begin():
            content = MaterialContentRepository(session).get_for_material(seed.second_material_id)
            segments = [
                {
                    "text": (f"Independent topic {index}. " * 100).strip(),
                    "source_reference": f"TXT segment {index}",
                }
                for index in range(2)
            ]
            content.plain_text = "\n".join(str(item["text"]) for item in segments)
            content.segments = segments
            content.content_hash = hashlib.sha256(content.plain_text.encode()).hexdigest()
        client = ContextAwareClient(candidates_per_call=20)
        with pytest.raises(KnowledgeExtractionError) as captured:
            make_service(session, settings, client).extract(seed.course_id, seed.second_material_id)
        assert captured.value.code == "KNOWLEDGE_EXTRACTION_INVALID_OUTPUT"
        run = KnowledgeExtractionRunRepository(session).get_latest_for_material(seed.second_material_id)
        assert run.status == KnowledgeExtractionStatus.FAILED
        assert KnowledgeCandidateRepository(session).list_for_run(run.id) == []


def test_material_delete_cascades_run_candidates_and_sources(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(session, settings)
        result = make_service(
            session,
            settings,
            ScriptedClient([{"candidates": [candidate()]}]),
        ).extract(seed.course_id, seed.material_id)
        run_id = result.run.id
        candidate_id = result.candidates[0].id
        source_id = result.candidates[0].sources[0].id
        with session.begin():
            session.delete(session.get(Material, seed.material_id))
        session.expire_all()
        assert session.get(KnowledgeExtractionRun, run_id) is None
        assert session.get(KnowledgeCandidate, candidate_id) is None
        assert session.get(KnowledgeCandidateSource, source_id) is None


def test_material_extraction_post_get_contract_and_routes(database) -> None:
    factory, settings = database
    client = ScriptedClient([{"candidates": [candidate()]}])
    with factory() as session:
        seed = seed_data(session, settings)
        service = make_service(session, settings, client)
        post = KnowledgeExtractionResponse.model_validate(
            extract_material_knowledge(
                seed.course_id,
                seed.material_id,
                KnowledgeExtractionRequest(),
                service,
            )
        )
        get = KnowledgeExtractionResponse.model_validate(
            get_material_knowledge_extraction(seed.course_id, seed.material_id, service)
        )
        assert post.run.status == KnowledgeExtractionStatus.SUCCESS
        assert get.run.id == post.run.id
        assert get.candidates[0].sources[0].source_reference == "PDF 第 1 页"

        with pytest.raises(ApiError) as captured:
            get_material_knowledge_extraction(seed.course_id, seed.second_material_id, service)
        assert captured.value.code == "KNOWLEDGE_EXTRACTION_NOT_READY"


def test_structured_output_rejects_mismatch_and_large_batch() -> None:
    with pytest.raises(ValidationError):
        KnowledgeExtractionOutput.model_validate({"candidates": "not-a-list"})
    with pytest.raises(ValidationError):
        KnowledgeExtractionOutput.model_validate({"candidates": [candidate(f"Topic {index}") for index in range(21)]})
