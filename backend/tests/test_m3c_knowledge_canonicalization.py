from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai import AIServiceError, GeneratedStructuredOutput, LLMClient
from backend.app.api.knowledge import (
    canonicalize_course_knowledge,
    get_course_knowledge_canonicalization,
    get_course_knowledge_model,
    get_knowledge_node_detail,
)
from backend.app.core.errors import ApiError
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeCandidate,
    KnowledgeCandidateResolution,
    KnowledgeCandidateSource,
    KnowledgeCanonicalizationRun,
    KnowledgeEdge,
    KnowledgeExtractionRun,
    KnowledgeNode,
    KnowledgeSource,
    Material,
    MaterialContent,
    User,
)
from backend.app.models import (
    KnowledgeCanonicalizationStatus,
    KnowledgeExtractionStatus,
    KnowledgeResolutionType,
    normalize_knowledge_name,
)
from backend.app.repositories import (
    CourseRepository,
    KnowledgeCandidateRepository,
    KnowledgeCandidateResolutionRepository,
    KnowledgeCanonicalizationRunRepository,
    KnowledgeEdgeRepository,
    KnowledgeExtractionRunRepository,
    KnowledgeNodeRepository,
    KnowledgeSourceRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.schemas.knowledge import (
    KnowledgeCanonicalizationRequest,
    KnowledgeCanonicalizationResponse,
    KnowledgeModelResponse,
    KnowledgeNodeDetailResponse,
)
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_canonicalization_service import (
    KnowledgeCanonicalizationError,
    KnowledgeCanonicalizationService,
)
from backend.app.services.knowledge_model_service import KnowledgeModelService


def migrate_database(tmp_path: Path, revision: str = "head", *, name: str = "m3c.sqlite3") -> str:
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
        "legacy_bootstrap_user": "canonical-owner@example.test",
        "legacy_bootstrap_user_display_name": "Canonical Owner",
        "llm_mode": "mock",
        "llm_max_attempts": 2,
    }
    values.update(overrides)
    return Settings(**values)


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    description: str = "A specific learnable course concept."
    importance: str = "medium"
    difficulty: str = "intermediate"


@dataclass(frozen=True)
class Seed:
    course_id: int
    private_course_id: int
    material_ids: list[int]
    candidate_ids: list[int]


class ScriptedCanonicalClient(LLMClient):
    provider = "scripted"
    model = "m3c-test-model"

    def __init__(self, responses: list[dict[str, object] | Exception], session: Session | None = None) -> None:
        self.responses = responses
        self.session = session
        self.calls = 0
        self.transaction_states: list[bool] = []
        self.messages: list[list[dict[str, str]]] = []

    def generate_structured(self, *, operation, messages, schema):
        assert operation == "knowledge_canonicalization"
        self.messages.append(messages)
        if self.session is not None:
            self.transaction_states.append(self.session.in_transaction())
        index = min(self.calls, len(self.responses) - 1)
        response = self.responses[index]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return GeneratedStructuredOutput(schema.model_validate(response), self.provider, self.model)


def add_current_extraction(
    session: Session,
    *,
    course_id: int,
    material_id: int,
    content_hash: str,
    reference: str,
    candidates: list[CandidateSpec],
    prompt_version: str = "knowledge_extraction_v1",
) -> list[int]:
    for current in session.scalars(
        select(KnowledgeExtractionRun).where(
            KnowledgeExtractionRun.material_id == material_id,
            KnowledgeExtractionRun.is_current.is_(True),
        )
    ):
        current.is_current = False
    run = KnowledgeExtractionRun(
        course_id=course_id,
        material_id=material_id,
        material_content_hash=content_hash,
        status=KnowledgeExtractionStatus.SUCCESS,
        provider="scripted",
        model="m3b-test-model",
        prompt_version=prompt_version,
        candidate_count=len(candidates),
        is_current=True,
    )
    session.add(run)
    session.flush()
    ids: list[int] = []
    for spec in candidates:
        candidate = KnowledgeCandidate(
            extraction_run_id=run.id,
            course_id=course_id,
            material_id=material_id,
            name=spec.name,
            normalized_name=normalize_knowledge_name(spec.name),
            description=spec.description,
            importance=spec.importance,
            difficulty=spec.difficulty,
        )
        session.add(candidate)
        session.flush()
        session.add(
            KnowledgeCandidateSource(
                candidate_id=candidate.id,
                material_id=material_id,
                source_reference=reference,
                excerpt=f"Evidence for {spec.name} in this course material.",
            )
        )
        ids.append(candidate.id)
    session.flush()
    return ids


def seed_data(
    session: Session,
    settings: Settings,
    material_candidates: list[list[CandidateSpec]],
) -> Seed:
    with session.begin():
        owner = User(
            email=settings.legacy_bootstrap_user,
            display_name=settings.legacy_bootstrap_user_display_name,
            is_active=True,
        )
        other = User(email="other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="Computer Architecture", description="")
        private = Course(owner_id=other.id, name="Private", description="")
        session.add_all([course, private])
        session.flush()

        material_ids: list[int] = []
        candidate_ids: list[int] = []
        for index, specs in enumerate(material_candidates, start=1):
            reference = f"TXT segment {index}"
            text = " ".join(spec.name for spec in specs) or "No candidates"
            material = Material(
                course_id=course.id,
                title=f"Notes {index}",
                material_type="txt",
                summary="",
                storage_status="NOT_STORED",
                extraction_status="SUCCESS",
                text_extracted=True,
                text_length=len(text),
                text_preview=text,
            )
            session.add(material)
            session.flush()
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            session.add(
                MaterialContent(
                    material_id=material.id,
                    plain_text=text,
                    segments=[{"text": text, "source_reference": reference}],
                    content_hash=content_hash,
                    parser_name="test-parser",
                    parser_version="1",
                    page_count=1,
                )
            )
            session.flush()
            candidate_ids.extend(
                add_current_extraction(
                    session,
                    course_id=course.id,
                    material_id=material.id,
                    content_hash=content_hash,
                    reference=reference,
                    candidates=specs,
                )
            )
            material_ids.append(material.id)
        return Seed(course.id, private.id, material_ids, candidate_ids)


def make_service(
    session: Session,
    settings: Settings,
    client_or_factory: LLMClient | Callable[[Settings], LLMClient],
) -> KnowledgeCanonicalizationService:
    factory = client_or_factory if callable(client_or_factory) else lambda _settings: client_or_factory
    return KnowledgeCanonicalizationService(
        session=session,
        course_repository=CourseRepository(session),
        extraction_run_repository=KnowledgeExtractionRunRepository(session),
        candidate_repository=KnowledgeCandidateRepository(session),
        content_repository=MaterialContentRepository(session),
        run_repository=KnowledgeCanonicalizationRunRepository(session),
        resolution_repository=KnowledgeCandidateResolutionRepository(session),
        node_repository=KnowledgeNodeRepository(session),
        source_repository=KnowledgeSourceRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
        llm_client_factory=factory,
    )


def make_model_service(session: Session, settings: Settings) -> KnowledgeModelService:
    return KnowledgeModelService(
        session=session,
        course_repository=CourseRepository(session),
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        node_repository=KnowledgeNodeRepository(session),
        edge_repository=KnowledgeEdgeRepository(session),
        source_repository=KnowledgeSourceRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
    )


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Settings], None, None]:
    database_url = migrate_database(tmp_path)
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory, make_settings(database_url, tmp_path)
    engine.dispose()


def merge_group(candidate_ids: list[int], name: str = "LRU Replacement") -> dict[str, object]:
    return {
        "candidate_ids": candidate_ids,
        "same_concept": True,
        "canonical_name": name,
        "canonical_description": "Least recently used replacement evicts the least recently accessed line.",
        "reason": "The terms denote the same replacement policy.",
    }


def test_fresh_and_m3b_upgrade_create_canonicalization_schema(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path, name="fresh.sqlite3")
    engine = make_engine(database_url)
    inspector = inspect(engine)
    assert {
        "knowledge_canonicalization_runs",
        "knowledge_candidate_resolutions",
    }.issubset(inspector.get_table_names())
    run_checks = {item["name"] for item in inspector.get_check_constraints("knowledge_canonicalization_runs")}
    resolution_unique = {item["name"] for item in inspector.get_unique_constraints("knowledge_candidate_resolutions")}
    candidate_indexes = {item["name"]: item for item in inspector.get_indexes("knowledge_candidates")}
    assert "knowledge_canonicalization_status" in run_checks
    assert "ck_knowledge_canonicalization_nodes_within_candidates" in run_checks
    assert "uq_knowledge_candidate_resolutions_run_candidate" in resolution_unique
    assert bool(candidate_indexes["uq_knowledge_candidates_id_course"]["unique"]) is True
    engine.dispose()

    database_url = migrate_database(tmp_path, "0004_m3b_knowledge_extraction", name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session, session.begin():
        owner = User(email="upgrade@example.test", display_name="Upgrade", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="Existing M3-B Course", description="")
        session.add(course)
        session.flush()
        course_id = course.id
    engine.dispose()
    migrate_database(tmp_path, name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session:
        assert session.get(Course, course_id).name == "Existing M3-B Course"
    engine.dispose()


def test_conservative_normalization_preserves_technical_identity() -> None:
    assert normalize_knowledge_name("  CACHE   Miss  ") == "cache miss"
    assert normalize_knowledge_name("x86 ‑ 64") == "x86-64"
    assert normalize_knowledge_name("Ｃ＋＋") == "c++"
    assert (
        len(
            {
                normalize_knowledge_name("C++"),
                normalize_knowledge_name("C#"),
                normalize_knowledge_name("L1 Cache"),
                normalize_knowledge_name("L2 Cache"),
                normalize_knowledge_name("x86-64"),
            }
        )
        == 5
    )


def test_exact_dedup_is_deterministic_without_llm_and_unions_sources(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [[CandidateSpec(" Cache Miss ")], [CandidateSpec("CACHE   MISS")]],
        )

        def forbidden_factory(_settings: Settings) -> LLMClient:
            raise AssertionError("Exact-only canonicalization must not initialize or call an LLM.")

        result = make_service(session, settings, forbidden_factory).canonicalize(seed.course_id)
        assert result.run.status == KnowledgeCanonicalizationStatus.SUCCESS
        assert result.run.candidate_count == 2
        assert result.run.canonical_node_count == 1
        assert result.run.merged_candidate_count == 1
        assert result.run.unresolved_count == 0
        assert result.nodes[0].normalized_name == "cache miss"
        assert {item.resolution_type for item in result.resolutions} == {KnowledgeResolutionType.EXACT}
        sources = KnowledgeSourceRepository(session).list_for_node(result.nodes[0].id)
        assert {source.material_id for source in sources} == set(seed.material_ids)


def test_semantic_merge_is_bounded_traceable_and_does_not_create_edges(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [
                [CandidateSpec("LRU Replacement", importance="high")],
                [
                    CandidateSpec("Least Recently Used Replacement", difficulty="advanced"),
                    CandidateSpec("Cache Miss"),
                ],
            ],
        )
        client = ScriptedCanonicalClient(
            [{"groups": [merge_group(seed.candidate_ids[:2])]}],
            session,
        )
        result = make_service(session, settings, client).canonicalize(seed.course_id)
        assert client.calls == 1
        assert client.transaction_states == [False]
        assert result.run.canonical_node_count == 2
        assert result.run.merged_candidate_count == 1
        assert {node.normalized_name for node in result.nodes} == {"lru replacement", "cache miss"}
        lru = next(node for node in result.nodes if node.normalized_name == "lru replacement")
        assert lru.importance.value == "high"
        assert lru.difficulty.value == "advanced"
        assert {source.material_id for source in KnowledgeSourceRepository(session).list_for_node(lru.id)} == set(
            seed.material_ids
        )
        assert {item.resolution_type for item in result.resolutions if item.knowledge_node_id == lru.id} == {
            KnowledgeResolutionType.SEMANTIC_MERGE
        }
        assert session.scalar(select(KnowledgeEdge)) is None


def test_related_or_numbered_concepts_remain_distinct(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [
                [CandidateSpec("Cache"), CandidateSpec("Cache Miss"), CandidateSpec("Cache Replacement")],
                [CandidateSpec("L1 Cache"), CandidateSpec("L2 Cache"), CandidateSpec("C++"), CandidateSpec("C#")],
            ],
        )
        client = ScriptedCanonicalClient([{"groups": []}], session)
        result = make_service(session, settings, client).canonicalize(seed.course_id)
        assert result.run.canonical_node_count == 7
        assert {node.name for node in result.nodes} == {
            "Cache",
            "Cache Miss",
            "Cache Replacement",
            "L1 Cache",
            "L2 Cache",
            "C++",
            "C#",
        }
        assert all(item.resolution_type == KnowledgeResolutionType.NEW_NODE for item in result.resolutions)


def test_unknown_candidate_id_retries_then_accepts_corrected_output(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [[CandidateSpec("LRU Replacement"), CandidateSpec("Least Recently Used Replacement")]],
        )
        client = ScriptedCanonicalClient(
            [
                {"groups": [merge_group([seed.candidate_ids[0], 999_999])]},
                {"groups": [merge_group(seed.candidate_ids)]},
            ],
            session,
        )
        result = make_service(session, settings, client).canonicalize(seed.course_id)
        assert client.calls == 2
        assert result.run.status == KnowledgeCanonicalizationStatus.SUCCESS
        assert result.run.canonical_node_count == 1
        assert "previous JSON violated" in client.messages[1][-1]["content"]


def test_duplicate_candidate_assignment_marks_run_failed_without_partial_nodes(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [[CandidateSpec("LRU"), CandidateSpec("Least Recently Used"), CandidateSpec("LRU Policy")]],
        )
        invalid = {
            "groups": [
                merge_group(seed.candidate_ids[:2], "LRU"),
                merge_group([seed.candidate_ids[0], seed.candidate_ids[2]], "LRU Policy"),
            ]
        }
        client = ScriptedCanonicalClient([invalid, invalid], session)
        with pytest.raises(KnowledgeCanonicalizationError) as captured:
            make_service(session, settings, client).canonicalize(seed.course_id)
        assert captured.value.code == "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT"
        latest = KnowledgeCanonicalizationRunRepository(session).get_latest_for_course(seed.course_id)
        assert latest.status == KnowledgeCanonicalizationStatus.FAILED
        assert latest.is_current is False
        assert latest.unresolved_count == 3
        assert KnowledgeNodeRepository(session).list_by_course(seed.course_id) == []
        assert KnowledgeCandidateResolutionRepository(session).list_for_run(latest.id) == []


def test_repeated_post_is_idempotent_without_another_llm_request(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [[CandidateSpec("LRU Replacement"), CandidateSpec("Least Recently Used Replacement")]],
        )
        client = ScriptedCanonicalClient([{"groups": [merge_group(seed.candidate_ids)]}], session)
        service = make_service(session, settings, client)
        first = service.canonicalize(seed.course_id)
        reused = service.canonicalize(seed.course_id)
        assert client.calls == 1
        assert reused.reused is True
        assert reused.run.id == first.run.id
        assert [node.id for node in reused.nodes] == [node.id for node in first.nodes]


def test_failed_regeneration_preserves_previous_current_model(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [[CandidateSpec("LRU Replacement"), CandidateSpec("Least Recently Used Replacement")]],
        )
        successful = make_service(
            session,
            settings,
            ScriptedCanonicalClient([{"groups": [merge_group(seed.candidate_ids)]}], session),
        ).canonicalize(seed.course_id)
        old_node_ids = [node.id for node in successful.nodes]
        failing_client = ScriptedCanonicalClient(
            [AIServiceError("AI_TIMEOUT", "timeout", retryable=True)],
            session,
        )
        with pytest.raises(KnowledgeCanonicalizationError) as captured:
            make_service(session, settings, failing_client).canonicalize(seed.course_id, regenerate=True)
        assert captured.value.code == "KNOWLEDGE_CANONICALIZATION_FAILED"
        current = make_service(session, settings, failing_client).get_canonicalization(seed.course_id)
        assert current.run.id == successful.run.id
        assert current.run.is_current is True
        assert [node.id for node in current.nodes] == old_node_ids
        latest = KnowledgeCanonicalizationRunRepository(session).get_latest_for_course(seed.course_id)
        assert latest.status == KnowledgeCanonicalizationStatus.FAILED
        assert latest.is_current is False


def test_new_current_extraction_changes_snapshot_and_replaces_managed_model(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(session, settings, [[CandidateSpec("Cache Miss")]])
        first = make_service(session, settings, lambda _settings: None).canonicalize(seed.course_id)
        old_node = first.nodes[0]
        with session.begin():
            content = MaterialContentRepository(session).get_for_material(seed.material_ids[0])
            content.plain_text = "Cache Hit"
            content.segments = [{"text": "Cache Hit", "source_reference": "TXT segment 1"}]
            content.content_hash = hashlib.sha256(content.plain_text.encode()).hexdigest()
            new_ids = add_current_extraction(
                session,
                course_id=seed.course_id,
                material_id=seed.material_ids[0],
                content_hash=content.content_hash,
                reference="TXT segment 1",
                candidates=[CandidateSpec("Cache Hit")],
                prompt_version="knowledge_extraction_v2",
            )
        second = make_service(session, settings, lambda _settings: None).canonicalize(seed.course_id)
        assert second.run.id != first.run.id
        assert second.run.candidate_snapshot_hash != first.run.candidate_snapshot_hash
        assert [resolution.candidate_id for resolution in second.resolutions] == new_ids
        assert [node.name for node in second.nodes] == ["Cache Hit"]
        assert old_node.is_active is False
        assert [node.name for node in KnowledgeNodeRepository(session).list_by_course(seed.course_id)] == ["Cache Hit"]


def test_existing_canonical_node_is_reused_and_receives_candidate_provenance(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(session, settings, [[CandidateSpec("Cache Miss", importance="high")]])
        with session.begin():
            existing = KnowledgeNodeRepository(session).create(
                KnowledgeNode(
                    course_id=seed.course_id,
                    name="cache miss",
                    normalized_name="cache miss",
                    description="Old description.",
                    importance="low",
                    difficulty="basic",
                )
            )
            existing_id = existing.id
        result = make_service(session, settings, lambda _settings: None).canonicalize(seed.course_id)
        assert [node.id for node in result.nodes] == [existing_id]
        assert result.nodes[0].importance.value == "high"
        assert KnowledgeSourceRepository(session).list_for_node(existing_id)[0].material_id == seed.material_ids[0]


def test_course_api_returns_only_canonical_nodes_and_traceable_detail(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [[CandidateSpec("Cache Miss")], [CandidateSpec("CACHE MISS")]],
        )
        service = make_service(session, settings, lambda _settings: None)
        post = KnowledgeCanonicalizationResponse.model_validate(
            canonicalize_course_knowledge(
                seed.course_id,
                KnowledgeCanonicalizationRequest(),
                service,
            )
        )
        get = KnowledgeCanonicalizationResponse.model_validate(
            get_course_knowledge_canonicalization(seed.course_id, service)
        )
        assert post.run.status == KnowledgeCanonicalizationStatus.SUCCESS
        assert get.run.id == post.run.id
        assert get.reused is True
        assert len(get.resolutions) == 2

        model_service = make_model_service(session, settings)
        model = KnowledgeModelResponse.model_validate(get_course_knowledge_model(seed.course_id, model_service))
        assert [node.id for node in model.nodes] == [post.nodes[0].id]
        assert model.edges == []
        assert "candidate_id" not in model.nodes[0].model_dump()
        detail = KnowledgeNodeDetailResponse.model_validate(
            get_knowledge_node_detail(seed.course_id, model.nodes[0].id, model_service)
        )
        assert {source.material_id for source in detail.sources} == set(seed.material_ids)
        assert detail.related_edges == []


def test_not_ready_and_ownership_checks_happen_before_llm(database) -> None:
    factory, settings = database
    client = ScriptedCanonicalClient([{"groups": []}])
    with factory() as session:
        seed = seed_data(session, settings, [[]])
        service = make_service(session, settings, client)
        with pytest.raises(KnowledgeCanonicalizationError) as captured:
            service.canonicalize(seed.course_id)
        assert captured.value.code == "KNOWLEDGE_CANONICALIZATION_NOT_READY"
        with pytest.raises(ResourceNotFoundError):
            service.canonicalize(seed.private_course_id)
        assert client.calls == 0
        with pytest.raises(ApiError) as api_error:
            canonicalize_course_knowledge(
                seed.course_id,
                KnowledgeCanonicalizationRequest(),
                service,
            )
        assert api_error.value.code == "KNOWLEDGE_CANONICALIZATION_NOT_READY"


def test_candidate_limit_rejects_snapshot_before_llm(database) -> None:
    factory, base_settings = database
    settings = base_settings.model_copy(update={"knowledge_canonicalization_max_candidates": 2})
    client = ScriptedCanonicalClient([{"groups": []}])
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [[CandidateSpec("Cache"), CandidateSpec("Cache Miss"), CandidateSpec("Cache Hit")]],
        )
        with pytest.raises(KnowledgeCanonicalizationError) as captured:
            make_service(session, settings, client).canonicalize(seed.course_id)
        assert captured.value.code == "KNOWLEDGE_CANONICALIZATION_NOT_READY"
        assert client.calls == 0


def test_resolution_database_constraints_and_course_cascade_are_real(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_data(session, settings, [[CandidateSpec("Cache Miss")]])
        result = make_service(session, settings, lambda _settings: None).canonicalize(seed.course_id)
        run_id = result.run.id
        node_id = result.nodes[0].id
        with session.begin():
            foreign_material = Material(
                course_id=seed.private_course_id,
                title="Foreign notes",
                material_type="txt",
                summary="",
                storage_status="NOT_STORED",
                extraction_status="SUCCESS",
                text_extracted=True,
                text_length=7,
                text_preview="Foreign",
            )
            session.add(foreign_material)
            session.flush()
            foreign_hash = hashlib.sha256(b"Foreign").hexdigest()
            session.add(
                MaterialContent(
                    material_id=foreign_material.id,
                    plain_text="Foreign",
                    segments=[{"text": "Foreign", "source_reference": "TXT segment foreign"}],
                    content_hash=foreign_hash,
                    parser_name="test-parser",
                    parser_version="1",
                    page_count=1,
                )
            )
            session.flush()
            foreign_candidate_id = add_current_extraction(
                session,
                course_id=seed.private_course_id,
                material_id=foreign_material.id,
                content_hash=foreign_hash,
                reference="TXT segment foreign",
                candidates=[CandidateSpec("Foreign Concept")],
            )[0]
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    KnowledgeCandidateResolution(
                        canonicalization_run_id=run_id,
                        course_id=seed.course_id,
                        candidate_id=foreign_candidate_id,
                        knowledge_node_id=node_id,
                        resolution_type=KnowledgeResolutionType.NEW_NODE,
                    )
                )
                session.flush()
        with session.begin():
            source_ids = [source.id for source in KnowledgeSourceRepository(session).list_for_node(node_id)]
        with session.begin():
            session.delete(session.get(Course, seed.course_id))
        session.expire_all()
        assert session.get(KnowledgeCanonicalizationRun, run_id) is None
        assert session.get(KnowledgeNode, node_id) is None
        assert all(session.get(KnowledgeSource, source_id) is None for source_id in source_ids)
        assert (
            session.scalar(
                select(KnowledgeCandidateResolution).where(
                    KnowledgeCandidateResolution.canonicalization_run_id == run_id
                )
            )
            is None
        )
