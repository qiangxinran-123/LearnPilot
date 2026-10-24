# LearnPilot V1 — M6-UX-FIX-5 Report

## Scope and root cause

FIX-5 keeps the existing M5 mastery/confidence calculation and M6 recommendation formula intact. The blocking condition was in M6 consumption: only `MEDIUM` or `HIGH` confidence mastery could enter the original priority scorer. A small course could therefore complete every currently available diagnostic question, retain honest `LOW` confidence states, and still have no eligible learning-plan target.

The fix adds an explicit learning-plan evidence level to the existing recommendation result:

- `PERSONALIZED`: the original M6 formula and prerequisite resolution, when trustworthy mastery covers at least half of the active course nodes.
- `PRELIMINARY`: submitted evidence exists but confidence or trustworthy-node coverage is limited. A trustworthy scored target is retained when available; otherwise the same engine chooses a safe prerequisite frontier using broad M5 status, graph importance and stable node ID. Unknown mastery is never converted to zero.
- `FOUNDATIONAL`: no submitted diagnostic evidence exists, but a valid knowledge model does. The engine selects a deterministic prerequisite foundation without claiming a personal knowledge gap.

`ALL_MASTERED` and invalid prerequisite contexts remain unavailable. A missing knowledge model remains a domain error and never produces a fabricated route.

## Necessary changes

- `backend/app/models/learning_plan.py`, `backend/app/models/__init__.py`: define and export the three typed plan levels.
- `backend/app/schemas/recommendation.py`, `backend/app/schemas/learning_plan.py`: expose the level and allow honest partial score breakdowns for structural fallback plans.
- `backend/app/services/recommendation_config.py`: centralize the proportional trustworthy-node coverage threshold; no global question-count threshold was added.
- `backend/app/services/recommendation_engine.py`: preserve the original personalized scorer and add deterministic preliminary/foundational fallback inside the same engine.
- `backend/app/services/learning_plan_service.py`: return the plan level, include it in the existing fingerprint, and use level-specific deterministic task wording.
- `frontend/src/types/learningPlan.ts`, `frontend/src/composables/useLearningPlan.ts`: consume the typed backend level while retaining stale-request isolation.
- `frontend/src/components/learning/planPresentation.ts`, `frontend/src/views/LearnView.vue`: show a prominent current-course context, honest level descriptions and explicit generation actions.
- M6 backend tests and learning-plan frontend tests: cover personalized regression, small-course preliminary plans, foundational routes, missing models, prerequisite behavior, idempotency, course switching and stale-response protection.

No database schema change or Alembic migration was required. The level is deterministic recommendation context, participates in the existing context fingerprint and is returned by the API.

## Data and behavior safety

- M5 mastery and confidence formulas were not changed.
- No Learning Evidence, diagnostic history or Mastery rows are created or modified by recommendation or plan generation.
- Preliminary plans use low-confidence state only as a broad, explicitly limited signal.
- Foundational plans use real active nodes and validated prerequisite edges only.
- Existing personalized priority weights, stable ordering, cycle handling, task-count limit, plan reuse and invalidation remain in effect.
- Course switching does not trigger automatic plan generation, and request version checks prevent an old course response from replacing the new course state.

## Verification

- Focused backend M6 tests: `40 passed`.
- Focused frontend learning-plan tests: `14 passed`.
- Full backend regression: `359 passed`.
- Full frontend regression: `143 passed`.
- Ruff lint and format: passed (`174 files already formatted`).
- TypeScript, ESLint and production build: passed. The existing non-blocking Vite chunk-size warning remains.
- `git diff --check`: passed.

## Manual verification

Automated component tests verify course selection, plan-level copy and request isolation. A final visual browser pass with representative `PERSONALIZED`, `PRELIMINARY` and `FOUNDATIONAL` course data is recommended; no real learning data was altered to manufacture those states during automated verification.

## Boundary

This change does not enter M7 and does not modify upload, summary, cards, QA, M3 extraction, M4 diagnostics, FIX-2 draft handling, FIX-3 question preparation, FIX-4 synchronization, M5 algorithms or the global visual system.
