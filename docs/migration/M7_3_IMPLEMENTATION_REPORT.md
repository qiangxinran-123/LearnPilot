# LearnPilot V1 — M7-3 Implementation Report

## 1. Objective

M7-3 adds a context-aware AI Tutor inside the existing Learning Session. It reuses M2's OpenAI-compatible Provider,
M5's read-only mastery view, M7-1 Session state and M7-2 traceable retrieval. It does not implement practice,
scoring, LearningEvidence, Mastery refresh or recommendation refresh.

## 2. Actual changes

Backend additions:

- `models/tutor.py`, `db/models/tutor_message.py`: five teaching strategies and the minimal Session message entity.
- `repositories/tutor_message_repository.py`: stable Session history, recent context and idempotency lookups.
- `schemas/tutor.py`: typed request, context, structured provider output, citations, messages and exchanges.
- `services/tutor_service.py`: trusted context assembly, prompt policy, Provider call, citation allow-list validation,
  message persistence and replay.
- `api/learning_sessions.py`: Session-scoped Tutor GET/POST endpoints and consistent AI/business error mapping.
- `ai/client.py`: explicit mock support for the new structured Tutor schema; real Provider behavior is unchanged.
- `0016_m7_3_tutor_messages.py`: the single minimal migration.
- `scripts/m7_3_provider_smoke.py`: isolated four-scenario real Provider verification using a temporary database.
- `tests/test_m7_3_tutor.py`: 17 focused backend/service/API/migration tests.

Frontend additions:

- `TutorPanel.vue`: Session-local chat, five mode controls, citations, empty/loading/error/retry/read-only states.
- `useTutor.ts`: history restoration, duplicate-send guard, stable retry key and stale-response protection.
- typed Tutor contracts and API calls in the existing Learning Session service/type modules.
- Session workspace expanded to a responsive reading + Tutor layout, without adding navigation.
- `tutor-panel.spec.ts` and `tutor-state.spec.ts`, plus Session-view regression updates.

## 3. Tutor Context and Teaching Policy

The backend derives all identity from `session_id`. It verifies configured-user ownership, Course ownership,
Course/KnowledgeNode ancestry, active target and writable Session state before calling the Provider. Context includes
the learning goal, current persisted task, M5 mastery availability/status/confidence, M7-2 cited segments and at most
eight recent messages. M7-4 question context remains absent rather than fabricated.

The supported modes are `hint`, `guided_question`, `example`, `step_by_step_explanation` and
`full_explanation`. Guided questioning is the default. Hint explicitly forbids complete answers; full explanation
explicitly permits one. One shared prompt template applies strategy-specific rules—there are no Agent variants.

## 4. Retrieval, prompt and structured output

Tutor calls `LearningContentService` with the current question and never performs its own retrieval. Exact
material/reference/hash identities form the citation allow-list. Unknown and cross-course references cause
`TUTOR_INVALID_CITATION` before any message is saved. When no validated citation is returned, the reply is marked
`insufficient_evidence` and the UI identifies it as general guidance.

System teaching rules, server context, untrusted source blocks, recent history and the current user question are
separate messages. The prompt says document instructions are data, not commands. Source context is capped at 55% of
`llm_context_chars`, history at 20%, and output is Pydantic-validated for answer, mode, citations and evidence state.
Timeout, retry, rate-limit, provider and invalid-output behavior remain owned by the M2 Provider Adapter; failures
are never silently replaced by mock output.

## 5. Persistence and idempotency

Migration `0016_m7_3_tutor_messages` stores user/assistant messages by Session and exchange, with an optional current
task reference. User rows own the unique `(session_id, idempotency_key)` identity. Repeating a completed request
returns the same pair without calling the Provider again. The frontend disables sending while pending and reuses the
same key for explicit retry. History is ordered by creation time and ID and never crosses Sessions.

A successful first Tutor exchange performs the already-frozen `CREATED → IN_PROGRESS` transition. Provider or
validation failure persists neither messages nor state changes. Completed/cancelled Sessions remain history-readable
but reject new messages.

## 6. Frontend interaction

Desktop layout keeps learning material as the wider primary column and places Tutor in a sticky auxiliary panel;
below 960px it stacks vertically. Messages use restrained role contrast, long content remains readable, citations
open the existing Material route, and the five mode labels use natural Chinese. Network errors keep the draft and
offer one “重试” action for either a failed history load or a failed send. A successful send retry clears the draft.
Switching Session clears the prior conversation immediately and ignores late history and Tutor responses.

## 7. Verification

- Backend focused M7-3: **17 passed**.
- Backend full regression: **394 passed** in 246.95 seconds.
- Frontend focused Tutor/Session: **18 passed** after the final stale-response and retry review.
- Frontend full regression: **163 passed** in 27 files before the two final focused regression cases were added;
  the affected three files were then rerun as the 18-test focused gate instead of repeating the full suite.
- TypeScript: **PASS**.
- ESLint: **PASS**.
- Production build: **PASS**. Existing Vite chunk-size advisory is non-failing.
- Ruff check: **PASS**; Ruff format check: **PASS** (193 files already formatted).
- Alembic: **PASS**. A populated M7-2 database upgraded without data loss, an empty database upgraded through the
  entire chain, and the single head is `0016_m7_3_tutor_messages`.
- Real DeepSeek: **PASS** for hint, full explanation with valid PDF citation, insufficient evidence with no invented
  citation, and different-Course Session isolation. Four calls used a temporary database; no key was printed.
- Git diff check: **PASS**. Branch remains `main` at `6e7bda3`; no commit, push, switch, `.env`, lock file or
  dependency-manifest change occurred, and all pre-existing M7 work remains present.
- Secret scan: **PASS** for M7-3 code, tests, migration, smoke tool and documents; no key/token/private-key pattern
  was found.

## 8. Compatibility

- M4 Question and deterministic scoring: unchanged and full regression passes.
- M5 Evidence/Mastery: no Tutor Evidence type or refresh call; zero-side-effect test passes.
- M6 Recommendation: no generate/recompute call; row-count side-effect test passes.
- M7-1 Session: ownership, state and recovery continue to pass; only the frozen first-write transition is used.
- M7-2 Retrieval: reused directly; provenance, scope and existing tests pass.

## 9. Open items

### BLOCKER

None.

### NON-BLOCKING

- A final human browser pass should visually confirm sticky-panel height and mobile stacking with representative
  long replies. Automated component and production-build gates pass.
- The existing bundle-size advisory and existing diagnostic-test Vue warnings remain unrelated to M7-3.

### DEFERRED

- Practice-question redaction and answer-aware Tutor behavior belong to M7-4.
- Tutor messages intentionally never contribute LearningEvidence or Mastery; closed-loop integration belongs to
  M7-5.
