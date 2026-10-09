# M3-C Knowledge Canonicalization Architecture

## 1. Scope

M3-C converts the current successful M3-B knowledge candidates for one course into a stable canonical
`KnowledgeNode` set. It adds deterministic normalization, exact deduplication, bounded semantic identity
judgement, candidate-to-node traceability, source propagation, idempotency, and safe regeneration. It does
not generate hierarchy, prerequisites, knowledge edges, frontend graph state, or student state.

## 2. Candidate vs Canonical Node

A `KnowledgeCandidate` is extraction evidence tied to one material and one successful extraction run. It
may duplicate another material''s wording and is never returned as a course knowledge node. A
`KnowledgeNode` is the canonical course concept produced after cross-material resolution. Candidate data is
preserved for audit; canonical nodes power the existing knowledge-model and node-detail read APIs.

## 3. CanonicalizationRun

`KnowledgeCanonicalizationRun` records course, candidate snapshot hash, status, provider, model, prompt and
configuration versions, candidate/node/merge/unresolved counts, errors, timestamps, and current-run state.
Statuses are `pending`, `running`, `success`, and `failed`. The idempotency lookup uses course, snapshot,
prompt version, model, and configuration version. Only a fully persisted success becomes current.

## 4. CandidateResolution

`KnowledgeCandidateResolution` maps one candidate to one canonical node within one canonicalization run.
Its enum is `exact`, `semantic_merge`, or `new_node`. A run/candidate unique constraint guarantees at most
one mapping. Composite run/course, node/course, and candidate/course foreign keys make cross-course
resolution invalid at the database level as well as in the service.

## 5. Deterministic Normalization

Names are normalized with Unicode NFKC, safe Unicode-dash folding, whitespace removal around hyphens,
whitespace collapse, and case folding. The algorithm deliberately preserves identity-bearing syntax and
numbers such as `C++`, `C#`, `L1`, `L2`, and `x86-64`. It performs no synonym inference or semantic rewrite.

## 6. Exact Deduplication

Candidates with the same deterministic normalized name form an exact group before any provider is
initialized. Exact-only input consumes no LLM request. Display name selection is stable; the longest
description is retained; importance and difficulty use deterministic highest-rank policies. Sources are
unioned by material and source reference.

## 7. Semantic Blocking

Only distinct exact groups can enter semantic judgement. Small bounded sets are considered together within
the configured context budget. Larger sets use deterministic lexical-token, acronym, and string-similarity
connected components, then fixed-size/context-bounded blocks. Blocking is only a conservative prefilter; it
never establishes identity and it avoids pair-per-request or unbounded all-course prompts. No embedding or
vector store is used.

## 8. LLM Merge Judgement

The independent `knowledge_canonicalization_v1` prompt asks only whether supplied IDs denote the same
learnable concept. Pydantic validates structured groups containing candidate IDs, the identity decision,
canonical name/description, and reason. Application validation rejects unknown IDs, repeated assignment,
blank or ungrounded names, and duplicate canonical identities. Invalid structured decisions receive only
the configured bounded retry; provider/auth failures are not reinterpreted as valid results.

## 9. Conservative Merge Policy

False merge is treated as more harmful than false split. Related, prerequisite, parent-child, same-chapter,
and numbered technical concepts are not identity. The prompt explicitly distinguishes Cache, Cache Hit,
Cache Miss, Cache Replacement, L1/L2 Cache, and similar cases. Omitted or uncertain groups remain separate.
Every current candidate must still resolve exactly once.

## 10. Canonical Node Construction

Canonical plans create `KnowledgeNode` rows or reuse a course node with the same normalized canonical name.
Reused nodes receive refreshed name, description, importance, and difficulty. New generated nodes are marked
as canonicalization-managed and active. A successful later run reuses matching identity and deactivates only
obsolete managed nodes; ambiguous pre-existing duplicate normalized identities fail safely instead of being
merged automatically.

## 11. KnowledgeSource Propagation

Candidate evidence becomes `KnowledgeSource` without asking the canonicalization model to rewrite excerpts.
The service carries forward the original `material_id`, `source_reference`, and excerpt, truncates only at the
existing 1,000-character storage limit, and deduplicates `(node, material, source_reference)`. Course and
reference validity are checked while building the candidate snapshot.

## 12. Provenance Chain

The persisted audit path is:

`KnowledgeNode -> KnowledgeCandidateResolution -> KnowledgeCandidate -> KnowledgeExtractionRun -> Material -> MaterialContent -> source_reference`.

The node-detail API exposes the final `KnowledgeSource` rows, while the canonicalization GET endpoint exposes
run metadata and resolution mappings. Candidate rows remain staging/audit records, not canonical nodes.

## 13. Idempotency

The snapshot hash deterministically covers current extraction run IDs, material/content hashes, extraction
prompt/model metadata, candidate identity and fields, and source references/excerpts. A repeated POST with an
unchanged snapshot, canonicalization prompt, model, and configuration returns the current successful run and
does not issue another LLM request. Extraction-run or candidate changes make a new run eligible.

## 14. Regeneration Safety

Explicit `regenerate=true` may create a new run for an unchanged snapshot. The prior current run, nodes, and
sources remain active until the replacement is fully validated and committed. A failed run records a bounded
error, remains non-current, and leaves the prior successful course model available.

## 15. Transaction Strategy

Candidate collection and validation use a short read transaction. Run creation uses a short write
transaction. Semantic calls run after that transaction is closed. Before persistence, the service recomputes
the snapshot; any change aborts replacement. Nodes, sources, resolutions, managed-node reconciliation, and
current-run activation then commit atomically in one short transaction. Failure rolls the whole update back.

## 16. Test Strategy

M3-C has real SQLite integration coverage for fresh and M3-B upgrades, normalization safety, exact and
semantic merges, related-concept separation, unknown IDs, duplicate assignment, bounded retry, completeness,
cross-material sources, idempotency, changed snapshots, failed regeneration, no transaction during LLM,
node reuse, API contracts, ownership/readiness, limits, composite foreign keys, cascades, and absence of
generated edges. The accepted run is 15/15 new tests and 125/125 full backend tests.

## 17. Real Provider Verification

The accepted provider-mode smoke used the configured OpenAI-compatible DeepSeek service and model
`deepseek-flash`. Five self-authored candidates across two materials became three nodes: LRU and its expanded
name merged, Set Associative spelling variants merged, and Cache Miss remained distinct. Both merged nodes
retained evidence from both materials, the repeated call reused the successful run, and no edge was created.
No credential, endpoint, or complete user material is recorded.

## 18. M3-D Extension Points

M3-D may consume the active canonical nodes, source-backed descriptions, and current successful run as the
stable input for explicit structure and prerequisite modelling. It must create any `CONTAINS` or
`PREREQUISITE` semantics in its own versioned workflow. M3-C intentionally contains no hierarchy inference,
edge generation, traversal engine, graph UI, or student mastery field.
