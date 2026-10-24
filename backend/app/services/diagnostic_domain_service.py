from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeNode,
    Question,
    QuestionKnowledgeNode,
    Response,
)
from backend.app.models import AssessmentStatus, AssessmentType, QuestionType
from backend.app.repositories import AssessmentRepository, QuestionRepository, ResponseRepository
from backend.app.schemas.diagnostic import (
    AssessmentQuestionSnapshotSchema,
    ObjectiveAnswerSchema,
    QuestionContentSchema,
    QuestionCreateSchema,
    QuestionKnowledgeRefSchema,
    ScoringPolicySchema,
)
from backend.app.services.deterministic_objective_scorer import (
    DeterministicObjectiveScorer,
    DeterministicScoringError,
)
from backend.app.services.diagnostic_report_service import DIAGNOSTIC_REPORT_POLICY_VERSION


class DiagnosticDomainError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class DiagnosticDomainService:
    """Diagnostic write boundary for immutable snapshots, protected answers, and deterministic scoring."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.questions = QuestionRepository(session)
        self.assessments = AssessmentRepository(session)
        self.responses = ResponseRepository(session)
        self.scorer = DeterministicObjectiveScorer()

    def create_question(self, owner_id: int, course_id: int, payload: QuestionCreateSchema) -> Question:
        try:
            with self.session.begin():
                self._require_owned_course(course_id, owner_id)
                nodes = self._require_nodes(course_id, [item.knowledge_node_id for item in payload.knowledge_nodes])
                content = payload.content
                question = self.questions.create(
                    Question(
                        course_id=course_id,
                        question_type=content.question_type,
                        stem=content.stem,
                        options=[option.model_dump(mode="json") for option in content.options],
                        correct_answer=list(content.correct_answer),
                        explanation=content.explanation,
                        difficulty=content.difficulty,
                        validation_status=payload.validation_status,
                        source_refs=[item.model_dump(mode="json") for item in content.source_refs],
                        generation_metadata=dict(payload.generation_metadata),
                        content_version=1,
                    )
                )
                for binding in payload.knowledge_nodes:
                    self.questions.add_knowledge_link(
                        QuestionKnowledgeNode(
                            course_id=course_id,
                            question_id=question.id,
                            knowledge_node_id=nodes[binding.knowledge_node_id].id,
                            relation_role=binding.relation_role,
                        )
                    )
                return question
        except IntegrityError as error:
            raise DiagnosticDomainError(
                "DIAGNOSTIC_INTEGRITY_ERROR", "Question data violates persistence rules."
            ) from error

    def update_question_content(self, owner_id: int, question_id: int, content: QuestionContentSchema) -> Question:
        with self.session.begin():
            question = self.questions.get_for_owner(question_id, owner_id)
            if question is None:
                raise DiagnosticDomainError("QUESTION_NOT_FOUND", "Question not found.")
            question.question_type = content.question_type
            question.stem = content.stem
            question.options = [option.model_dump(mode="json") for option in content.options]
            question.correct_answer = list(content.correct_answer)
            question.explanation = content.explanation
            question.difficulty = content.difficulty
            question.source_refs = [item.model_dump(mode="json") for item in content.source_refs]
            question.content_version += 1
            self.session.flush()
            return question

    def delete_question(self, owner_id: int, question_id: int) -> None:
        with self.session.begin():
            question = self.questions.get_for_owner(question_id, owner_id)
            if question is None:
                raise DiagnosticDomainError("QUESTION_NOT_FOUND", "Question not found.")
            self.questions.delete(question)

    def create_assessment_draft(self, owner_id: int, course_id: int) -> Assessment:
        with self.session.begin():
            self._require_owned_course(course_id, owner_id)
            return self.assessments.create(
                Assessment(
                    course_id=course_id,
                    owner_id=owner_id,
                    assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
                    status=AssessmentStatus.DRAFT,
                )
            )

    def fix_question_snapshots(
        self, owner_id: int, assessment_id: int, ordered_question_ids: list[int]
    ) -> list[AssessmentQuestion]:
        if not ordered_question_ids:
            raise DiagnosticDomainError("ASSESSMENT_QUESTIONS_REQUIRED", "At least one question is required.")
        if len(ordered_question_ids) != len(set(ordered_question_ids)):
            raise DiagnosticDomainError("ASSESSMENT_QUESTION_DUPLICATE", "Assessment questions must be unique.")
        try:
            with self.session.begin():
                assessment = self._require_assessment(owner_id, assessment_id)
                self._require_status(assessment, AssessmentStatus.DRAFT)
                snapshots: list[AssessmentQuestion] = []
                for order_index, question_id in enumerate(ordered_question_ids):
                    question = self.questions.get_for_course(question_id, assessment.course_id)
                    if question is None:
                        raise DiagnosticDomainError(
                            "ASSESSMENT_QUESTION_COURSE_MISMATCH",
                            "Every question must belong to the assessment course.",
                        )
                    snapshot = self.build_question_snapshot(question)
                    snapshots.append(
                        self.assessments.add_question_snapshot(
                            AssessmentQuestion(
                                assessment_id=assessment.id,
                                question_id=question.id,
                                order_index=order_index,
                                question_snapshot=snapshot.model_dump(mode="json"),
                            )
                        )
                    )
                assessment.status = AssessmentStatus.READY
                self.session.flush()
                return snapshots
        except IntegrityError as error:
            raise DiagnosticDomainError(
                "DIAGNOSTIC_INTEGRITY_ERROR", "Question snapshots could not be fixed atomically."
            ) from error

    def start_assessment(self, owner_id: int, assessment_id: int) -> Assessment:
        with self.session.begin():
            assessment = self._require_assessment(owner_id, assessment_id)
            self._require_status(assessment, AssessmentStatus.READY)
            now = datetime.now(timezone.utc)
            if not self.assessments.compare_and_set_status(
                assessment.id, AssessmentStatus.READY, AssessmentStatus.IN_PROGRESS, started_at=now
            ):
                raise DiagnosticDomainError("ASSESSMENT_STATE_CONFLICT", "Assessment state changed concurrently.")
            self.session.refresh(assessment)
            return assessment

    def save_draft_response(
        self,
        owner_id: int,
        assessment_id: int,
        assessment_question_id: int,
        answer: ObjectiveAnswerSchema,
    ) -> Response:
        try:
            with self.session.begin():
                assessment = self._require_assessment(owner_id, assessment_id)
                self._require_status(assessment, AssessmentStatus.IN_PROGRESS)
                assessment_question = self.assessments.get_question(assessment.id, assessment_question_id)
                if assessment_question is None:
                    raise DiagnosticDomainError(
                        "ASSESSMENT_QUESTION_NOT_FOUND", "Question does not belong to this assessment."
                    )
                payload = self._validated_answer_payload(assessment_question, answer)
                return self.responses.save_draft(
                    assessment_id=assessment.id,
                    assessment_question_id=assessment_question.id,
                    answer_payload=payload,
                    answered_at=datetime.now(timezone.utc),
                )
        except IntegrityError as error:
            raise DiagnosticDomainError("DIAGNOSTIC_INTEGRITY_ERROR", "Response violates persistence rules.") from error
        except ValueError as error:
            if isinstance(error, DiagnosticDomainError):
                raise
            raise DiagnosticDomainError("RESPONSE_LOCKED", str(error)) from error

    def discard_assessment(self, owner_id: int, assessment_id: int) -> None:
        """Discard an unfinished assessment and its draft responses atomically.

        Missing assessments are treated as already discarded so repeated client
        requests are safe. Submitted assessments are immutable and can never be
        discarded through this draft-only operation.
        """
        with self.session.begin():
            assessment = self.assessments.get_for_owner(assessment_id, owner_id)
            if assessment is None:
                return
            if assessment.status not in {
                AssessmentStatus.DRAFT,
                AssessmentStatus.READY,
                AssessmentStatus.IN_PROGRESS,
            }:
                raise DiagnosticDomainError(
                    "ASSESSMENT_INVALID_TRANSITION",
                    "Only an unfinished assessment can be discarded.",
                )
            self.assessments.delete(assessment)

    def submit_assessment(
        self,
        owner_id: int,
        assessment_id: int,
        final_answers: dict[int, ObjectiveAnswerSchema] | None = None,
    ) -> Assessment:
        try:
            with self.session.begin():
                assessment = self._require_assessment(owner_id, assessment_id)
                questions = self.assessments.list_questions(assessment.id)
                if assessment.status == AssessmentStatus.SUBMITTED:
                    self._assert_idempotent_submission(assessment.id, questions, final_answers)
                    return assessment
                self._require_status(assessment, AssessmentStatus.IN_PROGRESS)
                if final_answers is not None:
                    expected_ids = {item.id for item in questions}
                    if set(final_answers) != expected_ids:
                        raise DiagnosticDomainError(
                            "ASSESSMENT_INCOMPLETE", "Final answers must cover every assessment question exactly once."
                        )
                    for item in questions:
                        self.responses.save_draft(
                            assessment_id=assessment.id,
                            assessment_question_id=item.id,
                            answer_payload=self._validated_answer_payload(item, final_answers[item.id]),
                            answered_at=datetime.now(timezone.utc),
                        )
                responses = self.responses.list_for_assessment(assessment.id)
                existing_ids = {item.assessment_question_id for item in responses}
                if final_answers is None:
                    for item in questions:
                        if item.id not in existing_ids:
                            self.responses.save_draft(
                                assessment_id=assessment.id,
                                assessment_question_id=item.id,
                                answer_payload=self._validated_answer_payload(item, ObjectiveAnswerSchema()),
                                answered_at=datetime.now(timezone.utc),
                            )
                    responses = self.responses.list_for_assessment(assessment.id)
                if {item.assessment_question_id for item in responses} != {item.id for item in questions}:
                    raise DiagnosticDomainError("ASSESSMENT_INCOMPLETE", "Assessment answers are incomplete.")
                responses_by_question = {item.assessment_question_id: item for item in responses}
                for question in questions:
                    response = responses_by_question[question.id]
                    try:
                        score = self.scorer.score(question.question_snapshot, response.answer_payload)
                    except DeterministicScoringError as error:
                        raise DiagnosticDomainError(error.code, error.message) from error
                    response.is_correct = score.is_correct
                    response.points_awarded = score.points_awarded
                now = datetime.now(timezone.utc)
                if not self.assessments.compare_and_set_status(
                    assessment.id,
                    AssessmentStatus.IN_PROGRESS,
                    AssessmentStatus.SUBMITTED,
                    submitted_at=now,
                    report_policy_version=DIAGNOSTIC_REPORT_POLICY_VERSION,
                ):
                    raise DiagnosticDomainError("ASSESSMENT_STATE_CONFLICT", "Assessment state changed concurrently.")
                for response in responses:
                    response.submitted_at = now
                self.session.flush()
                self.session.refresh(assessment)
                return assessment
        except IntegrityError as error:
            raise DiagnosticDomainError(
                "DIAGNOSTIC_INTEGRITY_ERROR", "Assessment submission could not be committed atomically."
            ) from error
        except ValueError as error:
            if isinstance(error, DiagnosticDomainError):
                raise
            raise DiagnosticDomainError("RESPONSE_LOCKED", str(error)) from error

    def read_history(
        self, owner_id: int, assessment_id: int
    ) -> tuple[Assessment, list[AssessmentQuestion], list[Response]]:
        with self.session.begin():
            assessment = self.assessments.get_for_owner(assessment_id, owner_id, load_history=True)
            if assessment is None:
                raise DiagnosticDomainError("ASSESSMENT_NOT_FOUND", "Assessment not found.")
            return assessment, list(assessment.questions), list(assessment.responses)

    def _require_owned_course(self, course_id: int, owner_id: int) -> Course:
        course = self.session.scalar(select(Course).where(Course.id == course_id, Course.owner_id == owner_id))
        if course is None:
            raise DiagnosticDomainError("COURSE_NOT_FOUND", "Course not found.")
        return course

    def _require_nodes(self, course_id: int, node_ids: list[int]) -> dict[int, KnowledgeNode]:
        nodes = list(
            self.session.scalars(
                select(KnowledgeNode).where(
                    KnowledgeNode.course_id == course_id,
                    KnowledgeNode.id.in_(node_ids),
                    KnowledgeNode.is_active.is_(True),
                )
            )
        )
        by_id = {node.id: node for node in nodes}
        if set(by_id) != set(node_ids):
            raise DiagnosticDomainError(
                "QUESTION_KNOWLEDGE_COURSE_MISMATCH",
                "Every knowledge node must be active and belong to the question course.",
            )
        return by_id

    def _require_assessment(self, owner_id: int, assessment_id: int) -> Assessment:
        assessment = self.assessments.get_for_owner(assessment_id, owner_id)
        if assessment is None:
            raise DiagnosticDomainError("ASSESSMENT_NOT_FOUND", "Assessment not found.")
        return assessment

    @staticmethod
    def _require_status(assessment: Assessment, expected: AssessmentStatus) -> None:
        if assessment.status != expected:
            raise DiagnosticDomainError(
                "ASSESSMENT_INVALID_TRANSITION",
                f"Assessment must be {expected.value}; current state is {assessment.status.value}.",
            )

    @staticmethod
    def build_question_snapshot(question: Question) -> AssessmentQuestionSnapshotSchema:
        try:
            content = QuestionContentSchema.model_validate(
                {
                    "question_type": question.question_type,
                    "stem": question.stem,
                    "options": question.options,
                    "correct_answer": question.correct_answer,
                    "explanation": question.explanation,
                    "difficulty": question.difficulty,
                    "source_refs": question.source_refs,
                }
            )
            refs = [
                QuestionKnowledgeRefSchema(
                    id=link.knowledge_node.id,
                    name=link.knowledge_node.name,
                    role=link.relation_role,
                )
                for link in question.knowledge_links
            ]
            raw_version = question.generation_metadata.get("knowledge_model_version")
            model_version = str(raw_version) if raw_version is not None else None
            return AssessmentQuestionSnapshotSchema(
                **content.model_dump(mode="json"),
                source_question_id=question.id,
                source_question_version=question.content_version,
                knowledge_nodes=refs,
                knowledge_model_version=model_version,
                scoring_policy=ScoringPolicySchema(),
            )
        except (ValidationError, AttributeError) as error:
            raise DiagnosticDomainError(
                "QUESTION_SNAPSHOT_INVALID", "Question data cannot form a complete immutable snapshot."
            ) from error

    @staticmethod
    def _validated_answer_payload(
        assessment_question: AssessmentQuestion, answer: ObjectiveAnswerSchema
    ) -> dict[str, object]:
        raw_policy = assessment_question.question_snapshot.get("scoring_policy")
        policy_version = raw_policy.get("version") if isinstance(raw_policy, dict) else None
        if policy_version != DeterministicObjectiveScorer.POLICY_VERSION:
            raise DiagnosticDomainError("SCORING_POLICY_UNSUPPORTED", "Stored scoring policy version is not supported.")
        try:
            snapshot = AssessmentQuestionSnapshotSchema.model_validate(assessment_question.question_snapshot)
        except ValidationError as error:
            raise DiagnosticDomainError("QUESTION_SNAPSHOT_INVALID", "Stored question snapshot is invalid.") from error
        selected = answer.selected_options
        option_order = {item.key: index for index, item in enumerate(snapshot.options)}
        if not set(selected).issubset(option_order):
            raise DiagnosticDomainError("ANSWER_INVALID", "Answer contains an unknown option key.")
        if snapshot.question_type in {QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE} and len(selected) > 1:
            raise DiagnosticDomainError("ANSWER_INVALID", "This question accepts at most one selected option.")
        ordered = sorted(selected, key=option_order.__getitem__)
        return ObjectiveAnswerSchema(selected_options=ordered).model_dump(mode="json")

    def _assert_idempotent_submission(
        self,
        assessment_id: int,
        questions: list[AssessmentQuestion],
        final_answers: dict[int, ObjectiveAnswerSchema] | None,
    ) -> None:
        if final_answers is None:
            return
        if set(final_answers) != {item.id for item in questions}:
            raise DiagnosticDomainError("ASSESSMENT_ALREADY_SUBMITTED", "Submitted answers cannot be changed.")
        stored = {item.assessment_question_id: item for item in self.responses.list_for_assessment(assessment_id)}
        for item in questions:
            payload = self._validated_answer_payload(item, final_answers[item.id])
            if item.id not in stored or stored[item.id].answer_payload != payload:
                raise DiagnosticDomainError("ASSESSMENT_ALREADY_SUBMITTED", "Submitted answers cannot be changed.")


__all__ = ["DiagnosticDomainError", "DiagnosticDomainService"]
