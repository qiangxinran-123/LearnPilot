from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Assessment, AssessmentQuestion, LearningSession, LearningSessionTaskState, Response
from backend.app.db.session import get_db
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    ConfidenceLevel,
    LearningSessionStatus,
    LearningSessionTaskPhase,
    LearningSessionTaskStatus,
    MasteryStatus,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)
from backend.app.repositories import (
    AssessmentRepository,
    LearningSessionRepository,
    QuestionRepository,
    ResponseRepository,
    UserRepository,
)
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema
from backend.app.schemas.mastery_api import KnowledgeNodeMasteryReadSchema, KnowledgeStateAvailability
from backend.app.schemas.practice import (
    PracticeAnswerCreate,
    PracticeAttemptRead,
    PracticeQuestionRead,
    PracticeRead,
    PracticeSummaryRead,
)
from backend.app.services.deterministic_objective_scorer import (
    DeterministicObjectiveScorer,
    DeterministicScoringError,
)
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService
from backend.app.services.mastery_read_service import MasteryReadService

MAX_PRACTICE_QUESTIONS = 5
DIFFICULTY_ORDER = (
    QuestionDifficulty.EASY,
    QuestionDifficulty.MEDIUM,
    QuestionDifficulty.HARD,
)
DIFFICULTY_FALLBACK = {
    QuestionDifficulty.EASY: DIFFICULTY_ORDER,
    QuestionDifficulty.MEDIUM: (
        QuestionDifficulty.MEDIUM,
        QuestionDifficulty.EASY,
        QuestionDifficulty.HARD,
    ),
    QuestionDifficulty.HARD: tuple(reversed(DIFFICULTY_ORDER)),
}
SUPPORTED_TYPES = {
    QuestionType.SINGLE_CHOICE,
    QuestionType.MULTIPLE_CHOICE,
    QuestionType.TRUE_FALSE,
}


class AdaptivePracticeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class AdaptivePracticeService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.sessions = LearningSessionRepository(session)
        self.assessments = AssessmentRepository(session)
        self.questions = QuestionRepository(session)
        self.responses = ResponseRepository(session)
        self.users = UserRepository(session)
        self.scorer = DeterministicObjectiveScorer()

    def start_or_next_for_configured_user(self, session_id: int) -> PracticeRead:
        user_id, course_id, node_id, needs_initial = self._preflight(session_id)
        mastery = None
        if needs_initial:
            mastery = MasteryReadService(self.session, self.settings).node_mastery(course_id, node_id)

        try:
            with self.session.begin():
                learning_session = self._require_owned(session_id, user_id, for_update=True)
                task = self._require_practice_ready(learning_session)
                assessment = self._practice_assessment(learning_session, user_id, for_update=True)
                if assessment is None:
                    assessment = self.assessments.create(
                        Assessment(
                            course_id=learning_session.course_id,
                            owner_id=user_id,
                            assessment_type=AssessmentType.PRACTICE,
                            status=AssessmentStatus.IN_PROGRESS,
                            started_at=datetime.now(timezone.utc),
                        )
                    )
                    learning_session.practice_assessment_id = assessment.id
                    self._start_task(learning_session, task)
                    desired = _initial_difficulty(mastery)
                    self._set_progress(task, desired, answered_count=0, bank_exhausted=False)
                else:
                    desired = _stored_difficulty(task)

                if assessment.status == AssessmentStatus.SUBMITTED:
                    return self._read(learning_session, assessment, task, reused=True)
                current = _current_unanswered(assessment)
                if current is not None:
                    return self._read(learning_session, assessment, task, reused=True)

                attempts = _submitted_pairs(assessment)
                if len(attempts) >= MAX_PRACTICE_QUESTIONS:
                    self._complete_practice(assessment, task)
                    return self._read(learning_session, assessment, task)
                if attempts:
                    desired = _next_difficulty(attempts)

                selected = self._select_question(
                    owner_id=user_id,
                    course_id=learning_session.course_id,
                    node_id=learning_session.target_knowledge_node_id,
                    desired=desired,
                    excluded={item.question_id for item in assessment.questions if item.question_id is not None},
                )
                if selected is None:
                    self._set_progress(
                        task,
                        desired,
                        answered_count=len(attempts),
                        bank_exhausted=True,
                    )
                    if attempts:
                        self._complete_practice(assessment, task)
                    return self._read(learning_session, assessment, task)

                snapshot = DiagnosticDomainService.build_question_snapshot(selected)
                self.assessments.add_question_snapshot(
                    AssessmentQuestion(
                        assessment=assessment,
                        question_id=selected.id,
                        order_index=len(assessment.questions),
                        question_snapshot=snapshot.model_dump(mode="json"),
                    )
                )
                self._set_progress(
                    task,
                    selected.difficulty,
                    answered_count=len(attempts),
                    bank_exhausted=False,
                )
                self.session.flush()
                return self._read(learning_session, assessment, task)
        except DiagnosticDomainError as error:
            raise AdaptivePracticeError(error.code, error.message) from error
        except IntegrityError as error:
            self.session.rollback()
            return self._read_after_conflict(session_id, user_id, error)

    def answer_for_configured_user(
        self,
        *,
        session_id: int,
        assessment_question_id: int,
        payload: PracticeAnswerCreate,
    ) -> PracticeRead:
        if not payload.selected_options:
            raise AdaptivePracticeError("ANSWER_REQUIRED", "Select at least one answer before submitting.")
        try:
            with self.session.begin():
                user_id = self._owner_id()
                learning_session = self._require_owned(session_id, user_id, for_update=True)
                task = self._require_practice_ready(learning_session)
                assessment = self._practice_assessment(learning_session, user_id, for_update=True)
                if assessment is None:
                    raise AdaptivePracticeError("PRACTICE_NOT_STARTED", "Practice has not started.")
                question = next(
                    (item for item in assessment.questions if item.id == assessment_question_id),
                    None,
                )
                if question is None:
                    raise AdaptivePracticeError("PRACTICE_QUESTION_NOT_FOUND", "Practice question not found.")
                existing = question.response
                answer_payload = payload.model_dump(mode="json")
                if existing is not None:
                    if existing.answer_payload != answer_payload:
                        raise AdaptivePracticeError(
                            "PRACTICE_RESPONSE_LOCKED",
                            "A submitted practice answer cannot be changed.",
                        )
                    return self._read(learning_session, assessment, task, reused=True)
                if assessment.status != AssessmentStatus.IN_PROGRESS:
                    raise AdaptivePracticeError("PRACTICE_COMPLETED", "Practice is already complete.")
                current = _current_unanswered(assessment)
                if current is None or current.id != question.id:
                    raise AdaptivePracticeError(
                        "PRACTICE_QUESTION_STALE",
                        "This is no longer the current practice question.",
                    )

                try:
                    score = self.scorer.score(question.question_snapshot, payload)
                except DeterministicScoringError as error:
                    raise AdaptivePracticeError(error.code, error.message) from error
                now = datetime.now(timezone.utc)
                response = self.responses.create_submitted(
                    Response(
                        assessment_id=assessment.id,
                        assessment_question_id=question.id,
                        answer_payload=answer_payload,
                        answered_at=now,
                        submitted_at=now,
                        is_correct=score.is_correct,
                        points_awarded=score.points_awarded,
                    )
                )
                question.response = response
                attempts = _submitted_pairs(assessment)
                desired = _next_difficulty(attempts)
                self._set_progress(
                    task,
                    desired,
                    answered_count=len(attempts),
                    bank_exhausted=False,
                )
                if len(attempts) >= MAX_PRACTICE_QUESTIONS:
                    self._complete_practice(assessment, task)
                self.session.flush()
                return self._read(learning_session, assessment, task)
        except IntegrityError as error:
            self.session.rollback()
            return self._replay_answer(session_id, assessment_question_id, payload, error)
        except OperationalError as error:
            self.session.rollback()
            raise AdaptivePracticeError(
                "PRACTICE_STATE_CONFLICT",
                "Practice changed concurrently; retry the request.",
            ) from error

    def _preflight(self, session_id: int) -> tuple[int, int, int, bool]:
        with self.session.begin():
            user_id = self._owner_id()
            learning_session = self._require_owned(session_id, user_id)
            return (
                user_id,
                learning_session.course_id,
                learning_session.target_knowledge_node_id,
                learning_session.practice_assessment_id is None,
            )

    def _read_after_conflict(self, session_id: int, user_id: int, cause: IntegrityError) -> PracticeRead:
        with self.session.begin():
            learning_session = self._require_owned(session_id, user_id)
            task = self._practice_task(learning_session)
            assessment = self._practice_assessment(learning_session, user_id)
            if assessment is not None:
                return self._read(learning_session, assessment, task, reused=True)
        raise AdaptivePracticeError(
            "PRACTICE_STATE_CONFLICT",
            "Practice changed concurrently; retry the request.",
        ) from cause

    def _replay_answer(
        self,
        session_id: int,
        assessment_question_id: int,
        payload: PracticeAnswerCreate,
        cause: IntegrityError,
    ) -> PracticeRead:
        with self.session.begin():
            user_id = self._owner_id()
            learning_session = self._require_owned(session_id, user_id)
            task = self._practice_task(learning_session)
            assessment = self._practice_assessment(learning_session, user_id)
            if assessment is not None:
                question = next(
                    (item for item in assessment.questions if item.id == assessment_question_id),
                    None,
                )
                if question is not None and question.response is not None:
                    if question.response.answer_payload == payload.model_dump(mode="json"):
                        return self._read(learning_session, assessment, task, reused=True)
                    raise AdaptivePracticeError(
                        "PRACTICE_RESPONSE_LOCKED",
                        "A submitted practice answer cannot be changed.",
                    ) from cause
        raise AdaptivePracticeError(
            "PRACTICE_STATE_CONFLICT",
            "Practice changed concurrently; retry the request.",
        ) from cause

    def _practice_assessment(
        self,
        learning_session: LearningSession,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> Assessment | None:
        if learning_session.practice_assessment_id is None:
            return None
        assessment = self.assessments.get_for_owner(
            learning_session.practice_assessment_id,
            user_id,
            load_history=True,
            for_update=for_update,
        )
        if (
            assessment is None
            or assessment.course_id != learning_session.course_id
            or assessment.assessment_type != AssessmentType.PRACTICE
        ):
            raise AdaptivePracticeError("PRACTICE_SCOPE_INVALID", "Practice state is outside this Session.")
        return assessment

    def _select_question(
        self,
        *,
        owner_id: int,
        course_id: int,
        node_id: int,
        desired: QuestionDifficulty,
        excluded: set[int],
    ):
        candidates = [
            item
            for item in self.questions.list_for_primary_node(course_id, node_id)
            if item.validation_status == QuestionValidationStatus.VALIDATED
            and item.question_type in SUPPORTED_TYPES
            and item.id not in excluded
        ]
        exposure = self.assessments.question_exposure_counts(
            owner_id=owner_id,
            question_ids=[item.id for item in candidates],
        )
        bucket = {difficulty: index for index, difficulty in enumerate(DIFFICULTY_FALLBACK[desired])}
        return min(
            candidates,
            key=lambda item: (bucket[item.difficulty], exposure.get(item.id, 0), item.id),
            default=None,
        )

    def _owner_id(self) -> int:
        owner = self.users.get_by_email(self.settings.legacy_bootstrap_user)
        if owner is None:
            raise AdaptivePracticeError("SESSION_NOT_FOUND", "Learning session not found.")
        return owner.id

    def _require_owned(self, session_id: int, user_id: int, *, for_update: bool = False) -> LearningSession:
        learning_session = self.sessions.get_owned(session_id=session_id, user_id=user_id, for_update=for_update)
        if learning_session is None:
            raise AdaptivePracticeError("SESSION_NOT_FOUND", "Learning session not found.")
        return learning_session

    def _require_practice_ready(self, learning_session: LearningSession) -> LearningSessionTaskState:
        if learning_session.status not in {LearningSessionStatus.CREATED, LearningSessionStatus.IN_PROGRESS}:
            raise AdaptivePracticeError("SESSION_NOT_WRITABLE", "This learning session is read-only.")
        if not learning_session.target_knowledge_node.is_active:
            raise AdaptivePracticeError("KNOWLEDGE_NODE_INACTIVE", "The learning target is no longer available.")
        task = self._practice_task(learning_session)
        if any(
            previous.status != LearningSessionTaskStatus.COMPLETED
            for previous in learning_session.tasks
            if previous.order_index < task.order_index
        ):
            raise AdaptivePracticeError("PRACTICE_NOT_READY", "Complete earlier learning phases first.")
        return task

    @staticmethod
    def _practice_task(learning_session: LearningSession) -> LearningSessionTaskState:
        task = next(
            (item for item in learning_session.tasks if item.phase == LearningSessionTaskPhase.ADAPTIVE_PRACTICE),
            None,
        )
        if task is None:
            raise AdaptivePracticeError("SESSION_TASK_NOT_FOUND", "Adaptive practice task not found.")
        return task

    @staticmethod
    def _start_task(learning_session: LearningSession, task: LearningSessionTaskState) -> None:
        now = datetime.now(timezone.utc)
        task.status = LearningSessionTaskStatus.IN_PROGRESS
        task.started_at = task.started_at or now
        if learning_session.status == LearningSessionStatus.CREATED:
            learning_session.status = LearningSessionStatus.IN_PROGRESS
            learning_session.started_at = learning_session.started_at or now

    @staticmethod
    def _set_progress(
        task: LearningSessionTaskState,
        difficulty: QuestionDifficulty,
        *,
        answered_count: int,
        bank_exhausted: bool,
    ) -> None:
        task.progress = {
            "answered_count": answered_count,
            "max_questions": MAX_PRACTICE_QUESTIONS,
            "current_difficulty": difficulty.value,
            "bank_exhausted": bank_exhausted,
        }

    @staticmethod
    def _complete_practice(assessment: Assessment, task: LearningSessionTaskState) -> None:
        now = datetime.now(timezone.utc)
        assessment.status = AssessmentStatus.SUBMITTED
        assessment.submitted_at = assessment.submitted_at or now
        task.status = LearningSessionTaskStatus.COMPLETED
        task.completed_at = task.completed_at or now
        task.progress = {**task.progress, "completed": True}

    @staticmethod
    def _read(
        learning_session: LearningSession,
        assessment: Assessment,
        task: LearningSessionTaskState,
        *,
        reused: bool = False,
    ) -> PracticeRead:
        try:
            pairs = _submitted_pairs(assessment)
            attempts = [_attempt_read(question, response) for question, response in pairs]
            current = _current_unanswered(assessment)
            completed = assessment.status == AssessmentStatus.SUBMITTED
            bank_empty = bool(task.progress.get("bank_exhausted")) and not attempts and current is None
            correct = sum(item.is_correct for item in attempts)
            summary = None
            if completed:
                accuracy = (Decimal(correct) / Decimal(len(attempts))).quantize(Decimal("0.01"))
                summary = PracticeSummaryRead(
                    answered_count=len(attempts),
                    correct_count=correct,
                    accuracy=accuracy,
                )
            return PracticeRead(
                session_id=learning_session.id,
                knowledge_node_id=learning_session.target_knowledge_node_id,
                assessment_id=assessment.id,
                status="completed" if completed else "question_bank_empty" if bank_empty else "in_progress",
                current_difficulty=(
                    AssessmentQuestionSnapshotSchema.model_validate(current.question_snapshot).difficulty
                    if current is not None
                    else _stored_difficulty(task)
                ),
                current_question=_question_read(current) if current is not None else None,
                answered_count=len(attempts),
                max_questions=MAX_PRACTICE_QUESTIONS,
                attempts=attempts,
                summary=summary,
                reused=reused,
            )
        except ValidationError as error:
            raise AdaptivePracticeError("QUESTION_SNAPSHOT_INVALID", "Stored practice question is invalid.") from error


def _initial_difficulty(mastery: KnowledgeNodeMasteryReadSchema | None) -> QuestionDifficulty:
    if mastery is None or mastery.calculation_state != KnowledgeStateAvailability.CALCULATED:
        return QuestionDifficulty.MEDIUM
    if mastery.confidence_level in {ConfidenceLevel.INSUFFICIENT, ConfidenceLevel.LOW}:
        return QuestionDifficulty.EASY
    if mastery.mastery_status in {MasteryStatus.NEEDS_ATTENTION, MasteryStatus.POSSIBLY_WEAK}:
        return QuestionDifficulty.EASY
    if mastery.mastery_status == MasteryStatus.GOOD_PERFORMANCE:
        return QuestionDifficulty.HARD
    return QuestionDifficulty.MEDIUM


def _stored_difficulty(task: LearningSessionTaskState) -> QuestionDifficulty:
    raw = task.progress.get("current_difficulty", QuestionDifficulty.MEDIUM.value)
    try:
        return QuestionDifficulty(str(raw))
    except ValueError:
        return QuestionDifficulty.MEDIUM


def _submitted_pairs(assessment: Assessment) -> list[tuple[AssessmentQuestion, Response]]:
    return [
        (item, item.response)
        for item in sorted(assessment.questions, key=lambda row: (row.order_index, row.id or 0))
        if item.response is not None and item.response.submitted_at is not None
    ]


def _current_unanswered(assessment: Assessment) -> AssessmentQuestion | None:
    return next(
        (
            item
            for item in sorted(assessment.questions, key=lambda row: (row.order_index, row.id or 0))
            if item.response is None
        ),
        None,
    )


def _next_difficulty(attempts: list[tuple[AssessmentQuestion, Response]]) -> QuestionDifficulty:
    last_snapshot = AssessmentQuestionSnapshotSchema.model_validate(attempts[-1][0].question_snapshot)
    current_index = DIFFICULTY_ORDER.index(last_snapshot.difficulty)
    if len(attempts) >= 2 and all(response.is_correct is True for _, response in attempts[-2:]):
        return DIFFICULTY_ORDER[min(current_index + 1, len(DIFFICULTY_ORDER) - 1)]
    if len(attempts) >= 2 and all(response.is_correct is False for _, response in attempts[-2:]):
        return DIFFICULTY_ORDER[max(current_index - 1, 0)]
    return last_snapshot.difficulty


def _question_read(question: AssessmentQuestion) -> PracticeQuestionRead:
    snapshot = AssessmentQuestionSnapshotSchema.model_validate(question.question_snapshot)
    return PracticeQuestionRead(
        assessment_question_id=question.id,
        question_id=snapshot.source_question_id,
        question_number=question.order_index + 1,
        question_type=snapshot.question_type,
        stem=snapshot.stem,
        options=snapshot.options,
        difficulty=snapshot.difficulty,
    )


def _attempt_read(question: AssessmentQuestion, response: Response) -> PracticeAttemptRead:
    snapshot = AssessmentQuestionSnapshotSchema.model_validate(question.question_snapshot)
    return PracticeAttemptRead(
        attempt_id=response.id,
        assessment_question_id=question.id,
        question_id=snapshot.source_question_id,
        question_number=question.order_index + 1,
        question_type=snapshot.question_type,
        stem=snapshot.stem,
        options=snapshot.options,
        selected_options=list(response.answer_payload.get("selected_options", [])),
        correct_answer=snapshot.correct_answer,
        explanation=snapshot.explanation,
        difficulty=snapshot.difficulty,
        is_correct=response.is_correct is True,
        points_awarded=Decimal(response.points_awarded or 0),
        source_refs=snapshot.source_refs,
        submitted_at=response.submitted_at,
    )


def get_adaptive_practice_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> AdaptivePracticeService:
    return AdaptivePracticeService(session, settings)


__all__ = [
    "AdaptivePracticeError",
    "AdaptivePracticeService",
    "MAX_PRACTICE_QUESTIONS",
    "get_adaptive_practice_service",
]
