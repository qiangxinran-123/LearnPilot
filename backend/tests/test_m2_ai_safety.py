from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.ai import AIServiceError, GeneratedStructuredOutput
from backend.app.ai.chunking import TextChunk
from backend.app.ai.models import CardsOutput, QAOutput, StudyCardDraft, SummaryOutput
from backend.app.ai.prompts import cards as cards_prompt
from backend.app.core.settings import Settings
from backend.app.schemas.course import CourseCreate, CourseUpdate
from backend.app.services.material_ai_service import (
    MaterialAIService,
    ReadyMaterial,
    _normalize_source_reference,
    _resolve_source_reference,
)


class FakeStructuredClient:
    def __init__(self, *, qa_references: list[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.qa_references = qa_references

    def generate_structured(
        self, *, operation: str, messages: list[dict[str, str]], schema: type[SummaryOutput] | type[QAOutput]
    ) -> GeneratedStructuredOutput:
        self.calls.append((operation, messages[-1]["content"]))
        if schema is QAOutput:
            output = QAOutput(
                answer="Cache reduces latency.",
                sufficient_evidence=True,
                references=self.qa_references or [],
            )
        else:
            output = SummaryOutput(
                overview="A concise summary.",
                key_concepts=["Cache"],
                important_points=["Latency"],
                review_suggestions=["Review the source"],
            )
        return GeneratedStructuredOutput(output, "fake", "test-model")


def make_service(settings: Settings) -> MaterialAIService:
    service = object.__new__(MaterialAIService)
    service.settings = settings
    return service


def test_course_create_keeps_blank_description_as_empty_string() -> None:
    course = CourseCreate(name="Computer Systems", description="   ")
    assert course.description == ""


def test_course_update_rejects_explicit_null_name() -> None:
    with pytest.raises(ValidationError):
        CourseUpdate(name=None)
    assert CourseUpdate(description="updated").name is None


def test_long_summary_processes_every_source_segment() -> None:
    settings = Settings(llm_context_chars=2000, llm_chunk_chars=400, llm_summary_max_chunks=2)
    service = make_service(settings)
    segments = [
        {"text": f"SEGMENT_{index:02d} " + ("course evidence " * 12), "source_reference": f"段落 {index + 1}"}
        for index in range(20)
    ]
    ready = ReadyMaterial(1, "\n".join(str(segment["text"]) for segment in segments), segments)
    client = FakeStructuredClient()

    result = service._generate_summary_output(client, ready)

    assert isinstance(result.data, SummaryOutput)
    maps = [source for operation, source in client.calls if operation == "ai_summary_map"]
    assert 1 < len(maps) < len(segments)
    assert any(operation == "ai_summary_reduce" for operation, _ in client.calls)
    for index in range(20):
        assert any(f"SEGMENT_{index:02d}" in source for source in maps)


def test_fragmented_long_summary_does_not_multiply_provider_calls() -> None:
    settings = Settings(llm_context_chars=12000, llm_chunk_chars=800, llm_summary_max_chunks=8)
    service = make_service(settings)
    segments = [
        {"text": f"FRAGMENT_{index:03d} " + ("evidence " * 4), "source_reference": f"段落 {index + 1}"}
        for index in range(528)
    ]
    plain_text = "\n".join(str(segment["text"]) for segment in segments)
    ready = ReadyMaterial(1, plain_text, segments)
    client = FakeStructuredClient()

    service._generate_summary_output(client, ready)

    maps = [source for operation, source in client.calls if operation == "ai_summary_map"]
    assert len(maps) <= 3
    assert "FRAGMENT_000" in maps[0]
    assert "FRAGMENT_527" in maps[-1]


def test_summary_above_explicit_limit_fails_without_model_call() -> None:
    settings = Settings(llm_summary_max_input_chars=12000)
    service = make_service(settings)
    client = FakeStructuredClient()
    ready = ReadyMaterial(1, "x" * 12001, [{"text": "x" * 12001, "source_reference": "全文"}])

    with pytest.raises(AIServiceError) as error:
        service._generate_summary_output(client, ready)

    assert error.value.code == "AI_INPUT_TOO_LARGE"
    assert client.calls == []


def test_qa_rejects_fabricated_source_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(Settings())
    ready = ReadyMaterial(
        1, "Cache reduces latency.", [{"text": "Cache reduces latency.", "source_reference": "第 1 页"}]
    )
    client = FakeStructuredClient(qa_references=["第 99 页"])
    monkeypatch.setattr(service, "_load_ready_material", lambda material_id: ready)
    monkeypatch.setattr(service, "_chunks_for", lambda material: [TextChunk("Cache reduces latency.", "第 1 页")])
    monkeypatch.setattr("backend.app.services.material_ai_service.get_llm_client", lambda settings: client)

    with pytest.raises(AIServiceError) as error:
        service.answer_question(1, "What does cache reduce?")

    assert error.value.code == "AI_INVALID_OUTPUT"


def test_source_reference_normalization_only_removes_one_outer_bracket_pair() -> None:
    assert _normalize_source_reference("[PDF 第 2 页]") == "PDF 第 2 页"
    assert _normalize_source_reference(" PDF 第 1 页 ") == "PDF 第 1 页"
    assert _normalize_source_reference("[PDF 第 99 页]") == "PDF 第 99 页"
    assert _normalize_source_reference(None) is None

    allowed = {"PDF 第 2 页"}
    assert _resolve_source_reference("[PDF 第2页]", allowed) == "PDF 第 2 页"
    assert _resolve_source_reference("[PDF 第99页]", allowed) == "PDF 第99页"
    assert _resolve_source_reference("[[PDF 第2页]]", allowed) != "PDF 第 2 页"


def test_qa_accepts_bracketed_real_reference_and_returns_canonical_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(Settings())
    ready = ReadyMaterial(
        1,
        "LRU replaces the least recently used block.",
        [{"text": "LRU replaces the least recently used block.", "source_reference": "PDF 第 2 页"}],
    )
    client = FakeStructuredClient(qa_references=["[PDF 第2页]"])
    monkeypatch.setattr(service, "_load_ready_material", lambda material_id: ready)
    monkeypatch.setattr(
        service,
        "_chunks_for",
        lambda material: [TextChunk("LRU replaces the least recently used block.", "PDF 第 2 页")],
    )
    monkeypatch.setattr("backend.app.services.material_ai_service.get_llm_client", lambda settings: client)

    result = service.answer_question(1, "What does LRU replace?")

    assert result.grounded is True
    assert result.references == ["PDF 第 2 页"]


def test_cards_prompt_requires_exact_source_labels_or_null() -> None:
    system_message = cards_prompt.messages("[PDF 第 1 页]\nCache")[0]["content"]
    assert "source_reference" in system_message
    assert "方括号" in system_message
    assert "null" in system_message


def test_cards_reject_fabricated_source_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(Settings())
    ready = ReadyMaterial(
        1,
        "Cache reduces latency.",
        [{"text": "Cache reduces latency.", "source_reference": "PDF 第 1 页"}],
    )

    class FakeCardsClient:
        def generate_structured(self, **_kwargs: object) -> GeneratedStructuredOutput:
            cards = [
                StudyCardDraft(
                    question=f"Question {index}",
                    answer="Answer",
                    source_reference="[PDF 第99页]",
                )
                for index in range(1, 6)
            ]
            return GeneratedStructuredOutput(CardsOutput(cards=cards), "fake", "test-model")

    monkeypatch.setattr(service, "_load_ready_material", lambda material_id: ready)
    monkeypatch.setattr(
        service,
        "_chunks_for",
        lambda material: [TextChunk("Cache reduces latency.", "PDF 第 1 页")],
    )
    monkeypatch.setattr(
        "backend.app.services.material_ai_service.get_llm_client",
        lambda settings: FakeCardsClient(),
    )

    with pytest.raises(AIServiceError) as error:
        service.generate_cards(1)

    assert error.value.code == "AI_INVALID_OUTPUT"


def test_card_context_references_only_sent_segments() -> None:
    service = make_service(Settings(llm_context_chars=2000))
    context, references = service._bounded_chunk_text(
        [TextChunk("A" * 1995, "第 1 页"), TextChunk("B" * 20, "第 2 页")]
    )
    assert len(context) <= 2000
    assert references == {"第 1 页"}
    assert "第 2 页" not in context


def test_session_dependency_rolls_back_non_database_error_without_misleading_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from backend.app.db.session import get_db

    class FakeSession:
        rolled_back = False
        closed = False

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr("backend.app.db.session.get_session_factory", lambda: lambda: session)
    dependency = get_db()
    next(dependency)
    with pytest.raises(ValueError):
        dependency.throw(ValueError("validation failed"))
    assert session.rolled_back
    assert session.closed
    assert not any("Database request transaction failed" in record.message for record in caplog.records)
