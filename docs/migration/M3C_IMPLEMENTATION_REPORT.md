# M3-C Implementation Report

## Actual Changes

M3-C adds course-level canonicalization on top of the M3-B candidate staging layer. The implementation
includes run and resolution persistence, conservative normalization/deduplication, bounded structured
provider judgement, canonical-node reconciliation, provenance propagation, POST/GET APIs, configuration,
tests, and architecture documentation. Existing M0-M3-B behavior remains intact.

## Database Migration

`0005_m3c_canonicalization` follows `0004_m3b_knowledge_extraction`. It adds active/managed lifecycle flags to
knowledge nodes, creates canonicalization run and candidate resolution tables, and adds indexes, checks,
uniqueness, cascades, and composite course-context foreign keys. Fresh SQLite `upgrade head` and a staged
M3-B-to-M3-C upgrade both passed. Previously applied migrations were not rewritten.

## Exact Dedup

Unicode/whitespace/case/dash normalization groups exact identities before the provider is initialized.
Exact-only input makes zero LLM requests. Technical tokens and numbers remain significant. Field conflicts
use the documented highest importance/difficulty ranks and stable display/description selection.

## Semantic Dedup

Distinct exact groups enter deterministic bounded blocks. The model may propose identity only within the
supplied IDs. Pydantic plus application validation rejects malformed structures, unknown IDs, duplicate
assignment, ungrounded canonical names, and incomplete/duplicate final plans. Uncertain or merely related
concepts remain separate. No embeddings, pairwise LLM calls, or vector infrastructure were introduced.

## Prompt Version

Canonicalization uses the dedicated `knowledge_canonicalization_v1` prompt and
`canonicalization_config_v1`. These identifiers and the provider/model are stored on every run and
participate in idempotency. The M3-B extraction prompt remains unchanged and separate.

## Canonical Nodes

Validated plans create canonical `KnowledgeNode` rows and reuse existing course nodes by normalized
canonical identity. Reconciliation refreshes descriptive fields, reactivates reused identities, and
deactivates only obsolete nodes created and managed by canonicalization. Candidate rows never appear as
knowledge-model nodes. M3-C creates no `KnowledgeEdge`.

## Source Propagation

All current candidate sources are copied to node-level `KnowledgeSource` rows using original material IDs,
source references, and evidence excerpts. Sources are deduplicated by the existing node/material/reference
policy. Snapshot validation rejects stale references or candidates without evidence before any LLM request.

## Idempotency

The run key combines the deterministic candidate snapshot, prompt, model, and configuration versions.
Repeated default POST returns the current success without another provider request. A changed current
extraction run, candidate, content hash, or evidence changes the snapshot and permits a new canonicalization.

## Failure Safety

Run creation, provider analysis, and canonical model activation use separate boundaries. No database write
transaction remains open during the provider call. The service revalidates the snapshot before one atomic
node/source/resolution activation transaction. Failed regeneration is recorded as non-current and preserves
the prior successful model and sources.

## Tests

- New M3-C integration tests: **15/15 passed**.
- Full backend regression: **125/125 passed**; the prior baseline was 110/110.
- Ruff lint: **passed**.
- Fresh migration and M3-B-to-M3-C migration: **passed**.
- Frontend: not modified by M3-C.

Coverage includes deterministic and semantic resolution, false-merge protection, structured output retry,
one-candidate-one-resolution completeness, source traceability, current-run snapshots, API behavior,
ownership/readiness, idempotency, failure and transaction safety, database constraints, and cascades.

## Real DeepSeek Smoke

Provider mode used OpenAI-compatible DeepSeek model `deepseek-flash` on two self-authored cache materials.
Five candidates produced three canonical nodes. LRU wording variants and Set Associative spelling variants
merged correctly; Cache Miss stayed distinct; both cross-material merges retained sources from both
materials; repeated execution reused the run. The temporary fixture/database was removed. No secret,
endpoint, or complete user material is included in this report.

## Known Limitations

M3-C deliberately has no hierarchy generation, parent-child inference, prerequisite inference, knowledge
edge generation, graph visualization, embedding/vector search, student model, mastery, assessment, or
recommendation logic. Conservative blocking can leave uncertain synonyms split; this is the intended
false-merge-first policy, not a hidden failure.

## M3-D Entry Conditions

M3-D can start after user acceptance because canonical nodes are current-run scoped, fully resolved,
source-traceable, idempotent, and safely regenerable. M3-D must treat the active canonical model as input and
add separately versioned hierarchy/prerequisite decisions; it must not weaken M3-C provenance or course
isolation guarantees.
