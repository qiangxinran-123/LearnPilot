# LearnPilot V1 — M6-3 Implementation Report

Date: 2026-10-22

## Decision

- Stage: **M6-3 Learning Plan & Task Generation**
- Status: **COMPLETE**
- Migration: **0013_m6_learning_plans**
- Frontend change: **NONE**
- M7 behavior: **NONE**

## Actual changes

| Area | Files | Change |
| --- | --- | --- |
| Domain | `backend/app/models/learning_plan.py`, model exports | plan availability/status and three bounded task types |
| Persistence | `backend/app/db/models/learning_plan.py`, `learning_task.py`, model exports | ownership, target, recommendation snapshot, active-slot uniqueness, ordered task relation |
| Migration | `backend/alembic/versions/0013_m6_learning_plans.py` | creates both tables, foreign keys, checks, indexes, and uniqueness constraints |
| Repository | `backend/app/repositories/learning_plan_repository.py`, exports | current-plan read, insert, and supersede operations |
| Contracts | `backend/app/schemas/learning_plan.py` | typed plan/task response and availability validation |
| Service | `backend/app/services/learning_plan_service.py` | M6-2 conversion, templates, fingerprint, reuse, invalidation, transaction and conflict handling |
| API | `backend/app/api/learning_plans.py`, route registration | read-only GET and idempotent POST generation endpoints |
| Tests | `backend/tests/test_m6_3_learning_plans.py` | migration-backed generation, reuse, invalidation, isolation, rollback, concurrency and restoration tests |
| Architecture | `docs/architecture/M6_RECOMMENDATION_ARCHITECTURE.md` | M6-3 model, lifecycle, API and M7 boundary |

## Implemented behavior

- The service consumes the existing M6-1 context and M6-2 engine result directly.
- One plan has one target and one to three contiguous ordered tasks.
- Recommendation reason codes, score breakdown, prerequisite evidence and blocked targets are persisted without
  recomputation.
- Default non-review plans contain concept review, example walkthrough and targeted practice. A real review result
  contains targeted practice only.
- Template descriptions are neutral and do not invent learning content or sources.
- Canonical SHA-256 fingerprinting covers actual recommendation inputs/results and template versions, not request time.
- Same-input POST requests reuse the active plan. Changed inputs supersede it in the same transaction as replacement.
- The active-slot unique constraint and conflict recovery prevent duplicate concurrent active plans.
- GET only reads and reports stale state; it never creates or updates a plan.
- An unavailable recommendation creates no placeholder plan and supersedes an old plan only on explicit POST.

## Data and lifecycle decisions

`AVAILABLE` and `SUPERSEDED` are the only persisted statuses. `NOT_AVAILABLE` and `STALE` describe API outcomes.
Completion/failure statuses are intentionally absent because M6-3 has no execution evidence.

Deleting a plan cascades to its tasks. User/course/target deletion follows the explicit foreign-key policies in the
migration. Plan/task creation is atomic, so a failed write cannot leave orphan tasks.

## Verification

Commands:

- `.venv/bin/pytest -q backend/tests/test_m6_3_learning_plans.py`
- `.venv/bin/pytest -q backend/tests/test_m6_1_recommendation_foundation.py backend/tests/test_m6_2_recommendation_engine.py backend/tests/test_m6_3_learning_plans.py`
- `.venv/bin/pytest -q backend/tests`
- `.venv/bin/ruff check backend`
- `.venv/bin/ruff format --check backend`
- Alembic upgrade from `0012_m5c_mastery_state` to `head`
- `git diff --check`

Results:

- M6-3 tests: **9/9 PASS**
- M6-1 through M6-3 regression: **36/36 PASS**
- Complete backend regression: **335/335 PASS**
- Empty-database-to-head migrations: **PASS** (performed by every M6-3 fixture)
- Existing-M6-2-to-M6-3 migration: **PASS**, resulting head `0013_m6_learning_plans`
- Ruff lint: **PASS**
- Ruff format: **PASS**
- Git diff check: **PASS**
- Independent type checker: **NOT CONFIGURED**

## Scope compliance

- No recommendation formula or prerequisite algorithm was duplicated or changed.
- No M3-M5 algorithm, mastery row, or learning evidence row is modified by plan generation.
- No Learning Session, execution tracking, generated exercise, LLM call, frontend, queue, Redis, or new dependency.
- No unauthorized Git operation.

## Known limitations and M6-4 entry condition

- Identity remains the existing configured bootstrap-user bridge until the authorized identity layer changes it.
- GET reports stale plans without writing; POST performs superseding and replacement.
- Task duration values are declared template estimates, not personalized predictions.
- M6-4 may consume these endpoints after all final checks pass. It must not add M7 completion semantics or mutate
  mastery/evidence through the plan read path.
