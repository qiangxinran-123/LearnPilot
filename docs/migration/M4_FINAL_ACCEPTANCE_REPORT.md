# LearnPilot V1 — M4 Final Acceptance Report

## Result

M4 is **COMPLETE**. M4-A through M4-E are complete, and M4-F closure was performed with an isolated real HTTP
diagnostic lifecycle and a completed frontend production build. LearnPilot V1 project progress is **53%**; M5 is
ready to begin only on subsequent explicit authorization.

## Closure Evidence

- Backend full regression: JUnit result `232 tests`, `0 failures`, `0 errors`, `0 skipped`.
- Frontend full Vitest: `100 tests` across `19 files` passed. TypeScript and ESLint passed.
- Production build: the current frontend source was copied to an isolated Windows validation directory using its
  existing lockfile and dependencies. `npm.cmd run build` completed with `BUILD_EXIT_CODE=0`; Vite reported
  `✓ built in 7.93s`. Its only output warning was the non-blocking bundle-size warning.
- Alembic head remains `0009_m4e_diagnostic_report_policy`; Ruff check/format and the prior `git diff --check`
  evidence passed.
- M4-F HTTP integration flow: a temporary SQLite database was migrated to head, seeded with an isolated course,
  active knowledge node, and validated question bank, then exercised through a Uvicorn-hosted FastAPI application.
  The focused HTTP module completed with `8 passed`.

## Verified Diagnostic Lifecycle

The HTTP flow checked course readiness, deterministic validated-question assembly, candidate-view answer isolation,
single-choice/true-false/multiple-choice draft persistence, reload recovery, formal submission, deterministic score
and report retrieval, historical report rereads, idempotent repeat submission, and rejection of submitted-answer
updates. Report payloads contained historical question reviews, source references, primary-node performance, limited
evidence/preliminary status fields, and no Mastery or Confidence claim.

Browser navigation was not executed in this workstation session. The final acceptance policy explicitly permits the
equivalent real HTTP flow when browser operation is unavailable; map navigation is therefore recorded as browser
**NOT RUN**, while its exact historical node-id/map-availability contract remains covered by the report integration.

## Architecture Status

ARCH-01 is preserved: the exercised submit path uses the existing M4-C deterministic scorer; no LLM or client score
is accepted.

ARCH-02 is preserved: the report rereads the fixed AssessmentQuestion snapshot, saved score, historical node data,
and source reference data; no current Question or KnowledgeNode content is used to rebuild it.

ARCH-03 is preserved: answers persisted before submission were restored, repeated submission was idempotent, and a
post-submit response mutation was rejected.

## Actual Changes and Defects

No production application code was changed. One focused acceptance regression test was added to
`backend/tests/test_m4d_diagnostic_api.py`; it exercises the already-shipped HTTP path against isolated persistence.
No P0/P1 defect was found. The first test run exposed only an assertion that expected a JSON decimal as a numeric
value; the API correctly serializes it as the schema's decimal string, so the test expectation was corrected.

## Scope Boundary

No M5 model, Evidence Engine, Mastery, Confidence, recommendation, AI Tutor, or M4-F business feature was added.
