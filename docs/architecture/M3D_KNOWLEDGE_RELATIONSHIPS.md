# M3-D Knowledge Relationships

## 1. Scope

M3-D adds conservative, traceable course-level relationships between the active canonical `KnowledgeNode` records produced by M3-C. It persists `CONTAINS` and `PREREQUISITE` edges only. It does not create a graph UI, student state, mastery, recommendations, or learning paths.

## 2. CONTAINS Semantics

`source_node -> CONTAINS -> target_node` means the source is the broader parent concept and the target is its direct, more specific child. It is a conceptual hierarchy, not a learning-order assertion.

## 3. PREREQUISITE Semantics

`source_node -> PREREQUISITE -> target_node` means the source is direct course-local knowledge needed to understand the target. It is a learning dependency, not generic relatedness or membership in a topic.

## 4. KnowledgeRelationshipRun

`KnowledgeRelationshipRun` records the source snapshot hash, constrained lifecycle status, provider/model, prompt version, node and edge counts, rejected-edge count, error metadata, timestamps, and `is_current`. It is course-scoped and has an idempotency lookup over course, snapshot, prompt, and model.

## 5. KnowledgeEdgeEvidence

`KnowledgeEdgeEvidence` makes every generated edge explainable. `MODEL_INFERENCE` stores the short edge reason. `MATERIAL` optionally records only a validated material ID, source reference, and bounded excerpt that belongs to one endpoint. `STRUCTURAL` remains available for future deterministic confirmations without adding new evidence types.

## 6. Knowledge Snapshot

The service requires a current successful M3-C canonicalization run, then snapshots the active course nodes with IDs, normalized names, descriptions, importance, difficulty, and valid sources. The canonicalization run ID and node/source payload are SHA-256 hashed. Inactive historical nodes and raw candidates are excluded.

## 7. Hierarchy Forest Policy

`CONTAINS` is a forest: multiple roots are valid and no synthetic course-root node is introduced. This keeps a V1 hierarchy interpretable and ready for later visualization.

## 8. Parent Uniqueness

Each target node has at most one incoming `CONTAINS` edge. A second distinct parent is rejected rather than silently dropped.

## 9. Contains Cycle Detection

The domain validation layer uses a directed DFS over `CONTAINS` adjacency. A back edge rejects the entire generated result before persistence.

## 10. Prerequisite DAG

`PREREQUISITE` edges are validated as an independent directed acyclic graph. The two relation types can coexist for a pair but are never derived from each other.

## 11. Prerequisite Cycle Detection

The same deterministic DFS detects prerequisite cycles. Self edges, duplicates, and node IDs outside the active snapshot are rejected before either graph is persisted.

## 12. LLM Relationship Inference

`backend/app/ai/prompts/knowledge_relationships.py` owns the versioned `knowledge_relationships_v1` prompt. The Pydantic output contract accepts bounded `contains_edges` and `prerequisite_edges` lists using node IDs, concise reasons, and optional material references. Small catalogs use one bounded prompt; larger catalogs use fixed-size node groups, never O(N²) pairwise calls.

## 13. Evidence Validation

LLM IDs and citations are untrusted. A cited `(material_id, source_reference)` must exist in the current course''s `MaterialContent` and be attached through `KnowledgeSource` to the source or target node. Unknown materials, stale segments, cross-course sources, and fabricated citations invalidate the full generated result.

## 14. Conservative Inference Policy

The prompt explicitly asks for sparse, direct, defensible relations and allows empty arrays. Related or sibling concepts need no edge. `CONTAINS` and `PREREQUISITE` are separately inferred; no deterministic code converts one into the other.

## 15. Idempotency

For the same current snapshot, prompt version, and model, a normal POST returns the existing current successful run and its edges without calling the provider again. `regenerate=true` explicitly creates a new run.

## 16. Regeneration Safety

Old generated edges remain intact while inference and validation run. A failed or invalid regeneration becomes a failed run and leaves the previous current run and edges available. On a valid replacement, only edges with a non-null `relationship_run_id` are replaced; manual/fixture edges are preserved.

## 17. Transaction Strategy

The service uses short transactions to load/record state, calls the provider outside a write transaction, then rechecks the snapshot and atomically replaces generated edges, evidence, and current-run state. Deleting generated edges happens only inside that final successful persistence transaction.

## 18. API Contract

- `POST /api/courses/{course_id}/knowledge-relationships` generates synchronously and accepts optional `{"regenerate": true}`.
- `GET /api/courses/{course_id}/knowledge-relationships` returns current run metadata, separate contains/prerequisite edge arrays, and evidence.
- `GET /api/courses/{course_id}/knowledge-model` now includes manual edges plus only current successful generated edges.
- Node detail retains its related-edge shape but similarly hides inactive historical generated edges.

Relationship errors use the established API error envelope: `KNOWLEDGE_RELATIONSHIP_NOT_READY` (409), `KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT` (422), and `KNOWLEDGE_RELATIONSHIP_FAILED` (502).

## 19. Testing Strategy

The M3-D suite uses real SQLite foreign keys and migrations. It covers fresh and M3-C-to-M3-D migration, forest/DAG validation, roots, parent uniqueness, cycles, self and cross-course foreign keys, unknown-node retry, fabricated evidence rejection, evidence persistence, idempotency, snapshot changes, failure preservation, no LLM transaction, API reads, and material/node/course cascades. Existing M0-M3-C tests remain part of the full backend suite.

## 20. Real Provider Verification

Two bounded calls used a disposable SQLite database and self-authored cache concepts only. The real configured OpenAI-compatible DeepSeek provider reported model `deepseek-flash`. The reviewed result kept `Cache` as the broad parent, made `Cache Replacement -> LRU Replacement`, used `Cache Address Structure` as a prerequisite for direct-mapped and set-associative cache, had no cycles, and stored only validated provenance records. No API key, endpoint, or user course data was exposed.

## 21. M3-E Extension Points

M3-E can consume the current model and relationship APIs to visualize the persisted forest/DAG. It should not change relationship semantics, prompt behavior, provenance validation, run ownership, or the current-run visibility rule. Student mastery, learning paths, and interactive graph editing remain out of scope.
