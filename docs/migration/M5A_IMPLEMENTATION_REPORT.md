# LearnPilot V1 — M5-A Implementation Report

## Result

M5-A Learning Evidence Domain Foundation is **COMPLETE**. LearnPilot V1 progress is **55%**, and M5-B is **READY**
for a future, separately authorized stage.

Acceptance uses the completed implementation review plus the user's final local WSL verification: all 16 M5-A test
cases passed, the complete backend suite passed with zero failures, the Alembic upgrade passed, Ruff lint and format
checks passed, and `git diff --check` passed. The suites were not unnecessarily repeated during this closure review.

## Actual Modified Files

- Domain enum: `backend/app/models/evidence.py`, plus `backend/app/models/__init__.py` registration.
- ORM: `backend/app/db/models/learning_evidence.py`, plus `backend/app/db/models/__init__.py` registration.
- Schemas: `backend/app/schemas/learning_evidence.py`, plus `backend/app/schemas/__init__.py` registration.
- Repository: `backend/app/repositories/learning_evidence_repository.py`, plus repository registration.
- Write boundary: `backend/app/services/learning_evidence_service.py`.
- Migration: `backend/alembic/versions/0010_m5a_learning_evidence_foundation.py`.
- Tests: `backend/tests/test_m5a_learning_evidence.py`.
- Architecture: `docs/architecture/M5A_EVIDENCE_ARCHITECTURE.md`.
- This report: `docs/migration/M5A_IMPLEMENTATION_REPORT.md`.

No frontend file was changed for M5-A. Existing user M4 and frontend worktree changes were preserved.

## Data Model and Constraints

`LearningEvidence` uses the existing integer identity convention and stores required user/course/source
Assessment/source snapshot/source Response identities, a stable historical knowledge-node value reference, optional
historical knowledge-model version, bounded normalized score, the existing M4 difficulty enum, bounded attribution
weight, source scoring version, evidence schema version, occurrence time, and creation time.

The database idempotency key is:

```text
(source_type, source_question_snapshot_id,
 historical_knowledge_node_ref, evidence_schema_version)
```

`AssessmentQuestion.id` identifies a question occurrence in one fixed Assessment. Consequently, the same question-bank
item in different Assessments has different snapshot identities and is not incorrectly deduplicated. All unique-key
columns are non-null. Different historical nodes and evidence schema versions remain distinct.

Foreign keys protect user, course, Assessment, snapshot, and Response existence. The composite
`(source_assessment_id, source_question_snapshot_id)` foreign key protects Assessment/snapshot membership. The
historical node reference deliberately has no current KnowledgeNode foreign key, so graph deletion or rebuild cannot
erase evidence identity. Database CHECK constraints and Pydantic validation enforce score and attribution-weight
ranges.

## Repository and Ownership Boundary

`LearningEvidenceRepository` provides only `create`, `get_by_id`, `list_by_source`, and
`list_by_course_and_user`. It uses the caller's SQLAlchemy Session, flushes without committing, and propagates database
errors, including uniqueness conflicts.

`LearningEvidenceService` owns the new write transaction and validates:

- exact Assessment owner and course;
- submitted Assessment state;
- snapshot membership in the Assessment;
- Response membership in the snapshot and Assessment;
- submitted, deterministically scored Response state;
- historical node membership in the immutable snapshot;
- exact snapshot difficulty, knowledge-model version, and scoring-policy version;
- occurrence time equality with the original Response submission.

The service stores supplied evidence values but does not calculate normalized score or attribution, invoke an LLM, or
modify any M4 source entity.

## Migration

Revision `0010_m5a_learning_evidence` follows the actual M4 head
`0009_m4e_diagnostic_report_policy`. It creates only the `learning_evidence` table, focused indexes, foreign keys,
CHECK constraints, and the unique key. It performs no source scan, backfill, score calculation, or M4 data mutation.
The isolated M4-to-M5-A upgrade passed in the final local WSL verification.

## Tests

`backend/tests/test_m5a_learning_evidence.py` maps T01–T12 to 16 collected cases after parameterization:

- migration and M4-row preservation;
- persistence and repository reads;
- database duplicate rejection;
- distinct Assessment identity;
- multi-node evidence;
- Pydantic and database score/weight bounds;
- invalid source rejection;
- cross-user and cross-course rejection;
- source immutability;
- transaction rollback;
- evidence-version identity;
- empty-state reads.

Final evidence:

- M5-A tests: **16/16 PASS**.
- Backend full regression: **PASS, 0 failures** (user-executed full WSL suite; exact collected count was not supplied).
- Alembic: **PASS**.
- Ruff lint: **PASS**.
- Ruff format: **PASS**.
- Git diff check: **PASS**.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| AC-01 LearningEvidence ORM | PASS | Independent registered SQLAlchemy model exists. |
| AC-02 M4 compatibility | PASS | Uses real Assessment, AssessmentQuestion snapshot, Response, owner/course, difficulty, score, and version contracts. |
| AC-03 historical source traceability | PASS | Required Assessment, snapshot, and Response references are persisted and validated. |
| AC-04 historical node identity | PASS | Exact snapshot node ID is retained without a cascading current-node FK. |
| AC-05 database deduplication | PASS | Named non-null database `UniqueConstraint` enforces source/node/schema identity. |
| AC-06 distinct Assessments | PASS | Snapshot occurrence ID separates repeated question-bank use; T04 passed. |
| AC-07 user/course ownership | PASS | FKs plus explicit cross-table service validation; T08 passed. |
| AC-08 score/weight validation | PASS | Pydantic and database CHECK constraints; parameterized T06 passed. |
| AC-09 Alembic migration | PASS | Revision follows `0009`; isolated upgrade passed. |
| AC-10 M4 data unchanged | PASS | Additive migration only; source immutability and migration preservation tests passed. |
| AC-11 minimal Repository | PASS | Four session-scoped persistence/read methods, no HTTP or calculation logic. |
| AC-12 new tests | PASS | 16/16 M5-A cases passed. |
| AC-13 backend regression | PASS | Full backend suite completed with zero failures. |
| AC-14 Ruff | PASS | Lint and format checks passed. |
| AC-15 Git diff check | PASS | Final check passed. |
| AC-16 ARCH-01/02/03 | PASS | All three constraints preserved as detailed below. |
| AC-17 no M5-B–M5-F implementation | PASS | No extractor, import, synchronization, mastery, confidence, or recommendation logic added. |
| AC-18 no M6/M7/M8 scope | PASS | No later-stage model, API, engine, AI, or UI feature added. |
| AC-19 user files preserved | PASS | Existing worktree changes and user data were not reset, deleted, stashed, or overwritten. |
| AC-20 documentation | PASS | Architecture document and this final implementation report exist. |

## Architecture Preservation

- **ARCH-01 — PRESERVED:** Learning Evidence requires an already submitted/scored Response and records the immutable
  scoring-policy version. It neither calls an LLM nor reruns or changes deterministic scoring.
- **ARCH-02 — PRESERVED:** Evidence points to the exact Assessment, AssessmentQuestion snapshot, Response, snapshot
  node ID, and recorded versions. It never reconstructs historical identity from current names or current graph rows.
- **ARCH-03 — PRESERVED:** the new write path reads M4 facts and inserts only `LearningEvidence`; submitted answers,
  snapshots, and saved scores have no mutation path.

## Known Limitations and M5-B Boundary

- Only `diagnostic` is writable as a source type.
- M5-A does not calculate normalized score, attribution weights, or weight sums.
- No extraction, historical backfill, synchronization, Mastery, Confidence, StudentKnowledgeState, recommendation,
  learning path, tutor, RAG, practice, analytics, or frontend feature was implemented.
- M5-B must be separately authorized. Its intended entry point is `LearningEvidenceCreateSchema` through
  `LearningEvidenceService`, with database uniqueness conflicts handled explicitly.

There are no remaining M5-A acceptance blockers.
