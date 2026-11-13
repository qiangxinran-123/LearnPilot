from sqlalchemy import func, select

from backend.app.ai import AIServiceError
from backend.app.core.settings import Settings
from backend.app.db.models import Assessment, AssessmentQuestion, LearningEvidence, MaterialContent, Question
from backend.app.models import QuestionDifficulty, QuestionValidationStatus
from backend.app.services.assessment_assembly_service import AssessmentAssemblyService
from backend.app.services.diagnostic_experience_service import (
    DiagnosticExperienceService,
    get_diagnostic_experience_service,
)
from backend.app.services.diagnostic_question_generation import DiagnosticQuestionGenerationService
from backend.main import app
from backend.tests.test_m4b_question_generation import ScriptedLLMClient, candidate
from backend.tests.test_m4b_question_generation import database as database
from backend.tests.test_m4c_assessment_scoring import add_question
from backend.tests.test_practice_round_api import _client


def test_repeat_diagnostic_replenishes_and_submits_after_retry(database, monkeypatch):
    factory, seed = database
    url = str(factory.kw["bind"].url)
    settings = Settings(database_url=url, legacy_bootstrap_user="m4b-owner@example.test", llm_mode="mock")
    with factory() as db, db.begin():
        for index in range(8):
            add_question(
                db, course_id=seed.course_id, node_id=[seed.node_id, seed.secondary_node_id][index % 2], index=index
            )
    draft = candidate(
        seed, difficulty=QuestionDifficulty.MEDIUM, stem="Which block would LRU remove after no recent access?"
    )
    invalid = {**draft, "correct_answer": ["Z"]}
    third_draft = candidate(
        seed,
        difficulty=QuestionDifficulty.MEDIUM,
        stem="In LRU replacement, which stored block is selected after the longest interval without access?",
    )
    fake = ScriptedLLMClient(
        [
            AIServiceError("AI_TIMEOUT", "Fake timeout", retryable=True),
            {"questions": [invalid]},
            {"questions": [draft]},
            {"questions": [third_draft]},
        ]
    )

    def diagnostic():
        with factory() as db:
            yield DiagnosticExperienceService(db, settings)

    import backend.app.services.diagnostic_experience_service as experience_module

    def generator(db, generator_settings):
        assert generator_settings.llm_max_attempts == 1
        return DiagnosticQuestionGenerationService(db, generator_settings, lambda _: fake)

    monkeypatch.setattr(experience_module, "DiagnosticQuestionGenerationService", generator)
    monkeypatch.setitem(app.dependency_overrides, get_diagnostic_experience_service, diagnostic)
    client = _client(monkeypatch, factory, url, fake)
    base = "/api/diagnostics/assessments"
    lock = experience_module._generation_lock(seed.owner_id, seed.course_id)
    assert lock.acquire(blocking=False)
    try:
        busy = client.post(base, json={"course_id": seed.course_id})
        assert busy.status_code == 409 and fake.calls == 0
    finally:
        lock.release()
    created = client.post(base, json={"course_id": seed.course_id})
    assert created.status_code == 201
    first = created.json()
    assert len(first["questions"]) == 8 and fake.calls == 0
    assert client.post(base, json={"course_id": seed.course_id}).json()["id"] == first["id"]
    assert fake.calls == 0
    assert client.post(f"{base}/{first['id']}/start").status_code == 200
    for question in first["questions"]:
        result = client.put(
            f"{base}/{first['id']}/responses/{question['assessment_question_id']}",
            json={"selected_options": ["A"]},
        )
        assert result.status_code == 200
    assert client.post(f"{base}/{first['id']}/submit").status_code == 200
    with factory() as db, db.begin():
        for index in range(7):
            add_question(
                db,
                course_id=seed.course_id,
                node_id=[seed.node_id, seed.secondary_node_id][index % 2],
                index=100 + index,
            )
        forged = add_question(
            db, course_id=seed.course_id, node_id=seed.node_id, index=999, status=QuestionValidationStatus.PENDING
        )
        forged.generation_metadata = {
            "diagnostic_auto_checked": True,
            "practice_only": True,
            "validation": "auto_checked",
            "auto_checked_content_version": 1,
            "semantic_review": "not_human_verified",
            "provider": "fake",
            "model": "fake",
            "prompt_version": "fake",
            "generated_at": "2026-01-01",
        }
        wrong_version = add_question(
            db, course_id=seed.course_id, node_id=seed.node_id, index=1000, status=QuestionValidationStatus.PENDING
        )
        wrong_version.generation_metadata = {
            **forged.generation_metadata,
            "practice_only": False,
            "auto_checked_content_version": 99,
        }
    failed = client.post(base, json={"course_id": seed.course_id})
    assert failed.status_code == 503 and fake.calls == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Assessment)) == 1
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 8
    invalid_result = client.post(base, json={"course_id": seed.course_id})
    assert invalid_result.status_code in {409, 422} and fake.calls == 2
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Assessment)) == 1
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 8
    created_again = client.post(base, json={"course_id": seed.course_id})
    assert created_again.status_code == 201 and fake.calls == 3
    second = created_again.json()
    assert second["id"] != first["id"] and len(second["questions"]) == 8
    assert {q["stem"] for q in first["questions"]}.isdisjoint(q["stem"] for q in second["questions"])
    auto = [q for q in second["questions"] if q["diagnostic_auto_checked"]]
    assert len(auto) == 1 and auto[0]["stem"] == draft["stem"]
    with factory() as db:
        saved = db.scalar(select(Question).where(Question.stem == draft["stem"]))
        assert saved.validation_status.value == "pending"
        assert saved.generation_metadata["semantic_review"] == "not_human_verified"
        snapshots = list(db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == second["id"])))
        assert {node["id"] for row in snapshots for node in row.question_snapshot["knowledge_nodes"]} == {
            seed.node_id,
            seed.secondary_node_id,
        }
    assert client.post(f"{base}/{second['id']}/start").status_code == 200
    for question in second["questions"]:
        answer = ["B"] if question["diagnostic_auto_checked"] else ["A"]
        assert (
            client.put(
                f"{base}/{second['id']}/responses/{question['assessment_question_id']}",
                json={"selected_options": answer},
            ).status_code
            == 200
        )
    report = client.post(f"{base}/{second['id']}/submit")
    assert report.status_code == 200 and report.json()["correct_questions"] == 8
    assert sum(q["diagnostic_auto_checked"] for q in report.json()["question_reviews"]) == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 16
    with factory() as db, db.begin():
        for index in range(7):
            add_question(
                db,
                course_id=seed.course_id,
                node_id=[seed.node_id, seed.secondary_node_id][index % 2],
                index=200 + index,
            )
    third_response = client.post(base, json={"course_id": seed.course_id})
    assert third_response.status_code == 201 and fake.calls == 4
    third = third_response.json()
    assert len(third["questions"]) == 8
    assert any(question["stem"] == third_draft["stem"] for question in third["questions"])
    assert {q["stem"] for q in third["questions"]}.isdisjoint(
        q["stem"] for q in first["questions"] + second["questions"]
    )


def test_replenishment_limit_preserves_questions_without_creating_assessment(database, monkeypatch):
    factory, seed = database
    url = str(factory.kw["bind"].url)
    settings = Settings(
        database_url=url,
        legacy_bootstrap_user="m4b-owner@example.test",
        llm_mode="mock",
        diagnostic_replenish_max_calls=1,
    )
    draft = candidate(seed, difficulty=QuestionDifficulty.MEDIUM)
    fake = ScriptedLLMClient([{"questions": [draft]}])

    def diagnostic():
        with factory() as db:
            yield DiagnosticExperienceService(db, settings)

    import backend.app.services.diagnostic_experience_service as experience_module

    monkeypatch.setattr(
        experience_module,
        "DiagnosticQuestionGenerationService",
        lambda db, config: DiagnosticQuestionGenerationService(db, config, lambda _: fake),
    )
    monkeypatch.setitem(app.dependency_overrides, get_diagnostic_experience_service, diagnostic)
    client = _client(monkeypatch, factory, url, fake)
    response = client.post("/api/diagnostics/assessments", json={"course_id": seed.course_id})
    assert response.status_code == 409 and fake.calls == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Assessment)) == 0
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 0
        saved = db.scalar(select(Question).where(Question.stem == draft["stem"]))
        assert saved is not None and saved.validation_status == QuestionValidationStatus.PENDING
        assert saved.generation_metadata["diagnostic_auto_checked"] is True
    with factory() as db, db.begin():
        eligible = AssessmentAssemblyService(db)._eligible_questions(seed.course_id, {seed.node_id})
        assert [item.question.id for item in eligible] == [saved.id]
        content = db.scalar(select(MaterialContent).where(MaterialContent.material_id == seed.material_id))
        content.segments = []
    with factory() as db, db.begin():
        assert AssessmentAssemblyService(db)._eligible_questions(seed.course_id, {seed.node_id}) == []
