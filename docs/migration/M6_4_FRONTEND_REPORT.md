# LearnPilot V1 — M6-4 Frontend Integration Report

## Scope and reused API

M6-4 integrates the existing M6-3 learning-plan API without changing recommendation,
mastery, evidence, or plan-generation behavior:

- `GET /api/courses/{course_id}/learning-plan` reads the current plan.
- `POST /api/courses/{course_id}/learning-plan/generate` is called only after an
  explicit user action.
- `GET /api/courses/{course_id}/knowledge-model` resolves the real target and
  prerequisite node names and reuses the existing knowledge-map node identity.

The frontend uses the established Axios client and does not calculate priority,
prerequisite satisfaction, mastery, or task content.

## Implementation

- Added strict TypeScript contracts matching M6-3's availability, recommendation,
  plan, task, score-breakdown, and prerequisite-evidence schemas.
- Added a shared `useLearningPlan` state machine with `IDLE`, `LOADING`, `AVAILABLE`,
  `STALE`, `UNAVAILABLE`, and `ERROR` view states.
- Dashboard now shows the real target, reason, task count, and optional summed
  template estimate for the selected course.
- Learn now shows one target, structured reasons, direct prerequisite evidence,
  and the server-provided tasks in order. Tasks remain read-only plan descriptions.
- `STALE` is a normal business state. It never triggers automatic generation;
  regeneration is guarded against duplicate submissions and retains the stale
  state when the request fails.
- Course changes invalidate in-flight responses so an older request cannot replace
  the newly selected course's state.
- Unavailable guidance is selected only from backend status/error codes. Diagnostic
  guidance links to the existing Diagnose page and carries the selected course.
- The existing knowledge-map route is reused with the exact recommended node ID:
  `course-detail?tab=knowledge-structure&nodeId={target_node_id}`.

## Explicit boundaries

M6-4 does not add task completion controls, check-ins, completion percentages,
Learning Sessions, evidence writes, mastery updates, frontend scoring, or a second
recommendation implementation. It does not add a global store or a new visual
dependency.

## Files changed for M6-4

- `frontend/src/types/learningPlan.ts`
- `frontend/src/services/learningPlans.ts`
- `frontend/src/components/learning/planPresentation.ts`
- `frontend/src/composables/useLearningPlan.ts`
- `frontend/src/views/DashboardView.vue`
- `frontend/src/views/LearnView.vue`
- `frontend/src/views/DiagnoseView.vue`
- `frontend/src/tests/learning-plan-state.spec.ts`
- `frontend/src/tests/learning-plan-views.spec.ts`
- `frontend/src/tests/diagnose-view.spec.ts`
- `docs/migration/M6_4_FRONTEND_REPORT.md`

## Verification

- Frontend tests: `116/116` passed (`22/22` files).
- Frontend typecheck: passed.
- Frontend ESLint: passed with zero warnings.
- Frontend production build: passed. The existing non-blocking chunk-size warning
  remains.
- Backend regression: `335/335` passed.
- Backend Ruff lint: passed.
- Backend Ruff format check: passed (`172` files already formatted).
- Git whitespace check: passed before this report and is repeated at final handoff.

Browser verification was attempted using the installed Playwright workflow and the
application browser. The environment had no Chromium distribution available and
the application browser runtime exited unexpectedly on repeated initialization,
so browser verification is recorded as **NOT AVAILABLE**, not as a fabricated pass.
The state transitions and interaction boundaries are covered by deterministic
Vue Test Utils tests.

## Known limitations and M6-5 entry

- Personalized time prediction is not implemented; only M6-3 template estimates
  are displayed and are labelled as estimates.
- Knowledge-map integration is intentionally limited to exact node focus through
  the existing route; the graph renderer was not redesigned.
- Browser visual review should be repeated when a browser runtime is available.

All code-level M6-4 acceptance checks pass. M6-5 is ready, subject to the recorded
browser-environment limitation and user approval.
