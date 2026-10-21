# LearnPilot V1 — M4-D Implementation Report

## Outcome

M4-D is complete. LearnPilot now provides a safe diagnostic frontend from real-course readiness through persistent
answering, deterministic submission, basic completion feedback, and history. Project progress is 50%.

## Actual Changes

### Backend

- `backend/app/api/diagnostics.py`: thin diagnostic HTTP router and stable error mapping.
- `backend/app/api/routes.py`: registers the new router.
- `backend/app/schemas/diagnostic_api.py`: readiness, safe paper, saved-response, history, and result DTOs.
- `backend/app/schemas/assessment_scoring.py`: side-effect-free readiness contract.
- `backend/app/services/diagnostic_experience_service.py`: demo-owner application boundary, start/resume, safe reads,
  history, save, submit, and result orchestration.
- `backend/app/services/assessment_assembly_service.py`: read-only readiness preview and reusable loaded-snapshot DTO
  conversion; the assembly algorithm is unchanged.
- `backend/app/services/diagnostic_domain_service.py`: minimal M4-D compatibility extension that materializes
  unanswered questions as empty structured Responses during a bodyless server-truth submission.
- `backend/tests/test_m4d_diagnostic_api.py`: seven real-ASGI HTTP boundary tests.

### Frontend

- `frontend/src/types/diagnostic.ts` and `frontend/src/services/diagnostics.ts`: typed API contract.
- `frontend/src/services/http.ts`: typed PUT support.
- `frontend/src/composables/useDiagnosticAssessment.ts`: restore, navigation, per-question serialized autosave,
  submission flush, failure retry, and timeout reconciliation.
- `frontend/src/views/DiagnoseView.vue`: course/readiness/start-resume/history experience.
- `frontend/src/views/DiagnosticAssessmentView.vue`: three objective question interactions, navigation, save states,
  confirmation, submission loading, and basic score completion state.
- `frontend/src/router/index.ts`: fixed-assessment route.
- Three focused test files with ten M4-D tests.

## API and Security Verification

The server candidate payload excludes correct answer, explanation, source evidence, scoring policy, correctness, and
points. Ownership is enforced for readiness, paper reads, response writes, submission, result, and history. A response
cannot target a snapshot outside its Assessment. Submitted writes return a conflict. Invalid and foreign identifiers
return safe API errors.

## Autosave, Recovery, and Submission

Autosave is serialized per question and revision-aware. Tests prove a delayed old request cannot become the final
confirmed state. Failed saves do not display “saved.” Refresh restores server answers. Submission disables editing,
waits for every pending write, rejects local failed saves, and uses only the server-stored answer set. Unanswered items
are persisted as empty `objective_answer_v1` records and receive deterministic zero through M4-C. Timeout recovery
checks server state before offering retry.

## Regression and Quality Results

- M4-D focused frontend tests: **10/10 passed**.
- M4-D backend HTTP boundary tests: **7/7 passed**.
- Complete frontend Vitest suite: **97/97 passed**.
- Complete backend pytest suite: **229/229 passed** in 185.77 seconds.
- TypeScript typecheck: **PASS**.
- ESLint: **PASS**.
- Frontend production build: **PASS** (existing large-chunk advisory only).
- Ruff lint and format: **PASS**.
- Alembic: **NOT CHANGED**; M4-A head `0008_m4a_diagnostic_domain` remains sufficient.
- Git diff check: **PASS**.

An isolated `/tmp` SQLite database was migrated and seeded for browser validation without touching user data. The local
backend and Vite servers started successfully, but Playwright navigation was blocked by the workstation proxy routing
for isolated localhost ports. The manual browser flow is therefore recorded as **BLOCKED / NOT PASSED**, not silently
reported as successful. It is not a mandatory M4-D acceptance item; real HTTP and frontend automated coverage passed.

## Architecture Preservation

- **ARCH-01 preserved:** no frontend scorer exists; submit invokes M4-C deterministic scoring and renders its persisted
  result.
- **ARCH-02 preserved:** paper/recovery/history read immutable snapshots and persisted results, never current bank
  content.
- **ARCH-03 preserved:** answers are structured, owner-scoped, flushed before submission, atomically scored/locked,
  idempotent on repeat submission, and rejected after submission.

## Scope Confirmation

No M4-E knowledge report, weak-node analysis, explanation report, or knowledge-map integration was implemented. No
M4-F end-to-end product expansion and no M5 LearningEvidence, Mastery, Confidence, Recommendation, or Learning Path
model was created.

## Known Limitations

- The project still uses the established demo-user ownership foundation rather than full authentication.
- Readiness time is a transparent estimate derived from the actual predicted question count, not an observed personal
  completion-time model.
- Aggregate history is intentionally not a progress trend or knowledge-level report.
- Concurrent create requests from separate processes are not protected by a distributed idempotency key; ordinary
  sequential HTTP retries safely reuse an unfinished attempt.
