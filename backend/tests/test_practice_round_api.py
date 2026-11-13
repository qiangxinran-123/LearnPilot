import asyncio
import json as jsonlib
from urllib.parse import urlencode, urlsplit

import pytest
from sqlalchemy import func, select, update
from starlette.datastructures import Headers

from backend.app.ai import AIServiceError
from backend.app.db.models import KnowledgeEdge, KnowledgeNode, LearningEvidence, Question, StudentKnowledgeState
from backend.app.models import KnowledgeDifficulty, KnowledgeRelationType, QuestionValidationStatus
from backend.app.services.adaptive_practice_service import AdaptivePracticeService, get_adaptive_practice_service
from backend.app.services.diagnostic_question_generation import DiagnosticQuestionGenerationService
from backend.app.services.learning_session_service import LearningSessionService, get_learning_session_service
from backend.main import app
from backend.tests.test_m4b_question_generation import ScriptedLLMClient
from backend.tests.test_m7_4_adaptive_practice import _ready_session, _settings
from backend.tests.test_m7_4_adaptive_practice import practice_database as practice_database
from backend.tests.test_m7_5_settlement import _finished
from backend.tests.test_practice_replenishment import _add_generation_context


def _client(monkeypatch, factory, url, fake):
    settings = _settings(url)

    def practice():
        with factory() as db:
            generator = DiagnosticQuestionGenerationService(
                db, settings.model_copy(update={"llm_max_attempts": 1}), lambda _: fake
            )
            yield AdaptivePracticeService(db, settings, question_generator=generator)

    def sessions():
        with factory() as db:
            yield LearningSessionService(db, settings)

    monkeypatch.setitem(app.dependency_overrides, get_adaptive_practice_service, practice)
    monkeypatch.setitem(app.dependency_overrides, get_learning_session_service, sessions)

    class Response:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body

        def json(self):
            return jsonlib.loads(self._body)

    class Client:
        def request(self, method, path, *, json=None, params=None):
            async def call():
                parsed = urlsplit(path)
                query = urlencode(params or {}).encode()
                scope = {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": method,
                    "scheme": "http",
                    "path": parsed.path,
                    "raw_path": parsed.path.encode(),
                    "query_string": query,
                    "headers": Headers({"content-type": "application/json"}).raw,
                    "client": ("127.0.0.1", 12345),
                    "server": ("127.0.0.1", 80),
                }
                body = b"" if json is None else jsonlib.dumps(json).encode()
                sent_request = False
                done = asyncio.Event()
                status = 500
                output = bytearray()

                async def receive():
                    nonlocal sent_request
                    if not sent_request:
                        sent_request = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    await done.wait()
                    return {"type": "http.disconnect"}

                async def send(message):
                    nonlocal status
                    if message["type"] == "http.response.start":
                        status = message["status"]
                    elif message["type"] == "http.response.body":
                        output.extend(message.get("body", b""))
                        if not message.get("more_body", False):
                            done.set()

                await app(scope, receive, send)
                return Response(status, bytes(output))

            return asyncio.run(call())

        def post(self, path, **kwargs):
            return self.request("POST", path, **kwargs)

        def put(self, path, **kwargs):
            return self.request("PUT", path, **kwargs)

        def get(self, path, **kwargs):
            return self.request("GET", path, **kwargs)

    return Client()


@pytest.mark.parametrize(
    ("difficulty", "target"),
    [(KnowledgeDifficulty.BASIC, 3), (KnowledgeDifficulty.INTERMEDIATE, 4), (KnowledgeDifficulty.ADVANCED, 5)],
)
def test_question_target_follows_knowledge_difficulty(practice_database, monkeypatch, difficulty, target):
    factory, ids, _, url = practice_database
    with factory() as db, db.begin():
        db.get(KnowledgeNode, ids["cache"]).difficulty = difficulty
    session_id = _ready_session(factory, ids, url)
    fake = ScriptedLLMClient([AIServiceError("AI_TIMEOUT", "unused")])
    client = _client(monkeypatch, factory, url, fake)
    response = client.post(f"/api/learning/sessions/{session_id}/practice/next")
    assert response.status_code == 200
    assert response.json()["max_questions"] == target
    assert client.post(f"/api/learning/sessions/{session_id}/practice/finish").status_code == 409
    assert fake.calls == 0


@pytest.mark.parametrize("blocked_prerequisite", [False, True])
def test_basic_single_question_failure_can_finish_and_continue(practice_database, monkeypatch, blocked_prerequisite):
    factory, ids, correct, url = practice_database
    _add_generation_context(factory, ids)
    first_id = min(correct)
    with factory() as db, db.begin():
        db.get(KnowledgeNode, ids["cache"]).difficulty = KnowledgeDifficulty.BASIC
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"], Question.id != first_id)
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
        if blocked_prerequisite:
            db.add(
                KnowledgeEdge(
                    course_id=ids["course"],
                    source_node_id=ids["cache"],
                    target_node_id=ids["empty"],
                    relation_type=KnowledgeRelationType.PREREQUISITE,
                )
            )
    session_id = _ready_session(factory, ids, url)
    fake = ScriptedLLMClient([AIServiceError("AI_TIMEOUT", "offline timeout", retryable=True)])
    client = _client(monkeypatch, factory, url, fake)
    prefix = f"/api/learning/sessions/{session_id}"
    first = client.post(f"{prefix}/practice/next")
    assert first.status_code == 200 and first.json()["max_questions"] == 3
    question = first.json()["current_question"]
    payload = {"selected_options": correct[first_id]}
    response = client.put(f"{prefix}/practice/responses/{question['assessment_question_id']}", json=payload)
    assert response.status_code == 200 and response.json()["answered_count"] == 1
    retry = client.put(f"{prefix}/practice/responses/{question['assessment_question_id']}", json=payload)
    assert retry.status_code == 200 and retry.json()["reused"]
    paused = client.post(f"{prefix}/practice/next")
    assert paused.status_code == 200 and paused.json()["generation_error"] == "AI_TIMEOUT"
    assert paused.json()["status"] == "question_bank_empty" and fake.calls == 1
    restored = client.get(f"{prefix}/practice")
    assert restored.status_code == 200 and restored.json()["answered_count"] == 1
    assert restored.json()["attempts"][0]["assessment_question_id"] == question["assessment_question_id"]
    assert restored.json()["generation_error"] == "AI_TIMEOUT" and fake.calls == 1
    assert client.post(f"{prefix}/practice/next").json()["generation_error"] == "AI_TIMEOUT"
    assert fake.calls == 2
    other = client.get("/api/learning/sessions/active", params={"course_id": ids["other_course"]})
    assert other.status_code == 200 and other.json()["session"] is None
    finished = client.post(f"{prefix}/practice/finish")
    assert finished.status_code == 200 and finished.json()["completion_reason"] == "no_questions"
    detail = client.get(prefix)
    assert detail.status_code == 200 and detail.json()["status"] == "completed"
    assert len(detail.json()["practice_attempts"]) == 1
    recommendation = client.get(f"{prefix}/continuation").json()["recommendation"]
    if blocked_prerequisite:
        assert recommendation is None
    else:
        assert recommendation["knowledge_node_id"] == ids["empty"]
        next_session = client.post(
            "/api/learning/sessions",
            json={"course_id": ids["course"], "target_knowledge_node_id": recommendation["knowledge_node_id"]},
        )
        assert next_session.status_code in {200, 201}
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(LearningEvidence)
                .where(LearningEvidence.course_id == ids["other_course"])
            )
            == 0
        )
        assert db.get(Question, ids["foreign_question"]).validation_status == QuestionValidationStatus.VALIDATED
        state = db.scalar(select(StudentKnowledgeState))
        assert state.mastery_score is None and state.confidence_level.value == "insufficient"


def test_distinct_questions_reach_mastery_and_next_node_via_api(practice_database, monkeypatch):
    factory, ids, correct, url = practice_database
    with factory() as db, db.begin():
        db.add(
            KnowledgeEdge(
                course_id=ids["course"],
                source_node_id=ids["cache"],
                target_node_id=ids["empty"],
                relation_type=KnowledgeRelationType.PREREQUISITE,
            )
        )
    first_id = _finished(factory, ids, correct, url)
    from backend.app.services.learning_settlement_service import LearningSettlementService

    with factory() as db:
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(first_id)
    session_id = _ready_session(factory, ids, url)
    fake = ScriptedLLMClient([AIServiceError("AI_TIMEOUT", "unused", retryable=True)])
    client = _client(monkeypatch, factory, url, fake)
    prefix = f"/api/learning/sessions/{session_id}"
    selected = client.post(f"{prefix}/practice/next")
    assert selected.status_code == 200
    question = selected.json()["current_question"]
    answer = client.put(
        f"{prefix}/practice/responses/{question['assessment_question_id']}",
        json={"selected_options": correct[question["question_id"]]},
    )
    assert answer.status_code == 200 and answer.json()["completion_reason"] == "mastered"
    assert client.get(prefix).json()["status"] == "completed"
    recommendation = client.get(f"{prefix}/continuation").json()["recommendation"]
    assert recommendation["knowledge_node_id"] == ids["empty"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 6
        state = db.scalar(select(StudentKnowledgeState))
        assert state.mastery_score >= 80 and state.confidence_level.value == "medium"
    assert fake.calls == 0
