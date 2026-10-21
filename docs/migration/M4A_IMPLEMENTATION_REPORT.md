# LearnPilot V1 — M4-A Implementation Report

## 1. Outcome

M4-A Diagnostic Domain Foundation is COMPLETE. The project may record LearnPilot V1 progress as 42%. Work stopped at the M4-A boundary; M4-B through M4-F and M5 were not implemented.

## 2. M3 contract review

Reviewed `M3_FINAL_ACCEPTANCE_REPORT.md`, all architecture/migration inventories, actual SQLAlchemy models, Alembic chain, repositories, services, Pydantic schemas, fixtures, SQLite foreign-key setup, and frontend scripts. Confirmed integer IDs, Course ownership, mutable/rebuildable KnowledgeNode rows, source tracking, SQLAlchemy 2.x, Pydantic v2, repository flush behavior, and service-owned transactions.

## 3. Modified and added files

### Domain and persistence

- `backend/app/models/diagnostic.py`
- `backend/app/models/__init__.py`
- `backend/app/db/models/question.py`
- `backend/app/db/models/question_knowledge_node.py`
- `backend/app/db/models/assessment.py`
- `backend/app/db/models/assessment_question.py`
- `backend/app/db/models/response.py`
- `backend/app/db/models/__init__.py`

### Contracts, repositories, and lifecycle

- `backend/app/schemas/diagnostic.py`
- `backend/app/repositories/question_repository.py`
- `backend/app/repositories/assessment_repository.py`
- `backend/app/repositories/response_repository.py`
- `backend/app/repositories/__init__.py`
- `backend/app/services/diagnostic_domain_service.py`

### Migration, tests, and documentation

- `backend/alembic/versions/0008_m4a_diagnostic_domain_foundation.py`
- `backend/tests/test_m4a_diagnostic_domain.py`
- `docs/architecture/M4A_DIAGNOSTIC_DOMAIN_ARCHITECTURE.md`
- `docs/migration/M4A_IMPLEMENTATION_REPORT.md`

No frontend source, existing API, M2 adapter, M3 model algorithm, or prior migration was changed.

## 4. New models and migration

Migration revision: `0008_m4a_diagnostic_domain`, parent `0007_m3e_workspace_build_state`.

New tables: `questions`, `question_knowledge_nodes`, `assessments`, `assessment_questions`, and `responses`. Constraints cover enum values, course-bound live links, nonnegative ordering, unique positions and response ownership, and all required foreign keys/indexes.

`Response.is_correct` and `points_awarded` are nullable and remain unwritten. No scoring behavior exists.

## 5. Repository and service functions

- Question creation, owner/course queries, content version updates, deletion, and knowledge binding.
- Assessment draft creation, immutable snapshot fixation, owner-scoped history reads, and compare-and-set lifecycle transitions.
- Structured draft response insert/overwrite, assessment-scoped reads, and atomic submission lock.
- Identical repeated submission is idempotent; changed repeated submission is rejected.

There is no generic snapshot update, arbitrary status setter, or submitted-response update path.

## 6. Constraint implementation locations

- Database: migration and ORM `__table_args__` for FK/unique/check/index constraints.
- JSON shape: `backend/app/schemas/diagnostic.py`.
- Ownership, course equality, state transitions, snapshot fixation, response lock, and atomic submission: `DiagnosticDomainService`.
- Minimal persistence primitives: the three new repositories.

## 7. Immutable snapshot and response-lock verification

The persistence test creates Question V1 and KnowledgeNode V1, fixes and commits a snapshot, closes the Session, updates the Question to V2, deletes/rebuilds the node, deletes the source Question, opens a new Session, and reads the historical Assessment. V1 stem, correct answer, explanation, node ID/name/role, source references, policy, and source version remain intact; the live `question_id` is NULL.

Response tests verify draft overwrite, invalid option rejection, cross-Assessment rejection, one-row uniqueness, submission timestamps, post-submission mutation rejection, cross-Session idempotency, changed-repeat rejection, and full rollback when one final answer is invalid.

## 8. M3 data compatibility

An isolated database was migrated to `0007`, populated with User, Course, Material, and KnowledgeNode, then upgraded to head. All existing rows and values remained queryable and the new tables were available. The live QuestionKnowledgeNode link cascades away when an M3 node is rebuilt, so the M3 rebuild contract is not blocked; immutable AssessmentQuestion JSON remains independent.

## 9. Verification results

- M4-A tests: 20/20 passed.
- Full backend suite: 166/166 passed in the final run (89.95 seconds).
- Ruff lint: PASS (`ruff check backend`).
- Ruff format: PASS (117 files already formatted).
- Fresh Alembic upgrade: PASS, head `0008_m4a_diagnostic_domain`.
- Populated M3 upgrade: PASS.
- Frontend typecheck: PASS.
- Frontend lint: PASS.
- Frontend tests: 15 files / 87 tests PASS.
- Frontend build: PASS, 1744 modules transformed.
- Build retained the existing >500 kB chunk warning; no new frontend defect was introduced.
- Git diff check: PASS at final acceptance.

The Windows Node runtime could not reliably traverse the WSL UNC path. Frontend commands were therefore also run against an exact source/lockfile copy in the approved local temporary validation directory. Typecheck and lint passed there; Vitest and Vite passed after the sandbox `realpath` restriction was lifted. No repository frontend file changed.

`npm ci` reported six upstream dependency audit findings (3 moderate, 1 high, 2 critical). Dependency remediation is pre-existing package maintenance outside M4-A; no automatic or breaking `npm audit fix` was performed.

## 10. Architecture decisions

- ARCH-01: PASS. Correct answers and versioned scoring policy are snapshotted; no scorer or LLM judgment was implemented.
- ARCH-02: PASS. Historical reconstruction is self-contained and tested after live source deletion/rebuild.
- ARCH-03: PASS. Answers are structured, uniquely constrained, atomically submitted, and protected from ordinary mutation.

The formal architecture document states that later M4 stages must preserve all three decisions.

## 11. Explicitly not implemented

- M4-B: no DeepSeek question generation, prompts, LLM validation, or real-model smoke test.
- M4-C: no assembly algorithm, allocation/coverage optimization, deterministic scorer, score calculation, or weakness analysis.
- M4-D through M4-F: no diagnostic API, frontend, report UI, map result integration, or end-to-end student flow.
- M5: no LearningEvidence, mastery, confidence, weights, history, or aggregation service.

## 12. Acceptance conclusion

AC-A01 through AC-A31 are satisfied. Existing M0–M3 behavior remains compatible, all required quality gates passed, and M4-A is COMPLETE. The next stage is M4-B — AI Question Generation & Quality Control, only after explicit user approval.
