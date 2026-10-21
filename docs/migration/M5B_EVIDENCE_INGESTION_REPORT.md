# LearnPilot V1 — M5-B Diagnostic Evidence Ingestion Report

## Result

M5-B Diagnostic Evidence Ingestion is **COMPLETE**. LearnPilot V1 progress is **57%**, and M5-C is **READY** for a
future, separately authorized stage. M5-B adds a single, reusable path from submitted M4 diagnostic facts to `LearningEvidence`. It does not rescore an
answer, modify an M4 source row, calculate Mastery or Confidence, or add frontend behavior. Final stage status is
based on the complete isolated and repository-wide regression evidence below.

## Actual Modified Files

- Extractor and ingestion boundary: `backend/app/services/diagnostic_evidence_ingestion.py`.
- Post-submit integration: `backend/app/services/diagnostic_experience_service.py`.
- Ingestion result schemas: `backend/app/schemas/evidence_ingestion.py` and schema exports.
- Evidence current-node mapping: ORM/schema/service/repository updates in the existing M5-A Evidence files.
- Backfill entry point: `backend/scripts/backfill_diagnostic_evidence.py`.
- Additive migration: `backend/alembic/versions/0011_m5b_evidence_current_node_mapping.py`.
- Tests: `backend/tests/test_m5b_diagnostic_evidence_ingestion.py`.
- Contract documentation: `docs/architecture/M5A_EVIDENCE_ARCHITECTURE.md` and this report.

No frontend business file was changed for M5-B. Existing worktree changes were preserved.

## Evidence Source Contract

The extractor accepts only `Assessment.status = submitted`. For each immutable `AssessmentQuestion` occurrence it
validates the stored snapshot, then requires a matching submitted `Response` with persisted `points_awarded` and
`is_correct`. Evidence source identity is the exact Assessment, snapshot occurrence, Response, snapshot knowledge-node
ID, snapshot knowledge-model version, snapshot difficulty, and snapshot scoring-policy version.

No LLM, live question answer, live scoring rule, node name, or current diagnostic report participates in extraction.
Incomplete scoring, malformed snapshots, and illegal score inputs produce explicit issue/error codes instead of
guessed evidence. Source Assessment, snapshot, Response answer, and persisted scores are read-only.

## Normalization and Multi-Node Attribution

`normalized_score = persisted Response.points_awarded / snapshot.scoring_policy.max_points`, quantized to five decimal
places with decimal half-up rounding. Zero, full, and legal partial scores are supported. Negative points, points over
the snapshot maximum, or a non-positive maximum are rejected as `INVALID_NORMALIZED_SCORE`.

For `N` snapshot knowledge-node associations, one evidence candidate is created per historical node with
`attribution_weight = 1 / N`, also quantized to five decimal places. The normalized score is not divided. Associations
are consumed exactly as stored in the snapshot and are never regenerated or inferred.

## Uniqueness, Idempotency, and Recovery

M5-B reuses the M5-A database unique key:

```text
(source_type, source_question_snapshot_id,
 historical_knowledge_node_ref, evidence_schema_version)
```

The service reports an existing row as `SKIPPED_ALREADY_EXISTS`. It also treats a database uniqueness race as a skip
after verifying that the same identity now exists. First execution creates missing rows; later executions skip them
without updating existing evidence. If a later insert fails, committed M4 facts remain submitted and any already
created evidence remains valid; rerunning the same idempotent entry point safely fills only missing rows.

## Historical Backfill

The script uses the same `EvidenceIngestionService` as automatic synchronization:

```bash
python -m backend.scripts.backfill_diagnostic_evidence \
  --database-url '<database-url>' --dry-run

python -m backend.scripts.backfill_diagnostic_evidence \
  --database-url '<database-url>'
```

`--dry-run` extracts and checks existing identities but performs no insert. JSON output contains real counts for
scanned/eligible assessments, planned/created/skipped evidence, invalid snapshots, incomplete scoring, unavailable
current-node mappings, and per-assessment errors. The script does not delete or rewrite existing evidence or M4 data.

## Automatic Synchronization

After `DiagnosticDomainService.submit_assessment` has committed deterministic scoring, the application-level
`DiagnosticExperienceService.submit` invokes the shared ingestion service. Evidence synchronization therefore cannot
roll back or reset a successful M4 submission. Failures are logged with the Assessment ID; the normal API still
returns the committed diagnostic report, and the same ingestion/backfill entry point is the recovery path.

## Historical Node Mapping

`historical_knowledge_node_ref` always retains the exact ID stored in the immutable snapshot and is not a current-node
foreign key. Revision `0011_m5b_evidence_mapping` adds nullable `current_knowledge_node_id`. It is set only when the
same ID identifies an active node in the source course. Missing, inactive, deleted, rebuilt, ambiguous, or otherwise
unconfirmed nodes remain NULL. No same-name remapping occurs. The current-node FK uses `ON DELETE SET NULL`, so the
historical identity survives later graph changes.

The current KnowledgeNode schema does not expose a graph-version field. Consequently, M5-B does not claim a separate
version match: exact stable node identity plus active same-course ownership is the only positive mapping supported by
the existing domain contract. The snapshot `knowledge_model_version` remains historical metadata and no version is
invented. Any row that cannot satisfy that exact identity rule remains unresolved.

## Database Migration Status

`0011_m5b_evidence_mapping` follows `0010_m5a_learning_evidence`. It adds one nullable column, one focused index, and
one foreign key using SQLite-compatible Alembic batch operations. It creates no new domain table, performs no
backfill, and changes no M4 row or scoring semantic.

## Tests and Acceptance Evidence

The isolated M5-A/M5-B suite currently passes **37/37** cases. M5-B coverage includes valid and ineligible
diagnostics, repeated ingestion, database uniqueness, multi-node weights, M4 immutability, unavailable historical
nodes, dry-run and repeated backfill, automatic sync, failure recovery, owner/course isolation, malformed snapshots,
score boundaries, and the `0010 -> head` migration.

Final regression evidence:

- M5-A/M5-B isolated tests: **37/37 PASS**.
- Backend full tests: **270/270 PASS**.
- Frontend full tests: **100/100 PASS**. The first mapped-drive run had one 5-second timeout; the unchanged suite
  passed after increasing only the runner timeout for the slow Windows/WSL bridge.
- Frontend typecheck: **PASS**.
- Frontend build: **PASS**, 1,753 modules transformed. It was run from an unchanged local temporary copy because the
  Windows Node runtime crashed on the WSL mapped drive; the build emitted only the existing chunk-size warning.
- Alembic: **PASS**, empty SQLite database upgraded through `0011_m5b_evidence_mapping`.
- Ruff lint/format: **PASS**.
- Git diff check: **PASS**.

## M5-C Input Contract and Known Limitations

M5-C may consume only persisted `LearningEvidence` rows. A row supplies historical source identity, normalized score,
attribution weight, occurrence time, source/evidence versions, and an optional current node mapping. Evidence with
`current_knowledge_node_id IS NULL` must not be counted toward a current graph node without a separately authorized,
explicit migration policy.

Known limits are deliberate: synchronization is synchronous best-effort after the M4 commit, with logs and the
idempotent backfill as recovery; there is no queue, scheduler, distributed lock, automatic name remapping, Mastery,
Confidence, StudentKnowledgeState, recommendation, or UI. M5-C is not implemented in this stage.

## Remaining Issues and Readiness

There are no remaining M5-B acceptance blockers. M5-C may consume the documented Evidence contract but no M5-C
calculation, state model, API, or UI was implemented here.
