# LearnPilot V1 — M4-C Implementation Report

## Outcome

M4-C is complete. LearnPilot now assembles stable 8–20 question initial diagnostics from the M4-B validated bank and
atomically persists deterministic exact-match scores from M4-A snapshots and structured answers. Project progress is
48%.

## Implemented Changes

- `backend/app/repositories/question_repository.py`
  - Added a course-scoped `VALIDATED` question query with knowledge-link eager loading.
- `backend/app/schemas/diagnostic.py`
  - Extended `objective_answer_v1` with `selected_options=[]` as the explicit unanswered representation.
- `backend/app/schemas/assessment_scoring.py`
  - Added bank statistics, assembly metadata, candidate-safe item, score result, and basic score-summary contracts.
- `backend/app/services/assessment_assembly_service.py`
  - Added deterministic eligibility, dynamic count, knowledge coverage, soft distribution, atomic snapshot assembly,
    candidate-safe reads, ownership checks, and persisted-score summary reads.
- `backend/app/services/deterministic_objective_scorer.py`
  - Added the pure `objective_exact_match_v1` single/true-false/multiple-choice scorer.
- `backend/app/services/diagnostic_domain_service.py`
  - Reused the M4-A submission transaction to validate, score, persist, lock, and submit atomically.
  - Made the existing snapshot builder reusable by the assembly service without changing its snapshot contract.
- `backend/tests/test_m4c_assessment_scoring.py`
  - Added 19 focused M4-C tests.
- `docs/architecture/M4C_ASSESSMENT_SCORING_ARCHITECTURE.md`
- `docs/migration/M4C_IMPLEMENTATION_REPORT.md`

## Assembly Behavior

- Only `validated`, source-backed, structurally valid questions with exactly one active in-course PRIMARY node enter the
  pool.
- HIGH/MEDIUM active nodes define the core scope; LOW nodes are the fallback only when no higher-importance nodes exist.
- Stable greedy ordering prioritizes new-node coverage, importance, type/difficulty deficits, low node concentration,
  and Question ID.
- Dynamic targets are bounded to 8–20. Banks below eight or missing required core coverage fail with
  `QUESTION_BANK_INSUFFICIENT` and structured statistics.
- Soft targets are 70/20/remainder for single/true-false/multiple choice and 30/50/remainder for easy/medium/hard.
  Actual validated availability is reported rather than hidden.

## Snapshot and Candidate Safety

Assessment creation, all snapshots, and READY transition share one transaction. Tests verify rollback after an injected
snapshot failure, unique deterministic ordering, full answer/scoring/source/node snapshots, and stability after live
Question and KnowledgeNode changes. Candidate DTO tests confirm that answer, explanation, source, and scoring policy are
absent.

## Deterministic Scoring and Submission

- Single choice and true/false use exact canonical key equality.
- Multiple choice uses order-independent exact set equality with no partial credit.
- Empty selections are persisted and score zero.
- Unknown options and unsupported policy versions are rejected.
- The scorer has no AI/provider dependency and never reads current Question content.
- Successful submission writes `is_correct`, `points_awarded`, response timestamps, and Assessment status together.
- Identical resubmission does not rescore or duplicate rows; changed resubmission is rejected.
- Injected scoring failure rolls back final answers, all scores, timestamps, and the status transition.

## Database and Migration

No M4-C migration was required. M4-A already provided nullable `Response.is_correct` and
`Response.points_awarded`, which M4-C fills only after complete deterministic scoring. Alembic remains healthy at the
single head `0008_m4a_diagnostic_domain`. Existing fresh/upgrade migration tests are part of the passing backend suite.

## Verification

- M4-C focused tests: **19/19 passed**.
- Direct M4-A/B/C regression: **76/76 passed**.
- Complete backend regression: **222/222 passed** in 165.38 seconds.
- Ruff lint (`ruff check backend`): **PASS**.
- Ruff format (`ruff format --check backend`): **PASS**, 127 files checked.
- Alembic: **NOT CHANGED**, one healthy head.
- Git diff check: **PASS**.

Per the M4-C request, no real DeepSeek smoke test, frontend test/build, browser check, MySQL service check, or unrelated
large evaluation was run. None is reported as PASS.

## Architecture Decisions

- **ARCH-01:** preserved through a pure versioned exact-match scorer with no LLM or live Question dependency.
- **ARCH-02:** preserved through ordered self-contained snapshots and persisted response scores.
- **ARCH-03:** preserved through one response per snapshot, explicit unanswered records, transactional scoring, answer
  locks, and idempotent repeat submission.

## Scope Confirmation

- M4-D student API and Vue diagnostic experience: not implemented.
- M4-E/F knowledge-level report, weak-point analysis, map integration, and end-to-end experience: not implemented.
- M5 LearningEvidence, Mastery, Confidence, weighting, recommendations, and learning paths: not implemented.

## Known Limitations and Next Preconditions

- Soft distribution targets can degrade when the validated bank cannot supply a category; coverage is intentionally
  preferred over quota matching.
- Aggregate statistics are computed from persisted per-response scores rather than stored redundantly.
- M4-D must use the candidate-safe contract and existing owner-scoped service paths.
- M4-E must derive any knowledge-level interpretation from immutable snapshots and persisted M4-C scores without
  changing them.

