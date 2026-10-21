# M5-D Student Knowledge State API

## Scope

M5-D exposes persisted M5-C student knowledge state through three read-only endpoints. It does not ingest evidence, calculate or persist mastery, modify diagnostics, or change the knowledge map.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/courses/{course_id}/mastery` | Current active-node state for an owned course, ordered by existing knowledge-node ID order. |
| `GET /api/courses/{course_id}/knowledge/{node_id}/mastery` | Persisted state for one active current node. |
| `GET /api/courses/{course_id}/knowledge/{node_id}/evidence` | Bounded, whitelisted summaries of the evidence used by a current persisted state. `offset` and `limit` are supported; `limit` is at most 100. |

## Read-only contract

`MasteryReadService` only reads `StudentKnowledgeState`, current `KnowledgeNode`, and source-verified `LearningEvidence`. GET paths do not call `EvidenceIngestionService`, `MasteryService.refresh_state`, a repository `save` method, or a database migration. They do not create the legacy bootstrap user either: an absent owner produces the normal hidden `COURSE_NOT_FOUND` response.

The service recomputes only an in-memory fingerprint from already persisted evidence to decide whether a state is still usable. It never recomputes or persists mastery. A changed fingerprint, incompatible algorithm version, invalid evidence input, mixed historical model versions, or an explicit historical/current-node mismatch yields `calculation_state: stale`; the response suppresses a mastery claim and evidence detail. A missing state yields `not_calculated`, with `mastery_score: null`, `not_assessed`, and `insufficient` confidence. A persisted M5-C `not_assessed` state remains distinct: it is `calculated` but still has `mastery_score: null`.

## State and explanation fields

Node state returns the persisted M5-C mastery score, mastery status, confidence level and reason codes, evidence counts, knowledge-model version, algorithm version, and calculation time when `calculation_state` is `calculated`.

Evidence explanation uses an explicit whitelist only:

- Evidence ID and source type.
- Assessment and immutable assessment-question snapshot IDs.
- Historical knowledge-node reference.
- Persisted normalized score, difficulty, attribution weight, and occurrence time.

It never serializes `Response.answer_payload`, `AssessmentQuestion.question_snapshot`, a current `Question`, answer options, correct answers, or explanations.

## Authorization and historical safety

All reads are scoped to the existing bootstrap owner, its course, and an active node in that course. A foreign course is hidden as `COURSE_NOT_FOUND`; an inactive, foreign, or absent node is `KNOWLEDGE_NODE_NOT_FOUND`.

Evidence is joined to its original `Assessment` and `Response` before it can be exposed. It must be diagnostic evidence from the same owner and course, with a `SUBMITTED` assessment and submitted, deterministically scored response. Draft, ready, and in-progress assessment facts are therefore neither exposed nor counted by the read API.

Current state accepts evidence only where both `current_knowledge_node_id` and `historical_knowledge_node_ref` equal the requested node ID. Names are never used for mapping. Evidence with an unresolved current mapping remains preserved in M5-A/B but is not exposed as current-node mastery.

## Migration and M5-E contract

`DATABASE_MIGRATION = NOT REQUIRED`. M5-D reuses `learning_evidence` and `student_knowledge_states`; no duplicate state or evidence table is introduced. Existing Alembic head remains `0012_m5c_mastery_state`.

M5-E can consume the course endpoint's node records and distinguish `calculated`, `not_calculated`, and `stale` without requesting a write-side refresh. This stage does not supply map styling, frontend components, recommendations, or progress analytics.

## Known limitation

There is no separate persisted model-version lifecycle marker beyond the evidence/state versions already established by M5-A/B/C. M5-D therefore reports `stale` whenever the verifiable evidence fingerprint or algorithm contract no longer matches; it does not attempt automatic historical-node migration.
