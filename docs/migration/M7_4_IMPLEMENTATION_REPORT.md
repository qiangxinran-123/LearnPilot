# LearnPilot V1 — M7-4 Implementation Report

## 1. Objective and scope

M7-4 adds deterministic adaptive practice to the existing Learning Session. It reuses M4 questions, assessment
question snapshots, responses and objective scoring; M5 mastery is read only and is used only to choose the initial
difficulty. The implementation does not create LearningEvidence, update Mastery, recompute Recommendation or mark a
LearningSession complete. Those closed-loop operations remain owned by M7-5.

## 2. Actual files

Backend additions/changes:

- `backend/app/models/diagnostic.py`
- `backend/app/repositories/assessment_repository.py`
- `backend/app/repositories/response_repository.py`
- `backend/app/schemas/practice.py`
- `backend/app/schemas/tutor.py`
- `backend/app/services/adaptive_practice_service.py`
- `backend/app/services/tutor_service.py`
- `backend/app/api/learning_sessions.py`
- `backend/alembic/versions/0017_m7_4_practice_assessment.py`
- `backend/tests/test_m7_4_adaptive_practice.py`

Frontend additions/changes:

- `frontend/src/types/learningSession.ts`
- `frontend/src/services/learningSessions.ts`
- `frontend/src/composables/useAdaptivePractice.ts`
- `frontend/src/components/learning/PracticePanel.vue`
- `frontend/src/components/learning/TutorPanel.vue`
- `frontend/src/views/LearningSessionView.vue`
- `frontend/src/tests/practice-panel.spec.ts`
- `frontend/src/tests/learning-session-view.spec.ts`

## 3. Reused capabilities

- M3: the Session's server-derived Course and primary KnowledgeNode define the question boundary.
- M4: `Question`, `QuestionKnowledgeNode`, `Assessment`, `AssessmentQuestion`, `Response`,
  `DiagnosticDomainService.build_question_snapshot` and `DeterministicObjectiveScorer` are reused directly.
- M5: `MasteryReadService.node_mastery` supplies an optional initial difficulty signal without any write operation.
- M7-1: Session ownership, state, ordered task persistence and `practice_assessment_id` are reused.
- M7-3: Tutor uses a redacted current-question context before submission and an answer-aware context after submission.

No `PracticeAttempt` entity or second question/response system was introduced. A submitted M4 `Response` is the
durable practice attempt and its ID is the stable attempt identifier for M7-5.

## 4. Data model and migration

Migration `0017_m7_4_practice_assessment.py` extends the existing `AssessmentType` database constraint with
`practice`. It creates no table, copies no question data and changes no M4 scoring field. `LearningSession` continues
to reference the one practice Assessment through the M7-1 `practice_assessment_id` field.

The migration test upgrades a populated schema at revision 0016 to head, verifies the existing Assessment survives,
and verifies that a practice Assessment is accepted. A separate fresh-database upgrade through 0017 also passed.

## 5. Adaptive selection policy

The service admits only validated, active single-choice, multiple-choice and true/false questions owned by the
configured user, attached to the Session Course and linked to the Session's primary KnowledgeNode. Selection is
stable and deterministic:

1. Missing or stale mastery starts at medium; low/needs-attention starts at easy; good mastery starts at hard.
2. Two consecutive correct answers raise difficulty by one level.
3. Two consecutive incorrect answers lower difficulty by one level.
4. If the requested level is unavailable, selection falls back to the nearest level in a fixed order.
5. Questions already used in the Session are excluded. Remaining candidates prefer lower prior exposure, then ID.
6. A Session contains at most five submitted questions. If the bank is exhausted after at least one answer, the
   practice task completes with an explicit `bank_exhausted` summary; an initially empty bank remains an explicit
   empty state.

The policy is intentionally lightweight. It adds no IRT, reinforcement learning, random ranking or LLM-generated
questions.

## 6. API contract

Two frozen Session-scoped endpoints are implemented in `backend/app/api/learning_sessions.py`:

- `POST /api/learning/sessions/{session_id}/practice/next` starts or resumes practice and returns the current
  unanswered question, the last result or the final/empty summary.
- `PUT /api/learning/sessions/{session_id}/practice/responses/{assessment_question_id}` validates and stores one
  answer, applies M4 deterministic scoring and returns the updated practice state.

The client never supplies Course or KnowledgeNode identity. The service derives both from the owned Session and
validates Assessment ownership and Course equality. Correct answers and explanations are omitted from unanswered
question payloads. Errors use stable business codes for ownership/not-found, phase readiness, missing answer, stale
question, locked response, completion and concurrent state conflicts.

## 7. Persistence, recovery and idempotency

The current AssessmentQuestion snapshot, submitted Responses and task progress metadata are database-backed. A page
reload or re-entry returns the same unanswered question rather than selecting another one. Repeating `next` is
side-effect free once a current question exists. Repeating an identical answer returns the stored response; a changed
answer is rejected and cannot overwrite the original score.

Session/Assessment rows are selected with update-lock intent where supported. The existing unique Response identity
is the final duplicate-write guard. Integrity conflicts replay the committed state when possible; database lock
conflicts return a retryable practice-state conflict. Frontend pending guards improve interaction but are not the
idempotency mechanism.

Completing the five-question flow submits the practice Assessment and completes only the Adaptive Practice task. The
LearningSession remains `IN_PROGRESS`, so M7-4 cannot bypass M7-5's verified completion transaction.

## 8. Tutor integration and answer protection

Before a practice answer is submitted, Tutor context contains only the question stem, options, type and difficulty.
The correct answer and explanation are absent, and full/step-by-step modes are rejected to prevent answer leakage.
After submission, the persisted selected answer, correct answer, explanation and correctness may be included for
remediation. The prompt explicitly forbids revealing an answer early or submitting an answer for the learner.

The practice panel exposes a Hint entry before submission and a Step-by-step explanation entry after an incorrect
submission. Both reuse the existing M7-3 Tutor panel; no second chat or Provider path was created.

## 9. Frontend changes

- `PracticePanel.vue` renders start/resume, three objective question types, validation, submission feedback, source
  references, next-question flow, empty/error/retry states and a factual completion summary.
- `useAdaptivePractice.ts` keeps the backend authoritative, blocks duplicate pending actions and ignores stale
  responses after a Session switch.
- `learningSessions.ts` and `learningSession.ts` contain typed API methods and response contracts.
- `LearningSessionView.vue` places practice in the existing ordered task workspace and refreshes the Session after
  server-side task transitions.
- `TutorPanel.vue` exposes the existing message composer for the answer-safe practice Tutor entry.

The existing Calm Academic Intelligence tokens and responsive reading/Tutor layout are preserved. No navigation,
design system, mastery visualization or fabricated practice result was added.

## 10. M7-5 handoff contract

M7-5 can consume the existing persisted records without schema duplication:

- Session, Course and primary KnowledgeNode: `LearningSession`.
- Practice container and lifecycle: `Assessment` with type `practice`.
- Question identity, difficulty and immutable grading input: `AssessmentQuestion.question_snapshot`.
- Attempt identity and answer/score: `Response.id`, `answer_payload`, `is_correct`, `points_awarded`, timestamps.
- Practice readiness: submitted Assessment plus completed Adaptive Practice task.

M7-5 must create idempotent LearningEvidence, update Mastery, complete the Session and refresh Recommendation. None of
those operations occur in M7-4.

## 11. Verification

- Backend M7-4 focused tests: **9/9 passed**.
- Backend direct-dependency regression: **46/46 passed** (M4 scoring, M7-1 Session and M7-3 Tutor).
- Backend distinct targeted total: **55/55 passed**.
- Frontend focused tests: **25/25 passed** across practice panel, Session workspace and Tutor state/panel.
- TypeScript typecheck: **PASS**.
- ESLint: **PASS** after removing one unused test import.
- Ruff check: **PASS**; Ruff format check: **PASS** for all M7-4 backend files.
- Alembic populated upgrade and fresh-database upgrade: **PASS**; head is `0017_m7_4_practice`.
- Production build: **PASS**; the existing Vite chunk-size advisory remains non-failing.
- Full regression: **deferred to M7-6 at the user's request**; no already-passed targeted suite was repeated during
  finalization.
- Real DeepSeek: **not rerun**. M7-4 tests use the existing deterministic/mock Tutor boundary and make no paid call.
- Browser automation: **not run**. Component interaction tests cover the M7-4 states; a human visual pass remains in
  the acceptance checklist below.

## 12. Human acceptance checklist

1. Open a real recommendation and resume its Learning Session.
2. Complete Concept Learning and Guided Example if they are not already complete.
3. Start Adaptive Practice and verify Course/KnowledgeNode context and source reference.
4. Submit each supported objective question type and verify immediate deterministic feedback.
5. Verify an unanswered question offers Tutor Hint without exposing the answer.
6. Refresh on an unanswered question and confirm the same question is restored.
7. Submit two correct answers and two incorrect answers in prepared fixtures and verify bounded difficulty changes.
8. Repeat the same answer request and verify no duplicate Response; try a changed answer and verify rejection.
9. Complete or exhaust the five-question flow and verify only the practice task completes while Session remains in
   progress.
10. Confirm LearningEvidence, Mastery and Recommendation data are unchanged.

## 13. Known limitations and deferred work

- Only questions directly linked as primary to the Session target KnowledgeNode are eligible; broader prerequisite
  or related-node selection is intentionally outside M7-4.
- Practice is capped at five questions and uses three fixed difficulty levels.
- HTTP route behavior is exercised through the typed service boundary because the current environment does not have
  the optional FastAPI TestClient dependency; no dependency was installed solely for this stage.
- Final browser visual verification and the complete M0–M7 regression are deferred to M7-6.
- Evidence creation, Mastery update, Session completion, recommendation refresh and learning summary belong to
  M7-5.

## 14. M7-5 readiness

There is no blocking M7-4 architecture decision. Stable persisted attempts, deterministic scores, explicit practice
completion and server-side idempotency are available for the M7-5 closed-loop transaction. M7-5 is ready to begin
after human acceptance of this stage.
