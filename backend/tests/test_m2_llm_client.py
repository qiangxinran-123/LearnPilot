from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest
from pydantic import BaseModel

from backend.app.ai.client import ExplicitMockLLMClient, OpenAICompatibleLLMClient
from backend.app.ai.errors import AIServiceError
from backend.app.ai.models import CardsOutput, KnowledgeExtractionOutput
from backend.app.core.settings import Settings


class SmallOutput(BaseModel):
    answer: str


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.body


def make_client(*, max_attempts: int = 3) -> OpenAICompatibleLLMClient:
    return OpenAICompatibleLLMClient(
        Settings(
            _env_file=None,
            llm_api_key="test-canary-not-a-real-key",
            llm_base_url="https://example.test/v1",
            llm_model="test-model",
            llm_max_attempts=max_attempts,
        )
    )


def valid_response() -> FakeResponse:
    content = json.dumps({"answer": "Document-grounded answer"})
    return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"\\xff",
        b"[]",
        b"{}",
        b'{"choices":[]}',
        b'{"choices":{}}',
        b'{"choices":[null]}',
        b'{"choices":[{}]}',
        b'{"choices":[{"message":[]}]}',
        b'{"choices":[{"message":{"content":null}}]}',
    ],
)
def test_success_status_with_invalid_body_returns_ai_invalid_output(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, body: bytes
) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        return FakeResponse(body)

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    with pytest.raises(AIServiceError) as captured:
        make_client().generate_structured(operation="test", messages=[], schema=SmallOutput)
    assert captured.value.code == "AI_INVALID_OUTPUT"
    assert captured.value.retryable is False
    assert attempts == 1
    assert "test-canary-not-a-real-key" not in caplog.text


def test_invalid_structured_content_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return FakeResponse(b'{"choices":[{"message":{"content":"not-json"}}]}')
        return valid_response()

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.app.ai.client.time.sleep", lambda seconds: None)
    output = make_client(max_attempts=2).generate_structured(operation="test", messages=[], schema=SmallOutput)
    assert output.data.answer == "Document-grounded answer"
    assert attempts == 2


def test_knowledge_extraction_invalid_json_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return FakeResponse(b'{"choices":[{"message":{"content":"not-json"}}]}')
        content = json.dumps(
            {
                "candidates": [
                    {
                        "name": "Cache",
                        "description": "A small fast memory structure.",
                        "importance": "high",
                        "difficulty": "intermediate",
                        "source_references": ["PDF 第 1 页"],
                    }
                ]
            }
        )
        return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.app.ai.client.time.sleep", lambda seconds: None)
    output = make_client(max_attempts=2).generate_structured(
        operation="knowledge_extraction",
        messages=[],
        schema=KnowledgeExtractionOutput,
    )
    assert output.data.candidates[0].name == "Cache"
    assert attempts == 2


def test_schema_mismatch_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            invalid_content = json.dumps({"unexpected": "field"})
            return FakeResponse(json.dumps({"choices": [{"message": {"content": invalid_content}}]}).encode())
        return valid_response()

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.app.ai.client.time.sleep", lambda seconds: None)
    output = make_client(max_attempts=2).generate_structured(operation="test", messages=[], schema=SmallOutput)
    assert output.data.answer == "Document-grounded answer"
    assert attempts == 2


def test_invalid_structured_content_retries_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        return FakeResponse(b'{"choices":[{"message":{"content":"not-json"}}]}')

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.app.ai.client.time.sleep", lambda seconds: None)
    with pytest.raises(AIServiceError) as captured:
        make_client(max_attempts=2).generate_structured(operation="test", messages=[], schema=SmallOutput)
    assert captured.value.code == "AI_INVALID_OUTPUT"
    assert captured.value.retryable is True
    assert attempts == 2


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_http_error_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError("https://example.test", status, "transient", {}, None)
        return valid_response()

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.app.ai.client.time.sleep", lambda seconds: None)
    output = make_client().generate_structured(operation="test", messages=[], schema=SmallOutput)
    assert output.data.answer == "Document-grounded answer"
    assert attempts == 2


@pytest.mark.parametrize("status", [400, 401, 403])
def test_nontransient_http_error_is_not_retried(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        raise HTTPError("https://example.test", status, "bad request", {}, None)

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    with pytest.raises(AIServiceError) as captured:
        make_client().generate_structured(operation="test", messages=[], schema=SmallOutput)
    assert captured.value.code == "AI_PROVIDER_ERROR"
    assert attempts == 1


def test_timeout_retries_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        raise TimeoutError

    monkeypatch.setattr("backend.app.ai.client.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.app.ai.client.time.sleep", lambda seconds: None)
    with pytest.raises(AIServiceError) as captured:
        make_client(max_attempts=2).generate_structured(operation="test", messages=[], schema=SmallOutput)
    assert captured.value.code == "AI_TIMEOUT"
    assert attempts == 2


def test_explicit_mock_cards_use_only_real_source_labels() -> None:
    client = ExplicitMockLLMClient()
    with_source = client.generate_structured(
        operation="cards",
        messages=[{"role": "user", "content": "[PDF 第 3 页]\nCache locality improves access."}],
        schema=CardsOutput,
    )
    without_source = client.generate_structured(
        operation="cards",
        messages=[{"role": "user", "content": "Cache locality improves access."}],
        schema=CardsOutput,
    )
    assert all(card.source_reference == "PDF 第 3 页" for card in with_source.data.cards)
    assert all(card.source_reference is None for card in without_source.data.cards)
