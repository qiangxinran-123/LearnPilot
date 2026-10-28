# LearnPilot V1 — M7-5 Implementation Report

## Initial review and source weight decision

The targeted contract review identified an M5 source-weight decision. On 2026-10-28 the project owner chose
the existing diagnostic weight 1.0 for the new practice source; the diagnostic weight and calculation remain unchanged.

## Evidence

- The frozen `docs/architecture/M7_INTEGRATION_DESIGN.md` section 9 requires a distinct
  `EvidenceSourceType.PRACTICE` and preserves snapshot node links, persisted scores, difficulty and attribution.
- `backend/app/models/evidence.py` currently defines only `DIAGNOSTIC`.
- `backend/app/services/mastery_config.py` configures only `DIAGNOSTIC: Decimal("1.0")` in `source_weights`.
- `backend/app/services/mastery_calculator.py` rejects any evidence source without a configured weight with
  `UNSUPPORTED_EVIDENCE_SOURCE`. Assigning a practice weight changes the set of configured source weights and must
  reconcile the instruction to preserve M5 weights. Labelling practice as diagnostic would misrepresent provenance.
- `backend/app/repositories/learning_evidence_repository.py` currently filters submitted evidence to diagnostic only.
  Both `mastery_read_service.py` and `recommendation_context_service.py` use this filtered data to verify the M5
  fingerprint, so valid practice evidence must also be admitted through that ownership-checked read path; otherwise
  M6 will see the refreshed mastery state as stale.
- `backend/app/services/mastery_service.py` opens its own transaction. The frozen section 10 requires a
  transaction-aware internal entry point so Evidence, Mastery, Session completion and the stored summary commit
  atomically; M6 plan generation remains post-commit and retryable.

## Decision

Practice uses the existing diagnostic weight 1.0. Existing diagnostic weights and the M5 calculation and confidence
formulas remain unchanged.

## Initial worktree

- The current branch is `main`, HEAD `6e7bda3`; existing M7-0 through M7-4 changes remain in the worktree.
- `git diff --check` passed at the start of this pass.

## Implementation and changed files

- `backend/app/models/evidence.py` and `services/mastery_config.py`: add the practice source and authorized 1.0 mapping.
- `backend/alembic/versions/0018_m7_5_practice_evidence.py`: extend the evidence source constraint.
- `services/diagnostic_evidence_ingestion.py`, `learning_evidence_service.py`: reuse M4 snapshot and response
  extraction and M5 validation within a caller-owned transaction; practice evidence writes belong to settlement.
- `repositories/learning_evidence_repository.py`: accept submitted practice evidence only when assessment type,
  ownership and scored response match. M5 and M6 use this shared authorized read boundary.
- `services/mastery_service.py`: transaction-aware entry option without changing the calculation.
- `services/learning_settlement_service.py`, `api/learning_sessions.py`: atomic completion and post-commit M6
  recommendation refresh and recovery. `backend/tests/test_m7_5_settlement.py` verifies the direct chain.
- `frontend/src/types/learningSession.ts`, `services/learningSessions.ts`, `views/LearningSessionView.vue`,
  `components/learning/LearningSummary.vue`: typed summary, API and Session display.
- `frontend/src/tests/learning-summary.spec.ts` and `learning-session-view.spec.ts`: display and recovery tests.

## Practice to Evidence

The server obtains the configured user, owned Session, Course, target node and submitted practice Assessment.
Every question snapshot must include the Session target, and every question must have a persisted submitted, scored
Response. The existing extractor maps Assessment, snapshot and Response identities, node links, snapshot difficulty
and scoring version, persisted points/max, equal attribution and original submission time into M5 Evidence. Tutor
messages never become evidence. The existing unique source/snapshot/node/schema key guards each row; conflicting
pre-existing evidence is rejected. The client supplies no scoring values.

## Transaction, idempotency and recovery

The completion endpoint conditionally transitions the Session within one transaction, locks the course where
supported, validates all three completed phases, inserts or reuses evidence, invokes M5 mastery refresh, stores the
before/after result and commits. A pre-commit exception rolls back all changes. Conditional Session update and
database evidence uniqueness protect concurrent completions; a competing request may safely retry a conflict.
Repeating completion returns the saved summary without repeating evidence or mastery writes.

M6 `LearningPlanService.generate` runs after commit. Success stores the real recommendation and reason codes.
Failure records failed refresh while preserving the committed learning result; repeating completion retries only
recommendation. A process interruption after commit leaves a pending refresh that can be retried in the same way.
M6's existing fingerprint and active-slot logic remain responsible for plan reuse and ranking.

## Mastery and API

The existing M5 service refreshes each active node represented by question snapshots. Before comes from the
pre-settlement persisted state only if its fingerprint is current; otherwise it is unavailable. After, confidence
and calculation time come from M5. Scores retain the 0–100 scale; delta is calculated in percentage points only
when both values exist. Insufficient evidence can leave the score unavailable.

`POST /api/learning/sessions/{session_id}/complete` accepts no score payload and returns Session detail with
`completion_summary`: practice totals, per-node mastery before/after/delta/confidence, Evidence IDs and an optional
M6 recommendation. `recommendation_refresh_status` separates pending, failure and success.
`GET /api/learning/sessions/{session_id}` restores the saved summary without recalculation.

## Frontend

The existing Session displays completion, real practice counts and accuracy, comparison bars, neutral increase,
decrease, unchanged and unavailable states, evidence basis, and M6 recommendation with existing reason labels.
Recommendation failure is separate from successful settlement and offers retry. Duplicate clicks are guarded and
refresh reads the saved Session. The frontend-design skill informed the restrained blue/white hierarchy and mobile
layout.

## Verification

- M7-5 focused backend: **7 passed**, including evidence and mastery failure rollback, mismatched target, repeated
  completion, concurrent requests, recommendation failure/retry, isolation, persisted mastery rise/decrease and M6
  reading the updated mastery.
- Direct backend dependencies: **110 passed** for M5 evidence/mastery, M6 recommendation/plans and M7-4 practice;
  M5-D shared-state read regression: **4 passed**. The initial combined run had four new test fixture setup errors
  after import cleanup; the fixture was explicitly re-exported and only the affected M7-5 tests were rerun.
  Distinct targeted backend total: **121 passed**.
- Frontend: **22 distinct targeted tests passed** (5 summary, 11 Session workspace and 6 practice). The synthetic
  retry click emitted a Vue event-validation warning but its assertion passed.
- TypeScript, ESLint, Ruff check and Ruff format: **PASS**. Production build: **PASS** with the existing Vite
  chunk-size advisory.
- Alembic: fresh test databases upgraded through head; the M7-4 populated 0016-to-head migration test passed.
  Single head: `0018_m7_5_practice_evidence`.
- `git diff --check`: **PASS**. Original worktree changes were retained; no commit, push or branch switch.
- Full repository regression is deferred to M7-6 as requested; no real paid LLM call was made.

## M7-6 acceptance

Run full project regression and the browser end-to-end flow using a real course and real practice results; visually
review desktop/mobile summary and verify recommendation recovery. Service and component tests do not replace this
final browser integration acceptance.
