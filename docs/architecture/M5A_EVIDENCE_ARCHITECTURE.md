# LearnPilot V1 — M5-A Learning Evidence Architecture

## 1. Domain Position

`LearningEvidence` is a persisted, derived record that will be the input boundary for the future Student Knowledge
Model. It records one historical knowledge-node attribution for one already submitted and deterministically scored M4
diagnostic response. It is not a new score, a mastery estimate, a diagnostic report, or a mutable copy of an answer.

M5-A creates the schema and safe persistence boundary only. It performs no historical import, extraction, score
normalization, attribution calculation, synchronization, mastery/confidence calculation, recommendation, or UI work.

## 2. Relationship to M4 Historical Data

The source chain is:

```text
Assessment (owner/course/submission)
  -> AssessmentQuestion (immutable question_snapshot)
    -> Response (locked answer and persisted deterministic score)
      -> LearningEvidence (derived record)
```

The service accepts evidence values but does not calculate them. Before persistence it verifies that the Assessment is
submitted, its owner/course match the evidence, the snapshot belongs to that Assessment, the Response belongs to that
snapshot and is submitted/scored, and snapshot-backed difficulty/version/node identities match. It never updates any
Assessment, AssessmentQuestion, Response, Question, or KnowledgeNode.

## 3. Fields and Constraints

| Field | Meaning and constraint |
|---|---|
| `id` | Existing project integer primary-key convention. |
| `user_id`, `course_id` | Required owner/course references; both use restrictive deletion. |
| `source_type` | Constrained enum; M5-A permits only `diagnostic`. |
| `source_assessment_id` | Required reference to the historical Assessment. |
| `source_question_snapshot_id` | Required AssessmentQuestion identity; a composite FK also proves that it belongs to `source_assessment_id`. |
| `source_response_id` | Required reference to the scored Response. |
| `historical_knowledge_node_ref` | Positive historical node ID copied from the immutable snapshot; intentionally not an FK to the current KnowledgeNode table. |
| `current_knowledge_node_id` | Optional exact-ID mapping to an active current node in the same course. NULL means unavailable or unresolved; deletion sets it to NULL without changing the historical reference. Added by M5-B revision `0011`. |
| `knowledge_model_version` | Optional snapshot value. NULL is retained when M4 has no version; no value is invented. |
| `normalized_score` | Required decimal in the closed interval `[0, 1]`; M5-A validates/stores but never calculates it. |
| `difficulty` | Reuses M4 `QuestionDifficulty`: `easy`, `medium`, `hard`. |
| `attribution_weight` | Required decimal in `(0, 1]`; M5-A does not calculate or sum weights. |
| `source_scoring_version` | Required immutable snapshot scoring-policy version. |
| `evidence_schema_version` | Required version identity such as `learning_evidence_v1`. |
| `occurred_at` | Original Response submission time, verified against M4. |
| `created_at` | Time the derived row is created. |

Pydantic rejects invalid input before persistence; database CHECK constraints independently protect score and weight
ranges. All fields used by the uniqueness identity are non-null, avoiding SQLite's multiple-NULL uniqueness behavior.

## 4. Uniqueness and Idempotency

The database unique key is:

```text
(source_type, source_question_snapshot_id,
 historical_knowledge_node_ref, evidence_schema_version)
```

`AssessmentQuestion.id` is the identity of a fixed question occurrence and is globally unique. Two Assessments using
the same question-bank item receive different snapshot IDs, so they remain distinct without adding a redundant
Assessment column to the unique key. One snapshot may produce separate rows for different historical nodes. The same
snapshot/node may also coexist across evidence schema versions. Repository `flush()` propagates `IntegrityError`; it
does not hide uniqueness conflicts or perform a race-prone query-before-insert check.

## 5. Historical Node and Version Strategy

Historical node identity is read by exact ID from `question_snapshot.knowledge_nodes`; it is never inferred from a
name. `historical_knowledge_node_ref` deliberately has no
KnowledgeNode foreign key, so node deletion/rebuild cannot cascade into evidence or invalidate its historical
identity. M5-B may additionally set `current_knowledge_node_id` only when that same numeric ID is active and belongs
to the source course; missing or inactive nodes remain NULL and are never mapped by name. The optional knowledge-model
version, question difficulty, and scoring-policy version must exactly match the snapshot. Source Assessment,
snapshot, and Response references use `RESTRICT`, preserving the traceable source chain once evidence exists.

## 6. Ownership Strategy

Portable SQL constraints enforce existence of the referenced user/course/Assessment/snapshot/Response, and the
composite AssessmentQuestion FK enforces Assessment-to-snapshot membership. SQLite and MySQL cannot portably express
the remaining cross-table equality rules as a CHECK constraint. `LearningEvidenceService` is therefore the explicit
write boundary for:

- `user_id == Assessment.owner_id`;
- `course_id == Assessment.course_id`;
- `Response.assessment_id == Assessment.id`;
- `Response.assessment_question_id == AssessmentQuestion.id`.

Repository methods remain session-scoped and contain no HTTP or scoring logic. Direct administrative SQL is outside
the application write contract.

## 7. Alembic Migration

Revision `0010_m5a_learning_evidence` follows `0009_m4e_diagnostic_report_policy`. It creates only the
`learning_evidence` table, constraints, and focused indexes. It does not alter or scan M4 records and performs no
backfill. M5-B revision `0011_m5b_evidence_mapping` adds only the nullable current-node mapping, its index, and an
`ON DELETE SET NULL` foreign key; it performs no data scan or backfill. Downgrades are intended only for isolated
development/test databases.

## 8. M5-B Integration Point

M5-B may read submitted M4 Assessment/snapshot/Response facts, calculate the normalized score and attribution weights,
construct `LearningEvidenceCreateSchema`, and write through `LearningEvidenceService`. It must handle the surfaced
database uniqueness conflict as an idempotent duplicate outcome. M5-B must not rewrite M4 sources or infer historical
nodes from current names.

## 9. Known Limitations

- M5-B supplies extraction, backfill, and post-submit synchronization; this document continues to define the
  underlying Evidence persistence contract.
- Only diagnostic evidence is writable.
- M5-B V1 assigns `1 / N` to each valid node in a snapshot; decimal quantization may leave a negligible rounding
  remainder for node counts that do not divide evenly at five decimal places.
- M5-B computes `normalized_score` only from persisted Response points and snapshot max points; M5-A still enforces
  the independent input/database range boundary.
- No Mastery, Confidence, StudentKnowledgeState, snapshot, analytics, recommendation, or frontend feature exists.
