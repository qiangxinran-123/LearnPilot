# LearnPilot V1 — M6-UX-FIX-4 Implementation Report

## 1. Scope and changed files

This change adds incremental material synchronization to the existing Diagnose workflow. It does not introduce a second knowledge pipeline, question generator, scoring path, or job platform.

- `backend/app/db/models/course_knowledge_build_state.py`: stores the latest real added/reused node counts.
- `backend/alembic/versions/0014_m6_ux_fix4_sync_counts.py`: adds those two non-destructive counters.
- `backend/app/repositories/course_knowledge_build_state_repository.py`: clears stale counters when a new build is claimed.
- `backend/app/repositories/knowledge_candidate_resolution_repository.py`: reads prior candidate-to-node resolutions.
- `backend/app/services/course_knowledge_build_service.py`: calculates exact added/reused node counts from the pre-build checkpoint.
- `backend/app/services/course_knowledge_build_job_service.py`: exposes parsed, failed, synchronized and pending material counts and persists build results.
- `backend/app/services/knowledge_canonicalization_service.py`: retains a previously published node ID when a new alias is safely merged into exactly one historical node; ambiguous multi-node merges are rejected.
- `backend/app/api/knowledge.py`, `backend/app/schemas/knowledge.py`: extend the existing build contracts with typed synchronization statistics.
- `frontend/src/components/diagnostic/QuestionBankPanel.vue`: adds the explicit synchronization action, durable build-state polling, partial-failure feedback, and FIX-3 gap supplementation.
- `frontend/src/types/knowledge.ts`: matches the backend status contract.
- Focused backend/frontend tests: cover material detection, stable node identity, exact counters, explicit invocation, duplicate-submit protection and partial recovery.

## 2. New material detection

The existing M3-E build state remains the source of truth. Ready materials are identified only when parsing succeeded and non-empty `MaterialContent` exists. The material snapshot is a stable hash of sorted `(material_id, content_hash)` pairs. A parsed material is considered synchronized only when a current successful extraction run is tied to its current content hash.

The status API now separates:

- successfully parsed and synchronized materials;
- successfully parsed but pending synchronization materials;
- materials still pending parsing;
- materials whose parsing failed or produced unusable legacy content.

No timestamp-only inference is used.

## 3. Knowledge node matching and reuse

The implementation reuses M3-B extraction idempotency and M3-C exact/semantic canonicalization. Existing extraction candidates remain stable when their material content hash is unchanged. During an incremental canonicalization, prior candidate resolutions are inspected:

- one prior published node: reuse its ID even when the validated canonical alias changes;
- no prior node: create a new managed node;
- multiple prior published nodes in one proposed merge: reject the automatic merge instead of destructively combining historical identities;
- normalized-name collision with another published node: reject publication.

Historical nodes are never deleted by this workflow. Sources are refreshed only inside the existing canonicalization transaction.

## 4. Relationship update rules

Relationship inference continues to use the existing M3-D service. It validates same-course references, source evidence, duplicate/self edges, `contains` structure and prerequisite cycles before publication. Manual edges are included in validation. A failed relationship stage restores the previous knowledge checkpoint.

## 5. Diagnostic question supplementation

After an explicitly requested knowledge synchronization reaches the durable `ready` state, the Diagnose UI reloads server readiness and invokes the existing FIX-3 bounded preparation endpoint only when uncovered required nodes remain. Existing validated or pending coverage is not regenerated. Generated questions remain `PENDING` and require the existing human review API before they can enter assessment assembly.

The browser never auto-starts synchronization on load and never retries a paid generation request. A second click is blocked while the operation is running.

## 6. Version and historical diagnostic protection

- Existing and in-progress assessments keep immutable `AssessmentQuestion` snapshots, including order, answer, source and historical node identity.
- Incremental publication adds questions; it does not rewrite or delete existing question rows or assessment snapshots.
- Learning Evidence and Mastery are not written by synchronization or question preparation.
- New nodes have no fabricated state and therefore remain unassessed until real evidence exists.
- The M6 learning-plan fingerprint already includes the typed recommendation context; a changed node/edge context is detected as stale on the next plan read without rewriting Mastery.

## 7. Status, concurrency and failure recovery

The existing per-course database claim and lease prevent duplicate knowledge builds. The existing bounded question-preparation lock and duplicate checks protect the FIX-3 stage. The UI distinguishes:

- update available;
- running knowledge synchronization;
- completed synchronization;
- knowledge success with partial question failure;
- failed synchronization.

If knowledge succeeds but question generation fails, retrying reuses the successful material snapshot and only runs the remaining question-gap preparation. No Redis, Celery, queue, distributed lock or parallel job model was added.

## 8. Migration

Migration `0014_m6_ux_fix4_sync_counts` adds two integer counters with zero defaults to `course_knowledge_build_states`. It does not alter course materials, knowledge nodes, questions, assessments, responses, evidence, mastery or learning plans.

Both upgrade of an existing isolated database and a fresh upgrade to Alembic head were verified. The user's working database was not rebuilt, cleared or modified during automated validation.

## 9. Frontend behavior

The Diagnose page remains the only normal user entry. When a material update exists it shows one explicit action, a real-AI cost warning, non-percentage running feedback, and server-derived result counts. On success it refreshes the authoritative question-bank readiness; on partial failure it offers a safe manual retry. Course switches invalidate stale responses.

## 10. Verification

- Focused backend: `41 passed`.
- Full backend: `355 passed` after the final exact-counter migration refinement.
- Focused frontend: `43 passed` after the final contract refinement.
- Full frontend: `139 passed` after the final exact-counter contract refinement.
- Ruff lint and format: passed (`174 files already formatted`).
- TypeScript, ESLint and production build: passed; the existing non-blocking Vite chunk-size warning remains.
- Alembic: an existing isolated revision `0013` database and a fresh isolated database both reached `0014_m6_ux_fix4_sync_counts (head)`.
- Browser read-only check: the real Diagnose page loaded the current `计算机系统` course and showed server-backed `8 / 59` coverage and `8` validated questions. No update was pending, so no model call or data mutation was performed.
- Real paid provider calls: `0`.

## 11. Known limitations

- Question-generation locking is intentionally process-local plus database duplicate validation, matching the current single-process SQLite competition deployment; it is not a distributed exactly-once guarantee.
- Ambiguous proposals that would merge multiple already-published node identities are rejected for manual follow-up rather than automatically migrated.
- The synchronization result card is session-local, while durable recovery uses the knowledge-build status and question-bank readiness. Reloading never repeats paid work automatically.
- A real-provider smoke synchronization was not run because it would mutate course knowledge/question data and incur model cost; automated tests use scripted providers.

## 12. FIX-5 boundary

FIX-5 may consume the existing stale learning-plan behavior and unassessed-node semantics. This change does not implement learning-page course selection, evidence tiers, three-layer plans, new recommendation thresholds, Learning Session, Tutor, Agent, RAG or adaptive practice.
