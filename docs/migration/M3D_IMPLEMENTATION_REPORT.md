# M3-D Implementation Report

## Actual Changes

Added course-level relationship inference and persistence on top of the existing M3-C canonical node model. The work is limited to `CONTAINS`, `PREREQUISITE`, run tracking, provenance, validation, APIs, tests, and documentation.

## Migration

Added `0006_m3d_relationships`, based on `0005_m3c_canonicalization`. It creates `knowledge_relationship_runs` and `knowledge_edge_evidences`, and adds nullable `knowledge_edges.relationship_run_id` with a course-scoped composite foreign key. It does not modify previous migrations.

## RelationshipRun

`KnowledgeRelationshipRun` records the immutable inference input hash, lifecycle state, provider/model/prompt, counts, errors, current marker, and timestamps. Its repository supports current/latest lookup, idempotency lookup, activation clearing, and safe failure updates.

## Contains Inference

The versioned structured prompt defines `source -> CONTAINS -> target` as parent-to-child. Domain validation enforces an acyclic forest and one direct parent per target; multiple roots are legal.

## Prerequisite Inference

The prompt defines `source -> PREREQUISITE -> target` as direct course-local prior knowledge. It is inferred independently from containment and validated as a separate DAG.

## Edge Evidence

Each accepted generated edge stores a bounded `MODEL_INFERENCE` reason. Optional `MATERIAL` evidence is accepted only when its source reference exists in `MaterialContent` and belongs to a `KnowledgeSource` for either endpoint. Fabricated material or segment claims invalidate the complete generation.

## Cycle Validation

The lightweight domain validator performs DFS cycle detection before persistence. It rejects self edges, duplicate typed edges, unknown IDs, containment cycles, and prerequisite cycles.

## Forest Validation

The same validator enforces the V1 primary-hierarchy rule: a `CONTAINS` target can have at most one distinct parent. The existing minimal manual edge write path also invokes this validation.

## Prompt Version

`backend/app/ai/prompts/knowledge_relationships.py` defines `knowledge_relationships_v1`. The version is persisted with every relationship run. The explicit mock client returns an empty valid relationship output only in explicit mock mode; there is no fallback from provider mode.

## Idempotency

Unchanged current snapshots reuse the current successful run without an LLM request. Any canonical-node/source snapshot change makes a new run eligible. `regenerate=true` always creates a fresh run attempt.

## Failure Safety

LLM work runs outside a database write transaction. Invalid output is retried within the configured bound with validation feedback. If retry or provider work fails, the new run is marked failed and the old current generated edges remain. Valid replacement atomically removes only generated edges, persists new edges/evidence, and activates the new run.

## Tests

Added `backend/tests/test_m3d_knowledge_relationships.py` (10 tests) covering migrations, structural rules, current-node filtering, sparse no-edge behavior, provenance, idempotency, regeneration failure safety, API reads/ownership, real SQLite foreign keys, and cascades. Full backend regression was also executed.

## Real DeepSeek Smoke Test

Two cost-bounded real requests used an ephemeral SQLite database and eight self-authored cache concepts. The configured OpenAI-compatible provider ran model `deepseek-flash` successfully. The reviewed relationships were semantically reasonable, acyclic, directionally correct, and provenance-valid. Credentials, provider endpoint, and user material were not logged.

## Known Limitations

- No Knowledge Graph frontend or interaction.
- No embedding, vector database, graph database, semantic edge deduplication, or automatic topic node creation.
- No Student Model, mastery, diagnostic assessment, learning path, recommendation engine, or tutor.
- Large courses use fixed bounded node groups; cross-group semantic optimization is intentionally deferred.

## M3-E Entry Conditions

M3-E may consume the current relationship read contract for visualization after review. It must retain current-run filtering and edge provenance, and must not introduce student state or alter relationship inference semantics.
