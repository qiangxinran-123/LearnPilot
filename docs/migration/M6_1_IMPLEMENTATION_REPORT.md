# LearnPilot V1 — M6-1 Implementation Report

Date: 2026-10-21

## Decision

- Stage: **M6-1 Recommendation Input Contract & Foundation Rules**
- Status: **COMPLETE**
- M6-2 readiness: **READY**
- LearnPilot V1 progress: **65%**
- Database migration: **NOT REQUIRED**
- Frontend change: **NONE**

## Actual modified files

| File | Change |
| --- | --- |
| backend/app/models/recommendation.py | eligibility, availability, exclusion, prerequisite, and result enums |
| backend/app/models/__init__.py | exports the new recommendation enums |
| backend/app/schemas/recommendation.py | context, candidate, mastery/evidence input, priority, and result contracts |
| backend/app/services/recommendation_context_service.py | read-only context assembly, candidate rules, prerequisite filtering/validation |
| backend/app/services/mastery_read_service.py | extracts the existing state-fingerprint check into a reusable public pure helper; read behavior is unchanged |
| backend/tests/test_m6_1_recommendation_foundation.py | deterministic contract, isolation, graph, state, and no-write tests |
| docs/architecture/M6_RECOMMENDATION_ARCHITECTURE.md | M6-1 data mapping and architecture |
| docs/migration/M6_1_IMPLEMENTATION_REPORT.md | this implementation and acceptance record |

No frontend, Alembic migration, database model, dependency, router, or API file changed.

## Data audit result

The implementation was based on the current M3-M5 ORM models, repositories, services, schemas, APIs, tests, and
architecture reports rather than earlier completion claims.

Differences from the provisional plan:

- M3 already has node-level KnowledgeImportance (low, medium, high), so this input is available.
- There is no course-level importance field.
- M5 does not define a literal MASTERED mastery enum. M6 candidate MASTERED maps from M5 GOOD_PERFORMANCE, while
  retaining the original M5 status.
- M5 has separate mastery availability (calculated, not_calculated, stale) and confidence dimensions. M6-1
  preserves both.
- Valid M5 Evidence has an occurred_at timestamp. M6-1 uses the latest source-verified submitted occurrence as the
  latest valid assessment input.

The full source/type/nullability/API mapping is in the architecture document.

## Implemented contracts and rules

- RecommendationContext, CandidateNode, PriorityBreakdown, and RecommendationResult are strict Pydantic contracts.
- Uncomputed priority fields are None, never zero.
- Course ownership is enforced through get_for_owner; foreign courses are hidden as not found.
- Nodes, edges, states, and Evidence are loaded in course-level batches.
- Only source-verified submitted diagnostic Evidence is summarized.
- Persisted mastery is accepted only when the existing M5 algorithm version and Evidence fingerprint still match.
- Missing and stale mastery never becomes zero.
- Candidate states distinguish unassessed, low confidence, mastered, eligible, and invalid data.
- Only prerequisite edges enter the input. Duplicate pairs are safe, while course mismatch, inactive/unknown nodes,
  self-reference, and cycles block assembly.
- Assembly is read-only and deterministic.

## Test evidence

- New M6-1 tests: **11/11 PASS**
- Complete backend suite, including M3-M5 regression: **310/310 PASS**
- Ruff lint (backend): **PASS**
- Ruff format check (backend): **PASS**; 161 files formatted
- Git diff check: **PASS**
- Independent type checker: **NOT CONFIGURED** in the repository

Tests cover owned/private/missing courses, cross-course node isolation, no-model courses, real persisted mastery,
null unassessed mastery, low confidence, mastered and eligible states, prerequisite filtering/deduplication/direction,
invalid references, self references, course mismatch, cycles, Pydantic invariants, uncomputed priority fields, and
repeated no-write context reads.

## Explicitly unavailable inputs

- Course-level importance: UNAVAILABLE
- Review risk: UNAVAILABLE
- Any M6-2 priority component before calculation: None

Node-level M3 knowledge importance and the latest valid submitted Evidence occurrence are available.

## Side-effect and scope audit

- No mastery or Evidence mutation.
- No LearningPlan or LearningTask model/table.
- No recommendation history.
- No LLM call.
- No Recommendation API.
- No frontend change.
- No migration or database schema change.
- No new runtime dependency.
- No commit, push, tag, switch, merge, rebase, reset, clean, restore, or stash.

## Not implemented

Priority score, knowledge-gap weighting, dependency importance, course weighting, review risk, Top-N, sorting, final
node selection, prerequisite attainment/recursive decisions, plan/task generation, persistence, API, frontend, and
end-to-end recommendation evaluation remain unimplemented.

## Known risks and M6-2 entry conditions

There is no blocker to begin M6-2 after user approval. M6-2 must:

1. consume only a valid RecommendationContext;
2. define score ranges and normalization before populating PriorityBreakdown;
3. keep unavailable course importance/review risk distinct from numeric zero;
4. decide how low-confidence and mastered candidates participate without changing M5 semantics;
5. preserve the read-only M6-1 boundary and add algorithm-specific tests.

The current configured bootstrap-user identity remains an application-wide limitation; it is not expanded or
reworked in M6-1.
